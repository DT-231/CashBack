"""HTTP: nhận request, validate, gọi service, trả response. Không có nghiệp vụ, không import repository."""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.modules._template.schemas import ThingOut
from app.modules._template.service import ThingService

router = APIRouter(prefix="/api/v1/things", tags=["things"])


@router.get("/{thing_id}", response_model=ThingOut)
def get_thing(thing_id: int, request: Request):
    return ThingService(request.app.state.get_engine()).get(thing_id)
