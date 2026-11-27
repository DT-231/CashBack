"""Fixture dùng chung. Mọi test chạy MOCK=1, DB tạm, không đọc cookie/.env thật.

Lưu ý: server.py gọi load_env() lúc import (đọc .env nếu có). Fixture `clean_env` xóa
các biến nhạy cảm ngay sau đó để test không bao giờ dùng cookie/proxy thật.
"""
import os
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "packages" / "core"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Phải đặt TRƯỚC khi import server/affiliate lần đầu.
os.environ["MOCK"] = "1"

import affiliate  # noqa: E402,F401
import server  # noqa: E402
import store  # noqa: E402

SENSITIVE = [
    "SHOPEE_COOKIE", "AFF_COOKIE", "SHOPEE_PROXY", "SHOPEE_AF_AC_ENC_DAT", "SHOPEE_UA",
    "FEED_FILE", "SEARCH_ENGINE", "LINK_TEMPLATE", "AFF_CAMPAIGN", "SUB_ID_PAD",
    "IP_SALT", "PW_STATE", "VERBOSE",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in SENSITIVE:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MOCK", "1")
    monkeypatch.setenv("SHOPEE_AFF_ID", "17399999999")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "links.db"))
    store.init()
    return store


@pytest.fixture
def base_url(db, monkeypatch):
    """Server thật trên cổng ngẫu nhiên, DB tạm."""
    monkeypatch.setattr(server, "PUBLIC_BASE", "http://test.local")
    srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=lambda: srv.serve_forever(poll_interval=0.01), daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def feed_file(tmp_path, monkeypatch):
    f = tmp_path / "feed.csv"
    f.write_text(
        "itemid,shopid,product_name,price,commission_rate,sales,product_link\n"
        "900001,7001,Nồi chiên không dầu 6L,690000,8,1200,https://shopee.vn/product/7001/900001\n"
        "900002,7002,Kệ chén inox 2 tầng,159000,6,5100,https://shopee.vn/product/7002/900002\n"
        "900003,7003,Chảo chống dính 28cm,259000,5,2300,https://shopee.vn/product/7003/900003\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FEED_FILE", str(f))
    return f
