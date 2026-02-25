from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

from rsspot.auth import decode_jwt_expiry, is_token_expired


def _jwt_with_exp(expiry: datetime) -> str:
    header = {"alg": "none", "typ": "JWT"}
    payload = {"exp": int(expiry.timestamp())}

    def encode(value: object) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode("utf-8")).decode("utf-8").rstrip("=")

    return f"{encode(header)}.{encode(payload)}.signature"


def test_decode_jwt_expiry() -> None:
    expiry = datetime.now(UTC) + timedelta(minutes=5)
    token = _jwt_with_exp(expiry)
    decoded = decode_jwt_expiry(token)
    assert decoded is not None
    assert abs((decoded - expiry).total_seconds()) < 2


def test_is_token_expired_true_for_past_token() -> None:
    token = _jwt_with_exp(datetime.now(UTC) - timedelta(minutes=1))
    assert is_token_expired(token)


def test_is_token_expired_false_for_future_token() -> None:
    token = _jwt_with_exp(datetime.now(UTC) + timedelta(minutes=10))
    assert not is_token_expired(token)
