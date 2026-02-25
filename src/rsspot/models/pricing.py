from __future__ import annotations

from pydantic import Field

from rsspot.models.common import SpotModel


class PriceDetails(SpotModel):
    server_class_name: str
    display_name: str | None = None
    category: str | None = None
    region: str | None = None
    market_price: str | None = None
    cpu: str | None = None
    memory: str | None = None


class PriceDetailsList(SpotModel):
    items: list[PriceDetails] = Field(default_factory=list)
