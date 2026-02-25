from __future__ import annotations

from pathlib import Path

from rsspot.config.loader import dump_config, load_config
from rsspot.config.models import ProfileConfig, SDKConfig
from rsspot.constants import DEFAULT_CONFIG_FILE
from rsspot.errors import ConfigError


class ProfileManager:
    """Manage multi-account SDK profiles persisted to file.

    Example:
        >>> mgr = ProfileManager()
        >>> _ = mgr.list_profiles()
    """

    def __init__(self, config_file: str | Path | None = None) -> None:
        raw = Path(config_file or DEFAULT_CONFIG_FILE).expanduser()
        self._path = raw

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> SDKConfig:
        return load_config(self._path)

    def save(self, config: SDKConfig) -> None:
        dump_config(config, self._path)

    def list_profiles(self) -> list[str]:
        cfg = self.load()
        return sorted(cfg.profiles.keys())

    def get_profile(self, name: str | None = None) -> ProfileConfig:
        cfg = self.load()
        profile_name = name or cfg.active_profile or "default"
        profile = cfg.profiles.get(profile_name)
        if profile is None:
            raise ConfigError(
                f"profile '{profile_name}' not found in {self._path}; run 'rsspot configure --profile {profile_name}'"
            )
        return profile

    def upsert_profile(self, name: str, profile: ProfileConfig, *, activate: bool = False) -> SDKConfig:
        cfg = self.load()
        cfg.profiles[name] = profile
        if activate or not cfg.active_profile:
            cfg.active_profile = name
        self.save(cfg)
        return cfg

    def set_active_profile(self, name: str) -> SDKConfig:
        cfg = self.load()
        if name not in cfg.profiles:
            raise ConfigError(f"profile '{name}' not found in {self._path}")
        cfg.active_profile = name
        self.save(cfg)
        return cfg

    def delete_profile(self, name: str) -> SDKConfig:
        cfg = self.load()
        if name not in cfg.profiles:
            raise ConfigError(f"profile '{name}' not found in {self._path}")
        del cfg.profiles[name]
        if cfg.active_profile == name:
            cfg.active_profile = next(iter(cfg.profiles), None)
        self.save(cfg)
        return cfg
