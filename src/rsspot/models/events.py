from __future__ import annotations

from pydantic import Field

from rsspot.models.common import SpotModel


class OrganizationEventsResponse(SpotModel):
    org_id: str
    cloudspace_id: str | None = None
    type: str | None = None
    events: list[tuple[str, str]] = Field(default_factory=list)
