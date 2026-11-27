"""Kiểu dữ liệu vào/ra của module (Pydantic). Không chứa logic."""
from pydantic import BaseModel, Field


class ThingIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ThingOut(BaseModel):
    id: int
    name: str
