from __future__ import annotations

from typing import Any


class ServiceBase:
    """Base type for service classes bound to a SpotClient instance."""

    def __init__(self, client: Any) -> None:
        self._client = client
