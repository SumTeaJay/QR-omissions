from app.security.authorization import api_key_matches, is_organizer


def test_organizer_whitelist_and_api_key_comparison() -> None:
    allowed = frozenset({9001, 9002})
    assert is_organizer(9001, allowed)
    assert not is_organizer(42, allowed)
    assert api_key_matches("admin-key", "admin-key")
    assert not api_key_matches("wrong", "admin-key")
    assert not api_key_matches(None, "admin-key")
