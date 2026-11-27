from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.modules.auth.api import current_user
from app.modules.auth.schemas import UserOut
from app.modules.links.schemas import CreateLinkRequest, LinkOut, UserLinkOut
from app.modules.links.service import UserLinkService

router = APIRouter(prefix="/api/v1", tags=["links"])


def _service(request: Request) -> UserLinkService:
    return UserLinkService(request.app.state.settings, request.app.state.get_engine())


@router.post("/links", response_model=LinkOut)
def create_link(body: CreateLinkRequest, request: Request, user: UserOut = Depends(current_user)):
    return _service(request).create(user.id, body.url)


@router.get("/me/links", response_model=list[UserLinkOut])
def my_links(request: Request, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
             user: UserOut = Depends(current_user)):
    return _service(request).list_for_user(user.id, limit, offset)
