"""SQLite persistence for subscription ledgers."""

import json
import os
import sqlite3
import threading

DB_PATH = os.environ.get("DINGYUE_DB") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "dingyue.db")
_LOCK = threading.Lock()
_LOCAL = threading.local()


def use(path):
    global DB_PATH
    if path:
        DB_PATH = path
        _LOCAL.conn = None


def connect():
    conn = getattr(_LOCAL, "conn", None)
    if conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("""CREATE TABLE IF NOT EXISTS ledgers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, count INTEGER, total REAL,
            detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS subs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ledger_id INTEGER, merchant TEXT,
            category TEXT, amount REAL, cycle TEXT, annual REAL, next TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        conn.commit()
        _LOCAL.conn = conn
    return conn


def save(result):
    with _LOCK:
        conn = connect()
        cur = conn.execute("INSERT INTO ledgers(count, total, detail) VALUES (?,?,?)",
                           (result["count"], result["total"], json.dumps(result, ensure_ascii=False)))
        lid = cur.lastrowid
        for r in result["rows"]:
            conn.execute("INSERT INTO subs(ledger_id, merchant, category, amount, cycle, annual, next)"
                         " VALUES (?,?,?,?,?,?,?)",
                         (lid, r["merchant"], r["category"], r["amount"], r["cycle"], r["annual"], r["next"]))
        conn.commit()
        return lid


def ledgers(limit=10):
    with _LOCK:
        rows = connect().execute(
            "SELECT id, count, total, created_at FROM ledgers ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
