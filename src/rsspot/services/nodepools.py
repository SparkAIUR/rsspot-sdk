from __future__ import annotations

from typing import cast
from urllib.parse import quote

from rsspot.models.nodepools import (
    OnDemandNodePoolItem,
    OnDemandNodePoolListResponse,
    OnDemandNodePoolUpsert,
    SpotNodePoolItem,
    SpotNodePoolListResponse,
    SpotNodePoolUpsert,
)
from rsspot.services.base import ServiceBase


class SpotNodePoolsService(ServiceBase):
    """Spot nodepool CRUD operations."""

    async def list(self, *, org: str | None = None, cloudspace: str | None = None) -> SpotNodePoolListResponse:
        org_id = await self._client.resolve_org_id(org)
        path = f"/apis/ngpc.rxt.io/v1/namespaces/{org_id}/spotnodepools"
        if cloudspace:
            selector = quote(f"ngpc.rxt.io/cloudspace={cloudspace}", safe="")
            path = f"{path}?labelSelector={selector}"
        data = await self._client._request_json("GET", path)
        return SpotNodePoolListResponse.model_validate(data)

    async def get(self, name: str, *, org: str | None = None) -> SpotNodePoolItem:
        org_id = await self._client.resolve_org_id(org)
        data = await self._client._request_json(
            "GET",
            f"/apis/ngpc.rxt.io/v1/namespaces/{org_id}/spotnodepools/{name}",
        )
        return SpotNodePoolItem.model_validate(data)

    async def create(self, spec: SpotNodePoolUpsert, *, org: str | None = None) -> dict[str, object]:
        org_id = await self._client.resolve_org_id(org)
        payload = {
            "apiVersion": "ngpc.rxt.io/v1",
            "kind": "SpotNodePool",
            "metadata": {
                "name": spec.name,
                "namespace": org_id,
                "labels": {"ngpc.rxt.io/cloudspace": spec.cloudspace},
            },
            "spec": {
                "serverClass": spec.server_class,
                "desired": spec.desired,
                "cloudSpace": spec.cloudspace,
                "bidPrice": str(spec.bid_price).removeprefix("$"),
                "customAnnotations": spec.custom_annotations,
                "customLabels": spec.custom_labels,
                "customTaints": spec.custom_taints,
                "autoscaling": spec.autoscaling.model_dump(by_alias=True),
            },
        }
        return cast(
            dict[str, object],
            await self._client._request_json(
            "POST",
            f"/apis/ngpc.rxt.io/v1/namespaces/{org_id}/spotnodepools",
            json_data=payload,
            ),
        )

    async def update(self, spec: SpotNodePoolUpsert, *, org: str | None = None) -> dict[str, object]:
        org_id = await self._client.resolve_org_id(org)
        payload = {
            "spec": {
                "desired": spec.desired,
                "bidPrice": str(spec.bid_price).removeprefix("$"),
                "customAnnotations": spec.custom_annotations,
                "customLabels": spec.custom_labels,
                "customTaints": spec.custom_taints,
                "autoscaling": spec.autoscaling.model_dump(by_alias=True),
            }
        }
        return cast(
            dict[str, object],
            await self._client._request_json(
            "PATCH",
            f"/apis/ngpc.rxt.io/v1/namespaces/{org_id}/spotnodepools/{spec.name}",
            json_data=payload,
            content_type="application/merge-patch+json",
            ),
        )

    async def delete(self, name: str, *, org: str | None = None) -> dict[str, object]:
        org_id = await self._client.resolve_org_id(org)
        return cast(
            dict[str, object],
            await self._client._request_json(
            "DELETE",
            f"/apis/ngpc.rxt.io/v1/namespaces/{org_id}/spotnodepools/{name}",
            ),
        )


class OnDemandNodePoolsService(ServiceBase):
    """On-demand nodepool CRUD operations."""

    async def list(
        self,
        *,
        org: str | None = None,
        cloudspace: str | None = None,
    ) -> OnDemandNodePoolListResponse:
        org_id = await self._client.resolve_org_id(org)
        path = f"/apis/ngpc.rxt.io/v1/namespaces/{org_id}/ondemandnodepools"
        if cloudspace:
            selector = quote(f"ngpc.rxt.io/cloudspace={cloudspace}", safe="")
            path = f"{path}?labelSelector={selector}"
        data = await self._client._request_json("GET", path)
        return OnDemandNodePoolListResponse.model_validate(data)

    async def get(self, name: str, *, org: str | None = None) -> OnDemandNodePoolItem:
        org_id = await self._client.resolve_org_id(org)
        data = await self._client._request_json(
            "GET",
            f"/apis/ngpc.rxt.io/v1/namespaces/{org_id}/ondemandnodepools/{name}",
        )
        return OnDemandNodePoolItem.model_validate(data)

    async def create(self, spec: OnDemandNodePoolUpsert, *, org: str | None = None) -> dict[str, object]:
        org_id = await self._client.resolve_org_id(org)
        payload = {
            "apiVersion": "ngpc.rxt.io/v1",
            "kind": "OnDemandNodePool",
            "metadata": {
                "name": spec.name,
                "namespace": org_id,
                "labels": {"ngpc.rxt.io/cloudspace": spec.cloudspace},
            },
            "spec": {
                "serverClass": spec.server_class,
                "desired": spec.desired,
                "cloudSpace": spec.cloudspace,
                "customAnnotations": spec.custom_annotations,
                "customLabels": spec.custom_labels,
                "customTaints": spec.custom_taints,
                "autoscaling": spec.autoscaling.model_dump(by_alias=True),
            },
        }
        return cast(
            dict[str, object],
            await self._client._request_json(
            "POST",
            f"/apis/ngpc.rxt.io/v1/namespaces/{org_id}/ondemandnodepools",
            json_data=payload,
            ),
        )

    async def update(self, spec: OnDemandNodePoolUpsert, *, org: str | None = None) -> dict[str, object]:
        org_id = await self._client.resolve_org_id(org)
        payload = {
            "spec": {
                "desired": spec.desired,
                "customAnnotations": spec.custom_annotations,
                "customLabels": spec.custom_labels,
                "customTaints": spec.custom_taints,
                "autoscaling": spec.autoscaling.model_dump(by_alias=True),
            }
        }
        return cast(
            dict[str, object],
            await self._client._request_json(
            "PATCH",
            f"/apis/ngpc.rxt.io/v1/namespaces/{org_id}/ondemandnodepools/{spec.name}",
            json_data=payload,
            content_type="application/merge-patch+json",
            ),
        )

    async def delete(self, name: str, *, org: str | None = None) -> dict[str, object]:
        org_id = await self._client.resolve_org_id(org)
        return cast(
            dict[str, object],
            await self._client._request_json(
            "DELETE",
            f"/apis/ngpc.rxt.io/v1/namespaces/{org_id}/ondemandnodepools/{name}",
            ),
        )
