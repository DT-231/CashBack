"""SQLite: lưu link đã phát + log click. Không có postback thì click là dữ liệu duy nhất."""
import os
import sqlite3
import time
from pathlib import Path

DB_PATH = os.environ.get(
    "DB_PATH", str(Path(__file__).resolve().parent / "data" / "links.db")
)


def _conn():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS links(
                sub_id TEXT PRIMARY KEY,
                target TEXT NOT NULL,
                product_url TEXT,
                item_id INTEGER,
                shop_id INTEGER,
                name TEXT,
                keyword TEXT,
                created_at INTEGER
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS clicks(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sub_id TEXT,
                ts INTEGER,
                ip_hash TEXT,
                ua TEXT,
                referer TEXT
            )"""
        )


def save_link(sub_id, target, product_url=None, item_id=None, shop_id=None, name=None, keyword=None):
    with _conn() as c:
        c.execute(
            """INSERT INTO links(sub_id,target,product_url,item_id,shop_id,name,keyword,created_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(sub_id) DO UPDATE SET
                 target=excluded.target, product_url=excluded.product_url,
                 item_id=excluded.item_id, shop_id=excluded.shop_id,
                 name=excluded.name, keyword=excluded.keyword""",
            (str(sub_id), target, product_url, item_id, shop_id, name, keyword, int(time.time())),
        )


def get_target(sub_id):
    with _conn() as c:
        row = c.execute("SELECT * FROM links WHERE sub_id=?", (str(sub_id),)).fetchone()
        return dict(row) if row else None


def log_click(sub_id, ip_hash="", ua="", referer=""):
    with _conn() as c:
        c.execute(
            "INSERT INTO clicks(sub_id,ts,ip_hash,ua,referer) VALUES(?,?,?,?,?)",
            (str(sub_id), int(time.time()), ip_hash, ua[:300], referer[:300]),
        )


def stats(since_days=7):
    cutoff = int(time.time()) - since_days * 86400
    with _conn() as c:
        rows = c.execute(
            """SELECT l.sub_id, l.name, l.keyword,
                      COUNT(k.id) AS clicks,
                      MAX(k.ts) AS last_click
               FROM links l LEFT JOIN clicks k
                 ON k.sub_id = l.sub_id AND k.ts >= ?
               GROUP BY l.sub_id ORDER BY clicks DESC""",
            (cutoff,),
        ).fetchall()
        total = c.execute(
            "SELECT COUNT(*) AS n FROM clicks WHERE ts >= ?", (cutoff,)
        ).fetchone()["n"]
        links = c.execute("SELECT COUNT(*) AS n FROM links").fetchone()["n"]
    return {
        "links_issued": links,
        "clicks_total": total,
        "window_days": since_days,
        "by_link": [dict(r) for r in rows],
    }
