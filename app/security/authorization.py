from hmac import compare_digest


def is_organizer(telegram_id: int, organizer_ids: frozenset[int]) -> bool:
    return telegram_id in organizer_ids


def api_key_matches(provided: str | None, expected: str) -> bool:
    return bool(provided) and compare_digest(provided, expected)

