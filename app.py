from flask import Flask, request, abort
from linebot.v3.webhook import WebhookHandler
from linebot.v3.webhooks import PostbackEvent
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage, FlexMessage, FlexContainer
from linebot.v3.messaging import PushMessageRequest
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent
import sqlite3
import os
from groq import Groq
import db
import json

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import threading
import random

# Google Calendar API 関連のインポートを追加
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle

app = Flask(__name__)

client = Groq(api_key=os.environ["GROQ_API_KEY"])

db.init_db()

configuration = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])

# 9時に掃除場所を割り当てるためのスケジューラを起動
scheduler = BackgroundScheduler()

CLEAN_PLACE = {
    "下駄箱側のマット+講義室1までの廊下のコロコロがけ",
    "講義室2・3の廊下のコロコロがけ",
    # "講義室4・5の廊下のコロコロがけ",
    # "トイレ個室掃除・トイレのゴミ捨て",
    # "トイレの洗面台・トイレ内の廊下掃除・トイレ内の備品補充",
    # "ホワイエ1の掃除",
    # "ホワイエ2の清掃",
    # "セコム側入り口の看板周りの清掃",
    # "自分の学年の教室の掃除機がけ",
    # "自分の学年の教室机上の拭き取り・ゴミ箱内のチェック・回収",
    # "自分の学年の教室のホワイトボード清掃",
}

# YES/NO で NO が選択された際にコメントを受け取るかどうかを判定するための簡易メモリ管理
pending_comments = {}

SCOPES = ['https://www.googleapis.com/auth/calendar']
CALENDAR_ID = os.environ.get("CALENDAR_ID", "primary")  # 環境変数や固定IDなど必要に応じて設定

@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    db.save_user_id(user_id)
    
    welcome_message = TextMessage(text="友達追加ありがとうございます！お掃除頑張りましょう！")
    send_message(event, welcome_message)
        
    print(f"新しいユーザーが追加されました: {user_id}")
    db.save_user_name(user_id, event.message.text)

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text

    # ユーザーがコメント入力待ち状態かどうか
    if user_id in pending_comments and pending_comments[user_id] is True:
        comment = text
        del pending_comments[user_id]  # 状態クリア

        clean_user_id = db.get_clean_user(user_id)
        if clean_user_id:
            notify_text = f"チェック担当から次のコメントが届きました:\n「{comment}」"
            send_push_message(clean_user_id, notify_text)

        reply_msg = TextMessage(text="コメントを受け付けました。ご報告ありがとうございます。")
        send_message(event, reply_msg)
        return

    db.save_user_id(user_id)

    if text == "掃除完了":
        message = TextMessage(text="掃除完了報告を受け付けました。チェック担当者に通知します。")
        send_message(event, message)
        send_clean_completion_message(user_id)

    elif text == "チェック完了":
        with open("check.json", "r", encoding='utf-8') as file:
            flex_template = json.load(file)
        flex_msg = FlexMessage(
            alt_text="チェック完了報告",
            contents=FlexContainer.from_dict(flex_template)
        )
        with ApiClient(configuration) as api_client:
            linebot_api = MessagingApi(api_client)
            reply_message_request = ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[flex_msg]
            )
            linebot_api.reply_message(reply_message_request)

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    user_id = event.source.user_id
    
    if data == "CHECK_OK":
        message = TextMessage(text=f"チェック完了を受け付けました。お疲れさまでした。\n次回の掃除日程は、Googleカレンダーを確認してね。")
        send_postback_reply(event, message)
        send_check_completion_message(user_id)
        # 既存処理：フラグ更新
        db.update_clean_check(user_id, True)
        
        # 追加: 次回の掃除予定を Google Calendar に登録する
        place = db.get_cleaning_place(user_id)
        if place:
            create_next_calendar_event(user_id, place)
        else:
            print("掃除場所が見つかりませんでした。次回の掃除日程は登録しません。")

    elif data == "CHECK_NG":
        pending_comments[user_id] = True
        msg = TextMessage(text="仕上がりが十分ではなかったようです。\nコメント（改善点など）を入力してください。")
        send_postback_reply(event, msg)
        db.update_clean_check(user_id, False)

