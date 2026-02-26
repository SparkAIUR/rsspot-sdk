from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from rich.console import Console
from rich.table import Table

from rsspot.models.pricing import PriceDetails

RiskLevel = Literal["low", "med", "high"]
StrategyName = Literal["max_performance", "max_value", "balanced"]

MONTH_HOURS = 730
CPU_WEIGHT = 1.0
MEMORY_WEIGHT = 1.0
GEN2_MULTIPLIER = 1.10

DEFAULT_BUILD_CLASSES = ("gp", "ch", "mh")

RISK_BID_MULTIPLIER: dict[RiskLevel, float] = {
    "low": 1.35,
    "med": 1.20,
    "high": 1.05,
}

RISK_BALANCED_POOL_TARGET: dict[RiskLevel, int] = {
    "low": 3,
    "med": 2,
    "high": 1,
}

_MEMORY_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(GB|TB)?\s*$", re.IGNORECASE)
_VIRTUAL_GEN_RE = re.compile(r"\.vs([0-9]+)(?:[.\-]|$)", re.IGNORECASE)
_CLASS_PREFIX_RE = re.compile(r"^([^.]+)\.")


@dataclass(slots=True)
class NormalizedPricingItem:
    raw: PriceDetails
    class_prefix: str
    is_virtual: bool
    generation: int | None
    hourly_price: float | None
    cpu: float | None
    memory_gb: float | None

    @property
    def monthly_price(self) -> float | None:
        if self.hourly_price is None:
            return None
        return self.hourly_price * MONTH_HOURS

    @property
    def capacity_per_node(self) -> float:
        if self.cpu is None or self.memory_gb is None:
            return 0.0
        multiplier = GEN2_MULTIPLIER if self.generation == 2 else 1.0
        return (self.cpu * CPU_WEIGHT + self.memory_gb * MEMORY_WEIGHT) * multiplier

    @property
    def value_per_node(self) -> float:
        if self.hourly_price is None or self.hourly_price <= 0:
            return 0.0
        return self.capacity_per_node / self.hourly_price


@dataclass(slots=True)
class PoolRecommendation:
    server_class_name: str
    class_prefix: str
    region: str | None
    generation: int | None
    nodes: int
    cpu_per_node: float
    memory_gb_per_node: float
    hourly_per_node: float
    monthly_per_node: float
    hourly_total: float
    monthly_total: float
    suggested_bid_per_node: float
    capacity_per_node: float
    value_per_node: float


@dataclass(slots=True)
class BuildScenario:
    strategy: StrategyName
    status: str
    score: float
    total_hourly: float
    total_monthly: float
    total_cpu: float
    total_memory_gb: float
    pools: list[PoolRecommendation] = field(default_factory=list)


@dataclass(slots=True)
class BuildRecommendation:
    requested: dict[str, object]
    assumptions: dict[str, object]
    scenarios: list[BuildScenario] = field(default_factory=list)
    warning: str | None = None


def split_csv_flags(values: Sequence[str] | None) -> list[str]:
    if not values:
        return []

    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for part in raw.split(","):
            token = part.strip().lower()
            if not token or token in seen:
                continue
            output.append(token)
            seen.add(token)
    return output


