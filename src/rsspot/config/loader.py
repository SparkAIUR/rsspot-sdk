from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import tomli_w
import yaml

from rsspot.config.models import SDKConfig
from rsspot.errors import ConfigError


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


def _read_raw(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8")
    return _decode_raw(raw, suffix=suffix)


def load_config(path: Path) -> SDKConfig:
    """Load and validate SDK configuration from YAML/JSON/TOML.

    Example:
        >>> # load_config(Path("~/.spot_config").expanduser())
    """

    if not path.exists():
        return SDKConfig()

    try:
        payload = _read_raw(path)
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"failed to parse config file '{path}': {exc}") from exc

    try:
        return SDKConfig.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        raise ConfigError(f"invalid config structure for '{path}': {exc}") from exc


def dump_config(config: SDKConfig, path: Path) -> None:
    """Persist SDK configuration to YAML/JSON/TOML based on file extension."""

    payload = config.model_dump(mode="json", by_alias=True, exclude_none=True)
    suffix = path.suffix.lower()

    if suffix in {"", ".yaml", ".yml"}:
        rendered = yaml.safe_dump(payload, sort_keys=False)
    elif suffix == ".json":
        rendered = json.dumps(payload, indent=2) + "\n"
    elif suffix == ".toml":
        rendered = tomli_w.dumps(payload)
    else:
        raise ConfigError(f"unsupported config extension: {suffix}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    path.chmod(0o600)
