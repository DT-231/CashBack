"""Nghiệp vụ. KHÔNG biết HTTP, KHÔNG có SQL. Mở transaction ở đây; gọi module khác qua service công khai của nó."""
from __future__ import annotations

from sqlalchemy import Engine

from app.modules._template import repository
from app.modules._template.errors import ThingNotFound
from app.modules._template.schemas import ThingOut


class ThingService:
    def __init__(self, engine: Engine):
        self.engine = engine

    def get(self, thing_id: int) -> ThingOut:
        with self.engine.connect() as conn:
            row = repository.get(conn, thing_id)
        if row is None:
            raise ThingNotFound(f"không có thing {thing_id}")
        return ThingOut(**row)
