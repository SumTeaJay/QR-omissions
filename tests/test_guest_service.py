from __future__ import annotations

import pytest

from app.models import PointTransaction
from app.services.guests import (
    BonusOutOfRange,
    GuestService,
    GuestTokenMismatch,
)


def service(session) -> GuestService:
    return GuestService(
        session,
        token_secret="secret",
        checkin_points=10,
        bonus_min_points=2,
        bonus_max_points=50,
    )


def test_create_guest_issue_and_validate_token(session) -> None:
    guests = service(session)
    guest = guests.create_guest(" Ada ", " Speaker ", 1001)
    token = guests.issue_guest_token(guest.id)

    card = guests.get_card_by_token(token)
    assert card.guest_id == guest.id
    assert card.name == "Ada"
    assert card.category == "Speaker"
    assert card.points == 0
    assert card.checked_in is False

    guest.token_nonce = "rotated"
    with pytest.raises(GuestTokenMismatch):
        guests.get_card_by_token(token)


def test_check_in_is_one_time_and_awards_points(session) -> None:
    guests = service(session)
    guest = guests.create_guest("Ada", "Speaker")

    first = guests.check_in(guest.id, organizer_id=9001)
    second = guests.check_in(guest.id, organizer_id=9002)
    assert first.idempotent is False
    assert second.idempotent is True
    assert first.card.checked_in is True
    assert second.card.points == 10
    assert session.query(PointTransaction).count() == 1


def test_bonus_is_recorded_and_included_in_card(session) -> None:
    guests = service(session)
    guest = guests.create_guest("Ada", "Speaker")
    transaction = guests.add_bonus(guest.id, 9001, 7, "Best talk")

    assert transaction.kind == "bonus"
    assert transaction.amount == 7
    assert guests.get_card_by_guest_id(guest.id).points == 7


@pytest.mark.parametrize("amount", [1, 51])
def test_bonus_range_is_validated(session, amount: int) -> None:
    guests = service(session)
    guest = guests.create_guest("Ada", "Speaker")
    with pytest.raises(BonusOutOfRange):
        guests.add_bonus(guest.id, 9001, amount, "Out of range")

