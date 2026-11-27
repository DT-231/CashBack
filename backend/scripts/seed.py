"""Seed dữ liệu DEV: 1 admin, 2 member, cấu hình mặc định. Mật khẩu lấy từ SEED_PASSWORD."""
import _bootstrap  # noqa: F401
import json
import os

from argon2 import PasswordHasher
from sqlalchemy import create_engine, text

from app.core.config import load_settings

url = load_settings().database_url
if not url:
    raise SystemExit("Thiếu DATABASE_URL")
pw = os.environ.get("SEED_PASSWORD")
if not pw:
    raise SystemExit("Thiếu SEED_PASSWORD (chỉ dùng cho dev)")
ph = PasswordHasher()
engine = create_engine(url)

USERS = [("admin@example.test", "admin"), ("member1@example.test", "member"),
         ("member2@example.test", "member")]
SETTINGS = {"user_share_bp": 6000, "min_withdraw_vnd": 100000, "hold_days": 7}

with engine.begin() as c:
    for email, role in USERS:
        row = c.execute(text(
            "INSERT INTO users(email,password_hash,role,status) VALUES(:e,:p,:r,'active') "
            "ON CONFLICT(email) DO NOTHING RETURNING id"),
            {"e": email, "p": ph.hash(pw), "r": role}).fetchone()
        if row:
            c.execute(text("INSERT INTO wallets(user_id) VALUES(:i) ON CONFLICT DO NOTHING"), {"i": row[0]})
    for k, v in SETTINGS.items():
        c.execute(text(
            "INSERT INTO settings(key,value,effective_from) VALUES(:k,CAST(:v AS jsonb),'2000-01-01') "
            "ON CONFLICT(key,effective_from) DO NOTHING"), {"k": k, "v": json.dumps(v)})
print("seed ok")
