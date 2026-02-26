from __future__ import annotations

from rsspot.models.cloudspaces import VMCloudSpaceListResponse
from rsspot.state import StateStore
from rsspot.workflows import RegistrationStatus, RegistrationWorkflow


def test_registration_candidates_and_state_markers() -> None:
    vmcloudspaces = VMCloudSpaceListResponse.model_validate(
        {
            "items": [
                {
                    "metadata": {"name": "cloudspace-a"},
                    "spec": {"region": "us-central-dfw-1"},
                    "status": {
                        "assignedServers": {
                            "server-1": {
                                "displayName": "vm-a",
                                "serverName": "vm-uid-a",
                                "nodePoolName": "pool-a",
                            }
                        }
                    },
                }
            ]
        }
    )

    state = StateStore()
    try:
        workflow = RegistrationWorkflow(state)
        candidates = workflow.list_candidates(vmcloudspaces, org_id="org-1", omni_cluster="cluster-a")
        assert len(candidates) == 1
        candidate = candidates[0]

        workflow.mark_discovered(candidate)
        workflow.mark_token_issued(candidate, token_id="token-1")
        workflow.mark_registered(candidate)

        record = workflow.get_record(candidate.registration_key)
        assert record is not None
        assert record.status == RegistrationStatus.REGISTERED
        assert record.vm_uid == "vm-uid-a"
    finally:
        state.close()
