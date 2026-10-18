from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass


class InvalidToken(ValueError):
    """Raised when a QR token is malformed or has an invalid signature."""


@dataclass(frozen=True, slots=True)
class TokenPayload:
    guest_id: str
    nonce: str
    version: int


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise InvalidToken("invalid base64 payload") from exc


def issue_token(guest_id: str, nonce: str, secret: str) -> str:
    payload = json.dumps({"v": 1, "guest_id": guest_id, "nonce": nonce}, separators=(",", ":"), sort_keys=True).encode()
    encoded_payload = _encode(payload)
    signature = hmac.new(secret.encode(), encoded_payload.encode(), hashlib.sha256).digest()
    return f"qr1.{encoded_payload}.{_encode(signature)}"


def verify_token(token: str, secret: str) -> TokenPayload:
    parts = token.strip().split(".")
    if len(parts) != 3 or parts[0] != "qr1":
        raise InvalidToken("invalid token format")
    _, encoded_payload, encoded_signature = parts
    expected = hmac.new(secret.encode(), encoded_payload.encode(), hashlib.sha256).digest()
    received = _decode(encoded_signature)
    if not hmac.compare_digest(expected, received):
        raise InvalidToken("invalid token signature")
    try:
        data = json.loads(_decode(encoded_payload))
        version = int(data["v"])
        guest_id = str(data["guest_id"])
        nonce = str(data["nonce"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise InvalidToken("invalid token payload") from exc
    if version != 1 or not guest_id or not nonce:
        raise InvalidToken("unsupported token payload")
    return TokenPayload(guest_id=guest_id, nonce=nonce, version=version)

