"""Test schema trên Postgres thật. Cần DB đã migrate + seed: `make db-up` rồi `make test-db`.
Tự bỏ qua (skip) nếu không kết nối được Postgres.
"""
import os
import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from tests.integration.pg import DB_URL, pg_available  # noqa: E402

engine = create_engine(DB_URL)


def uid(c, email="member1@example.test"):
    return c.execute(text("SELECT id FROM users WHERE email=:e"), {"e": email}).scalar_one()


@unittest.skipUnless(pg_available(), "không có Postgres (make db-up)")
class SchemaTests(unittest.TestCase):
    def test_seed(self):
        with engine.connect() as c:
            roles = dict(c.execute(text("SELECT role, count(*) FROM users GROUP BY role")).all())
            self.assertEqual(roles, {"admin": 1, "member": 2})
            self.assertEqual(c.execute(text("SELECT count(*) FROM wallets")).scalar_one(), 3)

    def test_wallet_cannot_go_negative(self):
        with engine.connect() as c:
            with self.assertRaises(IntegrityError):
                c.execute(text("UPDATE wallets SET available_vnd=-1 WHERE user_id=:u"), {"u": uid(c)})
            c.rollback()

    def test_ledger_is_append_only_and_idempotent(self):
        with engine.connect() as c:
            u = uid(c)
            c.execute(text("DELETE FROM wallet_entries WHERE FALSE"))  # no-op, trigger FOR EACH ROW
            ins = ("INSERT INTO wallet_entries(user_id,kind,state,amount_vnd,share_bp,idem_key) "
                   "VALUES(:u,'accrual','pending',24225,6000,:k)")
            k = "test:" + os.urandom(4).hex()
            c.execute(text(ins), {"u": u, "k": k})
            with self.assertRaises(IntegrityError):  # idem_key trùng
                c.execute(text(ins), {"u": u, "k": k})
            c.rollback()
            c.execute(text(ins), {"u": u, "k": k})
            with self.assertRaises(DBAPIError):  # cấm UPDATE
                c.execute(text("UPDATE wallet_entries SET amount_vnd=1 WHERE idem_key=:k"), {"k": k})
            c.rollback()
            c.execute(text(ins), {"u": u, "k": k})
            with self.assertRaises(DBAPIError):  # cấm DELETE
                c.execute(text("DELETE FROM wallet_entries WHERE idem_key=:k"), {"k": k})
            c.rollback()

    def test_only_one_open_withdrawal(self):
        with engine.connect() as c:
            u = uid(c, "member2@example.test")
            q = "INSERT INTO withdrawals(user_id,amount_vnd) VALUES(:u,100000)"
            c.execute(text(q), {"u": u})
            with self.assertRaises(IntegrityError):
                c.execute(text(q), {"u": u})
            c.rollback()

    def test_link_code_unique_and_email_lowercase(self):
        with engine.connect() as c:
            with self.assertRaises(IntegrityError):
                c.execute(text("INSERT INTO users(email,password_hash) VALUES('A@B.C','x')"))
            c.rollback()


if __name__ == "__main__":
    unittest.main()
