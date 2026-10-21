from __future__ import annotations

from collections.abc import Generator
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import build_session_factory
from app.schemas import GuestCardResponse, GuestCreate, GuestResponse
from app.security.authorization import api_key_matches
from app.security.tokens import InvalidToken
from app.services.guests import GuestNotFound, GuestService, GuestTokenMismatch


def build_router(settings: Settings, session_factory=None) -> APIRouter:
    router = APIRouter()
    factory = session_factory or build_session_factory(settings.database_url)

    def session() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
        if not api_key_matches(x_admin_key, settings.admin_api_key):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin key")

    def card_response(card) -> GuestCardResponse:
        return GuestCardResponse(
            id=card.id,
            name=card.name,
            category=card.category,
            telegram_id=card.telegram_id,
            points=card.points,
            checked_in=card.checked_in,
            checked_in_at=card.checked_in_at,
        )

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.post("/admin/guests", response_model=GuestResponse, status_code=status.HTTP_201_CREATED)
    def create_guest(
        payload: GuestCreate,
        _: None = Depends(require_admin),
        db: Session = Depends(session),
    ) -> GuestResponse:
        service = GuestService(
            db,
            token_secret=settings.token_secret,
            checkin_points=settings.checkin_points,
            bonus_min_points=settings.bonus_min_points,
            bonus_max_points=settings.bonus_max_points,
        )
        try:
            guest = service.create_guest(payload.name, payload.category, payload.telegram_id)
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="Guest with this Telegram ID already exists") from exc
        return GuestResponse(
            id=guest.id,
            name=guest.name,
            category=guest.category,
            telegram_id=guest.telegram_id,
            token=service.issue_guest_token(guest.id),
        )

    def get_card(token: str, db: Session) -> GuestCardResponse:
        service = GuestService(
            db,
            token_secret=settings.token_secret,
            checkin_points=settings.checkin_points,
            bonus_min_points=settings.bonus_min_points,
            bonus_max_points=settings.bonus_max_points,
        )
        try:
            card = service.get_card_by_token(token)
        except (InvalidToken, GuestTokenMismatch, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid QR token") from exc
        except GuestNotFound as exc:
            raise HTTPException(status_code=404, detail="Guest not found") from exc
        return card_response(card)

    @router.get("/guests/by-token", response_model=GuestCardResponse)
    def guest_card_by_query(
        token: str = Query(..., min_length=1), db: Session = Depends(session)
    ) -> GuestCardResponse:
        return get_card(token, db)

    @router.get("/guests/{token}", response_model=GuestCardResponse)
    def guest_card_by_path(token: str, db: Session = Depends(session)) -> GuestCardResponse:
        return get_card(token, db)

    return router
