"""HTTP transport for Spot API calls."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

from rsspot.config.models import CacheConfig, RetryConfig
from rsspot.errors import APIError, RequestError
from rsspot.http.cache import CacheController
from rsspot.http.retry import RetryPolicy
from rsspot.state import StateStore

TokenProvider = Callable[[bool], Awaitable[str]]


class SpotTransport:
    """Async transport handling retries, caching, and authenticated requests."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float,
        verify_tls: bool,
        retry_config: RetryConfig,
        cache_config: CacheConfig,
        state: StateStore,
        token_provider: TokenProvider,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.retry = RetryPolicy(retry_config)
        self.cache = CacheController(cache_config, state)
        self._token_provider = token_provider
        self._owns_http_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout),
            verify=verify_tls,
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._client.aclose()

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int | float | bool] | None = None,
        json_data: Mapping[str, Any] | None = None,
        form_data: Mapping[str, Any] | None = None,
        content_type: str = "application/json",
        authenticated: bool = True,
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        method_upper = method.upper()
        attempts = max(1, self.retry.config.max_attempts)
        force_refresh = False

        params_dict = dict(params) if params else None
        json_dict = dict(json_data) if json_data else None

        cache_decision = self.cache.decision(method_upper, path)
        cache_key: str | None = None
        if cache_decision.enabled and authenticated and form_data is None:
            cache_key = self.cache.cache_key(method_upper, path, params_dict, json_dict)
            hit = self.cache.get(cache_key)
            if hit is not None:
                return hit

        for attempt in range(1, attempts + 1):
            headers: dict[str, str] = {}
            if content_type:
                headers["Content-Type"] = content_type
            if extra_headers:
                headers.update(extra_headers)
            if authenticated:
                token = await self._token_provider(force_refresh)
                headers["Authorization"] = f"Bearer {token}"
                force_refresh = False

            try:
                response = await self._client.request(
                    method_upper,
                    path,
                    params=params,
                    json=json_data,
                    data=form_data,
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                if self.retry.should_retry_exception(exc) and attempt < attempts:
                    await self.retry.wait(attempt)
                    continue
                raise RequestError(f"request failed after retries: {exc}") from exc

            if authenticated and response.status_code in {401, 403} and attempt < attempts:
                force_refresh = True
                continue

            if response.status_code == 429 or response.status_code >= 500:
                if self.retry.should_retry_status(response.status_code) and attempt < attempts:
                    await self.retry.wait(attempt)
                    continue
                raise APIError(
                    status_code=response.status_code,
                    message="transient upstream error",
                    body=response.text.strip() or None,
                )

            if response.status_code >= 400:
                raise APIError(
                    status_code=response.status_code,
                    message="request failed",
                    body=response.text.strip() or None,
                )

            if response.status_code == 204 or not response.text.strip():
                return {}

            try:
                decoded = response.json()
            except ValueError as exc:
                raise RequestError("response was not valid JSON") from exc

            if not isinstance(decoded, dict):
                raise RequestError("response payload must be a JSON object")

            if cache_key is not None and cache_decision.enabled:
                self.cache.set(cache_key, decoded, cache_decision.ttl)

            if method_upper != "GET":
                self.cache.invalidate_after_mutation(path)

            return decoded

        raise RequestError("request failed without a captured error")
