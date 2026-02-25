from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from threading import Lock
from typing import Any

import httpx

from rsspot.auth import is_token_expired
from rsspot.config.manager import ProfileManager
from rsspot.config.models import ProfileConfig, SDKConfig
from rsspot.constants import DEFAULT_CLIENT_ID
from rsspot.errors import APIError, AuthError, ConfigError, RequestError
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


class SpotClient:
    """Async Rackspace Spot SDK client.

    Example:
        >>> import asyncio
        >>> from rsspot.client import SpotClient
        >>> async def demo() -> None:
        ...     async with SpotClient(profile="default") as client:
        ...         _ = await client.regions.list()
        >>> asyncio.run(demo())
    """

    def __init__(
        self,
        *,
        profile: str | None = None,
        config_file: str | Path | None = None,
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
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._runtime = RuntimeSettings()
        self._profile_name, resolved_profile, resolved_config_file = self._resolve_profile(
            profile=profile,
            config_file=config_file,
        )
        self._config_file = resolved_config_file

        self.org = org if org is not None else (self._runtime.org or resolved_profile.org)
        self.org_id = org_id if org_id is not None else (self._runtime.org_id or resolved_profile.org_id)
        self.region = region if region is not None else (self._runtime.region or resolved_profile.region)

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
        self.max_retries = (
            max_retries
            if max_retries is not None
            else (self._runtime.max_retries if self._runtime.max_retries is not None else resolved_profile.max_retries)
        )
        self.retry_backoff_factor = (
            retry_backoff_factor
            if retry_backoff_factor is not None
            else (
                self._runtime.retry_backoff_factor
                if self._runtime.retry_backoff_factor is not None
                else resolved_profile.retry_backoff_factor
            )
        )
        self.verify_ssl = (
            verify_ssl
            if verify_ssl is not None
            else (self._runtime.verify_ssl if self._runtime.verify_ssl is not None else resolved_profile.verify_ssl)
        )

        self._owns_http_client = http_client is None
        timeout = httpx.Timeout(self.request_timeout_seconds)
        self._http = http_client or httpx.AsyncClient(
            base_url=self.base_url.rstrip("/"),
            timeout=timeout,
            verify=self.verify_ssl,
            follow_redirects=True,
        )

        self._token_lock = asyncio.Lock()
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

    @property
    def profile_name(self) -> str:
        return self._profile_name

    @property
    def config_file(self) -> Path:
        return self._config_file

    @property
    def access_token(self) -> str | None:
        return self._id_token

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

    async def __aenter__(self) -> SpotClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._http.aclose()

    async def authenticate(self, *, force_refresh: bool = False) -> str:
        """Return a valid Rackspace id_token, refreshing lazily when needed.

        Example:
            >>> import asyncio
            >>> from rsspot.client import SpotClient
            >>> async def auth() -> None:
            ...     client = SpotClient(refresh_token="token")
            ...     try:
            ...         _ = await client.authenticate()
            ...     finally:
            ...         await client.aclose()
            >>> # asyncio.run(auth())
        """

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
                response = await self._http.request(
                    "POST",
                    token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            except httpx.HTTPError as exc:
                raise AuthError(f"authentication request failed: {exc}") from exc

            if response.status_code != 200:
                raise AuthError(f"authentication failed with status {response.status_code}: {response.text.strip()}")

            try:
                decoded = response.json()
            except ValueError as exc:
                raise AuthError("authentication response was not valid JSON") from exc

            if not isinstance(decoded, dict):
                raise AuthError("authentication response had unexpected JSON shape")

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
        """Execute a Spot API request and decode a JSON object response."""

        attempts = max(1, self.max_retries + 1)
        force_refresh = False
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            headers: dict[str, str] = {}
            if content_type:
                headers["Content-Type"] = content_type
            if authenticated:
                token = await self.authenticate(force_refresh=force_refresh)
                headers["Authorization"] = f"Bearer {token}"
                force_refresh = False

            try:
                response = await self._http.request(
                    method.upper(),
                    path,
                    params=params,
                    json=json_data,
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= attempts:
                    raise RequestError(f"request failed after retries: {exc}") from exc
                await self._sleep_backoff(attempt)
                continue

            # One forced refresh attempt when token is stale/revoked.
            if authenticated and response.status_code in {401, 403} and attempt < attempts:
                force_refresh = True
                continue

            if response.status_code == 429 or response.status_code >= 500:
                last_error = APIError(
                    status_code=response.status_code,
                    message="transient upstream error",
                    body=response.text.strip() or None,
                )
                if attempt >= attempts:
                    raise last_error
                await self._sleep_backoff(attempt)
                continue

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

            return decoded

        if last_error is not None:
            raise RequestError(str(last_error)) from last_error
        raise RequestError("request failed without a captured error")

    async def _sleep_backoff(self, attempt: int) -> None:
        await asyncio.sleep(self.retry_backoff_factor * (2 ** (attempt - 1)))

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

    def _resolve_profile(
        self,
        *,
        profile: str | None,
        config_file: str | Path | None,
    ) -> tuple[str, ProfileConfig, Path]:
        file_path = Path(config_file).expanduser() if config_file else self._runtime.config_file.expanduser()
        manager = ProfileManager(file_path)
        cfg = manager.load()
        selected = profile or self._runtime.profile or cfg.active_profile or "default"

        profile_config = cfg.profiles.get(selected)
        if profile_config is None:
            if selected != "default" and (profile is not None or self._runtime.profile is not None):
                raise ConfigError(f"profile '{selected}' not found in {file_path}")
            profile_config = ProfileConfig()

        return selected, profile_config, file_path


_CLIENTS: dict[tuple[str, str], SpotClient] = {}
_CLIENTS_LOCK = Lock()


def get_client(
    *,
    profile: str | None = None,
    config_file: str | Path | None = None,
    singleton: bool = True,
    **kwargs: Any,
) -> SpotClient:
    """Return a SpotClient instance.

    By default this returns a process-level singleton per `(config_file, profile)`.
    Set `singleton=False` to force a fresh client instance.
    """

    if not singleton:
        return SpotClient(profile=profile, config_file=config_file, **kwargs)

    config_key = str(Path(config_file).expanduser()) if config_file else "<runtime>"
    profile_key = profile or "<runtime>"
    key = (config_key, profile_key)

    with _CLIENTS_LOCK:
        existing = _CLIENTS.get(key)
        if existing is not None:
            return existing
        created = SpotClient(profile=profile, config_file=config_file, **kwargs)
        _CLIENTS[key] = created
        return created


async def aclose_all_clients() -> None:
    """Close and clear all cached singleton clients."""

    with _CLIENTS_LOCK:
        clients = list(_CLIENTS.values())
        _CLIENTS.clear()

    for client in clients:
        await client.aclose()


def clear_client_cache() -> None:
    """Clear singleton cache without closing connections."""

    with _CLIENTS_LOCK:
        _CLIENTS.clear()


def list_profiles(*, config_file: str | Path | None = None) -> list[str]:
    manager = ProfileManager(config_file)
    return manager.list_profiles()


def set_active_profile(name: str, *, config_file: str | Path | None = None) -> SDKConfig:
    manager = ProfileManager(config_file)
    return manager.set_active_profile(name)
