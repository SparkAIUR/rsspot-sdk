from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta


def decode_jwt_expiry(token: str) -> datetime | None:
    """Decode JWT `exp` claim without verifying the signature.

    Example:
        >>> decode_jwt_expiry("eyJ...token") is None
        True
    """

    if not token:
        return None

    parts = token.split(".")
    if len(parts) != 3:
        return None

    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload + padding)
        claims = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    exp = claims.get("exp")
    if not isinstance(exp, (int, float)):
        return None

    return datetime.fromtimestamp(float(exp), tz=UTC)


def is_token_expired(token: str, *, skew_seconds: int = 60) -> bool:
    """Return True when a JWT should be treated as expired."""

    expiry = decode_jwt_expiry(token)
    if expiry is None:
        return True
    return datetime.now(UTC) >= (expiry - timedelta(seconds=skew_seconds))
