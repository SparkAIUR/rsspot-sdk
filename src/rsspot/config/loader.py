from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any

import tomli_w
import yaml

from rsspot.config.models import ConfigInput, ProfileConfig, ResolvedConfig, SDKConfig
from rsspot.constants import DEFAULT_CONFIG_DIR, DEFAULT_LEGACY_CONFIG_FILE
from rsspot.errors import ConfigError

CONFIG_PATH_ENVS = ("RSSPOT_CONFIG", "RSSPOT_CONFIG_FILE", "SPOT_CONFIG_FILE")


def _default_config_dir() -> Path:
    return Path(DEFAULT_CONFIG_DIR).expanduser()


def default_config_candidates() -> list[Path]:
    base = _default_config_dir()
    return [
        base / "config.yml",
        base / "config.yaml",
        base / "config.toml",
        base / "config.json",
    ]


def legacy_config_path() -> Path:
    return Path(DEFAULT_LEGACY_CONFIG_FILE).expanduser()


def _decode_raw(raw: str, *, suffix: str) -> dict[str, Any]:
    if suffix in {".yaml", ".yml"}:
        parsed = yaml.safe_load(raw) or {}
    elif suffix == ".json":
        parsed = json.loads(raw)
    elif suffix == ".toml":
        parsed = tomllib.loads(raw)
    else:
        # Extension-less files default to Spot's historical format.
        # Try TOML first for users storing ~/.spot_config in TOML.
        # Then fall back to YAML and finally JSON.
        for decode in (tomllib.loads, yaml.safe_load, json.loads):
            try:
                parsed = decode(raw) or {}
                break
            except Exception:  # noqa: BLE001
                continue
        else:
            raise ConfigError("failed to auto-detect config format (expected yaml/json/toml)")

    if not isinstance(parsed, dict):
        raise ConfigError("config must decode to an object/map")
    return parsed


def parse_config_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8")
    return _decode_raw(raw, suffix=suffix)


def ensure_default_config_exists(path: Path | None = None) -> Path:
    target = path or default_config_candidates()[0]
    target = target.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return target.resolve()

    default = SDKConfig(
        default_profile="default",
        active_profile="default",
        profiles={"default": ProfileConfig()},
    )
    save_config(default, path=target)
    return target.resolve()


def _load_from_path(path: Path, *, source: str) -> ResolvedConfig:
    try:
        payload = parse_config_file(path)
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"failed to parse config file '{path}': {exc}") from exc

    try:
        data = SDKConfig.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        raise ConfigError(f"invalid config structure for '{path}': {exc}") from exc

    return ResolvedConfig(source=source, path=path.resolve(), data=data)


def load_config(
    config: ConfigInput | str | Path | None = None,
    *,
    config_path: str | Path | None = None,
) -> ResolvedConfig:
    """Load and validate SDK configuration with precedence and migration support."""

    # Backward-compatible positional path support.
    if isinstance(config, (str, Path)) and config_path is None:
        config_path = config
        config = None

    if config is not None:
        if isinstance(config, SDKConfig):
            return ResolvedConfig(source="runtime-model", data=config)
        return ResolvedConfig(source="runtime-dict", data=SDKConfig.model_validate(config))

    if config_path is not None:
        path = Path(config_path).expanduser().resolve()
        if not path.exists():
            return ResolvedConfig(source="explicit-path-missing", path=path, data=SDKConfig())
        return _load_from_path(path, source="explicit-path")

    for env_name in CONFIG_PATH_ENVS:
        env_path = os.getenv(env_name)
        if not env_path:
            continue
        path = Path(env_path).expanduser().resolve()
        if not path.exists():
            return ResolvedConfig(source=f"env:{env_name}:missing", path=path, data=SDKConfig())
        return _load_from_path(path, source=f"env:{env_name}")

    for candidate in default_config_candidates():
        if candidate.exists():
            return _load_from_path(candidate.expanduser().resolve(), source="default-path")

    legacy = legacy_config_path()
    if legacy.exists():
        migrated = _load_from_path(legacy.expanduser().resolve(), source="legacy-path")
        target = ensure_default_config_exists()
        save_config(migrated.data, path=target)
        return ResolvedConfig(source="legacy-migrated", path=target.resolve(), data=migrated.data)

    return ResolvedConfig(
        source="default-empty",
        path=default_config_candidates()[0].expanduser().resolve(),
        data=SDKConfig(),
    )


def save_config(config: SDKConfig, *, path: Path | None = None) -> Path:
    target = (path or default_config_candidates()[0]).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    suffix = target.suffix.lower()

    payload = config.model_dump(mode="json", by_alias=True, exclude_none=True)
    if suffix in {"", ".yaml", ".yml"}:
        rendered = yaml.safe_dump(payload, sort_keys=False)
    elif suffix == ".json":
        rendered = json.dumps(payload, indent=2) + "\n"
    elif suffix == ".toml":
        rendered = tomli_w.dumps(payload)
    else:
        raise ConfigError(f"unsupported config extension: {suffix}")

    target.write_text(rendered, encoding="utf-8")
    target.chmod(0o600)
    return target.resolve()


# Compatibility alias for prior API surface.
def dump_config(config: SDKConfig, path: Path) -> None:
    save_config(config, path=path)
