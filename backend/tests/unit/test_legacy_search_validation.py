"""P2-10: /api/search cũ validate đầu vào; lỗi trả {"ok": false, "error": ...} như format cũ."""
import pytest


def bad(client, **params):
    r = client.get("/api/search", params=params)
    assert r.status_code == 400, (params, r.text)
    j = r.json()
    assert j["ok"] is False and isinstance(j["error"], str) and j["error"]
    return j["error"]


def test_keyword_too_long(client):
    assert "200" in bad(client, keyword="a" * 201)
    assert client.get("/api/search", params={"keyword": "a" * 200, "limit": 1}).status_code == 200


@pytest.mark.parametrize("kw", ["abc\r\nX-Evil: 1", "abc\ndef", "abc\rdef"])
def test_keyword_with_newline_rejected(client, kw):
    assert "xuống dòng" in bad(client, keyword=kw)


def test_keyword_blank_still_rejected(client):
    assert "thiếu keyword" in bad(client, keyword="   ")


def test_sort_must_be_known(client):
    assert "sort" in bad(client, keyword="x", sort="price")
    for ok in ("relevancy", "sales"):
        assert client.get("/api/search", params={"keyword": "x", "sort": ok, "limit": 1}).status_code == 200


def test_engine_must_be_known(client):
    assert "engine" in bad(client, keyword="x", engine="google")
    assert client.get("/api/search", params={"keyword": "x", "engine": "API", "limit": 1}).status_code == 200


def test_sub_is_validated_with_its_index(client):
    assert "5 slot" in bad(client, keyword="x", sub="fb01-camp-2026-11-27")      # +"-<i>" thành 6 slot
    assert "[0-9a-z]" in bad(client, keyword="x", sub="fb@01")
    assert client.get("/api/search", params={"keyword": "x", "sub": "FB01", "limit": 1}).status_code == 200


def test_limit_is_clamped_not_rejected(client):
    assert client.get("/api/search", params={"keyword": "x", "limit": 0}).json()["count"] == 1
    assert client.get("/api/search", params={"keyword": "x", "limit": 9999}).json()["count"] == 5   # chỉ có 5 mock
    assert client.get("/api/search", params={"keyword": "x", "limit": -3}).json()["count"] == 1
