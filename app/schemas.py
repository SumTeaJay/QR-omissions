from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GuestCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    telegram_id: int | None = Field(default=None, gt=0)


class GuestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    category: str
    telegram_id: int | None = None
    token: str


class GuestCardResponse(BaseModel):
    id: str
    name: str
    category: str
    telegram_id: int | None = None
    points: int
    checked_in: bool
    checked_in_at: datetime | None = None


class ErrorResponse(BaseModel):
    detail: str
