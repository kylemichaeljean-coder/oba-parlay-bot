import sqlite3
import time

DB_NAME = "oba.db"

def get_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guilds (
        guild_id INTEGER PRIMARY KEY,
        cycle INTEGER DEFAULT 1
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        guild_id INTEGER,
        user_id INTEGER,
        correct INTEGER DEFAULT 0,
        points INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS parlays (
        message_id INTEGER PRIMARY KEY,
        guild_id INTEGER,
        name TEXT,
        created_at INTEGER,
        lock_time INTEGER,
        closed INTEGER DEFAULT 0,
        finalized INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS picks (
        message_id INTEGER,
        user_id INTEGER,
        emoji TEXT,
        PRIMARY KEY (message_id, user_id)
    )
    """)

    conn.commit()
    conn.close()
