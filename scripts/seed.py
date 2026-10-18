from __future__ import annotations

import os

from app.config import Settings
from app.db import build_session_factory
from app.services import GuestService


def main() -> None:
    settings = Settings.from_env()
    factory = build_session_factory(settings.database_url)
    with factory() as session:
        service = GuestService(
            session,
            token_secret=settings.token_secret,
            checkin_points=settings.checkin_points,
            bonus_min_points=settings.bonus_min_points,
            bonus_max_points=settings.bonus_max_points,
        )
        guest = service.create_guest(
            os.getenv("SEED_GUEST_NAME", "Demo Guest"),
            os.getenv("SEED_GUEST_CATEGORY", "visitor"),
            int(os.environ["SEED_GUEST_TELEGRAM_ID"]) if os.getenv("SEED_GUEST_TELEGRAM_ID") else None,
        )
        session.commit()
        print(f"Created guest {guest.id}: {guest.name}")
        print(f"Token: {service.issue_guest_token(guest.id)}")


if __name__ == "__main__":
    main()
