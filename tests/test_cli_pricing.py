from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from typer.testing import CliRunner

import rsspot.cli as cli_module
from rsspot.models.pricing import PriceDetails, PriceDetailsList

runner = CliRunner()


class _FakePricingService:
    def __init__(self, payload: PriceDetailsList) -> None:
        self._payload = payload

    async def list(self, *, region: str | None = None) -> PriceDetailsList:
        if region is None:
            return self._payload
        return PriceDetailsList(items=[item for item in self._payload.items if item.region == region])

    async def for_server_class(self, server_class: str) -> PriceDetails:
        for item in self._payload.items:
            if item.server_class_name == server_class:
                return item
        raise ValueError(f"unknown server class: {server_class}")


class _FakeClient:
    def __init__(self, payload: PriceDetailsList) -> None:
        self.pricing = _FakePricingService(payload)

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any) -> None:
        return None


def _sample_payload() -> PriceDetailsList:
    return PriceDetailsList(
        items=[
            PriceDetails(
                server_class_name="gp.vs1.medium-dfw",
                category="General Purpose",
                region="us-central-dfw-1",
                market_price="$0.010000",
                cpu="2",
                memory="4GB",
            ),
            PriceDetails(
                server_class_name="ch.vs2.large-iad2",
                category="Compute Heavy",
                region="us-east-iad-2",
                market_price="$0.030000",
                cpu="4",
                memory="8GB",
            ),
            PriceDetails(
                server_class_name="gp.bm2.medium-dfw",
                category="Bare Metal",
                region="us-central-dfw-1",
                market_price="$0.005000",
                cpu="24",
                memory="64GB",
            ),
        ]
    )


@pytest.fixture()
def patched_cli(monkeypatch: pytest.MonkeyPatch) -> Callable[[PriceDetailsList], None]:
    def apply(payload: PriceDetailsList) -> None:
        monkeypatch.setattr(cli_module, "_record_history", lambda _ctx, _state: None)
        monkeypatch.setattr(cli_module, "_make_client", lambda _state: _FakeClient(payload))

    return apply


def test_pricing_list_defaults_to_table_output(patched_cli: Callable[[PriceDetailsList], None]) -> None:
    patched_cli(_sample_payload())
    result = runner.invoke(cli_module.app, ["pricing", "list"])
    assert result.exit_code == 0
    assert "Pricing (" in result.stdout
    assert "x1 nodes" in result.stdout
    assert "$/mo" in result.stdout


def test_pricing_list_json_when_explicit_output(patched_cli: Callable[[PriceDetailsList], None]) -> None:
    patched_cli(_sample_payload())
    result = runner.invoke(cli_module.app, ["-o", "json", "pricing", "list", "--class", "gp"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["nodes"] == 1
    assert "items" in payload
    assert payload["items"]
    assert all(item["server_class_name"].startswith("gp.") for item in payload["items"])


def test_pricing_list_json_with_nodes_multiplier(patched_cli: Callable[[PriceDetailsList], None]) -> None:
    patched_cli(_sample_payload())
    result = runner.invoke(cli_module.app, ["-o", "json", "pricing", "list", "--class", "gp", "--nodes", "5"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["nodes"] == 5
    assert payload["items"]
    first = payload["items"][0]
    assert first["hourly_per_node"] is not None
    assert first["hourly_for_nodes"] == pytest.approx(first["hourly_per_node"] * 5)


def test_pricing_build_returns_three_scenarios_by_default(patched_cli: Callable[[PriceDetailsList], None]) -> None:
    patched_cli(_sample_payload())
    result = runner.invoke(
        cli_module.app,
        ["-o", "json", "pricing", "build", "--nodes", "5", "--classes", "gp,ch,mh"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert {entry["strategy"] for entry in payload["scenarios"]} == {"max_performance", "max_value", "balanced"}


def test_pricing_build_returns_empty_when_hour_budget_excludes_all(
    patched_cli: Callable[[PriceDetailsList], None]
) -> None:
    patched_cli(_sample_payload())
    result = runner.invoke(
        cli_module.app,
        ["-o", "json", "pricing", "build", "--nodes", "5", "--min-hour", "10", "--max-hour", "11"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["scenarios"] == []
    assert payload["warning"] is not None


def test_pricing_build_returns_empty_when_month_budget_excludes_all(
    patched_cli: Callable[[PriceDetailsList], None]
) -> None:
    patched_cli(_sample_payload())
    result = runner.invoke(
        cli_module.app,
        ["-o", "json", "pricing", "build", "--nodes", "5", "--min-month", "10000", "--max-month", "11000"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["scenarios"] == []
    assert payload["warning"] is not None
