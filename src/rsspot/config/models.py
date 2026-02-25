from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, SecretStr, model_validator

from rsspot.constants import (
    DEFAULT_BASE_URL,
    DEFAULT_CLIENT_ID,
    DEFAULT_CONFIG_FILE,
    DEFAULT_OAUTH_URL,
)


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
    max_retries: int = Field(default=3, validation_alias=AliasChoices("max_retries", "maxRetries"))
    retry_backoff_factor: float = Field(
        default=0.6,
        validation_alias=AliasChoices("retry_backoff_factor", "retryBackoffFactor"),
    )
    verify_ssl: bool = Field(default=True, validation_alias=AliasChoices("verify_ssl", "verifySsl"))


class SDKConfig(BaseModel):
    """Root configuration model with profile-aware and legacy-compatible shape."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    active_profile: str | None = Field(
        default=None,
        validation_alias=AliasChoices("active_profile", "activeProfile"),
    )
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)

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
            "active_profile": active,
            "profiles": {
                "default": default_profile,
            },
        }


class ConfigPaths(BaseModel):
    """Resolved filesystem paths for runtime configuration."""

    model_config = ConfigDict(extra="forbid")

    config_file: Path = Path(DEFAULT_CONFIG_FILE).expanduser()
