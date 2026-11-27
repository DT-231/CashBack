"""SQL của ví. CHỈ module này được ghi `wallets` và `wallet_entries` (test_architecture ép luật này)."""
from __future__ import annotations

from sqlalchemy import Connection, text


def ensure_wallet(conn: Connection, user_id: int) -> None:
    conn.execute(text("INSERT INTO wallets(user_id) VALUES (:u) ON CONFLICT DO NOTHING"), {"u": user_id})


def lock_wallet(conn: Connection, user_id: int):
    """Khóa dòng ví cho tới hết transaction: mọi thay đổi số dư của một user được xếp hàng."""
    return conn.execute(text("SELECT pending_vnd, available_vnd, held_vnd FROM wallets WHERE user_id = :u FOR UPDATE"),
                        {"u": user_id}).mappings().one()


def get_wallet(conn: Connection, user_id: int):
    return conn.execute(text("SELECT pending_vnd, available_vnd, held_vnd FROM wallets WHERE user_id = :u"),
                        {"u": user_id}).mappings().first()


def insert_entry(conn: Connection, user_id: int, kind: str, state: str, amount: int, idem_key: str,
                 order_id: int | None, withdrawal_id: int | None, share_bp: int | None) -> int | None:
    """None nếu `idem_key` đã tồn tại (bút toán trùng): caller KHÔNG được đổi số dư."""
    return conn.execute(text(
        "INSERT INTO wallet_entries(user_id, order_id, withdrawal_id, kind, state, amount_vnd, share_bp, idem_key) "
        "VALUES (:u, :o, :w, :k, :s, :a, :sh, :i) ON CONFLICT (idem_key) DO NOTHING RETURNING id"),
        {"u": user_id, "o": order_id, "w": withdrawal_id, "k": kind, "s": state, "a": amount, "sh": share_bp,
         "i": idem_key}).scalar_one_or_none()


def apply_delta(conn: Connection, user_id: int, d_pending: int, d_available: int, d_held: int) -> None:
    conn.execute(text("UPDATE wallets SET pending_vnd = pending_vnd + :p, available_vnd = available_vnd + :a, "
                      "held_vnd = held_vnd + :h WHERE user_id = :u"),
                 {"p": d_pending, "a": d_available, "h": d_held, "u": user_id})


def order_totals(conn: Connection, order_id: int) -> dict[str, int]:
    """Tổng số tiền theo loại bút toán của một đơn: {'accrual': .., 'cancel': .., 'release': .., 'reverse': .., 'adjust': ..}."""
    rows = conn.execute(text("SELECT kind, sum(amount_vnd) AS total FROM wallet_entries WHERE order_id = :o GROUP BY kind"),
                        {"o": order_id}).all()
    return {k: int(t) for k, t in rows}


def count_for_order(conn: Connection, order_id: int) -> int:
    return conn.execute(text("SELECT count(*) FROM wallet_entries WHERE order_id = :o"), {"o": order_id}).scalar_one()


def first_accrual_share(conn: Connection, order_id: int) -> int | None:
    return conn.execute(text("SELECT share_bp FROM wallet_entries WHERE order_id = :o AND kind = 'accrual' "
                             "ORDER BY id LIMIT 1"), {"o": order_id}).scalar_one_or_none()


def list_entries(conn: Connection, user_id: int, limit: int, offset: int):
    return conn.execute(text("SELECT id, kind, state, amount_vnd, order_id, withdrawal_id, created_at "
                             "FROM wallet_entries WHERE user_id = :u ORDER BY id DESC LIMIT :l OFFSET :o"),
                        {"u": user_id, "l": limit, "o": offset}).mappings().all()
