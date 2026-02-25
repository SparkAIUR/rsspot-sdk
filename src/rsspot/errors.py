from __future__ import annotations

from dataclasses import dataclass


class RSSpotError(Exception):
    """Base error type for the rsspot SDK."""


class ConfigError(RSSpotError):
    """Raised when configuration cannot be loaded or validated."""


class AuthError(RSSpotError):
    """Raised when authentication or token refresh fails."""


class RequestError(RSSpotError):
    """Raised when an HTTP request fails after retries."""


@dataclass(slots=True)
class APIError(RequestError):
    """Represents a non-success Rackspace Spot API response."""

    status_code: int
    message: str
    body: str | None = None

    def __str__(self) -> str:
        if self.body:
            return f"HTTP {self.status_code}: {self.message} ({self.body})"
        return f"HTTP {self.status_code}: {self.message}"
