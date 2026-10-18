from __future__ import annotations

import os
from dataclasses import dataclass


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


def _integer(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    bot_token: str
    token_secret: str
    admin_api_key: str
    organizer_telegram_ids: frozenset[int]
    checkin_points: int
    bonus_min_points: int
    bonus_max_points: int

    @classmethod
    def from_env(cls) -> "Settings":
        raw_ids = os.getenv("ORGANIZER_TELEGRAM_IDS", "")
        ids: set[int] = set()
        for item in raw_ids.split(","):
            item = item.strip()
            if item:
                try:
                    ids.add(int(item))
                except ValueError as exc:
                    raise RuntimeError("ORGANIZER_TELEGRAM_IDS must contain integers") from exc

        settings = cls(
            database_url=_required("DATABASE_URL"),
            bot_token=_required("BOT_TOKEN"),
            token_secret=_required("TOKEN_SECRET"),
            admin_api_key=_required("ADMIN_API_KEY"),
            organizer_telegram_ids=frozenset(ids),
            checkin_points=_integer("CHECKIN_POINTS", 10),
            bonus_min_points=_integer("BONUS_MIN_POINTS", 1),
            bonus_max_points=_integer("BONUS_MAX_POINTS", 100),
        )
        if settings.checkin_points <= 0:
            raise RuntimeError("CHECKIN_POINTS must be positive")
        if settings.bonus_min_points <= 0 or settings.bonus_min_points > settings.bonus_max_points:
            raise RuntimeError("BONUS_MIN_POINTS and BONUS_MAX_POINTS are invalid")
        return settings

