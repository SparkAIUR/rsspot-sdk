from __future__ import annotations

from rsspot.models.organizations import Organization, OrganizationsResponse
from rsspot.services.base import ServiceBase


class OrganizationsService(ServiceBase):
    """Organization API operations."""

    async def list(self) -> OrganizationsResponse:
        data = await self._client._request_json("GET", "/apis/auth.ngpc.rxt.io/v1/organizations")
        return OrganizationsResponse.model_validate(data)

    async def get(self, name_or_id: str) -> Organization:
        orgs = await self.list()
        for org in orgs.organizations:
            if org.name == name_or_id or org.id == name_or_id:
                return org
        raise ValueError(f"organization not found: {name_or_id}")
