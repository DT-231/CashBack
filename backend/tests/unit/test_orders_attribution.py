import pytest

from app.core import subid
from app.modules.orders.attribution import attribute

SECRET = "s" * 32


def ok(*_):
    return True


def no(*_):
    return False


def test_user_click_is_attributed_and_checked_against_db():
    a = attribute(subid.encode("u", 7, 99, SECRET), SECRET, ok)
    assert (a.source_type, a.user_id, a.click_id, a.orphan_reason) == ("user", 7, 99, None)
    assert attribute(subid.encode("u", 7, 99, SECRET), SECRET, no).orphan_reason == "click_not_found"


def test_user_link_level_has_no_click():
    a = attribute(subid.encode("l", 7, 3, SECRET), SECRET, ok)
    assert (a.source_type, a.user_id, a.click_id) == ("user", 7, None)
    assert attribute(subid.encode("l", 7, 3, SECRET), SECRET, no).orphan_reason == "link_not_found"


def test_post_source():
    a = attribute(subid.encode("p", 412, 1, SECRET), SECRET, ok)
    assert (a.source_type, a.post_id, a.user_id) == ("post", 412, None)
    assert attribute(subid.encode("p", 412, 1, SECRET), SECRET, no).orphan_reason == "post_not_found"


@pytest.mark.parametrize("utm,reason", [("", "no_sub_id"), ("----", "no_sub_id"), ("fb01-1---", "legacy_sub_id")])
def test_unattributable_inputs_become_orphans(utm, reason):
    a = attribute(utm, SECRET, ok)
    assert a.orphan_reason == reason and a.user_id is None and a.post_id is None


def test_forged_or_foreign_signature_is_orphan_never_a_user():
    s = subid.encode("u", 7, 99, SECRET)
    forged = s.replace("-7-", "-8-")
    a = attribute(forged, SECRET, ok)
    assert a.source_type == "unknown" and a.user_id is None and a.orphan_reason.startswith("invalid_sub_id")
    assert attribute(s, "z" * 32, ok).user_id is None


def test_other_source_goes_to_admin():
    a = attribute(subid.encode("x", 0, 5, SECRET), SECRET, ok)
    assert a.orphan_reason == "other_source" and a.user_id is None


# ---------- T-018: đổi SUBID_SECRET mà link đã phát hành vẫn quy được về user ----------
OLD, NEW, OLDER = "o" * 32, "n" * 32, "d" * 32


def test_link_signed_with_a_previous_key_is_still_attributed():
    old_link = subid.encode("l", 7, 3, OLD)
    a = attribute(old_link, [NEW, OLD], ok)
    assert (a.source_type, a.user_id, a.orphan_reason) == ("user", 7, None)
    assert attribute(old_link, [NEW, OLDER, OLD], ok).user_id == 7              # khóa cũ nào cũng được
    assert attribute(old_link, NEW, ok).orphan_reason.startswith("invalid_sub_id")   # không khai báo khóa cũ: mồ côi (hành vi cũ)
    assert attribute(subid.encode("u", 7, 99, NEW), [NEW, OLD], ok).click_id == 99  # link mới (khóa hiện hành) vẫn đúng


def test_previous_key_still_requires_ownership_check():
    old_link = subid.encode("l", 7, 3, OLD)
    assert attribute(old_link, [NEW, OLD], no).orphan_reason == "link_not_found"   # chữ ký đúng nhưng link không thuộc user: mồ côi


def test_unknown_signature_is_rejected_with_any_number_of_keys():
    forged = subid.encode("l", 7, 3, "x" * 32)
    assert attribute(forged, [NEW, OLD, OLDER], ok).orphan_reason.startswith("invalid_sub_id")


def test_extra_keys_raise_false_match_rate_only_by_about_n_over_46656():
    """Ước lượng thực nghiệm: chữ ký ngẫu nhiên khớp ít nhất một trong 3 khóa với xác suất ~3/46656 (~6.4e-5), không hơn nhiều."""
    import random
    rng, keys, hits, n = random.Random(1), [NEW, OLD, OLDER], 0, 60000
    for _ in range(n):
        sig = "".join(rng.choice(subid.ALPHABET) for _ in range(3))
        hits += subid.decode(f"1l-7-3-{sig}-", keys).status == "ok"
    assert hits <= 12                                                           # kỳ vọng ~3.9; 12 là ngưỡng rất rộng
