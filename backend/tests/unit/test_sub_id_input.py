"""P1-6: sub_id do client đưa vào phải ra đúng ≤5 slot [0-9a-z]{0,8}, nếu không thì 400 (không để thành đơn mồ côi)."""
import pytest
from fastapi.testclient import TestClient

from app.core import subid
from app.main_api import create_app
from app.modules.links.affiliate_link import LinkInputError, normalize_sub_id


def test_lowercases_and_pads():
    assert normalize_sub_id("FB01") == "fb01----"
    assert normalize_sub_id("a_b_c") == "a-b-c--"
    assert normalize_sub_id("fb01-1-2-3-4") == "fb01-1-2-3-4"
    assert normalize_sub_id(None) == "0----" and normalize_sub_id("") == "0----"


def test_too_many_slots_raises():
    with pytest.raises(LinkInputError, match="tối đa 5 slot"):
        normalize_sub_id("fb01-camp-2026-11-27-01")


@pytest.mark.parametrize("bad", ["fb@01", "tiếng-việt", "a.b", "x" * 9, "ok-" + "y" * 9])
def test_bad_charset_or_slot_length_raises(bad):
    with pytest.raises(LinkInputError):
        normalize_sub_id(bad)


def test_v1_encoded_sub_id_still_passes_unchanged():
    sid = subid.encode("p", 412, 1, "s" * 32)
    assert normalize_sub_id(sid) == sid


def test_no_pad_mode_still_validates():
    assert normalize_sub_id("a b", pad=False) == "a-b"
    with pytest.raises(LinkInputError):
        normalize_sub_id("a-b-c-d-e-f", pad=False)


def test_api_link_uppercase_sub_is_lowercased(client):
    r = client.post("/api/link", json={"item_id": 1, "shop_id": 2, "sub": "FB01"}).json()
    assert r["ok"] and r["aff_link"].endswith("utm_content=fb01----")


def test_api_link_too_many_slots_is_400_with_message(client):
    r = client.post("/api/link", json={"item_id": 1, "shop_id": 2, "sub": "FB01-camp-2026-11-27-01"})
    assert r.status_code == 400 and r.json()["ok"] is False and "5 slot" in r.json()["error"]


def test_link_input_error_maps_to_400_in_v1_error_format(make_settings):
    from app.main_api import LinkInputError
    app = create_app(make_settings())

    @app.get("/boom")
    def boom():
        raise LinkInputError("sub_id sai")
    r = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_input"
