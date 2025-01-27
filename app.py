from flask import Flask, request, abort
from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage, FlexMessage, FlexContainer
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent
from linebot.v3.messaging import PushMessageRequest
import sqlite3
import os
import groq
import db

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import threading
import random

app = Flask(__name__)

client = groq(api_key=os.environ["GROQ_API_KEY"])

db.init_db()

configuration = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])

CLEAN_PLACE = {
    "下駄箱側のマット+講義室1までの廊下のコロコロがけ",
    "講義室2・3の廊下のコロコロがけ",
    "講義室4・5の廊下のコロコロがけ",
    "トイレ個室掃除・トイレのゴミ捨て",
    "トイレの洗面台・トイレ内の廊下掃除・トイレ内の備品補充",
    "ホワイエ1の掃除",
    "ホワイエ2の清掃",
    "セコム側入り口の看板周りの清掃",
    "自分の学年の教室の掃除機がけ",
    "自分の学年の教室机上の拭き取り・ゴミ箱内のチェック・回収",
    "自分の学年の教室のホワイトボード清掃",
}



@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

#フォローイベント
@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    db.save_user_id(user_id)
    
    welcome_message = TextMessage(text="友達追加ありがとうございます!頑張って掃除しましょう!")
    
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        reply_message_request = ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[welcome_message]
        )
        line_bot_api.reply_message(reply_message_request)
    
    print(f"新しいユーザーが追加されました: {user_id}")
    
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    db.save_user_id(user_id)
    text = event.message.text
    
    if text == "掃除完了":
        # 掃除完了メッセージを送信
        message = TextMessage(text="掃除完了メッセージを送信しました。")
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            reply_message_request = ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[message]
            )
            line_bot_api.reply_message(reply_message_request)

    clean_name = db.get_user_name(user_id)
    send_clean_completion_message(event, clean_name)

    
def send_clean_completion_message(event, clean_user):
    message = TextMessage(text=f"{db.get_name(clen)}さんの掃除が完了しました。チェックしましょう。")
    check_user = db.get_check_user(cle)
    send_push_message(check_user, message)

    

def assign_random_cleaning_place():
    # 全ユーザーIDを取得
    user_ids = db.get_all_user_ids()
    
    # 掃除場所のリストを作成
    clean_places = list(CLEAN_PLACE)
    
    # 掃除場所の数だけユーザーを選択
    selected_users = user_ids[:len(clean_places)]
    
    # 掃除場所をシャッフル
    random.shuffle(clean_places)
    
    # チェック用の掃除場所リストを作成
    check_places = clean_places.copy()
    
    # 各ユーザーに掃除場所とチェック場所を割り当て
    for i, user_id in enumerate(selected_users):
        # 掃除場所を割り当て
        assigned_place = clean_places[i]
        
        # チェック場所用のリストから自分の掃除場所を除外
        available_check_places = [place for place in check_places if place != assigned_place]
        
        # チェック場所をランダムに選択
        check_place = random.choice(available_check_places)
        
        # データベースに保存
        db.update_cleaning_place(user_id, assigned_place)
        db.update_checking_place(user_id, check_place)
        
    print("掃除場所とチェック場所の割り当てが完了しました")

def send_message(event, text):
    with ApiClient(configuration) as api_client:
        linebot_api = MessagingApi(api_client)
        
        # メッセージオブジェクトを作成
        message = TextMessage(text=text)
        reply_message_request = ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[message]
        )
        linebot_api.reply_message(reply_message_request)

def send_push_message(user_id, text):
    with ApiClient(configuration) as api_client:
        linebot_api = MessagingApi(api_client)

        # メッセージオブジェクトを作成
        message = TextMessage(text=text)
        push_message_request = PushMessageRequest(
            to=user_id,
            messages=[message]
        )
        linebot_api.push_message(push_message_request)