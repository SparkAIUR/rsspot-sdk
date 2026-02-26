from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx

from rsspot.auth import is_token_expired
from rsspot.config import CacheConfig, ConfigInput, ProfileConfig, RetryConfig, SDKConfig, load_config
from rsspot.constants import DEFAULT_CLIENT_ID
from rsspot.errors import APIError, AuthError, ConfigError, RequestError
from rsspot.http import SpotTransport
from rsspot.services import (
    CloudspacesService,
    InventoryService,
    OnDemandNodePoolsService,
    OrganizationsService,
    PricingService,
    RegionsService,
    ServerClassesService,
    SpotNodePoolsService,
)
from rsspot.settings import RuntimeSettings
from rsspot.state import StateStore, default_state_path

JsonObject = dict[str, Any]
RequestParams = Mapping[str, str | int | float | bool]


def _secret_to_str(value: object) -> str | None:
    if value is None:
        return None
    getter = getattr(value, "get_secret_value", None)
    if callable(getter):
        secret = getter()
        return str(secret) if secret else None
    raw = str(value)
    return raw if raw else None


def _normalize_org_id(value: str) -> str:
    return value.replace("_", "-").lower()


def _retry_from_legacy(max_retries: int | None, retry_backoff_factor: float | None) -> RetryConfig:
    attempts = (max_retries if max_retries is not None else 3) + 1
    base_delay = retry_backoff_factor if retry_backoff_factor is not None else 0.6
    return RetryConfig(max_attempts=attempts, base_delay=base_delay, max_delay=max(2.5, base_delay * 16))


