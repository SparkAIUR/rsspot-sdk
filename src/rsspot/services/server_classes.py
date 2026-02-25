from __future__ import annotations

from rsspot.models.server_classes import (
    ServerClassItem,
    ServerClassListResponse,
    ServerClassSummary,
)
from rsspot.services.base import ServiceBase


def _to_price(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if value.startswith("$"):
        return value
    return f"${value}"


class ServerClassesService(ServiceBase):
    """Server class API operations."""

    async def list(self, *, region: str | None = None, only_available: bool = True) -> list[ServerClassSummary]:
        data = await self._client._request_json("GET", "/apis/ngpc.rxt.io/v1/serverclasses")
        response = ServerClassListResponse.model_validate(data)

        out: list[ServerClassSummary] = []
        for item in response.items:
            spec = item.spec
            status = item.status
            if region and spec.region != region:
                continue
            if only_available and spec.availability != "available":
                continue
            out.append(
                ServerClassSummary(
                    name=item.metadata.name,
                    display_name=spec.displayName,
                    category=spec.category,
                    region=spec.region,
                    availability=spec.availability,
                    market_price_per_hour=_to_price(
                        status.spotPricing.marketPricePerHour if status and status.spotPricing else None
                    ),
                    min_bid_price_per_hour=_to_price(spec.minBidPricePerHour),
                    on_demand_price_per_hour=_to_price(spec.onDemandPricing.cost if spec.onDemandPricing else None),
                    cpu=spec.resources.cpu,
                    memory=spec.resources.memory,
                )
            )
        return out

    async def get(self, name: str) -> ServerClassSummary:
        data = await self._client._request_json("GET", f"/apis/ngpc.rxt.io/v1/serverclasses/{name}")
        item = ServerClassItem.model_validate(data)
        spec = item.spec
        status = item.status
        return ServerClassSummary(
            name=item.metadata.name,
            display_name=spec.displayName,
            category=spec.category,
            region=spec.region,
            availability=spec.availability,
            market_price_per_hour=_to_price(
                status.spotPricing.marketPricePerHour if status and status.spotPricing else None
            ),
            min_bid_price_per_hour=_to_price(spec.minBidPricePerHour),
            on_demand_price_per_hour=_to_price(spec.onDemandPricing.cost if spec.onDemandPricing else None),
            cpu=spec.resources.cpu,
            memory=spec.resources.memory,
        )
