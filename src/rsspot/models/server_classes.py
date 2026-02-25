from __future__ import annotations

from pydantic import Field

from rsspot.models.common import Metadata, SpotModel


class ServerClassResources(SpotModel):
    cpu: str | None = None
    memory: str | None = None
    gpu: str | None = None


class ServerClassOnDemandPricing(SpotModel):
    cost: str | None = None


class ServerClassSpec(SpotModel):
    availability: str | None = None
    displayName: str | None = None
    category: str | None = None
    region: str | None = None
    minBidPricePerHour: str | None = None
    onDemandPricing: ServerClassOnDemandPricing | None = None
    resources: ServerClassResources = Field(default_factory=ServerClassResources)


class ServerClassSpotPricing(SpotModel):
    marketPricePerHour: str | None = None


class ServerClassStatus(SpotModel):
    spotPricing: ServerClassSpotPricing | None = None


class ServerClassItem(SpotModel):
    metadata: Metadata
    spec: ServerClassSpec
    status: ServerClassStatus | None = None


class ServerClassListResponse(SpotModel):
    items: list[ServerClassItem] = Field(default_factory=list)


class ServerClassSummary(SpotModel):
    name: str
    display_name: str | None = None
    category: str | None = None
    region: str | None = None
    availability: str | None = None
    market_price_per_hour: str | None = None
    min_bid_price_per_hour: str | None = None
    on_demand_price_per_hour: str | None = None
    cpu: str | None = None
    memory: str | None = None
