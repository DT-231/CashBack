"""Tái hiện lỗi #1–#4 trong docs/refactor/01-audit.md.

Mỗi test mô tả hành vi ĐÚNG và đang xfail(strict) vì code hiện tại sai. Khi sửa lỗi ở bước 9,
strict=True sẽ làm test báo XPASS -> phải bỏ dấu xfail (nhắc không quên).
"""
import pytest
import requests


@pytest.mark.xfail(strict=True, reason="audit #1: sub_id mặc định 'api' làm link sau ghi đè link trước")
def test_links_without_sub_do_not_overwrite_each_other(base_url):
    a = requests.post(base_url + "/api/link", json={"url": "https://shopee.vn/product/1/1"}, timeout=10).json()
    b = requests.post(base_url + "/api/link", json={"url": "https://shopee.vn/product/2/2"}, timeout=10).json()
    assert a["click_url"] != b["click_url"]


@pytest.mark.xfail(strict=True, raises=requests.exceptions.ConnectionError,
                   reason="audit #2: limit không phải số làm đứt kết nối thay vì trả 4xx")
def test_bad_limit_returns_client_error(base_url):
    r = requests.get(base_url + "/api/search", params={"keyword": "x", "limit": "abc"}, timeout=10)
    assert r.status_code in (400, 422)


@pytest.mark.xfail(strict=True, reason="audit #3: không có xác thực; khi cấu hình API key phải trả 401")
def test_stats_requires_key_when_configured(base_url, monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "k" * 32)   # tên biến tạm; chốt ở bước 9
    assert requests.get(base_url + "/api/stats", timeout=10).status_code == 401


@pytest.mark.xfail(strict=True, reason="audit #4: sub_id chứa keyword người dùng, không theo codec v1")
def test_search_sub_id_does_not_embed_keyword(base_url):
    r = requests.get(base_url + "/api/search", params={"keyword": "noi chien khong dau", "limit": 1},
                     timeout=10).json()
    assert "noi" not in r["items"][0]["sub_id"]