def parse_market_price(value: str | None) -> float | None:
    if not value:
        return None
    normalized = value.strip().replace("$", "").replace(",", "")
    if not normalized:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def parse_cpu(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def parse_memory_gb(value: str | None) -> float | None:
    if not value:
        return None
    match = _MEMORY_RE.match(value)
    if match is None:
        return None
    amount = float(match.group(1))
    unit = (match.group(2) or "GB").upper()
    if unit == "TB":
        return amount * 1024.0
    return amount


def class_prefix(name: str | None) -> str:
    if not name:
        return ""
    match = _CLASS_PREFIX_RE.match(name.lower())
    if match is None:
        return ""
    return match.group(1)


def detect_virtual_generation(name: str | None) -> int | None:
    if not name:
        return None
    match = _VIRTUAL_GEN_RE.search(name.lower())
    if match is None:
        return None
    return int(match.group(1))


def normalize_pricing_items(items: Sequence[PriceDetails]) -> list[NormalizedPricingItem]:
    normalized: list[NormalizedPricingItem] = []
    for item in items:
        generation = detect_virtual_generation(item.server_class_name)
        normalized.append(
            NormalizedPricingItem(
                raw=item,
                class_prefix=class_prefix(item.server_class_name),
                is_virtual=generation is not None,
                generation=generation,
                hourly_price=parse_market_price(item.market_price),
                cpu=parse_cpu(item.cpu),
                memory_gb=parse_memory_gb(item.memory),
            )
        )
    return normalized


def filter_rows_for_list(
    rows: Sequence[NormalizedPricingItem],
    *,
    class_filters: Sequence[str] | None,
    gen: int | None,
    min_cpu: float | None,
    max_cpu: float | None,
    regions: Sequence[str] | None = None,
) -> list[NormalizedPricingItem]:
    class_set = set(split_csv_flags(class_filters))
    region_set = set(split_csv_flags(regions))
    out: list[NormalizedPricingItem] = []
    for row in rows:
        region_name = (row.raw.region or "").lower()
        if region_set and region_name not in region_set:
            continue
        if class_set and row.class_prefix not in class_set:
            continue
        if gen is not None and row.is_virtual and row.generation != gen:
            continue
        if min_cpu is not None and (row.cpu is None or row.cpu < min_cpu):
            continue
        if max_cpu is not None and (row.cpu is None or row.cpu > max_cpu):
            continue
        out.append(row)
    return out


def _format_cpu(value: float | None) -> str:
    if value is None:
        return "-"
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _format_memory(value: float | None) -> str:
    if value is None:
        return "-"
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _format_hourly(value: float | None) -> str:
    if value is None:
        return "-"
    return f"${value:.6f}"


def _format_monthly(value: float | None) -> str:
    if value is None:
        return "-"
    return f"${value:.2f}"


def list_rows_payload(rows: Sequence[NormalizedPricingItem], *, nodes: int) -> dict[str, object]:
    payload_rows: list[dict[str, object]] = []
    for row in rows:
        hourly_per_node = row.hourly_price
        monthly_per_node = row.monthly_price
        payload_rows.append(
            {
                "server_class_name": row.raw.server_class_name,
                "display_name": row.raw.display_name,
                "category": row.raw.category,
                "region": row.raw.region,
                "market_price": row.raw.market_price,
                "cpu": row.raw.cpu,
                "memory": row.raw.memory,
                "class": row.class_prefix,
                "gen": row.generation,
                "hourly_per_node": hourly_per_node,
                "monthly_per_node": monthly_per_node,
                "hourly_for_nodes": (hourly_per_node * nodes) if hourly_per_node is not None else None,
                "monthly_for_nodes": (monthly_per_node * nodes) if monthly_per_node is not None else None,
            }
        )
    return {"nodes": nodes, "items": payload_rows}


def render_pricing_list_table(rows: Sequence[NormalizedPricingItem], *, nodes: int) -> None:
    console = Console()
    if not rows:
        console.print("[yellow]No pricing entries matched the provided filters.[/yellow]")
        return

    table = Table(title=f"Pricing ({len(rows)} classes, x{nodes} nodes)", show_header=True, header_style="bold")
    table.add_column("Server Class", style="cyan")
    table.add_column("Class")
    table.add_column("Region")
    table.add_column("Gen", justify="center")
    table.add_column("vCPU", justify="right")
    table.add_column("RAM (GB)", justify="right")
    table.add_column("$/hr", justify="right", style="green")
    table.add_column(f"$/hr x{nodes}", justify="right", style="green")
    table.add_column(f"$/mo x{nodes} (730h)", justify="right", style="green")

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            row.hourly_price if row.hourly_price is not None else float("inf"),
            -(row.cpu or 0.0),
            row.raw.server_class_name,
        ),
    )

    for row in sorted_rows:
        table.add_row(
            row.raw.server_class_name,
            row.class_prefix,
            row.raw.region or "-",
            str(row.generation) if row.generation is not None else "-",
            _format_cpu(row.cpu),
            _format_memory(row.memory_gb),
            _format_hourly(row.hourly_price),
            _format_hourly((row.hourly_price * nodes) if row.hourly_price is not None else None),
            _format_monthly((row.monthly_price * nodes) if row.monthly_price is not None else None),
        )
    console.print(table)


def _normalize_score(value: float, min_value: float, max_value: float) -> float:
    if math.isclose(min_value, max_value):
        return 1.0
    return (value - min_value) / (max_value - min_value)


def _distribute_nodes(total_nodes: int, pool_count: int) -> list[int]:
    base = total_nodes // pool_count
    remainder = total_nodes % pool_count
    return [base + (1 if index < remainder else 0) for index in range(pool_count)]


def _build_pool(row: NormalizedPricingItem, *, nodes: int, bid_multiplier: float) -> PoolRecommendation:
    hourly_per_node = row.hourly_price or 0.0
    monthly_per_node = hourly_per_node * MONTH_HOURS
    cpu_per_node = row.cpu or 0.0
    memory_per_node = row.memory_gb or 0.0
    return PoolRecommendation(
        server_class_name=row.raw.server_class_name,
        class_prefix=row.class_prefix,
        region=row.raw.region,
        generation=row.generation,
        nodes=nodes,
        cpu_per_node=cpu_per_node,
        memory_gb_per_node=memory_per_node,
        hourly_per_node=hourly_per_node,
        monthly_per_node=monthly_per_node,
        hourly_total=hourly_per_node * nodes,
        monthly_total=monthly_per_node * nodes,
        suggested_bid_per_node=hourly_per_node * bid_multiplier,
        capacity_per_node=row.capacity_per_node,
        value_per_node=row.value_per_node,
    )