class AsyncSpotClient:
    """Async Rackspace Spot SDK client."""

    def __init__(
        self,
        config: ConfigInput | None = None,
        *,
        config_path: str | Path | None = None,
        profile: str | None = None,
        org: str | None = None,
        org_id: str | None = None,
        region: str | None = None,
        client_id: str | None = None,
        refresh_token: str | None = None,
        access_token: str | None = None,
        base_url: str | None = None,
        oauth_url: str | None = None,
        request_timeout_seconds: float | None = None,
        max_retries: int | None = None,
        retry_backoff_factor: float | None = None,
        verify_ssl: bool | None = None,
        retries: RetryConfig | None = None,
        cache: CacheConfig | None = None,
        state_path: str | Path | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._runtime = RuntimeSettings()
        resolved = load_config(config, config_path=config_path)
        self._resolved_config = resolved
        self.config: SDKConfig = resolved.data

        effective_state = state_path or self.config.state_path
        if effective_state is None:
            effective_state = default_state_path(resolved.path)
        self._state = StateStore(effective_state)

        self._profile_name, resolved_profile = self._resolve_profile(profile=profile)

        self.org = (
            org
            if org is not None
            else (
                self._runtime.org
                or self._state.get_preference("default_org")
                or self.config.preferences.profile_orgs.get(self._profile_name)
                or self.config.preferences.default_org
                or resolved_profile.org
            )
        )
        self.org_id = org_id if org_id is not None else (self._runtime.org_id or resolved_profile.org_id)
        self.region = (
            region
            if region is not None
            else (
                self._runtime.region
                or self._state.get_preference("default_region")
                or self.config.preferences.profile_regions.get(self._profile_name)
                or self.config.preferences.default_region
                or resolved_profile.region
            )
        )

        self.client_id = client_id or self._runtime.client_id or resolved_profile.client_id or DEFAULT_CLIENT_ID
        self.refresh_token = (
            refresh_token
            or _secret_to_str(self._runtime.refresh_token)
            or _secret_to_str(resolved_profile.refresh_token)
        )
        self._id_token = (
            access_token or _secret_to_str(self._runtime.access_token) or _secret_to_str(resolved_profile.access_token)
        )

        self.base_url = base_url or self._runtime.base_url or resolved_profile.base_url
        self.oauth_url = oauth_url or self._runtime.oauth_url or resolved_profile.oauth_url

        self.request_timeout_seconds = (
            request_timeout_seconds
            if request_timeout_seconds is not None
            else (
                self._runtime.request_timeout_seconds
                if self._runtime.request_timeout_seconds is not None
                else resolved_profile.request_timeout_seconds
            )
        )
        self.verify_ssl = (
            verify_ssl
            if verify_ssl is not None
            else (self._runtime.verify_ssl if self._runtime.verify_ssl is not None else resolved_profile.verify_ssl)
        )

        effective_retry = retries
        if effective_retry is None:
            if resolved_profile.retry is not None:
                effective_retry = resolved_profile.retry
            elif max_retries is not None or retry_backoff_factor is not None:
                effective_retry = _retry_from_legacy(max_retries, retry_backoff_factor)
            elif self._runtime.max_retries is not None or self._runtime.retry_backoff_factor is not None:
                effective_retry = _retry_from_legacy(self._runtime.max_retries, self._runtime.retry_backoff_factor)
            else:
                effective_retry = self.config.retry

        effective_cache = cache or resolved_profile.cache or self.config.cache

        self._token_lock = asyncio.Lock()
        self._transport = SpotTransport(
            base_url=self.base_url,
            timeout=self.request_timeout_seconds,
            verify_tls=self.verify_ssl,
            retry_config=effective_retry,
            cache_config=effective_cache,
            state=self._state,
            token_provider=self.authenticate,
            http_client=http_client,
        )

        self._org_cache_by_name: dict[str, str] = {}
        self._org_cache_by_id: dict[str, str] = {}

        self._organizations: OrganizationsService | None = None
        self._regions: RegionsService | None = None
        self._server_classes: ServerClassesService | None = None
        self._pricing: PricingService | None = None
        self._cloudspaces: CloudspacesService | None = None
        self._spot_nodepools: SpotNodePoolsService | None = None
        self._ondemand_nodepools: OnDemandNodePoolsService | None = None
        self._inventory: InventoryService | None = None

    def _resolve_profile(self, *, profile: str | None) -> tuple[str, ProfileConfig]:
        selected = (
            profile
            or self._runtime.profile
            or self._state.get_preference("default_profile")
            or self.config.preferences.default_profile
            or self.config.default_profile
            or self.config.active_profile
            or "default"
        )

        profile_config = self.config.profiles.get(selected)
        if profile_config is None:
            if selected != "default" and (profile is not None or self._runtime.profile is not None):
                raise ConfigError(f"profile '{selected}' not found")
            profile_config = ProfileConfig()

        return selected, profile_config

    @property
    def profile_name(self) -> str:
        return self._profile_name

    @property
    def access_token(self) -> str | None:
        return self._id_token

    @property
    def raw(self) -> AsyncSpotClient:
        return self

    @property
    def state(self) -> StateStore:
        return self._state

    @property
    def organizations(self) -> OrganizationsService:
        if self._organizations is None:
            self._organizations = OrganizationsService(self)
        return self._organizations

    @property
    def regions(self) -> RegionsService:
        if self._regions is None:
            self._regions = RegionsService(self)
        return self._regions

    @property
    def server_classes(self) -> ServerClassesService:
        if self._server_classes is None:
            self._server_classes = ServerClassesService(self)
        return self._server_classes

    @property
    def pricing(self) -> PricingService:
        if self._pricing is None:
            self._pricing = PricingService(self)
        return self._pricing

    @property
    def cloudspaces(self) -> CloudspacesService:
        if self._cloudspaces is None:
            self._cloudspaces = CloudspacesService(self)
        return self._cloudspaces

    @property
    def spot_nodepools(self) -> SpotNodePoolsService:
        if self._spot_nodepools is None:
            self._spot_nodepools = SpotNodePoolsService(self)
        return self._spot_nodepools

    @property
    def ondemand_nodepools(self) -> OnDemandNodePoolsService:
        if self._ondemand_nodepools is None:
            self._ondemand_nodepools = OnDemandNodePoolsService(self)
        return self._ondemand_nodepools

    @property
    def inventory(self) -> InventoryService:
        if self._inventory is None:
            self._inventory = InventoryService(self)
        return self._inventory

    async def __aenter__(self) -> AsyncSpotClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._transport.aclose()
        self._state.close()

    async def authenticate(self, force_refresh: bool = False) -> str:
        """Return a valid Rackspace id_token, refreshing lazily when needed."""

        async with self._token_lock:
            if not force_refresh and self._id_token and not is_token_expired(self._id_token):
                return self._id_token

            if not self.refresh_token:
                raise AuthError("refresh_token is required to authenticate")

            token_url = f"{self.oauth_url.rstrip('/')}/oauth/token"
            payload = {
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "refresh_token": self.refresh_token,
            }
            try:
                decoded = await self._transport.request_json(
                    "POST",
                    token_url,
                    form_data=payload,
                    content_type="application/x-www-form-urlencoded",
                    authenticated=False,
                )
            except (APIError, RequestError) as exc:
                raise AuthError(f"authentication request failed: {exc}") from exc

            token = decoded.get("id_token")
            if not isinstance(token, str) or not token:
                raise AuthError("authentication response missing id_token")

            self._id_token = token
            return token

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: RequestParams | None = None,
        json_data: Mapping[str, Any] | None = None,
        content_type: str = "application/json",
        authenticated: bool = True,
    ) -> JsonObject:
        return await self._transport.request_json(
            method,
            path,
            params=params,
            json_data=json_data,
            content_type=content_type,
            authenticated=authenticated,
        )

    async def resolve_org_id(self, org: str | None = None) -> str:
        """Resolve org selector (name or id) to canonical org id."""

        candidate = org or self.org_id or self.org
        if not candidate:
            raise ConfigError("organization is required")

        if candidate.startswith("org-") or candidate.startswith("org_"):
            normalized = _normalize_org_id(candidate)
            return normalized

        if candidate in self._org_cache_by_name:
            return self._org_cache_by_name[candidate]

        found = await self.organizations.get(candidate)
        resolved = _normalize_org_id(found.id)
        self._org_cache_by_name[found.name] = resolved
        self._org_cache_by_name[candidate] = resolved
        self._org_cache_by_id[resolved] = found.name
        return resolved

    async def resolve_org_name(self, org: str | None = None) -> str:
        """Resolve org selector (name or id) to canonical org name."""

        candidate = org or self.org or self.org_id
        if not candidate:
            raise ConfigError("organization is required")

        if not (candidate.startswith("org-") or candidate.startswith("org_")):
            return candidate

        normalized = _normalize_org_id(candidate)
        cached = self._org_cache_by_id.get(normalized)
        if cached:
            return cached

        found = await self.organizations.get(normalized)
        self._org_cache_by_name[found.name] = _normalize_org_id(found.id)
        self._org_cache_by_id[_normalize_org_id(found.id)] = found.name
        return found.name


@asynccontextmanager
async def connect(*args: Any, **kwargs: Any):
    client = AsyncSpotClient(*args, **kwargs)
    try:
        yield client
    finally:
        await client.aclose()
