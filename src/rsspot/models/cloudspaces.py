from __future__ import annotations

from datetime import datetime

from pydantic import Field

from rsspot.models.common import Condition, Metadata, SpotModel


class AssignedServer(SpotModel):
    cpu: str | None = None
    displayName: str | None = None
    ipAddress: str | None = None
    nodePoolName: str | None = None
    serverClassName: str | None = None
    serverName: str | None = None
    serverType: str | None = None


class CloudspaceSpec(SpotModel):
    deploymentType: str | None = None
    cloud: str | None = None
    region: str | None = None
    webhook: str | None = None
    cni: str | None = None
    kubernetesVersion: str | None = None
    HAControlPlane: bool | None = None
    gpuEnabled: bool | None = None


class CloudspaceStatus(SpotModel):
    apiServerEndpoint: str | None = None
    assignedServers: dict[str, AssignedServer] = Field(default_factory=dict)
    conditions: list[Condition] = Field(default_factory=list)
    health: str | None = None
    phase: str | None = None
    reason: str | None = None
    firstReadyTimestamp: datetime | None = None


class CloudspaceItem(SpotModel):
    apiVersion: str | None = None
    kind: str | None = None
    metadata: Metadata
    spec: CloudspaceSpec
    status: CloudspaceStatus | None = None


class CloudspaceListResponse(SpotModel):
    items: list[CloudspaceItem] = Field(default_factory=list)


class CloudspaceCreateSpec(SpotModel):
    """Normalized create spec for cloudspace creation.

    Example:
        >>> CloudspaceCreateSpec(name="demo", region="us-central-dfw-1")
    """

    name: str
    region: str
    kubernetes_version: str = "1.31.1"
    deployment_type: str = "gen2"
    cloud: str = "default"
    cni: str = "calico"
    preemption_webhook_url: str | None = None
    ha_control_plane: bool = False
    gpu_enabled: bool = False


class KubeconfigData(SpotModel):
    kubeconfig: str


class KubeconfigResponse(SpotModel):
    data: KubeconfigData


class VMCloudSpaceSpec(SpotModel):
    bidRequests: list[str] = Field(default_factory=list)
    region: str | None = None


class VMCloudSpaceStatus(SpotModel):
    assignedServers: dict[str, AssignedServer] = Field(default_factory=dict)
    conditions: list[Condition] = Field(default_factory=list)
    firstReadyTimestamp: datetime | None = None
    health: str | None = None
    phase: str | None = None


class VMCloudSpaceItem(SpotModel):
    apiVersion: str | None = None
    kind: str | None = None
    metadata: Metadata
    spec: VMCloudSpaceSpec
    status: VMCloudSpaceStatus


class VMCloudSpaceListResponse(SpotModel):
    items: list[VMCloudSpaceItem] = Field(default_factory=list)