def _build_scenario(
    strategy: StrategyName,
    ranked: Sequence[NormalizedPricingItem],
    *,
    nodes: int,
    pool_count: int,
    bid_multiplier: float,
    cap_min: float,
    cap_max: float,
    value_min: float,
    value_max: float,
) -> BuildScenario | None:
    selected = list(ranked[:pool_count])
    if not selected:
        return None

    allocations = _distribute_nodes(nodes, len(selected))
    pools = [
        _build_pool(row, nodes=allocation, bid_multiplier=bid_multiplier)
        for row, allocation in zip(selected, allocations, strict=True)
        if allocation > 0
    ]
    if not pools:
        return None

    total_hourly = sum(pool.hourly_total for pool in pools)
    total_monthly = sum(pool.monthly_total for pool in pools)
    total_cpu = sum(pool.cpu_per_node * pool.nodes for pool in pools)
    total_memory = sum(pool.memory_gb_per_node * pool.nodes for pool in pools)
    total_capacity = sum(pool.capacity_per_node * pool.nodes for pool in pools)
    value_metric = total_capacity / total_hourly if total_hourly > 0 else 0.0

    if strategy == "max_performance":
        score = total_capacity
    elif strategy == "max_value":
        score = value_metric
    else:
        cap_score = _normalize_score(total_capacity / nodes, cap_min, cap_max)
        value_score = _normalize_score(value_metric, value_min, value_max)
        score = 0.5 * cap_score + 0.5 * value_score

    return BuildScenario(
        strategy=strategy,
        status="ok",
        score=score,
        total_hourly=total_hourly,
        total_monthly=total_monthly,
        total_cpu=total_cpu,
        total_memory_gb=total_memory,
        pools=pools,
    )


def _within_cost_bounds(
    scenario: BuildScenario,
    *,
    min_hour: float | None,
    max_hour: float | None,
    min_month: float | None,
    max_month: float | None,
) -> bool:
    if min_hour is not None and scenario.total_hourly < min_hour:
        return False
    if max_hour is not None and scenario.total_hourly > max_hour:
        return False
    if min_month is not None and scenario.total_monthly < min_month:
        return False
    if max_month is not None and scenario.total_monthly > max_month:
        return False
    return True


