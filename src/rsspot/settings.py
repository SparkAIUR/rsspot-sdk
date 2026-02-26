from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from rsspot.constants import (
    DEFAULT_BASE_URL,
    DEFAULT_CLIENT_ID,
    DEFAULT_CONFIG_FILE,
    DEFAULT_OAUTH_URL,
)


class RuntimeSettings(BaseSettings):
    """Environment-driven runtime overrides for client/profile resolution."""

    model_config = SettingsConfigDict(
        env_prefix="RSSPOT_",
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
    )

    config_file: Path = Field(
        default=Path(DEFAULT_CONFIG_FILE).expanduser(),
        validation_alias=AliasChoices("RSSPOT_CONFIG", "RSSPOT_CONFIG_FILE", "SPOT_CONFIG_FILE"),
    )
    profile: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RSSPOT_PROFILE", "SPOT_PROFILE"),
    )

    org: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RSSPOT_ORG", "RACKSPACE_ORG", "SPOT_ORG"),
    )
    org_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "RSSPOT_ORG_ID",
            "RSSPOT_ORGID",
            "RACKSPACE_ORG_ID",
            "SPOT_ORG_ID",
        ),
    )
    region: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RSSPOT_REGION", "RACKSPACE_REGION", "SPOT_REGION"),
    )

    client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RSSPOT_CLIENT_ID", "RACKSPACE_CLIENT_ID", "RXTSPOT_CLIENT_ID"),
    )
    refresh_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "RSSPOT_REFRESH_TOKEN",
            "RACKSPACE_REFRESH_TOKEN",
            "SPOT_REFRESH_TOKEN",
        ),
    )
    access_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("RSSPOT_ACCESS_TOKEN", "RACKSPACE_ACCESS_TOKEN", "SPOT_ACCESS_TOKEN"),
    )

    base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RSSPOT_BASE_URL", "RACKSPACE_BASE_URL", "SPOT_BASE_URL"),
    )
    oauth_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RSSPOT_OAUTH_URL", "RACKSPACE_OAUTH_URL", "SPOT_AUTH_URL"),
    )

    request_timeout_seconds: float | None = Field(
        default=None,
        validation_alias=AliasChoices("RSSPOT_REQUEST_TIMEOUT_SECONDS", "SPOT_REQUEST_TIMEOUT"),
    )
    max_retries: int | None = Field(
        default=None,
        validation_alias=AliasChoices("RSSPOT_MAX_RETRIES", "SPOT_MAX_RETRIES"),
    )
    retry_backoff_factor: float | None = Field(
        default=None,
        validation_alias=AliasChoices("RSSPOT_RETRY_BACKOFF_FACTOR", "SPOT_RETRY_BACKOFF_FACTOR"),
    )
    verify_ssl: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("RSSPOT_VERIFY_SSL", "SPOT_VERIFY_SSL"),
    )

    @property
    def fallback_base_url(self) -> str:
        return self.base_url or DEFAULT_BASE_URL

    @property
    def fallback_oauth_url(self) -> str:
        return self.oauth_url or DEFAULT_OAUTH_URL

    @property
    def fallback_client_id(self) -> str:
        return self.client_id or DEFAULT_CLIENT_ID
