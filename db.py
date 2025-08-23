import sqlite3
import pandas as pd

DB_FILE = "app.db"

def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def db_execute(query, params=()):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    return cur

def db_query(query, params=(), as_df=False):
    conn = get_conn()
    if as_df:
        return pd.read_sql_query(query, conn, params=params)
    cur = conn.cursor()
    cur.execute(query, params)
    return cur.fetchall()


