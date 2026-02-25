from __future__ import annotations

from urllib.parse import quote

from rsspot.models.cloudspaces import VMCloudSpaceListResponse
from rsspot.models.events import OrganizationEventsResponse
from rsspot.models.nodepools import OnDemandNodePoolListResponse
from rsspot.services.base import ServiceBase


class InventoryService(ServiceBase):
    """VM-level inventory APIs used by controller-style workflows."""

    async def list_vmcloudspaces(self, *, org: str | None = None) -> VMCloudSpaceListResponse:
        org_id = await self._client.resolve_org_id(org)
        data = await self._client._request_json(
            "GET",
            f"/apis/ngpc.rxt.io/v1/namespaces/{org_id}/vmcloudspaces",
        )
        return VMCloudSpaceListResponse.model_validate(data)

    async def list_vmpools(
        self,
        *,
        vmcloudspace: str,
        org: str | None = None,
    ) -> OnDemandNodePoolListResponse:
        org_id = await self._client.resolve_org_id(org)
        selector = quote(f"ngpc.rxt.io/vmcloudspace={vmcloudspace}", safe="")
        data = await self._client._request_json(
            "GET",
            f"/apis/ngpc.rxt.io/v1/namespaces/{org_id}/vmpools?labelSelector={selector}",
        )
        return OnDemandNodePoolListResponse.model_validate(data)

    async def list_organization_events(self, *, limit: int = 100) -> OrganizationEventsResponse:
        data = await self._client._request_json(
            "GET",
            "/apis/metrics.ngpc.rxt.io/v1/events/organizations",
            params={"limits": str(limit)},
        )
        return OrganizationEventsResponse.model_validate(data)
