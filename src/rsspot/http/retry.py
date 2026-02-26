"""Retry policy implementation."""

from __future__ import annotations

import asyncio
import random

import httpx

from rsspot.config.models import RetryConfig


class RetryPolicy:
    def __init__(self, config: RetryConfig) -> None:
        self.config = config

    def _delay_for_attempt(self, attempt: int) -> float:
        base = self.config.base_delay * (2 ** max(0, attempt - 1))
        clipped = min(base, self.config.max_delay)
        if self.config.jitter <= 0:
            return clipped

        spread = clipped * self.config.jitter
        return max(0.0, clipped + random.uniform(-spread, spread))

    def should_retry_status(self, status_code: int) -> bool:
        return status_code in self.config.retry_statuses

    def should_retry_exception(self, exc: Exception) -> bool:
        return isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError))

    async def wait(self, attempt: int) -> None:
        await asyncio.sleep(self._delay_for_attempt(attempt))
