from __future__ import annotations

from pathlib import Path

from rsspot.config.loader import dump_config, load_config
from rsspot.config.models import SDKConfig


def test_load_extensionless_spot_config_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / ".spot_config"
    config_path.write_text(
        "\n".join(
            [
                "org: sparkai",
                "refreshToken: token-123",
                "accessToken: token-abc",
                "region: us-central-dfw-1",
            ]
        ),
        encoding="utf-8",
    )
    cfg = load_config(config_path)
    assert cfg.active_profile == "default"
    assert "default" in cfg.profiles
    assert cfg.profiles["default"].org == "sparkai"


def test_legacy_flat_schema_normalized_to_default_profile() -> None:
    cfg = SDKConfig.model_validate({"org": "sparkai", "region": "us-central-dfw-1"})
    assert cfg.active_profile == "default"
    assert cfg.profiles["default"].org == "sparkai"


def test_dump_extensionless_defaults_to_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / ".spot_config"
    cfg = SDKConfig.model_validate(
        {
            "active_profile": "prod",
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
    assert "active_profile: prod" in rendered
    loaded = load_config(config_path)
    assert loaded.active_profile == "prod"
