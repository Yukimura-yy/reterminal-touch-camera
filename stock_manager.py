import tkinter as tk
import tkinter.ttk as ttk
import cv2
import PIL.Image, PIL.ImageTk
import numpy as np
import time
import threading
import psycopg2
import rcs620s
import seeed_python_reterminal.core as rt
import io
from pyzbar.pyzbar import decode

# DB接続情報 
DB_HOST = 'IP_address'
DB_PORT = 'port'
DB_NAME = 'DB_name'
DB_USER = 'username'
DB_PASS = 'password'

# 設定
DISP_WIDTH = 1280
DISP_HEIGHT = 720
IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
FONT1 = 80  # 出庫/入庫
FONT2 = 40  # 上段メッセージ
FONT3 = 25  # 各種項目
BEEP = True

# シリアル通信設定
SERIAL_PORT = "/dev/ttyS0"

class Application(tk.Frame):
    def __init__(self,master=None):
        super().__init__(master)

        # マスターウィンドウ
        master.title("在庫管理")
        master.geometry(f"{DISP_WIDTH}x{DISP_HEIGHT}+0+0")
        master.attributes("-fullscreen", True)
        master.config(cursor="none")
        self.pack()

        # ルートフレーム
        self.root_frame = tk.Frame(self,width=DISP_WIDTH,height=DISP_HEIGHT)
        self.root_frame.pack()
        
        # 情報初期化
        self.reset_info()
        self.reset_stock()
        
        # 社員情報ラベル
        self.var_lb_employeeinfo = tk.StringVar()
        self.var_lb_employeeinfo.set(f"社員番号 : {self.employeenum}  氏名 : {self.user}")
        # 在庫数ラベル
        self.var_lb_stock = tk.StringVar()
        self.var_lb_stock.set("0")
        # メッセージラベル
        self.var_lb_message = tk.StringVar()
        self.var_lb_message.set("社員証をタッチしてください")

        # 情報入力フレーム作成
        self.create_info_frame()
        # カード待ちフレーム作成
        self.create_wait_card_frame()
        # エラーフレーム作成
        self.create_error_frame()

        # ICカードリーダー初期化
        self.init_icreader()
        # 画面描画関連
        self.init_opencv()

        # カード待ち
        self.wait_touch()


    # カードリーダー初期化
    def init_icreader(self):
        self.ic_reader = rcs620s.Rcs620s()
        self.ic_reader.init(SERIAL_PORT)

    # OpenCV初期化
    def init_opencv(self):
        self.vcap = cv2.VideoCapture(0)
        self.vcap.set(cv2.CAP_PROP_FRAME_WIDTH, IMAGE_WIDTH)
        self.vcap.set(cv2.CAP_PROP_FRAME_HEIGHT, IMAGE_HEIGHT)
        #self.vcap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('H', '2', '6', '4'))
        self.vcap.set(cv2.CAP_PROP_FPS, 30)
        self.vcap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.tempimg = None
        self.delay = 33 # 更新頻度(ms) 33-> 約30Hz
        self.update()   # 表示処理開始

    # 情報初期化
    def reset_info(self):
        self.reading_flag = False # 読取中フラグ
        self.inout = 1    # 入庫 or 出庫(1 or -1)
        self.cardidm = ""
        self.user = "〇〇 〇〇"
        self.employeenum = "*****"

    # 在庫情報初期化
    def reset_stock(self):
        self.data_exist = False
        self.barcode = ""
        self.stock_num = 0
        self.code = ""
        self.model = ""
        self.name = ""
        self.shelf_num = ""
        self.quantity = 0
        self.barcode_cnt = 0

    # カード待ち処理
    def wait_touch(self):
        # 情報初期化
        self.reset_info()
        # カード待ち画面最前面
        self.wait_card_frame.tkraise()
        # カード待ち処理のスレッド作成
        self.thread_wait = threading.Thread(target=self.wait_card)
        # デーモン化(メインスレッドと同時に終了)
        self.thread_wait.setDaemon(True)
        # カード待ちバックグラウンド処理開始
        self.thread_wait.start()

    # カード待ちバックグラウンド処理
    def wait_card(self):
        time.sleep(1.0) # 1.0秒待ち
        while True:
            self.change_message("社員証をタッチしてください",'black')
            # カードタッチ待ち
            while True:
                card_id = self.ic_reader.polling_Mifare()
                if(card_id != ""):
                    self.cardidm = card_id
                    break
                time.sleep(0.2)
            try:
                # DB接続
                conn = self.get_connection() 
                cur = conn.cursor()
                # カードIDでユーザー検索
                cur.execute("SELECT employeenum,username FROM users where cardidm= %s",(self.cardidm,))
                if cur.rowcount == 1:
                    # Beepを鳴らす
                    self.beep(0.01)
                    rows = cur.fetchone()
                    self.employeenum = rows[0]
                    self.user = rows[1]
                    self.var_lb_employeeinfo.set(f"社員番号 : {self.employeenum}  氏名 : {self.user}")
                    self.info_frame.tkraise()
                    cur.close()
                    conn.close()

                    # reading_flagをTrueにするとカメラ読込処理開始
                    self.reading_flag = True
                    break
                else:
                    # Beepを鳴らす
                    self.beep(0.1)
                    self.change_message("カードが登録されていません",'red')
                    cur.close()
                    conn.close()
                    time.sleep(1.5) # 1.5秒待ち
            except:
                self.beep(0.1)
                self.change_message("通信エラー発生",'red')
                time.sleep(1.5) # 1.5秒待ち
                self.change_message("社員証をタッチしてください",'black') # 戻す
                self.error_frame.tkraise()
                break
    
    # カメラ読込処理
    def update(self):
        if self.reading_flag:
            _, frame = self.vcap.read()
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = cv2.rotate(frame,cv2.ROTATE_180) # 180度回転
            data = decode(frame)
            if data:
                self.barcode_cnt = 0
                counter = 0
                for barcode in data:
                    barcodeData = barcode.data.decode('utf-8')
                    code_color = (0,255,0) # 緑
                    pts = np.array([barcode.polygon],np.int32)
                    cv2.polylines(frame,[pts],True,code_color,2)
                    # 番号表示
                    counter += 1
                    if counter == 1:
                        self.barcode = barcodeData # 1つ目のバーコード値を格納
                    x, y, w, h = barcode.rect
                    frame = cv2.putText(frame, str(counter), (int(x+w/2-5), int(y+h/2+5)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, code_color, 2, cv2.LINE_AA)

            self.photo = PIL.ImageTk.PhotoImage(image = PIL.Image.fromarray(frame))
            self.canvas1.create_image(0,0, image= self.photo, anchor = tk.NW)

        # 0.66秒間は読込値を維持
        self.barcode_cnt += 2
        if self.barcode_cnt > self.delay:
            self.barcode = ""
        self.master.after(self.delay, self.update)
    
    # キー操作
    def key_event(self,e):
        if e.keycode == 38:   # F1
            self.down()
        elif e.keycode == 39: # F2
            self.up()
        elif e.keycode == 40: # F3
            self.restart_read()
        elif e.keycode == 41: # F4
            self.get_data()

    # DB接続
    def get_connection(self): 
        return psycopg2.connect('postgresql://{user}:{password}@{host}:{port}/{dbname}'
            .format(user=DB_USER,
                    password=DB_PASS,
                    host=DB_HOST,
                    port=DB_PORT,
                    dbname=DB_NAME
            ))
    
    # Beepを鳴らす
    def beep(self,time_width):
        if BEEP:
            rt.buzzer = True
            time.sleep(time_width)
            rt.buzzer = False
    
    # アプリ終了
    def exit(self):
        self.master.destroy()

    # カード待ち画面メッセージ変更
    def change_message(self,message,color):
        self.var_lb_message.set(message)
        self.lb_message["fg"] = color

    # カード待ちフレーム作成
    def create_wait_card_frame(self):
        # ベースフレーム
        self.wait_card_frame = tk.Frame(self.root_frame,width=DISP_WIDTH,height=DISP_HEIGHT)
        self.wait_card_frame.place(x=0,y=0)
        # カード待ちラベル
        self.lb_message = tk.Label(self.wait_card_frame)
        self.lb_message["textvariable"] = self.var_lb_message
        self.lb_message["font"] = "",int(FONT2*1.5)
        self.lb_message.place(relx=0,rely=0,relwidth=1.0,relheight=0.95)

    # エラーフレーム作成
    def create_error_frame(self):
        # ベースフレーム
        self.error_frame = tk.Frame(self.root_frame,width=DISP_WIDTH,height=DISP_HEIGHT)
        self.error_frame.place(x=0,y=0)
        # エラーラベル
        self.lb_error_message = tk.Label(self.error_frame)
        self.lb_error_message["text"] = "エラーが発生しました"
        self.lb_error_message["font"] = "",int(FONT2*1.5)
        self.lb_error_message["fg"] = "red"
        self.lb_error_message.place(relx=0,rely=0,relwidth=1.0,relheight=0.95)
        # 再開ボタン
        self.bt_error_restart = tk.Button(self.error_frame)
        self.bt_error_restart["text"] = "再開"
        self.bt_error_restart["font"] = "",20
        self.bt_error_restart["command"] = self.wait_touch
        self.bt_error_restart.place(relx=0.4,rely=0.7,relwidth=0.2,relheight=0.1)
        # 終了ボタン
        self.bt_error_exit = tk.Button(self.error_frame)
        self.bt_error_exit["text"] = "アプリ終了"
        self.bt_error_exit["font"] = "",20
        self.bt_error_exit["command"] = self.exit
        self.bt_error_exit.place(relx=0.4,rely=0.9,relwidth=0.2,relheight=0.1)

    # 情報入力フレーム作成
    def create_info_frame(self):
        # ベースフレーム
        self.info_frame = tk.Frame(self.root_frame,width=DISP_WIDTH,height=DISP_HEIGHT)
        self.info_frame.place(x=0,y=0)

        # フレーム1(社員情報)----------------------------------------------------------------
        self.frame1 = tk.Frame(self.info_frame,bg="#efe")
        # 終了ボタン
        self.bt_exit = tk.Button(self.frame1)
        self.bt_exit["text"] = "X"
        self.bt_exit["font"] = "",5
        self.bt_exit["command"] = self.exit
        self.bt_exit.place(relx=0,rely=0,relwidth=0.05,relheight=1.0)  
        # キャンセルボタン
        self.bt_cancel = tk.Button(self.frame1)
        self.bt_cancel["text"] = "キャンセル"
        self.bt_cancel["font"] = "",25
        self.bt_cancel["command"] = self.cancel
        self.bt_cancel.place(relx=0.05,rely=0,relwidth=0.15,relheight=1.0)
        # 再読込ボタン
        self.bt_reload = tk.Button(self.frame1)
        self.bt_reload["text"] = "再読込(F3)"
        self.bt_reload["font"] = "",FONT3
        self.bt_reload["command"] = self.restart_read
        self.bt_reload.place(relx=0.20,rely=0,relwidth=0.15,relheight=1.0)
        # 読取ボタン
        self.bt_cancel = tk.Button(self.frame1)
        self.bt_cancel["text"] = "読取(〇)"
        self.bt_cancel["font"] = "",FONT3
        self.bt_cancel["command"] = self.get_data
        self.bt_cancel.place(relx=0.35,rely=0,relwidth=0.15,relheight=1.0)
        # 社員情報ラベル
        self.lb_employeeinfo = tk.Label(self.frame1)
        self.lb_employeeinfo["textvariable"] = self.var_lb_employeeinfo
        self.lb_employeeinfo["font"] = "",int(FONT3/1.2)
        self.lb_employeeinfo.place(relx=0.5,rely=0,relwidth=0.5,relheight=1.0)
        # フレーム1配置
        self.frame1.place(relx=0,rely=0,relwidth=1.0,relheight=0.1)

        # フレーム2(体温)--------------------------------------------------------------------
        self.frame2 = tk.Frame(self.info_frame)

        # 画像キャンバス
        self.canvas1 = tk.Canvas(self.frame2)
        self.canvas1.configure( width= IMAGE_WIDTH, height=IMAGE_HEIGHT)
        self.canvas1.place(relx=0,rely=0,relwidth=0.5,relheight=1.0)

        # 部品情報表
        self.style = ttk.Style()
        self.style.configure("Treeview.Heading", font=("", 20))
        self.style.configure("Treeview", font=("", 30))
        self.style.configure('Treeview', rowheight=60)
        self.tree = ttk.Treeview(self.frame2)
        self.tree["columns"] = (1,2)
        self.tree["show"] = "headings"
        self.tree.heading(1,text="項目")
        self.tree.heading(2,text="値")
        self.tree.column(1,width=200,stretch=False)
        self.tree.insert("","end",id=0,tags="white",values=("ｺｰﾄﾞ",""))
        self.tree.insert("","end",id=1,tags="gray",values=("型式",""))
        self.tree.insert("","end",id=2,tags="white",values=("部品名",""))
        self.tree.insert("","end",id=3,tags="gray",values=("棚番号",""))
        self.tree.insert("","end",id=4,tags="white",values=("数量",""))
        self.tree.tag_configure("white",background="white")
        self.tree.tag_configure("gray",background="lightgray")
        self.style.map('Treeview', foreground=self.fixed_map('foreground'), background=self.fixed_map('background'))
        self.tree.place(relx=0.5,rely=0,relwidth=0.5,relheight=1.0)
        # フレーム2配置
        self.frame2.place(relx=0,rely=0.1,relwidth=1.0,relheight=0.667)

        # フレーム3(症状)--------------------------------------------------------------------
        self.frame3 = tk.Frame(self.info_frame)
        # 在庫↑ボタン ▲
        self.bt_up = tk.Button(self.frame3)
        self.bt_up["text"] = "▲(F2)"
        self.bt_up["font"] = "",FONT3
        self.bt_up["width"] = 4
        self.bt_up["command"] = self.up
        self.bt_up.place(relx=0,rely=0,relwidth=0.1,relheight=0.5)
        # 在庫↓ボタン ▼
        self.bt_down = tk.Button(self.frame3)
        self.bt_down["text"] = "▼(F1)"
        self.bt_down["font"] = "",FONT3
        self.bt_down["width"] = 4
        self.bt_down["command"] = self.down
        self.bt_down.place(relx=0,rely=0.5,relwidth=0.1,relheight=0.5)

        # 部品在庫数ラベル
        self.lb_stock = tk.Label(self.frame3)
        self.lb_stock["textvariable"] = self.var_lb_stock
        self.lb_stock["font"] = "",FONT1
        self.lb_stock["relief"] = "sunken"
        self.lb_stock["borderwidth"] = 5
        self.lb_stock.place(relx=0.1,rely=0,relwidth=0.4,relheight=1.0)

        # 入庫ボタン
        self.bt_record = tk.Button(self.frame3)
        self.bt_record["text"] = "入庫"
        self.bt_record["font"] = "",FONT1
        self.bt_record["width"] = 3
        self.bt_record["bg"] = "green4"
        self.bt_record["command"] = self.entering
        self.bt_record.place(relx=0.5,rely=0,relwidth=0.25,relheight=1.0)
        # 出庫ボタン
        self.bt_record = tk.Button(self.frame3)
        self.bt_record["text"] = "出庫"
        self.bt_record["font"] = "",FONT1
        self.bt_record["width"] = 3
        self.bt_record["bg"] = "orange"
        self.bt_record["command"] = self.leaving
        self.bt_record.place(relx=0.75,rely=0,relwidth=0.25,relheight=1.0)
        # フレーム3配置
        self.frame3.place(relx=0,rely=0.767,relwidth=1.0,relheight=0.233)

        # キーイベント
        self.master.bind("<KeyPress>",self.key_event)

    # 在庫↑ボタン
    def up(self):
        self.stock_num += 1
        self.var_lb_stock.set(self.stock_num)

    # 在庫↓ボタン
    def down(self):
        if self.stock_num > 0:
            self.stock_num -= 1
        self.var_lb_stock.set(self.stock_num)

    # treeviewに値をセット
    def set_tree(self,val0,val1,val2,val3,val4):
        self.reading_flag = False
        self.stock_num = 0
        self.var_lb_stock.set(0)
        self.tree.item(0,values=["ｺｰﾄﾞ",val0])
        self.tree.item(1,values=["型式",val1])
        self.tree.item(2,values=["部品名",val2])
        self.tree.item(3,values=["棚番号",val3])
        self.tree.item(4,values=["数量",val4])

    # カードタッチに戻る
    def cancel(self):
        self.change_message("社員証をタッチしてください",'black')
        self.wait_touch()

    # QRコード読込再開
    def restart_read(self):
        self.reading_flag = True
        
    # 部品コードから情報取得
    def get_data(self):
        data = self.get_stock_data(self.barcode)
        if data:
            self.get_stock_quantity(self.barcode)
            self.set_tree(self.code,self.model,self.name,self.shelf_num,self.quantity)
        else:
            self.set_tree(self.barcode,"","","","")

    # 在庫情報取得
    def get_stock_data(self,code):
        try:
            conn = self.get_connection() 
            cur = conn.cursor()
            # 在庫情報取得
            cur.execute("SELECT code,image,model,name,shelf_num FROM stock where code=%s ",(code,))
            if cur.rowcount == 1:
                # Beepを鳴らす
                self.beep(0.01)
                row = cur.fetchone()
                self.code = row[0]
                self.model = row[2]
                self.name = row[3]
                self.shelf_num = row[4]
                if row[1]: # imageが存在すればcanvas1に表示
                    self.img_bin = io.BytesIO(row[1])
                    img = PIL.Image.open(self.img_bin)
                    self.tempimg = PIL.ImageTk.PhotoImage(img)
                    self.canvas1.create_image(0,0, image=self.tempimg, anchor = tk.NW)
                else:      # 無ければ「No image」の画像生成して表示
                    self.create_dummy('No image')
                cur.close()
                conn.close()
                self.data_exist = True
                return 1
            else:
                # Beepを鳴らす
                self.beep(0.1)
                # データがない場合は「No data」の画像用生成して表示
                self.create_dummy('No data')
                cur.close()
                conn.close()
                self.reset_stock()
                return 0
        except:
            self.beep(0.1)
            self.change_message("通信エラー発生",'red')
            app.after(1500,self.reset)

    def get_stock_quantity(self,code):
        try:
            # DB接続
            conn = self.get_connection() 
            cur = conn.cursor()
            cur.execute("SELECT sum(quantity) FROM stock_history where code=%s",(code,))
            if cur.rowcount == 1:
                row = cur.fetchone()
                self.quantity = row[0]
            cur.close()
            conn.close()
        except:
            self.beep(0.1)
            self.change_message("通信エラー発生",'red')
            app.after(1500,self.reset)

    # 入庫処理
    def entering(self):
        if self.data_exist:
            self.inout = 1
            self.change_message("登録処理中・・・",'orange')
            self.wait_card_frame.tkraise()
            app.after(1,self.regist) # 1ms置いて画面表示を更新させる
    
    # 出庫処理
    def leaving(self):
        if self.data_exist:
            if self.stock_num <= self.quantity:
                self.inout = -1
                self.change_message("登録処理中・・・",'orange')
                self.wait_card_frame.tkraise()
                app.after(1,self.regist) # 1ms置いて画面表示を更新させる
            else:
                self.stock_num = self.quantity
                self.var_lb_stock.set(self.stock_num)

    def regist(self):
        try:
            self.stock_num *= self.inout
            conn = self.get_connection() 
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO stock_history (code,quantity,created_by,created_at,updated_at) VALUES (%s,%s,%s,now(),now())",
                (self.code,str(self.stock_num),self.employeenum,)
            )
            conn.commit()
            cur.close()
            conn.close()
            self.change_message("登録完了",'green4')
            app.after(1500,self.reset)
        except:
            self.beep(0.1)
            self.change_message("通信エラー発生",'red')
            app.after(1500,self.reset)# 1.5秒待ち

    # 読込後、エラー後のリセット
    def reset(self):
        self.reset_stock()
        self.set_tree(self.barcode,"","","","")
        self.info_frame.tkraise()
        self.restart_read()

    # treeviewのバグフィックス用
    def fixed_map(self,option):
        return [elm for elm in self.style.map('Treeview', query_opt=option) if
            elm[:2] != ('!disabled', '!selected')]

    # ダミー画像の生成
    def create_dummy(self,text):
        (w,h),_=cv2.getTextSize(text,cv2.FONT_HERSHEY_SIMPLEX,3,4)
        blank_img = np.full((IMAGE_HEIGHT,IMAGE_WIDTH,3),(255,255,255),dtype=np.uint8)
        cv2.putText(blank_img,text,(int((IMAGE_WIDTH-w)/2),int((IMAGE_HEIGHT+h)/2)),cv2.FONT_HERSHEY_SIMPLEX,3,(0,0,0),4)
        self.tempimg = PIL.ImageTk.PhotoImage(image = PIL.Image.fromarray(blank_img))
        self.canvas1.create_image(0,0, image=self.tempimg, anchor = tk.NW)

root = tk.Tk()
app = Application(master=root)
app.mainloop()