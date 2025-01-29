from flask import Flask, request, abort
import sqlite3

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # 既存のテーブル作成
    c.execute('''CREATE TABLE IF NOT EXISTS users
                (user_id TEXT PRIMARY KEY, 
                cleaning_place TEXT,
                checking_place TEXT)''')
    
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

def update_cleaning_place(user_id, assigned_place):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    # 假に users テーブルに assigned_place カラムがある場合
    c.execute("UPDATE users SET assigned_place = ? WHERE user_id = ?", (assigned_place, user_id))
    conn.commit()
    conn.close()

def update_checking_place(user_id, check_place):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    # 假に users テーブルに check_place カラムがある場合
    c.execute("UPDATE users SET check_place = ? WHERE user_id = ?", (check_place, user_id))
    conn.commit()
    conn.close()

def get_cleaning_place(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT assigned_place FROM users WHERE user_id = ?", (user_id,))
    assigned_place = c.fetchone()
    conn.close()
    return assigned_place[0] if assigned_place else None

def get_checking_place(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT check_place FROM users WHERE user_id = ?", (user_id,))
    check_place = c.fetchone()
    conn.close()
    return check_place[0] if check_place else None

def get_check_user(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id != ?", (user_id,))
    check_user_id = c.fetchone()
    conn.close()
    return check_user_id[0] if check_user_id else None

def get_clean_user(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id != ?", (user_id,))
    clean_user_id = c.fetchone()
    conn.close()
    return clean_user_id[0] if clean_user_id else None

def update_clean_check(user_id, clean_check):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET clean_check = ? WHERE user_id = ?", (clean_check, user_id))
    conn.commit()
    conn.close()
    
def get_next_cleaning_date():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    try:
        c.execute("SELECT cleaning_date FROM cleaning_schedule WHERE cleaning_date >= DATE('now') ORDER BY cleaning_date LIMIT 1")
        result = c.fetchone()
        return result[0] if result else "予定なし"
    finally:
        conn.close()