from __future__ import annotations

from rsspot.models.pricing import PriceDetails, PriceDetailsList
from rsspot.services.base import ServiceBase


class PricingService(ServiceBase):
    """Pricing projections sourced from server-class APIs."""

    async def list(self, *, region: str | None = None) -> PriceDetailsList:
        classes = await self._client.server_classes.list(region=region)
        return PriceDetailsList(
            items=[
                PriceDetails(
                    server_class_name=item.name,
                    display_name=item.display_name,
                    category=item.category,
                    region=item.region,
                    market_price=item.market_price_per_hour,
                    cpu=item.cpu,
                    memory=item.memory,
                )
                for item in classes
            ]
        )

    async def for_server_class(self, server_class: str) -> PriceDetails:
        item = await self._client.server_classes.get(server_class)
        return PriceDetails(
            server_class_name=item.name,
            display_name=item.display_name,
            category=item.category,
            region=item.region,
            market_price=item.market_price_per_hour,
            cpu=item.cpu,
            memory=item.memory,
        )

    async def for_region(self, region: str) -> PriceDetailsList:
        return await self.list(region=region)
