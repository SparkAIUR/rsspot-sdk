"""VM registration workflow primitives for external orchestrators."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from rsspot.models.cloudspaces import VMCloudSpaceListResponse
from rsspot.state import StateStore


class RegistrationStatus(StrEnum):
    DISCOVERED = "discovered"
    TOKEN_ISSUED = "token_issued"
    SUBMITTED = "submitted"
    REGISTERED = "registered"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(slots=True)
class RegistrationCandidate:
    registration_key: str
    vm_uid: str
    vm_name: str
    org_id: str | None
    vmcloudspace: str
    vmpool: str | None
    omni_cluster: str | None


@dataclass(slots=True)
class RegistrationLedgerRecord:
    registration_key: str
    vm_uid: str
    status: RegistrationStatus
    org_id: str | None = None
    vmcloudspace: str | None = None
    vmpool: str | None = None
    vm_name: str | None = None
    omni_cluster: str | None = None
    token_id: str | None = None
    token_expires_at: float | None = None
    last_error: str | None = None
    payload: dict[str, Any] | None = None


class RegistrationWorkflow:
    """Idempotent VM registration state transitions backed by sqlite."""

    def __init__(self, state: StateStore) -> None:
        self.state = state

    @staticmethod
    def registration_key(
        *,
        vm_uid: str,
        org_id: str | None,
        vmcloudspace: str,
        vmpool: str | None,
        omni_cluster: str | None,
    ) -> str:
        raw = "|".join(
            [
                vm_uid,
                org_id or "",
                vmcloudspace,
                vmpool or "",
                omni_cluster or "",
            ]
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"vmreg-{digest[:32]}"

    def list_candidates(
        self,
        vmcloudspaces: VMCloudSpaceListResponse,
        *,
        org_id: str | None = None,
        omni_cluster: str | None = None,
    ) -> list[RegistrationCandidate]:
        candidates: list[RegistrationCandidate] = []
        for space in vmcloudspaces.items:
            cloudspace_name = space.metadata.name
            for key, assigned in space.status.assignedServers.items():
                vm_uid = assigned.serverName or key
                vm_name = assigned.displayName or assigned.serverName or key
                vmpool = assigned.nodePoolName
                reg_key = self.registration_key(
                    vm_uid=vm_uid,
                    org_id=org_id,
                    vmcloudspace=cloudspace_name,
                    vmpool=vmpool,
                    omni_cluster=omni_cluster,
                )
                candidates.append(
                    RegistrationCandidate(
                        registration_key=reg_key,
                        vm_uid=vm_uid,
                        vm_name=vm_name,
                        org_id=org_id,
                        vmcloudspace=cloudspace_name,
                        vmpool=vmpool,
                        omni_cluster=omni_cluster,
                    )
                )
        return candidates

    def mark_discovered(self, candidate: RegistrationCandidate, *, payload: dict[str, Any] | None = None) -> None:
        self.state.registration_upsert(
            candidate.registration_key,
            vm_uid=candidate.vm_uid,
            org_id=candidate.org_id,
            vmcloudspace=candidate.vmcloudspace,
            vmpool=candidate.vmpool,
            vm_name=candidate.vm_name,
            omni_cluster=candidate.omni_cluster,
            status=RegistrationStatus.DISCOVERED,
            payload=payload,
        )

    def mark_token_issued(
        self,
        candidate: RegistrationCandidate,
        *,
        token_id: str,
        token_expires_at: float | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.state.registration_upsert(
            candidate.registration_key,
            vm_uid=candidate.vm_uid,
            org_id=candidate.org_id,
            vmcloudspace=candidate.vmcloudspace,
            vmpool=candidate.vmpool,
            vm_name=candidate.vm_name,
            omni_cluster=candidate.omni_cluster,
            token_id=token_id,
            token_expires_at=token_expires_at,
            status=RegistrationStatus.TOKEN_ISSUED,
            payload=payload,
        )

    def mark_submitted(self, candidate: RegistrationCandidate, *, payload: dict[str, Any] | None = None) -> None:
        self.state.registration_upsert(
            candidate.registration_key,
            vm_uid=candidate.vm_uid,
            org_id=candidate.org_id,
            vmcloudspace=candidate.vmcloudspace,
            vmpool=candidate.vmpool,
            vm_name=candidate.vm_name,
            omni_cluster=candidate.omni_cluster,
            status=RegistrationStatus.SUBMITTED,
            payload=payload,
        )

    def mark_registered(self, candidate: RegistrationCandidate, *, payload: dict[str, Any] | None = None) -> None:
        self.state.registration_upsert(
            candidate.registration_key,
            vm_uid=candidate.vm_uid,
            org_id=candidate.org_id,
            vmcloudspace=candidate.vmcloudspace,
            vmpool=candidate.vmpool,
            vm_name=candidate.vm_name,
            omni_cluster=candidate.omni_cluster,
            status=RegistrationStatus.REGISTERED,
            payload=payload,
        )

    def mark_failed(
        self,
        candidate: RegistrationCandidate,
        *,
        error: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.state.registration_upsert(
            candidate.registration_key,
            vm_uid=candidate.vm_uid,
            org_id=candidate.org_id,
            vmcloudspace=candidate.vmcloudspace,
            vmpool=candidate.vmpool,
            vm_name=candidate.vm_name,
            omni_cluster=candidate.omni_cluster,
            status=RegistrationStatus.FAILED,
            last_error=error,
            payload=payload,
        )

    def mark_skipped(self, candidate: RegistrationCandidate, *, payload: dict[str, Any] | None = None) -> None:
        self.state.registration_upsert(
            candidate.registration_key,
            vm_uid=candidate.vm_uid,
            org_id=candidate.org_id,
            vmcloudspace=candidate.vmcloudspace,
            vmpool=candidate.vmpool,
            vm_name=candidate.vm_name,
            omni_cluster=candidate.omni_cluster,
            status=RegistrationStatus.SKIPPED,
            payload=payload,
        )

    def get_record(self, registration_key: str) -> RegistrationLedgerRecord | None:
        row = self.state.registration_get(registration_key)
        if row is None:
            return None

        return RegistrationLedgerRecord(
            registration_key=row["registration_key"],
            vm_uid=row["vm_uid"],
            status=RegistrationStatus(row["status"]),
            org_id=row.get("org_id"),
            vmcloudspace=row.get("vmcloudspace"),
            vmpool=row.get("vmpool"),
            vm_name=row.get("vm_name"),
            omni_cluster=row.get("omni_cluster"),
            token_id=row.get("token_id"),
            token_expires_at=row.get("token_expires_at"),
            last_error=row.get("last_error"),
            payload=row.get("payload"),
        )
