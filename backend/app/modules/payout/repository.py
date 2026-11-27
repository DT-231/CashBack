"""SQL của rút tiền và tài khoản ngân hàng. Không ghi ví (đi qua wallet.money)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Connection, text

OPEN = ("requested", "approved", "processing")
_W = ("w.id, w.user_id, w.amount_vnd, w.status, w.bank_account_id, w.provider_ref, w.decided_reason, w.created_at, w.updated_at, "
      "w.approved_by, w.approved_at, w.paid_by, w.paid_at, b.bank_code, b.last4")


def count_active_accounts(conn: Connection, user_id: int) -> int:
    return conn.execute(text("SELECT count(*) FROM bank_accounts WHERE user_id = :u AND deactivated_at IS NULL"), {"u": user_id}).scalar_one()


def insert_account(conn: Connection, user_id: int, bank_code: str, enc: str, key_id: str, last4: str, name: str,
                   usable_from: datetime) -> dict:
    return conn.execute(text(
        "INSERT INTO bank_accounts(user_id, bank_code, account_no_enc, key_id, last4, account_name, usable_from) "
        "VALUES (:u, :b, :e, :k, :l, :n, :f) RETURNING id, bank_code, account_name, last4, usable_from, created_at"),
        {"u": user_id, "b": bank_code, "e": enc, "k": key_id, "l": last4, "n": name, "f": usable_from}).mappings().one()


def list_accounts(conn: Connection, user_id: int):
    return conn.execute(text(
        "SELECT id, bank_code, account_name, last4, usable_from, created_at FROM bank_accounts "
        "WHERE user_id = :u AND deactivated_at IS NULL ORDER BY id"), {"u": user_id}).mappings().all()


def get_account(conn: Connection, user_id: int, account_id: int):
    return conn.execute(text(
        "SELECT id, usable_from FROM bank_accounts WHERE id = :i AND user_id = :u AND deactivated_at IS NULL"),
        {"i": account_id, "u": user_id}).mappings().first()


def get_by_idem(conn: Connection, user_id: int, idem_key: str):
    return conn.execute(text(f"SELECT {_W} FROM withdrawals w LEFT JOIN bank_accounts b ON b.id = w.bank_account_id "
                             "WHERE w.user_id = :u AND w.idem_key = :k"), {"u": user_id, "k": idem_key}).mappings().first()


def has_open(conn: Connection, user_id: int) -> bool:
    return conn.execute(text("SELECT 1 FROM withdrawals WHERE user_id = :u AND status IN ('requested','approved','processing')"),
                        {"u": user_id}).first() is not None


def insert_withdrawal(conn: Connection, user_id: int, amount: int, account_id: int, idem_key: str) -> int:
    return conn.execute(text(
        "INSERT INTO withdrawals(user_id, amount_vnd, bank_account_id, idem_key) VALUES (:u, :a, :b, :k) RETURNING id"),
        {"u": user_id, "a": amount, "b": account_id, "k": idem_key}).scalar_one()


def get_withdrawal(conn: Connection, wid: int):
    return conn.execute(text(f"SELECT {_W} FROM withdrawals w LEFT JOIN bank_accounts b ON b.id = w.bank_account_id "
                             "WHERE w.id = :i"), {"i": wid}).mappings().first()


def list_for_user(conn: Connection, user_id: int, limit: int, offset: int):
    return conn.execute(text(f"SELECT {_W} FROM withdrawals w LEFT JOIN bank_accounts b ON b.id = w.bank_account_id "
                             "WHERE w.user_id = :u ORDER BY w.id DESC LIMIT :l OFFSET :o"),
                        {"u": user_id, "l": limit, "o": offset}).mappings().all()


def list_all(conn: Connection, status: str | None, limit: int, offset: int):
    sql = f"SELECT {_W} FROM withdrawals w LEFT JOIN bank_accounts b ON b.id = w.bank_account_id"
    params: dict = {"l": limit, "o": offset}
    if status:
        sql += " WHERE w.status = :s"
        params["s"] = status
    return conn.execute(text(sql + " ORDER BY w.id DESC LIMIT :l OFFSET :o"), params).mappings().all()


def transition(conn: Connection, wid: int, to: str, from_states: tuple[str, ...], **cols):
    """Đổi trạng thái CÓ ĐIỀU KIỆN trạng thái cũ (một câu UPDATE nguyên tử): hai lần gọi song song chỉ một lần thắng.
    None nếu trạng thái hiện tại không nằm trong `from_states` (hoặc không có yêu cầu)."""
    sets = "".join(f", {k} = :{k}" for k in cols)
    return conn.execute(text(
        f"UPDATE withdrawals SET status = :to, updated_at = now(){sets} WHERE id = :id AND status = ANY(:f) "
        "RETURNING id, user_id, amount_vnd, bank_account_id"),
        {"to": to, "id": wid, "f": list(from_states), **cols}).mappings().first()


def account_cipher(conn: Connection, account_id: int):
    return conn.execute(text("SELECT user_id, bank_code, account_no_enc, key_id, account_name FROM bank_accounts WHERE id = :i"),
                        {"i": account_id}).mappings().first()
