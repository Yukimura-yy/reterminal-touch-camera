import tkinter as tk
import time
import threading
import psycopg2
import rcs620s
import seeed_python_reterminal.core as rt

# DB接続情報 
DB_HOST = 'IP_address'
DB_PORT = 'port'
DB_NAME = 'DB_name'
DB_USER = 'username'
DB_PASS = 'password'

# 設定
DISP_WIDTH = 1280
DISP_HEIGHT = 720
FONT1 = 160 # 体温
FONT2 = 60  # メッセージ
FONT3 = 40  # 各種項目
BEEP = True

# シリアル通信設定
SERIAL_PORT = "/dev/ttyS0"

class Application(tk.Frame):
    def __init__(self,master=None):
        super().__init__(master)

        # マスターウィンドウ
        master.title("健康チェック")
        master.geometry(f"{DISP_WIDTH}x{DISP_HEIGHT}+0+0")
        master.attributes("-fullscreen", True)
        master.config(cursor="none")
        self.pack()

        # ルートフレーム
        self.root_frame = tk.Frame(self,width=DISP_WIDTH,height=DISP_HEIGHT)
        self.root_frame.pack()
        
        # 情報初期化
        self.reset_info()
        
        # 社員情報ラベル
        self.var_lb_employeeinfo = tk.StringVar()
        self.var_lb_employeeinfo.set(f"社員番号 : {self.employeenum}  氏名 : {self.user}")
        # 体温ラベル
        self.var_lb_tempreture = tk.StringVar()
        self.var_lb_tempreture.set(str(self.tempreture)+"℃ ")
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
        # カード待ち
        self.wait_touch()

    # カードリーダー初期化
    def init_icreader(self):
        self.ic_reader = rcs620s.Rcs620s()
        self.ic_reader.init(SERIAL_PORT)
    
    # 情報初期化
    def reset_info(self):
        self.cardidm = ""
        self.user = "〇〇 〇〇"
        self.employeenum = "*****"
        self.tempreture = 36.5    

    # 症状初期化
    def reset_symptom(self):
        self.var_fever.set(0)
        self.var_fatigue.set(0)
        self.var_suffocating.set(0)
        self.change_radio_color()

    # カード待ち処理
    def wait_touch(self):
        # 情報初期化
        self.reset_info()
        self.reset_symptom()
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
                cur.execute("SELECT employeenum,username FROM users where cardidm=%s",(self.cardidm,))
                if cur.rowcount == 1:
                    # Beepを鳴らす
                    self.beep(0.01)
                    rows = cur.fetchone()
                    self.employeenum = rows[0]
                    self.user = rows[1]
                    self.var_lb_employeeinfo.set(f"社員番号 : {self.employeenum}  氏名 : {self.user}")
                    self.info_frame.tkraise()
                    cur.execute("select avg(tempreture) from health_check where employeenum=%s and tempreture>30.0",(self.employeenum,))
                    rows = cur.fetchone()
                    if rows[0] == None:
                        self.tempreture = 36.5
                    else:
                        self.tempreture = round(rows[0],1)
                    self.var_lb_tempreture.set(str(self.tempreture)+"℃ ")
                    cur.close()
                    conn.close()
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
        self.lb_message["font"] = "",FONT2
        self.lb_message.place(relx=0,rely=0,relwidth=1.0,relheight=0.95)

    # エラーフレーム作成
    def create_error_frame(self):
        # ベースフレーム
        self.error_frame = tk.Frame(self.root_frame,width=DISP_WIDTH,height=DISP_HEIGHT)
        self.error_frame.place(x=0,y=0)
        # エラーラベル
        self.lb_error_message = tk.Label(self.error_frame)
        self.lb_error_message["text"] = "エラーが発生しました"
        self.lb_error_message["font"] = "",FONT2
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
        self.bt_exit.place(relx=0,rely=0,relwidth=0.04,relheight=1.0)  
        # キャンセルボタン
        self.bt_cancel = tk.Button(self.frame1)
        self.bt_cancel["text"] = "キャンセル"
        self.bt_cancel["font"] = "",25
        self.bt_cancel["command"] = self.cancel
        self.bt_cancel.place(relx=0.04,rely=0,relwidth=0.16,relheight=1.0)
        # 社員情報ラベル
        self.lb_employeeinfo = tk.Label(self.frame1)
        self.lb_employeeinfo["textvariable"] = self.var_lb_employeeinfo
        self.lb_employeeinfo["font"] = "",FONT3
        self.lb_employeeinfo.place(relx=0.2,rely=0,relwidth=0.8,relheight=1.0)
        # フレーム1配置
        self.frame1.place(relx=0,rely=0,relwidth=1.0,relheight=0.1)

        # フレーム2(体温)--------------------------------------------------------------------
        self.frame2 = tk.Frame(self.info_frame)
        # 体温ラベル
        self.lb = tk.Label(self.frame2)
        self.lb["text"] = "体温 :"
        self.lb["font"] = "",25
        self.lb.place(relx=0,rely=0,relwidth=0.10,relheight=1.0)
        # 体温(数字)ラベル
        self.lb_tempreture = tk.Label(self.frame2)
        self.lb_tempreture["textvariable"] = self.var_lb_tempreture
        self.lb_tempreture["font"] = "",FONT1
        self.lb_tempreture.place(relx=0.10,rely=0,relwidth=0.6,relheight=1.0)
        # 体温上昇ボタン ▲
        self.bt_up = tk.Button(self.frame2)
        self.bt_up["text"] = "▲"
        self.bt_up["font"] = "",int(FONT1/2)
        self.bt_up["width"] = 4
        self.bt_up["command"] = self.up
        self.bt_up.place(relx=0.7,rely=0,relwidth=0.3,relheight=0.5)
        # 体温下降ボタン ▼
        self.bt_down = tk.Button(self.frame2)
        self.bt_down["text"] = "▼"
        self.bt_down["font"] = "",int(FONT1/2)
        self.bt_down["width"] = 4
        self.bt_down["command"] = self.down
        self.bt_down.place(relx=0.7,rely=0.5,relwidth=0.3,relheight=0.5)
        # フレーム2配置
        self.frame2.place(relx=0,rely=0.1,relwidth=1.0,relheight=0.6)

        # フレーム3(症状)--------------------------------------------------------------------
        self.frame3 = tk.Frame(self.info_frame)
        # 発熱ラジオボタンフレーム
        self.frame_fever = tk.LabelFrame(self.frame3)
        self.frame_fever["text"] = "発熱"
        self.frame_fever["font"] = "",FONT3
        self.frame_fever.place(relx=0,rely=0,relwidth=0.17,relheight=1.0)
        # ラジオボタン状態変数
        self.var_fever = tk.IntVar()
        self.var_fever.set(0)
        # 発熱なし
        self.rd_fever_F = tk.Radiobutton(self.frame_fever)
        self.rd_fever_F["text"] = "なし"
        self.rd_fever_F["font"] = "",FONT3
        self.rd_fever_F["value"] = 0
        self.rd_fever_F["bg"] = 'turquoise'
        self.rd_fever_F["variable"] = self.var_fever
        self.rd_fever_F["command"] = self.change_radio_color
        self.rd_fever_F.pack()
        # 発熱あり
        self.rd_fever_T = tk.Radiobutton(self.frame_fever)
        self.rd_fever_T["text"] = "あり"
        self.rd_fever_T["font"] = "",FONT3
        self.rd_fever_T["value"] = 1
        self.rd_fever_T["variable"] = self.var_fever
        self.rd_fever_T["command"] = self.change_radio_color
        self.rd_fever_T.pack()

        # 倦怠ラジオボタン
        self.frame_fatigue = tk.LabelFrame(self.frame3)
        self.frame_fatigue["text"] = "倦怠感"
        self.frame_fatigue["font"] = "",FONT3
        self.frame_fatigue.place(relx=0.17,rely=0,relwidth=0.17,relheight=1.0)
        # ラジオボタン状態変数
        self.var_fatigue = tk.IntVar()
        self.var_fatigue.set(0)
        # 倦怠なし
        self.rd_fatigue_F = tk.Radiobutton(self.frame_fatigue)
        self.rd_fatigue_F["text"] = "なし"
        self.rd_fatigue_F["font"] = "",FONT3
        self.rd_fatigue_F["value"] = 0
        self.rd_fatigue_F["bg"] = 'turquoise'
        self.rd_fatigue_F["variable"] = self.var_fatigue
        self.rd_fatigue_F["command"] = self.change_radio_color
        self.rd_fatigue_F.pack()
        # 倦怠あり
        self.rd_fatigue_T = tk.Radiobutton(self.frame_fatigue)
        self.rd_fatigue_T["text"] = "あり"
        self.rd_fatigue_T["font"] = "",FONT3
        self.rd_fatigue_T["value"] = 1
        self.rd_fatigue_T["variable"] = self.var_fatigue
        self.rd_fatigue_T["command"] = self.change_radio_color
        self.rd_fatigue_T.pack()

        # 息苦ラジオボタン
        self.frame_suffocating = tk.LabelFrame(self.frame3)
        self.frame_suffocating["text"] = "息苦しさ"
        self.frame_suffocating["font"] = "",FONT3
        self.frame_suffocating.place(relx=0.34,rely=0,relwidth=0.17,relheight=1.0)
        # ラジオボタン状態変数
        self.var_suffocating = tk.IntVar()
        self.var_suffocating.set(0)
        # 息苦なし
        self.rd_suffocating_F = tk.Radiobutton(self.frame_suffocating)
        self.rd_suffocating_F["text"] = "なし"
        self.rd_suffocating_F["font"] = "",FONT3
        self.rd_suffocating_F["value"] = 0
        self.rd_suffocating_F["bg"] = 'turquoise'
        self.rd_suffocating_F["variable"] = self.var_suffocating
        self.rd_suffocating_F["command"] = self.change_radio_color
        self.rd_suffocating_F.pack()
        # 息苦あり
        self.rd_suffocating_T = tk.Radiobutton(self.frame_suffocating)
        self.rd_suffocating_T["text"] = "あり"
        self.rd_suffocating_T["font"] = "",FONT3
        self.rd_suffocating_T["value"] = 1
        self.rd_suffocating_T["variable"] = self.var_suffocating
        self.rd_suffocating_T["command"] = self.change_radio_color
        self.rd_suffocating_T.pack()
        
        # 登録ボタン
        self.bt_record = tk.Button(self.frame3)
        self.bt_record["text"] = "登録"
        self.bt_record["font"] = "",int(FONT1/1.5)
        self.bt_record["width"] = 3
        self.bt_record["bg"] = "orange"
        self.bt_record["command"] = self.register
        self.bt_record.place(relx=0.7,rely=0,relwidth=0.3,relheight=1.0)
        # フレーム3配置
        self.frame3.place(relx=0,rely=0.7,relwidth=1.0,relheight=0.3)

    # 温度↑ボタン
    def up(self):
        self.tempreture = ((self.tempreture*10.0 + 1)/10.0)
        self.var_lb_tempreture.set(str(self.tempreture)+"℃ ")
        if self.tempreture >= 37.5:
            self.var_fever.set(1)
            self.rd_fever_F["bg"] = root.cget("bg")
            self.rd_fever_T["bg"] = 'red2'

    # 温度↓ボタン
    def down(self):
        self.tempreture = ((self.tempreture*10.0 - 1)/10.0)
        self.var_lb_tempreture.set(str(self.tempreture)+"℃ ")
        if self.tempreture < 37.5:
            self.var_fever.set(0)
            self.rd_fever_F["bg"] = 'turquoise'
            self.rd_fever_T["bg"] = root.cget("bg")

    # 背景色の変化
    def change_radio_color(self):
        default_color = root.cget("bg")
        if self.var_fever.get():
            self.rd_fever_F["bg"] = default_color
            self.rd_fever_T["bg"] = 'red2'
        else:
            self.rd_fever_F["bg"] = 'turquoise'
            self.rd_fever_T["bg"] = default_color
        if self.var_fatigue.get():
            self.rd_fatigue_F["bg"] = default_color
            self.rd_fatigue_T["bg"] = 'red2'
        else:
            self.rd_fatigue_F["bg"] = 'turquoise'
            self.rd_fatigue_T["bg"] = default_color
        if self.var_suffocating.get():
            self.rd_suffocating_F["bg"] = default_color
            self.rd_suffocating_T["bg"] = 'red2'
        else:
            self.rd_suffocating_F["bg"] = 'turquoise'
            self.rd_suffocating_T["bg"] = default_color

    def cancel(self):
        self.wait_touch()

    def register(self):
        self.change_message("登録処理中・・・",'orange')
        self.wait_card_frame.tkraise()
        app.after(1,self.complete) # 1ms置いて画面表示を更新させる

    def complete(self):
        try:
            conn = self.get_connection() 
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO health_check (employeenum,tempreture,fever,fatigue,suffocating,created_at,updated_at,record_datetime) VALUES (%s,%s,%s,%s,%s,now(),now(),now())",
                (self.employeenum,self.tempreture,bool(self.var_fever.get()),bool(self.var_fatigue.get()),bool(self.var_suffocating.get()))
            )
            conn.commit()
            cur.close()
            conn.close()
            self.change_message("登録完了",'green4')
            # カード待ち画面へ戻る
            self.wait_touch()
        except:
            self.beep(0.1)
            self.change_message("通信エラー発生",'red')
            time.sleep(1.5) # 1.5秒待ち
            self.change_message("社員証をタッチしてください",'black') # 戻す
            self.error_frame.tkraise()

root = tk.Tk()
app = Application(master=root)
app.mainloop()