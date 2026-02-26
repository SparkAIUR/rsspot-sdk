from __future__ import annotations

import math

from rsspot.models.pricing import PriceDetails
from rsspot.pricing_optimizer import (
    build_recommendation,
    filter_rows_for_list,
    normalize_pricing_items,
    parse_market_price,
    parse_memory_gb,
)


def _sample_items() -> list[PriceDetails]:
    return [
        PriceDetails(
            server_class_name="gp.vs1.medium-dfw",
            category="General Purpose",
            region="us-central-dfw-1",
            market_price="$0.010000",
            cpu="2",
            memory="4GB",
        ),
        PriceDetails(
            server_class_name="gp.vs2.medium-dfw2",
            category="General Purpose",
            region="us-central-dfw-2",
            market_price="$0.020000",
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
            server_class_name="mh.vs1.large-lon",
            category="Memory Heavy",
            region="uk-lon-1",
            market_price="$0.025000",
            cpu="4",
            memory="30GB",
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


def test_price_and_memory_parsing() -> None:
    assert parse_market_price("$0.123000") == 0.123
    assert parse_memory_gb("7.5GB") == 7.5
    assert parse_memory_gb("1TB") == 1024.0


def test_list_gen_filter_keeps_bare_metal() -> None:
    rows = normalize_pricing_items(_sample_items())
    filtered = filter_rows_for_list(rows, class_filters=None, gen=1, min_cpu=None, max_cpu=None)
    names = {row.raw.server_class_name for row in filtered}
    assert "gp.vs1.medium-dfw" in names
    assert "mh.vs1.large-lon" in names
    assert "gp.vs2.medium-dfw2" not in names
    assert "ch.vs2.large-iad2" not in names
    assert "gp.bm2.medium-dfw" in names


def test_list_class_and_cpu_filters() -> None:
    rows = normalize_pricing_items(_sample_items())
    filtered = filter_rows_for_list(rows, class_filters=["gp,ch"], gen=None, min_cpu=2.0, max_cpu=4.0)
    assert filtered
    assert all(row.class_prefix in {"gp", "ch"} for row in filtered)
    assert all(row.cpu is not None and 2.0 <= row.cpu <= 4.0 for row in filtered)


def test_build_recommendation_default_scenarios() -> None:
    rows = normalize_pricing_items(_sample_items())
    recommendation = build_recommendation(
        rows,
        nodes=5,
        gen=None,
        risk="med",
        balanced=False,
        regions=None,
        classes=None,
        min_hour=None,
        max_hour=None,
        min_month=None,
        max_month=None,
    )
    strategies = {scenario.strategy for scenario in recommendation.scenarios}
    assert strategies == {"max_performance", "max_value", "balanced"}
    assert recommendation.warning is None


def test_build_balanced_distribution_for_low_risk() -> None:
    rows = normalize_pricing_items(_sample_items())
    recommendation = build_recommendation(
        rows,
        nodes=5,
        gen=None,
        risk="low",
        balanced=True,
        regions=None,
        classes=["gp,ch,mh"],
        min_hour=None,
        max_hour=None,
        min_month=None,
        max_month=None,
    )
    balanced = next(scenario for scenario in recommendation.scenarios if scenario.strategy == "balanced")
    assert sorted((pool.nodes for pool in balanced.pools), reverse=True) == [2, 2, 1]
    for pool in balanced.pools:
        assert math.isclose(pool.suggested_bid_per_node, pool.hourly_per_node * 1.35)


def test_build_no_match_returns_warning() -> None:
    rows = normalize_pricing_items(_sample_items())
    recommendation = build_recommendation(
        rows,
        nodes=5,
        gen=None,
        risk="med",
        balanced=False,
        regions=None,
        classes=None,
        min_hour=5.0,
        max_hour=6.0,
        min_month=None,
        max_month=None,
    )
    assert recommendation.scenarios == []
    assert recommendation.warning is not None


def test_build_no_match_returns_warning_for_monthly_bounds() -> None:
    rows = normalize_pricing_items(_sample_items())
    recommendation = build_recommendation(
        rows,
        nodes=5,
        gen=None,
        risk="med",
        balanced=False,
        regions=None,
        classes=None,
        min_hour=None,
        max_hour=None,
        min_month=5000.0,
        max_month=6000.0,
    )
    assert recommendation.scenarios == []
    assert recommendation.warning is not None
