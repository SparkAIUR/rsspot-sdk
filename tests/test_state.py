from __future__ import annotations

from rsspot.state import StateStore


def test_history_add_and_count() -> None:
    state = StateStore()
    try:
        state.history_add(
            command="rsspot organizations list",
            argv=["rsspot", "organizations", "list"],
            profile="default",
            org="sparkai",
            region="us-central-dfw-1",
        )
        assert state.history_count() == 1
        rows = state.history_list(limit=5)
        assert len(rows) == 1
        assert rows[0]["command"].startswith("rsspot organizations")
        assert rows[0]["profile"] == "default"
    finally:
        state.close()


def test_history_prunes_to_limit() -> None:
    state = StateStore()
    try:
        for i in range(6):
            state.history_add(
                command=f"rsspot cmd {i}",
                argv=["rsspot", "cmd", str(i)],
                profile="default",
                org=None,
                region=None,
                max_entries=3,
            )
        assert state.history_count() == 3
        rows = state.history_list(limit=10)
        commands = [str(row["command"]) for row in rows]
        assert commands[0] == "rsspot cmd 5"
        assert commands[-1] == "rsspot cmd 3"
    finally:
        state.close()


def test_registration_ledger_upsert_and_get() -> None:
    state = StateStore()
    try:
        state.registration_upsert(
            "vmreg-1",
            vm_uid="vm-1",
            org_id="org-1",
            vmcloudspace="cs-1",
            vmpool="pool-a",
            vm_name="vm-a",
            omni_cluster="cluster-a",
            status="discovered",
            payload={"foo": "bar"},
        )
        row = state.registration_get("vmreg-1")
        assert row is not None
        assert row["vm_uid"] == "vm-1"
        assert row["status"] == "discovered"
        assert row["payload"] == {"foo": "bar"}

        state.registration_upsert(
            "vmreg-1",
            vm_uid="vm-1",
            status="registered",
        )
        updated = state.registration_get("vmreg-1")
        assert updated is not None
        assert updated["status"] == "registered"
    finally:
        state.close()
