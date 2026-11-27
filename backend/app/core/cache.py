"""Cache TTL trong bộ nhớ, an toàn đa luồng. ttl <= 0 = tắt cache."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any


class TTLCache:
    def __init__(self, ttl: float, clock: Callable[[], float] = time.monotonic, max_entries: int = 512):
        self.ttl, self._clock, self.max_entries = ttl, clock, max_entries
        self._data: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_or_set(self, key, factory: Callable[[], Any], cacheable: Callable[[Any], bool] = lambda v: True):
        """Trả giá trị còn hạn; nếu không thì gọi factory. Kết quả không `cacheable` (vd lỗi) không được nhớ."""
        if self.ttl <= 0:
            return factory()
        now = self._clock()
        with self._lock:
            hit = self._data.get(key)
            if hit and hit[0] > now:
                return hit[1]
        value = factory()
        if cacheable(value):
            with self._lock:
                now = self._clock()
                if len(self._data) >= self.max_entries:   # bỏ mục hết hạn, rồi mục cũ nhất nếu vẫn đầy
                    self._data = {k: v for k, v in self._data.items() if v[0] > now}
                    while len(self._data) >= self.max_entries:
                        self._data.pop(next(iter(self._data)))
                self._data[key] = (now + self.ttl, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
