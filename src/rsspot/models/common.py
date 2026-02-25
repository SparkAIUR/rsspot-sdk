from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SpotModel(BaseModel):
    """Base model with permissive extra handling for upstream compatibility."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Metadata(SpotModel):
    name: str
    namespace: str | None = None
    uid: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    creationTimestamp: datetime | None = None


class Condition(SpotModel):
    type: str
    status: str
    lastTransitionTime: datetime | None = None
