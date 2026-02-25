from __future__ import annotations

from datetime import datetime

from pydantic import Field

from rsspot.models.common import Metadata, SpotModel


class Autoscaling(SpotModel):
    enabled: bool = False
    minNodes: int = 0
    maxNodes: int = 0


class SpotNodePoolSpec(SpotModel):
    serverClass: str | None = None
    desired: int | None = None
    cloudSpace: str | None = None
    bidPrice: str | None = None
    customAnnotations: dict[str, str] = Field(default_factory=dict)
    customLabels: dict[str, str] = Field(default_factory=dict)
    customTaints: list[dict[str, str]] = Field(default_factory=list)
    autoscaling: Autoscaling | None = None


class SpotNodePoolStatus(SpotModel):
    bidStatus: str | None = None
    wonCount: int | None = None


class SpotNodePoolItem(SpotModel):
    apiVersion: str | None = None
    kind: str | None = None
    metadata: Metadata
    spec: SpotNodePoolSpec
    status: SpotNodePoolStatus | None = None


class SpotNodePoolListResponse(SpotModel):
    items: list[SpotNodePoolItem] = Field(default_factory=list)


class OnDemandNodePoolSpec(SpotModel):
    serverClass: str | None = None
    desired: int | None = None
    cloudSpace: str | None = None
    customAnnotations: dict[str, str] = Field(default_factory=dict)
    customLabels: dict[str, str] = Field(default_factory=dict)
    customTaints: list[dict[str, str]] = Field(default_factory=list)
    autoscaling: Autoscaling | None = None


class OnDemandNodePoolStatus(SpotModel):
    reservedStatus: str | None = None
    reservedCount: int | None = None


class OnDemandNodePoolItem(SpotModel):
    apiVersion: str | None = None
    kind: str | None = None
    metadata: Metadata
    spec: OnDemandNodePoolSpec
    status: OnDemandNodePoolStatus | None = None


class OnDemandNodePoolListResponse(SpotModel):
    items: list[OnDemandNodePoolItem] = Field(default_factory=list)


class SpotNodePoolUpsert(SpotModel):
    """User-facing request model for spot nodepool create/update."""

    name: str
    cloudspace: str
    server_class: str
    desired: int = 1
    bid_price: str
    custom_annotations: dict[str, str] = Field(default_factory=dict)
    custom_labels: dict[str, str] = Field(default_factory=dict)
    custom_taints: list[dict[str, str]] = Field(default_factory=list)
    autoscaling: Autoscaling = Field(default_factory=Autoscaling)


class OnDemandNodePoolUpsert(SpotModel):
    """User-facing request model for ondemand nodepool create/update."""

    name: str
    cloudspace: str
    server_class: str
    desired: int = 1
    custom_annotations: dict[str, str] = Field(default_factory=dict)
    custom_labels: dict[str, str] = Field(default_factory=dict)
    custom_taints: list[dict[str, str]] = Field(default_factory=list)
    autoscaling: Autoscaling = Field(default_factory=Autoscaling)


class NodePoolSummary(SpotModel):
    name: str
    cloudspace: str
    server_class: str
    desired: int
    status: str | None = None
    created_at: datetime | None = None
