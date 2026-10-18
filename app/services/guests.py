from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
from hmac import compare_digest

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import CheckIn, Guest, PointTransaction
from app.security.tokens import InvalidToken, issue_token, verify_token


class GuestNotFound(LookupError):
    """The requested guest does not exist."""


class GuestTokenMismatch(ValueError):
    """A validly signed token does not match the guest's current nonce."""


class BonusOutOfRange(ValueError):
    """A manual bonus is outside the configured bounds."""


@dataclass(frozen=True, slots=True)
class GuestCard:
    guest_id: str
    name: str
    category: str
    telegram_id: int | None
    points: int
    checked_in: bool
    checked_in_at: datetime | None

    @property
    def id(self) -> str:
        """Compatibility alias for API response models and Telegram handlers."""
        return self.guest_id

    @property
    def total_points(self) -> int:
        return self.points


@dataclass(frozen=True, slots=True)
class CheckInResult:
    card: GuestCard
    idempotent: bool


class GuestService:
    """Use cases for issuing passes and tracking guest points.

    Mutating methods flush their changes but deliberately do not commit the
    caller's session. This keeps check-in and bonus operations composable with
    the API's request transaction and lets callers decide the transaction
    boundary.
    """

    def __init__(
        self,
        session: Session,
        token_secret: str,
        checkin_points: int = 10,
        bonus_min_points: int = 1,
        bonus_max_points: int = 100,
    ) -> None:
        if checkin_points <= 0:
            raise ValueError("checkin_points must be positive")
        if bonus_min_points <= 0 or bonus_min_points > bonus_max_points:
            raise ValueError("bonus bounds are invalid")
        self.session = session
        self.token_secret = token_secret
        self.checkin_points = checkin_points
        self.bonus_min_points = bonus_min_points
        self.bonus_max_points = bonus_max_points

    def create_guest(self, name: str, category: str, telegram_id: int | None = None) -> Guest:
        name = name.strip()
        category = category.strip()
        if not name:
            raise ValueError("name must not be empty")
        if not category:
            raise ValueError("category must not be empty")
        guest = Guest(
            name=name,
            category=category,
            telegram_id=telegram_id,
            token_nonce=secrets.token_urlsafe(32),
        )
        self.session.add(guest)
        self.session.flush()
        return guest

    def get_guest(self, guest_id: str) -> Guest:
        guest = self.session.get(Guest, guest_id)
        if guest is None:
            raise GuestNotFound(guest_id)
        return guest

    def get_guest_by_telegram_id(self, telegram_id: int) -> Guest | None:
        return self.session.scalar(select(Guest).where(Guest.telegram_id == telegram_id))

    def issue_guest_token(self, guest_id: str) -> str:
        guest = self.get_guest(guest_id)
        return issue_token(guest.id, guest.token_nonce, self.token_secret)

    def get_guest_by_token(self, token: str) -> Guest:
        try:
            payload = verify_token(token, self.token_secret)
        except InvalidToken:
            raise
        guest = self.session.get(Guest, payload.guest_id)
        if guest is None:
            raise GuestNotFound(payload.guest_id)
        if not compare_digest(guest.token_nonce, payload.nonce):
            raise GuestTokenMismatch("token nonce does not match")
        return guest

    def get_card_by_token(self, token: str) -> GuestCard:
        return self.get_card_by_guest(self.get_guest_by_token(token))

    def get_card_by_guest_id(self, guest_id: str) -> GuestCard:
        return self.get_card_by_guest(self.get_guest(guest_id))

    def get_card_by_guest(self, guest: Guest) -> GuestCard:
        points = self.session.scalar(
            select(func.coalesce(func.sum(PointTransaction.amount), 0)).where(
                PointTransaction.guest_id == guest.id
            )
        )
        check_in = self.session.scalar(select(CheckIn).where(CheckIn.guest_id == guest.id))
        return GuestCard(
            guest_id=guest.id,
            name=guest.name,
            category=guest.category,
            telegram_id=guest.telegram_id,
            points=int(points or 0),
            checked_in=check_in is not None,
            checked_in_at=check_in.checked_in_at if check_in else None,
        )

    def check_in(self, guest_id: str, organizer_id: int) -> CheckInResult:
        """Record one check-in and its points transaction atomically.

        The unique guest_id constraint on ``check_ins`` is the final guard for
        concurrent requests. A nested transaction allows a concurrent loser to
        recover by returning the already-created check-in as an idempotent
        response while preserving the caller's outer transaction.
        """
        guest = self.get_guest(guest_id)
        try:
            with self.session.begin_nested():
                existing = self.session.scalar(
                    select(CheckIn)
                    .where(CheckIn.guest_id == guest.id)
                    .with_for_update()
                )
                if existing is not None:
                    return CheckInResult(self.get_card_by_guest(guest), True)
                check_in = CheckIn(guest_id=guest.id, organizer_telegram_id=organizer_id)
                self.session.add(check_in)
                self.session.flush()
                self.session.add(
                    PointTransaction(
                        guest_id=guest.id,
                        actor_telegram_id=organizer_id,
                        amount=self.checkin_points,
                        reason="check-in",
                        kind="checkin",
                        checkin_key=str(check_in.id),
                    )
                )
                self.session.flush()
        except IntegrityError:
            # Another transaction won the unique check-in race. The SAVEPOINT
            # rollback leaves the outer session usable.
            existing = self.session.scalar(select(CheckIn).where(CheckIn.guest_id == guest.id))
            if existing is None:
                raise
            return CheckInResult(self.get_card_by_guest(guest), True)
        return CheckInResult(self.get_card_by_guest(guest), False)

    def add_bonus(
        self,
        guest_id: str,
        organizer_id: int,
        amount: int,
        reason: str,
    ) -> PointTransaction:
        if amount < self.bonus_min_points or amount > self.bonus_max_points:
            raise BonusOutOfRange(
                f"bonus must be between {self.bonus_min_points} and {self.bonus_max_points}"
            )
        reason = reason.strip()
        if not reason:
            raise ValueError("reason must not be empty")
        guest = self.get_guest(guest_id)
        transaction = PointTransaction(
            guest_id=guest.id,
            actor_telegram_id=organizer_id,
            amount=amount,
            reason=reason,
            kind="bonus",
        )
        self.session.add(transaction)
        self.session.flush()
        return transaction

