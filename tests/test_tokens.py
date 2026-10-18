from __future__ import annotations

import json

import pytest

from app.security.tokens import InvalidToken, issue_token, verify_token


def test_token_round_trip() -> None:
    token = issue_token("guest-1", "nonce-1", "secret")
    payload = verify_token(token, "secret")
    assert payload.guest_id == "guest-1"
    assert payload.nonce == "nonce-1"
    assert payload.version == 1


@pytest.mark.parametrize("secret", ["wrong", ""])
def test_token_rejects_wrong_secret(secret: str) -> None:
    token = issue_token("guest-1", "nonce-1", "secret")
    with pytest.raises(InvalidToken):
        verify_token(token, secret)


def test_token_rejects_tampered_payload_and_signature() -> None:
    token = issue_token("guest-1", "nonce-1", "secret")
    parts = token.split(".")
    parts[1] = parts[1][:-1] + ("A" if parts[1][-1] != "A" else "B")
    with pytest.raises(InvalidToken):
        verify_token(".".join(parts), "secret")

    parts = token.split(".")
    parts[2] = parts[2][:-1] + ("A" if parts[2][-1] != "A" else "B")
    with pytest.raises(InvalidToken):
        verify_token(".".join(parts), "secret")


def test_token_rejects_malformed_payload() -> None:
    # Correct HMAC over a payload that is not the required JSON shape.
    from app.security.tokens import _encode
    import hashlib
    import hmac

    encoded = _encode(json.dumps({"v": 2}).encode())
    signature = _encode(hmac.new(b"secret", encoded.encode(), hashlib.sha256).digest())
    with pytest.raises(InvalidToken):
        verify_token(f"qr1.{encoded}.{signature}", "secret")