def build_recommendation(
    rows: Sequence[NormalizedPricingItem],
    *,
    nodes: int,
    gen: int | None,
    risk: RiskLevel,
    balanced: bool,
    regions: Sequence[str] | None,
    classes: Sequence[str] | None,
    min_hour: float | None,
    max_hour: float | None,
    min_month: float | None,
    max_month: float | None,
) -> BuildRecommendation:
    class_filters = split_csv_flags(classes) or list(DEFAULT_BUILD_CLASSES)
    region_filters = split_csv_flags(regions)

    candidates: list[NormalizedPricingItem] = []
    for row in rows:
        if not row.is_virtual:
            continue
        if gen is not None and row.generation != gen:
            continue
        if row.class_prefix not in class_filters:
            continue
        if region_filters and (row.raw.region or "").lower() not in set(region_filters):
            continue
        if row.hourly_price is None or row.hourly_price <= 0:
            continue
        if row.cpu is None or row.cpu <= 0:
            continue
        if row.memory_gb is None or row.memory_gb <= 0:
            continue
        candidates.append(row)

    recommendation = BuildRecommendation(
        requested={
            "nodes": nodes,
            "gen": gen,
            "risk": risk,
            "balanced": balanced,
            "regions": region_filters,
            "classes": class_filters,
            "min_hour": min_hour,
            "max_hour": max_hour,
            "min_month": min_month,
            "max_month": max_month,
        },
        assumptions={
            "month_hours": MONTH_HOURS,
            "cpu_weight": CPU_WEIGHT,
            "memory_weight": MEMORY_WEIGHT,
            "gen2_multiplier": GEN2_MULTIPLIER,
            "risk_bid_multiplier": RISK_BID_MULTIPLIER[risk],
        },
    )

    if not candidates:
        recommendation.warning = "No pricing candidates matched the provided filters."
        return recommendation

    cap_values = [row.capacity_per_node for row in candidates]
    value_values = [row.value_per_node for row in candidates]
    cap_min = min(cap_values)
    cap_max = max(cap_values)
    value_min = min(value_values)
    value_max = max(value_values)

    performance_ranked = sorted(
        candidates,
        key=lambda row: (-row.capacity_per_node, row.hourly_price or float("inf"), row.raw.server_class_name),
    )
    value_ranked = sorted(
        candidates,
        key=lambda row: (-row.value_per_node, row.hourly_price or float("inf"), row.raw.server_class_name),
    )
    balanced_ranked = sorted(
        candidates,
        key=lambda row: (
            -(
                0.5 * _normalize_score(row.capacity_per_node, cap_min, cap_max)
                + 0.5 * _normalize_score(row.value_per_node, value_min, value_max)
            ),
            row.hourly_price or float("inf"),
            row.raw.server_class_name,
        ),
    )

    bid_multiplier = RISK_BID_MULTIPLIER[risk]
    balanced_pool_count = 1
    if balanced:
        balanced_pool_count = min(
            nodes,
            len(balanced_ranked),
            RISK_BALANCED_POOL_TARGET[risk],
        )
        balanced_pool_count = max(1, balanced_pool_count)

    scenarios: list[BuildScenario] = []
    performance = _build_scenario(
        "max_performance",
        performance_ranked,
        nodes=nodes,
        pool_count=1,
        bid_multiplier=bid_multiplier,
        cap_min=cap_min,
        cap_max=cap_max,
        value_min=value_min,
        value_max=value_max,
    )
    if performance is not None:
        scenarios.append(performance)

    max_value = _build_scenario(
        "max_value",
        value_ranked,
        nodes=nodes,
        pool_count=1,
        bid_multiplier=bid_multiplier,
        cap_min=cap_min,
        cap_max=cap_max,
        value_min=value_min,
        value_max=value_max,
    )
    if max_value is not None:
        scenarios.append(max_value)

    balanced_scenario = _build_scenario(
        "balanced",
        balanced_ranked,
        nodes=nodes,
        pool_count=balanced_pool_count,
        bid_multiplier=bid_multiplier,
        cap_min=cap_min,
        cap_max=cap_max,
        value_min=value_min,
        value_max=value_max,
    )
    if balanced_scenario is not None:
        scenarios.append(balanced_scenario)

    bounded = [
        scenario
        for scenario in scenarios
        if _within_cost_bounds(
            scenario,
            min_hour=min_hour,
            max_hour=max_hour,
            min_month=min_month,
            max_month=max_month,
        )
    ]
    if not bounded:
        recommendation.warning = "No scenarios matched the provided hourly/monthly budget constraints."
        recommendation.scenarios = []
        return recommendation

    recommendation.scenarios = bounded
    return recommendation


def render_build_recommendation_table(recommendation: BuildRecommendation) -> None:
    console = Console()
    if recommendation.warning:
        console.print(f"[yellow]{recommendation.warning}[/yellow]")
    if not recommendation.scenarios:
        return

    summary = Table(title="Pricing Build Recommendations", show_header=True, header_style="bold")
    summary.add_column("Strategy")
    summary.add_column("Score", justify="right")
    summary.add_column("Pools", justify="right")
    summary.add_column("Total $/hr", justify="right", style="green")
    summary.add_column("Total $/mo", justify="right", style="green")
    summary.add_column("Total vCPU", justify="right")
    summary.add_column("Total RAM (GB)", justify="right")
    for scenario in recommendation.scenarios:
        summary.add_row(
            scenario.strategy,
            f"{scenario.score:.4f}",
            str(len(scenario.pools)),
            _format_hourly(scenario.total_hourly),
            _format_monthly(scenario.total_monthly),
            _format_cpu(scenario.total_cpu),
            _format_memory(scenario.total_memory_gb),
        )
    console.print(summary)

    for scenario in recommendation.scenarios:
        table = Table(title=f"{scenario.strategy} pools", show_header=True, header_style="bold")
        table.add_column("Server Class", style="cyan")
        table.add_column("Class")
        table.add_column("Region")
        table.add_column("Gen", justify="center")
        table.add_column("Nodes", justify="right")
        table.add_column("vCPU/node", justify="right")
        table.add_column("RAM/node", justify="right")
        table.add_column("$/hr node", justify="right", style="green")
        table.add_column("$/hr total", justify="right", style="green")
        table.add_column("Bid/node", justify="right")

        for pool in scenario.pools:
            table.add_row(
                pool.server_class_name,
                pool.class_prefix,
                pool.region or "-",
                str(pool.generation) if pool.generation is not None else "-",
                str(pool.nodes),
                _format_cpu(pool.cpu_per_node),
                _format_memory(pool.memory_gb_per_node),
                _format_hourly(pool.hourly_per_node),
                _format_hourly(pool.hourly_total),
                _format_hourly(pool.suggested_bid_per_node),
            )

        table.add_row(
            "TOTAL",
            "",
            "",
            "",
            str(sum(pool.nodes for pool in scenario.pools)),
            _format_cpu(scenario.total_cpu),
            _format_memory(scenario.total_memory_gb),
            "",
            _format_hourly(scenario.total_hourly),
            "",
        )
        console.print(table)
