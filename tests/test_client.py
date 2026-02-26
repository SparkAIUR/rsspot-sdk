from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from rsspot.client import (
    AsyncSpotClient,
    SpotClient,
    aclose_all_clients,
    clear_client_cache,
    configure,
    get_client,
)
from rsspot.config import RetryConfig


def _jwt_with_exp(expiry: datetime) -> str:
    header = {"alg": "none", "typ": "JWT"}
    payload = {"exp": int(expiry.timestamp())}

    def encode(value: object) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode("utf-8")).decode("utf-8").rstrip("=")

    return f"{encode(header)}.{encode(payload)}.signature"


def _config(url: str = "https://spot.rackspace.com") -> dict[str, object]:
    return {
        "default_profile": "default",
        "profiles": {
            "default": {
                "base_url": url,
                "oauth_url": url,
            }
        },
    }


@pytest.mark.asyncio
async def test_async_request_fetches_token_and_calls_api(tmp_path: Path) -> None:
    future_token = _jwt_with_exp(datetime.now(UTC) + timedelta(minutes=5))
    seen: dict[str, int] = {"oauth": 0, "orgs": 0}
    state_path = tmp_path / "state.db"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            seen["oauth"] += 1
            return httpx.Response(200, json={"id_token": future_token})
        if request.url.path == "/apis/auth.ngpc.rxt.io/v1/organizations":
            seen["orgs"] += 1
            assert request.headers.get("Authorization") == f"Bearer {future_token}"
            return httpx.Response(
                200,
                json={"organizations": [{"name": "sparkai", "id": "org-gzvcn7fap0t1msep"}]},
            )
        return httpx.Response(404, json={"message": "not found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://spot.rackspace.com", transport=transport) as http_client:
        client = AsyncSpotClient(
            config=_config(),
            refresh_token="refresh-token",
            state_path=state_path,
            http_client=http_client,
        )
        response = await client.organizations.list()
        assert len(response.organizations) == 1
        assert seen["oauth"] == 1
        assert seen["orgs"] == 1
        await client.aclose()


@pytest.mark.asyncio
async def test_async_request_retries_on_5xx(tmp_path: Path) -> None:
    future_token = _jwt_with_exp(datetime.now(UTC) + timedelta(minutes=5))
    counter = {"regions": 0}
    state_path = tmp_path / "state.db"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"id_token": future_token})
        if request.url.path == "/apis/ngpc.rxt.io/v1/regions":
            counter["regions"] += 1
            if counter["regions"] == 1:
                return httpx.Response(500, json={"message": "boom"})
            return httpx.Response(
                200,
                json={"items": [{"metadata": {"name": "us-central-dfw-1"}, "spec": {"description": "dfw"}}]},
            )
        return httpx.Response(404, json={})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://spot.rackspace.com", transport=transport) as http_client:
        client = AsyncSpotClient(
            config=_config(),
            refresh_token="refresh-token",
            retries=RetryConfig(max_attempts=2, base_delay=0.0, max_delay=0.0, jitter=0.0),
            state_path=state_path,
            http_client=http_client,
        )
        regions = await client.regions.list()
        assert len(regions) == 1
        assert counter["regions"] == 2
        await client.aclose()


def test_unified_sync_client_method(tmp_path: Path) -> None:
    future_token = _jwt_with_exp(datetime.now(UTC) + timedelta(minutes=5))
    state_path = tmp_path / "state.db"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"id_token": future_token})
        if request.url.path == "/apis/auth.ngpc.rxt.io/v1/organizations":
            return httpx.Response(200, json={"organizations": [{"name": "sparkai", "id": "org-1"}]})
        return httpx.Response(404, json={})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(base_url="https://spot.rackspace.com", transport=transport)
    try:
        client = SpotClient(
            config=_config(),
            refresh_token="refresh-token",
            state_path=state_path,
            http_client=http_client,
        )
        payload = client.organizations.list()
        assert payload.organizations[0].name == "sparkai"
        client.close()
    finally:
        import asyncio

        asyncio.run(http_client.aclose())


@pytest.mark.asyncio
async def test_unified_sync_methods_fail_inside_event_loop(tmp_path: Path) -> None:
    future_token = _jwt_with_exp(datetime.now(UTC) + timedelta(minutes=5))
    state_path = tmp_path / "state.db"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"id_token": future_token})
        if request.url.path == "/apis/auth.ngpc.rxt.io/v1/organizations":
            return httpx.Response(200, json={"organizations": [{"name": "sparkai", "id": "org-1"}]})
        return httpx.Response(404, json={})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://spot.rackspace.com", transport=transport) as http_client:
        client = SpotClient(
            config=_config(),
            refresh_token="refresh-token",
            state_path=state_path,
            http_client=http_client,
        )
        with pytest.raises(RuntimeError, match="active event loop"):
            _ = client.organizations.list()
        await client.aclose()


def test_singleton_client_cache(tmp_path: Path) -> None:
    state_path = tmp_path / "state.db"
    configure(config=_config(), state_path=state_path)
    c1 = get_client(profile="default")
    c2 = get_client(profile="default")
    assert c1 is c2
    clear_client_cache()
    c3 = get_client(profile="default")
    assert c3 is not c1


@pytest.mark.asyncio
async def test_close_all_clients_clears_registry(tmp_path: Path) -> None:
    state_path = tmp_path / "state.db"
    configure(config=_config(), state_path=state_path)
    _ = get_client(profile="default")
    await aclose_all_clients()
    c_new = get_client(profile="default")
    assert c_new is not None
    await aclose_all_clients()
