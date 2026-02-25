from __future__ import annotations

from pydantic import Field

from rsspot.models.common import SpotModel


class Organization(SpotModel):
    name: str
    id: str


class OrganizationsResponse(SpotModel):
    organizations: list[Organization] = Field(default_factory=list)
