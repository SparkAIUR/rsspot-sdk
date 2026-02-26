from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from rsspot.config.loader import (
    default_config_candidates,
    dump_config,
    legacy_config_path,
    load_config,
)
from rsspot.config.models import SDKConfig


def test_runtime_dict_precedence_over_paths(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "default_profile": "file",
                "profiles": {"file": {"base_url": "https://file.example", "oauth_url": "https://file.example"}},
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(
        {
            "default_profile": "runtime",
            "profiles": {"runtime": {"base_url": "https://runtime.example", "oauth_url": "https://runtime.example"}},
        },
        config_path=path,
    )

    assert cfg.source == "runtime-dict"
    assert cfg.data.default_profile == "runtime"


def test_explicit_path_precedence_over_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / "env.json"
    env_path.write_text(
        json.dumps(
            {
                "default_profile": "env",
                "profiles": {"env": {"base_url": "https://env.example", "oauth_url": "https://env.example"}},
            }
        ),
        encoding="utf-8",
    )

    explicit_path = tmp_path / "explicit.toml"
    explicit_path.write_text(
        'default_profile = "explicit"\n[profiles.explicit]\nbase_url = "https://explicit.example"\noauth_url = "https://explicit.example"\n',
        encoding="utf-8",
    )

    monkeypatch.setenv("RSSPOT_CONFIG", str(env_path))
    cfg = load_config(config_path=explicit_path)

    assert cfg.source == "explicit-path"
    assert cfg.data.default_profile == "explicit"


def test_env_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / "env.yml"
    env_path.write_text(
        yaml.safe_dump(
            {
                "default_profile": "env",
                "profiles": {"env": {"base_url": "https://env.example", "oauth_url": "https://env.example"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RSSPOT_CONFIG", str(env_path))

    cfg = load_config()
    assert cfg.source.startswith("env:")
    assert cfg.data.default_profile == "env"


def test_legacy_flat_schema_normalized_to_default_profile() -> None:
    cfg = SDKConfig.model_validate({"org": "sparkai", "region": "us-central-dfw-1"})
    assert cfg.default_profile == "default"
    assert cfg.profiles["default"].org == "sparkai"


def test_dump_extensionless_defaults_to_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / ".spot_config"
    cfg = SDKConfig.model_validate(
        {
            "default_profile": "prod",
            "profiles": {
                "prod": {
                    "org": "sparkai",
                    "refreshToken": "token-123",
                    "region": "us-central-dfw-1",
                }
            },
        }
    )
    dump_config(cfg, config_path)
    rendered = config_path.read_text(encoding="utf-8")
    assert "default_profile: prod" in rendered
    loaded = load_config(config_path=config_path)
    assert loaded.data.default_profile == "prod"


def test_legacy_path_is_migrated_to_new_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy = legacy_config_path()
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        "\n".join(
            [
                "org: sparkai",
                "refreshToken: token-123",
                "region: us-central-dfw-1",
            ]
        ),
        encoding="utf-8",
    )

    resolved = load_config()
    assert resolved.source == "legacy-migrated"
    assert resolved.data.profiles["default"].org == "sparkai"

    default_candidates = default_config_candidates()
    assert default_candidates[0].exists()
