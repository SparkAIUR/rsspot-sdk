from __future__ import annotations

from rsspot.models.regions import RegionsListResponse, RegionSummary
from rsspot.services.base import ServiceBase


class RegionsService(ServiceBase):
    """Region API operations."""

    async def list(self) -> list[RegionSummary]:
        data = await self._client._request_json("GET", "/apis/ngpc.rxt.io/v1/regions")
        response = RegionsListResponse.model_validate(data)
        return [RegionSummary(name=item.metadata.name, description=item.spec.description) for item in response.items]

    async def get(self, name: str) -> RegionSummary:
        regions = await self.list()
        for region in regions:
            if region.name == name:
                return region
        raise ValueError(f"region not found: {name}")
