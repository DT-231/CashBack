"""T-065: /api/v1/admin/health (admin + TOTP): DB, đồng bộ, cookie Shopee, sao lưu; không lộ đường dẫn/DSN/bí mật."""
import os
import time
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.main_api import create_app
from app.modules.adminstats.health import backup_status, build_health
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
PW = "mat-khau-hop-le-1"


@pytest.fixture
def pg():
    eng = create_engine(DB_URL)
    with eng.connect() as c:
        last_run = c.execute(text("SELECT coalesce(max(id), 0) FROM sync_runs")).scalar_one()
        sess = c.execute(text("SELECT id, cookie_enc, key_id, status, failure_count FROM shopee_sessions")).all()
    yield eng
    with eng.begin() as c:
        c.execute(text("DELETE FROM sync_runs WHERE id > :i"), {"i": last_run})
        c.execute(text("DELETE FROM shopee_sessions"))
        for r in sess:
            c.execute(text("INSERT INTO shopee_sessions(id, cookie_enc, key_id, status, failure_count) VALUES (:i, :c, :k, :s, :f)"),
                      {"i": r[0], "c": r[1], "k": r[2], "s": r[3], "f": r[4]})
        users = "(SELECT id FROM users WHERE email LIKE 'itest-%@example.test')"
        c.execute(text(f"DELETE FROM refresh_tokens WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM users WHERE email LIKE 'itest-%@example.test'"))
    eng.dispose()


@pytest.fixture
def settings(make_settings, tmp_path):
    return make_settings(database_url=DB_URL, jwt_secret="j" * 40, ip_salt="i" * 24, admin_mfa_required=False, backup_dir=str(tmp_path / "bk"))


def client(settings, pg):
    return TestClient(create_app(settings, engine=pg), raise_server_exceptions=False)


def user(api, pg, role):
    email = f"itest-{uuid.uuid4().hex[:8]}@example.test"
    uid = api.post("/api/v1/auth/register", json={"email": email, "password": PW}).json()["id"]
    with pg.begin() as c:
        c.execute(text("UPDATE users SET role = :r WHERE id = :i"), {"r": role, "i": uid})
    return {"Authorization": "Bearer " + api.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()["access_token"]}


def sync_run(pg, result, hours_ago):
    with pg.begin() as c:
        c.execute(text("INSERT INTO sync_runs(kind, started_at, finished_at, result) VALUES ('orders', now() - make_interval(hours => :h), "
                       "now() - make_interval(hours => :h), :r)"), {"h": hours_ago, "r": result})


def backup_file(settings, age_hours):
    d = os.path.expanduser(settings.backup_dir)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"backup-{uuid.uuid4().hex[:6]}.dump.enc")
    open(p, "wb").write(b"x")
    t = time.time() - age_hours * 3600
    os.utime(p, (t, t))


def test_admin_only(settings, pg):
    api = client(settings, pg)
    for role, code in (("member", 403), ("staff", 403)):
        assert api.get("/api/v1/admin/health", headers=user(api, pg, role)).status_code == code
    assert api.get("/api/v1/admin/health").status_code == 401
    assert api.get("/api/v1/admin/health", headers=user(api, pg, "admin")).status_code == 200


def test_components_and_overall(settings, pg):
    api = client(settings, pg)
    ah = user(api, pg, "admin")
    sync_run(pg, "ok", 1)
    backup_file(settings, 2)
    with pg.begin() as c:
        c.execute(text("DELETE FROM shopee_sessions"))
        c.execute(text("INSERT INTO shopee_sessions(id, cookie_enc, key_id, status, failure_count, last_ok_at) VALUES (1, 'x', 'k1', 'healthy', 0, now())"))
    h = api.get("/api/v1/admin/health", headers=ah).json()
    assert h["db"]["status"] == "ok" and h["db"]["ms"] >= 0
    assert h["sync"]["status"] == "ok" and h["sync"]["result"] == "ok" and h["sync"]["age_hours"] <= 1.1
    assert h["shopee_session"] == {"status": "ok", "failure_count": 0, "has_cookie": True}
    assert h["backup"]["status"] == "ok" and h["backup"]["count"] == 1 and h["backup"]["latest_age_hours"] <= 2.1
    assert h["overall"] == "ok" and h["warnings"] == []
    sync_run(pg, "failed", 0)
    h = api.get("/api/v1/admin/health", headers=ah).json()
    assert h["sync"]["status"] == "warn" and h["sync"]["result"] == "failed" and h["overall"] == "warn"


