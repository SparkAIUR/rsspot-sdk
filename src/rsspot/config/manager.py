from __future__ import annotations

from pathlib import Path

from rsspot.config.loader import default_config_candidates, load_config, save_config
from rsspot.config.models import ProfileConfig, SDKConfig
from rsspot.errors import ConfigError


class ProfileManager:
    """Manage multi-account SDK profiles persisted to file."""

    def __init__(self, config_file: str | Path | None = None) -> None:
        self._explicit = config_file is not None
        raw = Path(config_file).expanduser() if config_file else default_config_candidates()[0].expanduser()
        self._path = raw

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> SDKConfig:
        if self._explicit:
            resolved = load_config(config_path=self._path)
        else:
            resolved = load_config()
            if resolved.path is not None:
                self._path = resolved.path
        return resolved.data

    def save(self, config: SDKConfig) -> None:
        self._path = save_config(config, path=self._path)

    def list_profiles(self) -> list[str]:
        cfg = self.load()
        return sorted(cfg.profiles.keys())

    def get_profile(self, name: str | None = None) -> ProfileConfig:
        cfg = self.load()
        profile_name = name or cfg.default_profile or cfg.active_profile or "default"
        profile = cfg.profiles.get(profile_name)
        if profile is None:
            raise ConfigError(
                f"profile '{profile_name}' not found in {self._path}; run 'rsspot configure --profile {profile_name}'"
            )
        return profile

    def upsert_profile(self, name: str, profile: ProfileConfig, *, activate: bool = False) -> SDKConfig:
        cfg = self.load()
        cfg.profiles[name] = profile
        if activate or (not cfg.active_profile and not cfg.default_profile):
            cfg.active_profile = name
            cfg.default_profile = name
        self.save(cfg)
        return cfg

    def set_active_profile(self, name: str) -> SDKConfig:
        cfg = self.load()
        if name not in cfg.profiles:
            raise ConfigError(f"profile '{name}' not found in {self._path}")
        cfg.active_profile = name
        cfg.default_profile = name
        self.save(cfg)
        return cfg

    def delete_profile(self, name: str) -> SDKConfig:
        cfg = self.load()
        if name not in cfg.profiles:
            raise ConfigError(f"profile '{name}' not found in {self._path}")
        del cfg.profiles[name]
        if cfg.active_profile == name:
            cfg.active_profile = next(iter(cfg.profiles), None)
        if cfg.default_profile == name:
            cfg.default_profile = cfg.active_profile
        self.save(cfg)
        return cfg
