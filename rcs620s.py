from curses import A_ALTCHARSET
import time
import serial

class Rcs620s:
    def init(self, portName):
        # シリアル通信初期化
        self.ser = serial.Serial(
            port=portName, 
            baudrate=115200, 
            timeout=0.5
        )

        # 通信確認(GetFirmwareVersion)
        rcv_data = self.send_frame(b'\xd4\x02')
        if rcv_data != b'\xd5\x03\x33\x01\x30\x07':
            return False

        # タイミング設定(RFConfiguration)
        #rcv_data = self.send_frame(b'\xd4\x32\x02\x00\x00\x00')
        #if rcv_data != b'\xd5\x33':
        #    return False

        # リトライ回数設定(RFConfiguration)
        rcv_data = self.send_frame(b'\xd4\x32\x05\x00\x00\x00')
        if rcv_data != b'\xd5\x33':
            return False
        
        # ウェイト時間設定(RFConfiguration)
        rcv_data = self.send_frame(b'\xd4\x32\x81\x00')
        if rcv_data != b'\xd5\x33':
            return False

        # エラーがなければ初期化成功
        return True

    # Mifareカードの検出
    def polling_Mifare(self) :
        recv_data = self.send_frame(b'\xd4\x4a\x01\x00')
        if len(recv_data) != 12:
            return ''
        if not recv_data.startswith(b'\xd5\x4b\x01\x01'):
            return ''

        # エラーがなければカードIDを返す
        return recv_data[8:14].hex().upper()
        
    # PowerOff
    def power_off(self):
        recv_data = self.send_frame(b'\xd4\x16\x01\x00')

    # Normalフレーム送信
    def send_frame(self, data):
        self.ser.flush()

        # 送信フレーム生成
        lcs = 256 - (len(data) % 256)  # LENチェックサム
        dcs = self.calcDCS(data) # データチェックサム

        send = b'\x00\x00\xff' # Premable(00h),Start Of Packet(00h ffh)
        send += len(data).to_bytes(1,byteorder='big')
        send += lcs.to_bytes(1,byteorder='big')
        send += data
        send += dcs.to_bytes(1,byteorder='big')
        send += b'\x00' # Postamble

        # ホストコマンドパケット送信
        self.ser.write(send)

        # ACK受信(00h 00h ffh 00h ffh 00h 固定)
        res=self.ser.read(6)
        if res != b'\x00\x00\xff\x00\xff\x00':
            self.cancel()
            return ""

        # レスポンス受信
        if self.ser.read(3) != b'\x00\x00\xff':
            self.cancel()
            return ''

        # 受信データ長確認
        rcv_data = self.ser.read(2)
        if (rcv_data[0]+rcv_data[1] & 0xff) != 0:
            self.cancel()
            return ''

        # データ部受信
        receive_len = rcv_data[0]
        rcv_data = self.ser.read(receive_len)

        # 受信データ確認
        dcs = self.calcDCS(rcv_data)
        rcv_dcs = self.ser.read(2)
        if dcs != rcv_dcs[0]:
            self.cancel()
            return ''

        return rcv_data

    def cancel(self):
        # ACK送信
        self.ser.write(b'\x00\x00\xff\x00\xff\x00')
        time.sleep(0.001) #1ms待ち
        self.ser.flush()
        time.sleep(0.001) #1ms待ち

    # チェックサム計算
    def calcDCS(self, data):
        sum = 0
        for ch in data:
            sum += ch
        return -sum & 0xff
