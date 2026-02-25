from __future__ import annotations

from typing import cast

from rsspot.models.cloudspaces import (
    CloudspaceCreateSpec,
    CloudspaceItem,
    CloudspaceListResponse,
    KubeconfigResponse,
)
from rsspot.services.base import ServiceBase


class CloudspacesService(ServiceBase):
    """Cloudspace API operations."""

    async def list(self, org: str | None = None) -> CloudspaceListResponse:
        org_id = await self._client.resolve_org_id(org)
        data = await self._client._request_json(
            "GET",
            f"/apis/ngpc.rxt.io/v1/namespaces/{org_id}/cloudspaces",
        )
        return CloudspaceListResponse.model_validate(data)

    async def get(self, name: str, *, org: str | None = None) -> CloudspaceItem:
        org_id = await self._client.resolve_org_id(org)
        data = await self._client._request_json(
            "GET",
            f"/apis/ngpc.rxt.io/v1/namespaces/{org_id}/cloudspaces/{name}",
        )
        return CloudspaceItem.model_validate(data)

    async def create(self, spec: CloudspaceCreateSpec, *, org: str | None = None) -> dict[str, object]:
        org_id = await self._client.resolve_org_id(org)
        payload = {
            "apiVersion": "ngpc.rxt.io/v1",
            "kind": "CloudSpace",
            "metadata": {
                "name": spec.name,
                "namespace": org_id,
                "annotations": {},
            },
            "spec": {
                "deploymentType": spec.deployment_type,
                "cloud": spec.cloud,
                "region": spec.region,
                "webhook": spec.preemption_webhook_url,
                "cni": spec.cni,
                "kubernetesVersion": spec.kubernetes_version,
                "HAControlPlane": spec.ha_control_plane,
                "gpuEnabled": spec.gpu_enabled,
            },
        }
        return cast(
            dict[str, object],
            await self._client._request_json(
            "POST",
            f"/apis/ngpc.rxt.io/v1/namespaces/{org_id}/cloudspaces",
            json_data=payload,
            ),
        )

    async def delete(self, name: str, *, org: str | None = None) -> dict[str, object]:
        org_id = await self._client.resolve_org_id(org)
        return cast(
            dict[str, object],
            await self._client._request_json(
            "DELETE",
            f"/apis/ngpc.rxt.io/v1/namespaces/{org_id}/cloudspaces/{name}",
            ),
        )

    async def generate_kubeconfig(self, cloudspace_name: str, *, org: str | None = None) -> str:
        org_name = await self._client.resolve_org_name(org)
        refresh = self._client.refresh_token
        if refresh is None:
            raise ValueError("refresh_token is required to generate kubeconfig")

        payload = {
            "organization_name": org_name,
            "cloudspace_name": cloudspace_name,
            "refresh_token": refresh,
        }
        data = await self._client._request_json(
            "POST",
            "/apis/auth.ngpc.rxt.io/v1/generate-kubeconfig",
            json_data=payload,
        )
        response = KubeconfigResponse.model_validate(data)
        return response.data.kubeconfig
