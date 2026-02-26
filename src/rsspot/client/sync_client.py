"""Unified sync/async Spot client.

Sync methods use plain names.
Async methods use an `a` prefix.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from rsspot.client.async_client import AsyncSpotClient


class _SyncRunner:
    """Persistent sync runner to keep all sync calls on a single event loop."""

    def __init__(self) -> None:
        self._runner = asyncio.Runner()
        self._closed = False

    def run(self, coro: Any) -> Any:
        if self._closed:
            raise RuntimeError("sync client is closed")

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return self._runner.run(coro)

        raise RuntimeError("sync client methods cannot run inside an active event loop")

    def close(self) -> None:
        if self._closed:
            return

        self._runner.close()
        self._closed = True


class _SyncAPIProxy:
    def __init__(self, target: Any, run_sync: Any) -> None:
        self._target = target
        self._run_sync = run_sync

    def __getattr__(self, item: str) -> Any:
        attr = getattr(self._target, item)
        if not callable(attr):
            return attr

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = attr(*args, **kwargs)
            try:
                if hasattr(result, "__aiter__"):

                    async def collect() -> list[Any]:
                        return [entry async for entry in result]

                    return self._run_sync(collect())
                return self._run_sync(result)
            except RuntimeError:
                closer = getattr(result, "close", None)
                if callable(closer):
                    closer()
                raise

        return wrapper


class SpotClient:
    """Unified Spot client exposing both sync and async methods."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._sync_runner = _SyncRunner()
        self._closed = False
        self._async = AsyncSpotClient(*args, **kwargs)

        # Sync grouped API surfaces.
        self.organizations = _SyncAPIProxy(self._async.organizations, self._sync_runner.run)
        self.regions = _SyncAPIProxy(self._async.regions, self._sync_runner.run)
        self.server_classes = _SyncAPIProxy(self._async.server_classes, self._sync_runner.run)
        self.pricing = _SyncAPIProxy(self._async.pricing, self._sync_runner.run)
        self.cloudspaces = _SyncAPIProxy(self._async.cloudspaces, self._sync_runner.run)
        self.spot_nodepools = _SyncAPIProxy(self._async.spot_nodepools, self._sync_runner.run)
        self.ondemand_nodepools = _SyncAPIProxy(self._async.ondemand_nodepools, self._sync_runner.run)
        self.inventory = _SyncAPIProxy(self._async.inventory, self._sync_runner.run)

        # Native async grouped surfaces.
        self.aorganizations = self._async.organizations
        self.aregions = self._async.regions
        self.aserver_classes = self._async.server_classes
        self.apricing = self._async.pricing
        self.acloudspaces = self._async.cloudspaces
        self.aspot_nodepools = self._async.spot_nodepools
        self.aondemand_nodepools = self._async.ondemand_nodepools
        self.ainventory = self._async.inventory

    @property
    def raw(self) -> SpotClient:
        return self

    @property
    def profile_name(self) -> str:
        return self._async.profile_name

    @property
    def state(self):
        return self._async.state

    # Core helpers -------------------------------------------------------------

    def authenticate(self, force_refresh: bool = False) -> str:
        return self._sync_runner.run(self._async.authenticate(force_refresh=force_refresh))

    async def aauthenticate(self, force_refresh: bool = False) -> str:
        return await self._async.authenticate(force_refresh=force_refresh)

    def resolve_org_id(self, org: str | None = None) -> str:
        return self._sync_runner.run(self._async.resolve_org_id(org))

    async def aresolve_org_id(self, org: str | None = None) -> str:
        return await self._async.resolve_org_id(org)

    def resolve_org_name(self, org: str | None = None) -> str:
        return self._sync_runner.run(self._async.resolve_org_name(org))

    async def aresolve_org_name(self, org: str | None = None) -> str:
        return await self._async.resolve_org_name(org)

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int | float | bool] | None = None,
        json_data: dict[str, Any] | None = None,
        content_type: str = "application/json",
        authenticated: bool = True,
    ) -> dict[str, Any]:
        return self._sync_runner.run(
            self._async._request_json(
                method,
                path,
                params=params,
                json_data=json_data,
                content_type=content_type,
                authenticated=authenticated,
            )
        )

    async def arequest_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int | float | bool] | None = None,
        json_data: dict[str, Any] | None = None,
        content_type: str = "application/json",
        authenticated: bool = True,
    ) -> dict[str, Any]:
        return await self._async._request_json(
            method,
            path,
            params=params,
            json_data=json_data,
            content_type=content_type,
            authenticated=authenticated,
        )

    def stream(self, async_iterator: AsyncIterator[dict[str, Any]]) -> list[dict[str, Any]]:

        async def collect() -> list[dict[str, Any]]:
            return [evt async for evt in async_iterator]

        return self._sync_runner.run(collect())

    # Lifecycle ----------------------------------------------------------------

    async def aclose(self) -> None:
        if self._closed:
            return

        await self._async.aclose()
        self._sync_runner.close()
        self._closed = True

    def close(self) -> None:
        if self._closed:
            return

        try:
            self._sync_runner.run(self._async.aclose())
        finally:
            self._sync_runner.close()
            self._closed = True

    async def __aenter__(self) -> SpotClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    def __enter__(self) -> SpotClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
