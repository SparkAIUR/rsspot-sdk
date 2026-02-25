from __future__ import annotations

from pydantic import Field

from rsspot.models.common import Metadata, SpotModel


class RegionSpec(SpotModel):
    description: str | None = None


class RegionItem(SpotModel):
    metadata: Metadata
    spec: RegionSpec


class RegionsListResponse(SpotModel):
    items: list[RegionItem] = Field(default_factory=list)


class RegionSummary(SpotModel):
    name: str
    description: str | None = None
