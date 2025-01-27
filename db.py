from flask import Flask, request, abort
import sqlite3

# データベース接続とテーブル作成
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                (user_id TEXT PRIMARY KEY 
                name TEXT
                assigned_place TEXT
                check_place TEXT
                clean_check BOOLEAN
                )''')
    conn.commit()
    conn.close()

# ユーザーIDを保存
def save_user_id(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

# 全ユーザーIDを取得
def get_all_user_ids():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    user_ids = [row[0] for row in c.fetchall()]
    conn.close()
    return user_ids