def test_each_session_status_maps_and_blocked_is_down(settings, pg):
    now = datetime.now(UTC)
    expect = {"healthy": "ok", "unknown": "unknown", "degraded": "warn", "blocked": "down", "expired": "down"}
    for status, want in expect.items():
        with pg.begin() as c:
            c.execute(text("DELETE FROM shopee_sessions"))
            c.execute(text("INSERT INTO shopee_sessions(id, cookie_enc, key_id, status) VALUES (1, 'x', 'k1', :s)"), {"s": status})
        assert build_health(settings, pg, now)["shopee_session"]["status"] == want, status
    with pg.begin() as c:
        c.execute(text("DELETE FROM shopee_sessions"))
    assert build_health(settings, pg, now)["shopee_session"]["status"] == "not_configured"
    with pg.begin() as c:
        c.execute(text("INSERT INTO shopee_sessions(id, cookie_enc, key_id, status) VALUES (1, 'x', 'k1', 'blocked')"))
    assert build_health(settings, pg, now)["overall"] == "down"


def test_sync_age_and_unknown(settings, pg):
    now = datetime.now(UTC)
    with pg.connect() as c:
        had = c.execute(text("SELECT count(*) FROM sync_runs WHERE finished_at IS NOT NULL")).scalar_one()
    if had == 0:
        assert build_health(settings, pg, now)["sync"] == {"status": "unknown"}
    sync_run(pg, "ok", 30)                                                              # ok nhưng quá SYNC_MAX_AGE_HOURS (24)
    s = build_health(settings, pg, now)["sync"]
    assert s["status"] == "warn" and s["age_hours"] >= 29


def test_backup_states(settings):
    now = datetime.now(UTC)
    assert backup_status(settings.model_copy(update={"backup_dir": ""}), now) == {"status": "not_configured"}
    assert backup_status(settings, now) == {"status": "down", "count": 0}               # thư mục chưa có / rỗng
    backup_file(settings, 40)
    b = backup_status(settings, now)
    assert b["status"] == "warn" and b["count"] == 1 and b["latest_age_hours"] >= 39    # quá 36 giờ
    backup_file(settings, 1)
    b = backup_status(settings, now)
    assert b["status"] == "ok" and b["count"] == 2 and b["latest_age_hours"] <= 1.1     # xét bản MỚI NHẤT, không phải cũ nhất
    open(os.path.join(settings.backup_dir, "not-a-backup.txt"), "w").write("x")
    assert backup_status(settings, now)["count"] == 2


def test_db_down_still_answers_without_leaking_the_dsn(settings):
    bad = create_engine("postgresql+psycopg://leaky_user:leaky_pass@127.0.0.1:1/leaky_db", connect_args={"connect_timeout": 1})
    h = build_health(settings, bad)
    assert h["overall"] == "down" and h["db"] == {"status": "down"}
    blob = str(h)
    for leak in ("leaky_user", "leaky_pass", "leaky_db", settings.backup_dir):
        assert leak not in blob


def test_response_never_contains_paths_or_secrets(settings, pg):
    api = client(settings, pg)
    ah = user(api, pg, "admin")
    backup_file(settings, 1)
    text_ = api.get("/api/v1/admin/health", headers=ah).text
    for leak in (settings.backup_dir, "backup-", ".dump.enc", "cookie_enc", "postgresql", "cashback_dev"):
        assert leak not in text_, leak


def test_warnings_from_startup_checks_degrade_overall(make_settings, pg, tmp_path):
    s = make_settings(database_url=DB_URL, bff_enabled=True, backup_dir=str(tmp_path / "bk"))        # BFF bật mà thiếu BFF_SHARED_SECRET
    backup_file(s, 1)
    h = build_health(s, pg)
    assert h["warnings"] and h["overall"] in ("warn", "down")
    assert (build_health(s.model_copy(update={"bff_enabled": False}), pg)["warnings"]) == []


def test_backup_not_configured_alone_makes_overall_warn(make_settings, pg):
    s = make_settings(database_url=DB_URL, backup_dir="")
    sync_run(pg, "ok", 1)
    with pg.begin() as c:
        c.execute(text("DELETE FROM shopee_sessions"))
        c.execute(text("INSERT INTO shopee_sessions(id, cookie_enc, key_id, status) VALUES (1, 'x', 'k1', 'healthy')"))
    h = build_health(s, pg)
    assert (h["db"]["status"], h["sync"]["status"], h["shopee_session"]["status"], h["backup"]["status"]) == ("ok", "ok", "ok", "not_configured")
    assert h["overall"] == "warn"
