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
