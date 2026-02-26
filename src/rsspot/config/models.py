from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, SecretStr, model_validator

from rsspot.constants import (
    DEFAULT_BASE_URL,
    DEFAULT_CLIENT_ID,
    DEFAULT_CONFIG_FILE,
    DEFAULT_OAUTH_URL,
)


class RetryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = 4
    base_delay: float = 0.2
    max_delay: float = 2.5
    jitter: float = 0.2
    retry_statuses: list[int] = Field(default_factory=lambda: [429, 500, 502, 503, 504])


class CacheConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    ttl_defaults: dict[str, float] = Field(
        default_factory=lambda: {
            "GET:/apis/auth.ngpc.rxt.io/v1/organizations": 10.0,
            "GET:/apis/ngpc.rxt.io/v1/regions": 20.0,
            "GET:/apis/ngpc.rxt.io/v1/namespaces/*": 5.0,
            "GET:/apis/metrics.ngpc.rxt.io/v1/events/organizations": 5.0,
        }
    )
    default_ttl: float = 5.0
    max_entries: int = 1000
    backend: Literal["sqlite", "memory"] = "sqlite"


class ProfileConfig(BaseModel):
    """Resolved profile configuration used for API requests."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    org: str | None = Field(default=None, validation_alias=AliasChoices("org", "organization"))
    org_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("org_id", "orgId", "organization_id", "organizationId"),
    )
    region: str | None = Field(default=None, validation_alias=AliasChoices("region", "default_region"))
    client_id: str = Field(
        default=DEFAULT_CLIENT_ID,
        validation_alias=AliasChoices("client_id", "clientId"),
    )
    refresh_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("refresh_token", "refreshToken"),
    )
    access_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("access_token", "accessToken"),
    )
    base_url: str = Field(default=DEFAULT_BASE_URL, validation_alias=AliasChoices("base_url", "baseUrl"))
    oauth_url: str = Field(
        default=DEFAULT_OAUTH_URL,
        validation_alias=AliasChoices("oauth_url", "oauthUrl", "auth_url", "authUrl"),
    )
    request_timeout_seconds: float = Field(
        default=30.0,
        validation_alias=AliasChoices("request_timeout_seconds", "requestTimeoutSeconds"),
    )
    verify_ssl: bool = Field(default=True, validation_alias=AliasChoices("verify_ssl", "verifySsl"))

    # Legacy retry knobs preserved for backwards compatibility.
    max_retries: int = Field(default=3, validation_alias=AliasChoices("max_retries", "maxRetries"))
    retry_backoff_factor: float = Field(
        default=0.6,
        validation_alias=AliasChoices("retry_backoff_factor", "retryBackoffFactor"),
    )

    # V2 structured knobs.
    retry: RetryConfig | None = None
    cache: CacheConfig | None = None


class Preferences(BaseModel):
    model_config = ConfigDict(extra="allow")

    default_profile: str | None = None
    default_org: str | None = None
    default_region: str | None = None
    profile_orgs: dict[str, str] = Field(default_factory=dict)
    profile_regions: dict[str, str] = Field(default_factory=dict)


class SDKConfig(BaseModel):
    """Root configuration model with profile-aware and legacy-compatible shape."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    version: str = "2"
    default_profile: str | None = None
    active_profile: str | None = Field(
        default=None,
        validation_alias=AliasChoices("active_profile", "activeProfile"),
    )
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)
    preferences: Preferences = Field(default_factory=Preferences)

    retry: RetryConfig = Field(default_factory=RetryConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    state_path: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_schema(cls, data: object) -> object:
        if not isinstance(data, Mapping):
            return data

        data_dict = dict(data)
        profiles = data_dict.get("profiles")
        if isinstance(profiles, Mapping):
            if "active_profile" not in data_dict and "activeProfile" in data_dict:
                data_dict["active_profile"] = data_dict.get("activeProfile")
            return data_dict

        legacy_keys = {
            "org",
            "organization",
            "orgId",
            "org_id",
            "region",
            "client_id",
            "clientId",
            "refreshToken",
            "refresh_token",
            "accessToken",
            "access_token",
            "base_url",
            "baseUrl",
            "oauth_url",
            "oauthUrl",
            "auth_url",
            "authUrl",
            "requestTimeoutSeconds",
            "request_timeout_seconds",
            "maxRetries",
            "max_retries",
            "retryBackoffFactor",
            "retry_backoff_factor",
            "verifySsl",
            "verify_ssl",
        }
        if not any(key in data_dict for key in legacy_keys):
            return data_dict

        default_profile = {key: value for key, value in data_dict.items() if key in legacy_keys}
        active = data_dict.get("active_profile") or data_dict.get("activeProfile") or "default"
        return {
            "version": "1",
            "active_profile": active,
            "default_profile": active,
            "profiles": {
                "default": default_profile,
            },
        }


class ResolvedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    path: Path | None = None
    data: SDKConfig


class ConfigPaths(BaseModel):
    """Resolved filesystem paths for runtime configuration."""

    model_config = ConfigDict(extra="forbid")

    config_file: Path = Path(DEFAULT_CONFIG_FILE).expanduser()


ConfigInput = SDKConfig | dict[str, Any]
