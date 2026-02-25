from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from rsspot.client import SpotClient, aclose_all_clients, clear_client_cache, get_client


def _jwt_with_exp(expiry: datetime) -> str:
    header = {"alg": "none", "typ": "JWT"}
    payload = {"exp": int(expiry.timestamp())}

    def encode(value: object) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode("utf-8")).decode("utf-8").rstrip("=")

    return f"{encode(header)}.{encode(payload)}.signature"


@pytest.mark.asyncio
async def test_request_fetches_token_and_calls_api() -> None:
    future_token = _jwt_with_exp(datetime.now(UTC) + timedelta(minutes=5))
    seen: dict[str, int] = {"oauth": 0, "orgs": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            seen["oauth"] += 1
            return httpx.Response(200, json={"id_token": future_token})
        if request.url.path == "/apis/auth.ngpc.rxt.io/v1/organizations":
            seen["orgs"] += 1
            assert request.headers.get("Authorization") == f"Bearer {future_token}"
            return httpx.Response(
                200,
                json={"organizations": [{"name": "songzcorp", "id": "org-gzvcn7fap0t1msep"}]},
            )
        return httpx.Response(404, json={"message": "not found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://spot.rackspace.com",
        transport=transport,
    ) as http_client:
        client = SpotClient(
            refresh_token="refresh-token",
            oauth_url="https://spot.rackspace.com",
            http_client=http_client,
            config_file="/nonexistent.yaml",
            max_retries=0,
        )
        response = await client.organizations.list()
        assert len(response.organizations) == 1
        assert seen["oauth"] == 1
        assert seen["orgs"] == 1


@pytest.mark.asyncio
async def test_request_retries_on_5xx() -> None:
    future_token = _jwt_with_exp(datetime.now(UTC) + timedelta(minutes=5))
    counter = {"regions": 0}

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
        client = SpotClient(
            refresh_token="refresh-token",
            oauth_url="https://spot.rackspace.com",
            http_client=http_client,
            config_file="/nonexistent.yaml",
            max_retries=2,
            retry_backoff_factor=0.001,
        )
        regions = await client.regions.list()
        assert len(regions) == 1
        assert counter["regions"] == 2


@pytest.mark.asyncio
async def test_resolve_org_id_from_name() -> None:
    future_token = _jwt_with_exp(datetime.now(UTC) + timedelta(minutes=5))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"id_token": future_token})
        if request.url.path == "/apis/auth.ngpc.rxt.io/v1/organizations":
            return httpx.Response(
                200,
                json={"organizations": [{"name": "songzcorp", "id": "org-gzvcn7fap0t1msep"}]},
            )
        return httpx.Response(404, json={})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://spot.rackspace.com", transport=transport) as http_client:
        client = SpotClient(
            refresh_token="refresh-token",
            oauth_url="https://spot.rackspace.com",
            http_client=http_client,
            config_file="/nonexistent.yaml",
        )
        org_id = await client.resolve_org_id("songzcorp")
        assert org_id == "org-gzvcn7fap0t1msep"


def test_singleton_client_cache(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("profiles: {}\n", encoding="utf-8")
    c1 = get_client(config_file=cfg, profile="default", singleton=True)
    c2 = get_client(config_file=cfg, profile="default", singleton=True)
    assert c1 is c2
    clear_client_cache()
    c3 = get_client(config_file=cfg, profile="default", singleton=True)
    assert c3 is not c1


@pytest.mark.asyncio
async def test_close_all_clients_clears_registry(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("profiles: {}\n", encoding="utf-8")
    _ = get_client(config_file=cfg, profile="default", singleton=True)
    await aclose_all_clients()
    # Should create a new instance after registry close.
    c_new = get_client(config_file=cfg, profile="default", singleton=True)
    assert c_new is not None
    await aclose_all_clients()
