"""Global singleton helpers for Spot clients."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from rsspot.client.async_client import AsyncSpotClient
from rsspot.client.sync_client import SpotClient
from rsspot.config import ConfigInput
from rsspot.config.manager import ProfileManager
from rsspot.config.models import SDKConfig


class _GlobalConfig:
    def __init__(self) -> None:
        self.config: ConfigInput | None = None
        self.config_path: str | Path | None = None
        self.state_path: str | Path | None = None


_global_config = _GlobalConfig()
_async_clients: dict[tuple[str | None, str | None, str | None], AsyncSpotClient] = {}
_sync_clients: dict[tuple[str | None, str | None, str | None], SpotClient] = {}

_ctx_profile: ContextVar[str | None] = ContextVar("rsspot_profile", default=None)
_ctx_org: ContextVar[str | None] = ContextVar("rsspot_org", default=None)
_ctx_region: ContextVar[str | None] = ContextVar("rsspot_region", default=None)


def configure(
    config: ConfigInput | None = None,
    *,
    config_path: str | Path | None = None,
    state_path: str | Path | None = None,
) -> None:
    _global_config.config = config
    _global_config.config_path = config_path
    _global_config.state_path = state_path


def _effective(
    profile: str | None,
    org: str | None,
    region: str | None,
) -> tuple[str | None, str | None, str | None]:
    return profile or _ctx_profile.get(), org or _ctx_org.get(), region or _ctx_region.get()


def get_async_client(
    *,
    profile: str | None = None,
    org: str | None = None,
    region: str | None = None,
) -> AsyncSpotClient:
    resolved = _effective(profile, org, region)
    if resolved not in _async_clients:
        _async_clients[resolved] = AsyncSpotClient(
            _global_config.config,
            config_path=_global_config.config_path,
            state_path=_global_config.state_path,
            profile=resolved[0],
            org=resolved[1],
            region=resolved[2],
        )
    return _async_clients[resolved]


def get_client(
    *,
    profile: str | None = None,
    org: str | None = None,
    region: str | None = None,
) -> SpotClient:
    resolved = _effective(profile, org, region)
    if resolved not in _sync_clients:
        _sync_clients[resolved] = SpotClient(
            _global_config.config,
            config_path=_global_config.config_path,
            state_path=_global_config.state_path,
            profile=resolved[0],
            org=resolved[1],
            region=resolved[2],
        )
    return _sync_clients[resolved]


def get_sync_client(
    *,
    profile: str | None = None,
    org: str | None = None,
    region: str | None = None,
) -> SpotClient:
    return get_client(profile=profile, org=org, region=region)


def set_default_profile(name: str) -> None:
    client = get_client()
    client.state.set_preference("default_profile", name)


def set_default_org(name: str) -> None:
    client = get_client()
    client.state.set_preference("default_org", name)


def set_default_region(name: str) -> None:
    client = get_client()
    client.state.set_preference("default_region", name)


@contextmanager
def use_profile(name: str):
    token = _ctx_profile.set(name)
    try:
        yield
    finally:
        _ctx_profile.reset(token)


@contextmanager
def use_org(name: str):
    token = _ctx_org.set(name)
    try:
        yield
    finally:
        _ctx_org.reset(token)


@contextmanager
def use_region(name: str):
    token = _ctx_region.set(name)
    try:
        yield
    finally:
        _ctx_region.reset(token)


async def aclose_all_clients() -> None:
    async_clients = list(_async_clients.values())
    sync_clients = list(_sync_clients.values())
    _async_clients.clear()
    _sync_clients.clear()

    for client in async_clients:
        await client.aclose()
    for client in sync_clients:
        await client.aclose()


def clear_client_cache() -> None:
    _async_clients.clear()
    _sync_clients.clear()


def list_profiles(*, config_file: str | Path | None = None) -> list[str]:
    manager = ProfileManager(config_file)
    return manager.list_profiles()


def set_active_profile(name: str, *, config_file: str | Path | None = None) -> SDKConfig:
    manager = ProfileManager(config_file)
    return manager.set_active_profile(name)