def send_postback_reply(event, message_obj):
    with ApiClient(configuration) as api_client:
        linebot_api = MessagingApi(api_client)
        reply_message_request = ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[message_obj]
        )
        linebot_api.reply_message(reply_message_request)

def send_clean_completion_message(clean_user_id):
    check_user_id = db.get_check_user(clean_user_id)
    if not check_user_id:
        return
    message_text = (
        "担当者が掃除完了報告をしました。\n"
        "掃除場所の確認をお願いいたします。"
    )
    send_push_message(check_user_id, message_text)

def send_check_completion_message(user_id):
    clean_user_id = db.get_clean_user(user_id)
    if not clean_user_id:
        return
    message_text = (
        "チェックが完了しました。\n"
        "お疲れさまでした。"
    )
    send_push_message(clean_user_id, message_text)

def assign_random_cleaning_place():
    user_ids = db.get_all_user_ids()
    clean_places = list(CLEAN_PLACE)
    random.shuffle(clean_places)
    selected_users = user_ids[:len(clean_places)]
    check_places = clean_places.copy()

    for i, user_id in enumerate(selected_users):
        assigned_place = clean_places[i]
        available_check_places = [p for p in check_places if p != assigned_place]
        check_place = random.choice(available_check_places)
        db.update_cleaning_place(user_id, assigned_place)
        db.update_checking_place(user_id, check_place)

    print("掃除場所とチェック場所の割り当てが完了しました。")

def create_calendar_event(user_id, place):
    creds = None
    # 認証トークンが保存されていれば読み込む
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # 資格情報がないか期限切れの場合は新規に認証フローを実行
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # トークンを保存
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    service = build('calendar', 'v3', credentials=creds)

    # イベントの開始・終了時刻例（当日9:00〜10:00）
    start_time = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(hours=1)

    event = {
        'summary': f"あなたの掃除当番",
        'description': f"場所: {place}",
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'Asia/Tokyo',
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'Asia/Tokyo',
        },
    }

def create_next_calendar_event(user_id, place):
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    service = build('calendar', 'v3', credentials=creds)

    # 1週間後の同じ時刻に設定（現在時刻から一週間後）
    start_time = datetime.now() + timedelta(weeks=1)
    start_time = start_time.replace(hour=9, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(hours=1)

    event = {
        'summary': f"掃除当番",
        'description': f"場所: {place}",
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'Asia/Tokyo',
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'Asia/Tokyo',
        },
    }

    event_result = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    print(f"次回掃除予定をカレンダーに登録しました: {event_result.get('htmlLink')}")

def assign_and_send_random_cleaning_place():
    assign_random_cleaning_place()
    user_ids = db.get_all_user_ids()
    for user_id in user_ids:
        place = db.get_cleaning_place(user_id)
        check_place = db.get_checking_place(user_id)
        if place and check_place:
            msg = (
                "本日の掃除場所をお知らせします。\n"
                f"掃除場所: {place}\n"
                f"チェック場所: {check_place}\n\n"
                "よろしくお願いします！"
            )
            send_push_message(user_id, msg)

scheduler.add_job(assign_and_send_random_cleaning_place, 'cron', hour=9, minute=0)

def send_message(event, message_obj):
    with ApiClient(configuration) as api_client:
        linebot_api = MessagingApi(api_client)
        reply_message_request = ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[message_obj]
        )
        linebot_api.reply_message(reply_message_request)

def send_push_message(user_id, text):
    with ApiClient(configuration) as api_client:
        linebot_api = MessagingApi(api_client)
        message = TextMessage(text=text)
        push_message_request = PushMessageRequest(
            to=user_id,
            messages=[message]
        )
        linebot_api.push_message(push_message_request)

def console_input():
    while True:
        command = input("コマンドを入力してください（'send': 配信メッセージ送信, 'init': DB初期化）: ")
        if command.lower() == 'send':
            assign_and_send_random_cleaning_place()
            print("掃除場所の通知を送信し、Googleカレンダーに登録しました。")
        elif command.lower() == 'init':
            db.init_db()
            print("データベースを初期化しました。")

if __name__ == "__main__":
    db.init_db()
    scheduler.start()
    input_thread = threading.Thread(target=console_input, daemon=True)
    input_thread.start()
    app.run(port=8000, debug=True)