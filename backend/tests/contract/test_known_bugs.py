"""Tái hiện lỗi trong docs/refactor/01-audit.md. Test mô tả hành vi ĐÚNG và đang xfail(strict) vì code hiện tại
sai; khi sửa (bước 9) strict=True báo XPASS -> phải bỏ dấu xfail.

#1 (link ghi đè nhau) đã được giải quyết theo thiết kế: đường dẫn cũ không còn lưu gì, link AI mới
idempotent theo post_key (xem tests/integration/test_agent_api.py).
"""
import pytest


@pytest.mark.xfail(strict=True, reason="audit #2: limit không phải số làm lỗi 500 thay vì 4xx")
def test_bad_limit_returns_client_error(client):
    assert client.get("/api/search", params={"keyword": "x", "limit": "abc"}).status_code in (400, 422)


@pytest.mark.xfail(strict=True, reason="audit #3: không có xác thực; khi cấu hình API key phải trả 401")
def test_legacy_search_requires_key_when_configured(make_settings):
    from fastapi.testclient import TestClient
    from app.main_api import create_app
    c = TestClient(create_app(make_settings(agent_api_key="k" * 32)))
    assert c.get("/api/search", params={"keyword": "x"}).status_code == 401


@pytest.mark.xfail(strict=True, reason="audit #4: sub_id chứa keyword người dùng, không theo codec v1")
def test_search_sub_id_does_not_embed_keyword(client):
    r = client.get("/api/search", params={"keyword": "noi chien khong dau", "limit": 1}).json()
    assert "noi" not in r["items"][0]["sub_id"]
