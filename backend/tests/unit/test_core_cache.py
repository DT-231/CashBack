from app.core.cache import TTLCache


def test_hit_expire_and_disabled():
    t = [0.0]
    c = TTLCache(10, clock=lambda: t[0])
    n = []
    f = lambda: n.append(1) or len(n)  # noqa: E731
    assert c.get_or_set("k", f) == 1 and c.get_or_set("k", f) == 1
    t[0] = 11
    assert c.get_or_set("k", f) == 2
    off = TTLCache(0)
    assert off.get_or_set("k", f) == 3 and off.get_or_set("k", f) == 4


def test_uncacheable_not_stored_and_clear():
    c = TTLCache(10)
    n = []
    f = lambda: n.append(1) or False  # noqa: E731
    c.get_or_set("k", f, cacheable=bool); c.get_or_set("k", f, cacheable=bool)
    assert len(n) == 2
    c.get_or_set("g", lambda: 1); c.clear()
    assert c.get_or_set("g", lambda: 2) == 2
