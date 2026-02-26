"""Persistent SDK state (preferences, HTTP cache, CLI history, registration ledger)."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class StateStore:
    """SQLite-backed state for preferences, HTTP cache, CLI history, and registration ledger."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser().resolve() if path else None
        self._lock = threading.RLock()

        if self.path is None:
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.path), check_same_thread=False)

        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS preferences (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL,
                  updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS http_cache (
                  key TEXT PRIMARY KEY,
                  payload TEXT NOT NULL,
                  expires_at REAL NOT NULL,
                  created_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_http_cache_expires_at ON http_cache(expires_at);

                CREATE TABLE IF NOT EXISTS command_history (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  created_at REAL NOT NULL,
                  command TEXT NOT NULL,
                  argv_json TEXT NOT NULL,
                  profile TEXT,
                  org TEXT,
                  region TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_command_history_created_at ON command_history(created_at);
                CREATE INDEX IF NOT EXISTS idx_command_history_command ON command_history(command);

                CREATE TABLE IF NOT EXISTS registration_ledger (
                  registration_key TEXT PRIMARY KEY,
                  vm_uid TEXT NOT NULL,
                  org_id TEXT,
                  vmcloudspace TEXT,
                  vmpool TEXT,
                  vm_name TEXT,
                  omni_cluster TEXT,
                  token_id TEXT,
                  token_expires_at REAL,
                  status TEXT NOT NULL,
                  last_error TEXT,
                  payload_json TEXT,
                  updated_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_registration_ledger_status ON registration_ledger(status);
                CREATE INDEX IF NOT EXISTS idx_registration_ledger_vm_uid ON registration_ledger(vm_uid);
                """
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def set_preference(self, key: str, value: str) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO preferences (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, now),
            )
            self._conn.commit()

    def get_preference(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
            if row is None:
                return None
            return str(row[0])

    def set_json_preference(self, key: str, value: dict[str, str]) -> None:
        self.set_preference(key, json.dumps(value, sort_keys=True))

    def get_json_preference(self, key: str) -> dict[str, str]:
        raw = self.get_preference(key)
        if raw is None:
            return {}
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return {str(k): str(v) for k, v in payload.items()}
        return {}

    def cache_get(self, key: str) -> str | None:
        now = time.time()
        with self._lock:
            row = self._conn.execute(
                "SELECT payload, expires_at FROM http_cache WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            payload, expires_at = str(row[0]), float(row[1])
            if expires_at < now:
                self._conn.execute("DELETE FROM http_cache WHERE key = ?", (key,))
                self._conn.commit()
                return None
            return payload

    def cache_set(self, key: str, payload: str, ttl_seconds: float) -> None:
        now = time.time()
        expires_at = now + ttl_seconds
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO http_cache (key, payload, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                  payload=excluded.payload,
                  expires_at=excluded.expires_at,
                  created_at=excluded.created_at
                """,
                (key, payload, expires_at, now),
            )
            self._conn.commit()

    def cache_invalidate_prefixes(self, prefixes: list[str]) -> None:
        with self._lock:
            for prefix in prefixes:
                self._conn.execute("DELETE FROM http_cache WHERE key LIKE ?", (f"{prefix}%",))
            self._conn.commit()

    def cache_gc(self) -> int:
        now = time.time()
        with self._lock:
            cur = self._conn.execute("DELETE FROM http_cache WHERE expires_at < ?", (now,))
            self._conn.commit()
            return int(cur.rowcount)

    def cache_prune_to_limit(self, max_entries: int) -> None:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM http_cache").fetchone()
            total = int(row[0]) if row else 0
            if total <= max_entries:
                return

            extra = total - max_entries
            self._conn.execute(
                """
                DELETE FROM http_cache
                WHERE key IN (
                    SELECT key FROM http_cache ORDER BY created_at ASC LIMIT ?
                )
                """,
                (extra,),
            )
            self._conn.commit()

    def history_add(
        self,
        *,
        command: str,
        argv: list[str],
        profile: str | None,
        org: str | None,
        region: str | None,
        max_entries: int = 2000,
    ) -> None:
        now = time.time()
        argv_json = json.dumps(argv, ensure_ascii=True)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO command_history (created_at, command, argv_json, profile, org, region)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now, command, argv_json, profile, org, region),
            )
            self._conn.commit()
            self.history_prune_to_limit(max_entries)

    def history_prune_to_limit(self, max_entries: int) -> None:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM command_history").fetchone()
            total = int(row[0]) if row else 0
            if total <= max_entries:
                return

            extra = total - max_entries
            self._conn.execute(
                """
                DELETE FROM command_history
                WHERE id IN (
                    SELECT id FROM command_history ORDER BY created_at ASC LIMIT ?
                )
                """,
                (extra,),
            )
            self._conn.commit()

    def history_count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM command_history").fetchone()
            return int(row[0]) if row else 0

    def history_clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM command_history")
            self._conn.commit()

    def history_list(self, *, limit: int = 100) -> list[dict[str, str | int | float | None]]:
        capped = max(1, min(limit, 2000))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, created_at, command, argv_json, profile, org, region
                FROM command_history
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (capped,),
            ).fetchall()

        result: list[dict[str, str | int | float | None]] = []
        for row in rows:
            result.append(
                {
                    "id": int(row[0]),
                    "created_at": float(row[1]),
                    "command": str(row[2]),
                    "argv_json": str(row[3]),
                    "profile": str(row[4]) if row[4] is not None else None,
                    "org": str(row[5]) if row[5] is not None else None,
                    "region": str(row[6]) if row[6] is not None else None,
                }
            )
        return result

    def history_suggest(self, prefix: str, *, limit: int = 20) -> list[str]:
        needle = prefix.strip()
        capped = max(1, min(limit, 200))

        if not needle:
            with self._lock:
                rows = self._conn.execute(
                    """
                    SELECT command
                    FROM command_history
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (capped,),
                ).fetchall()
        else:
            with self._lock:
                rows = self._conn.execute(
                    """
                    SELECT command
                    FROM command_history
                    WHERE command LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (f"{needle}%", capped),
                ).fetchall()

        seen: set[str] = set()
        suggestions: list[str] = []
        for row in rows:
            command = str(row[0])
            if command in seen:
                continue
            seen.add(command)
            suggestions.append(command)
        return suggestions

    def registration_upsert(
        self,
        registration_key: str,
        *,
        vm_uid: str,
        status: str,
        org_id: str | None = None,
        vmcloudspace: str | None = None,
        vmpool: str | None = None,
        vm_name: str | None = None,
        omni_cluster: str | None = None,
        token_id: str | None = None,
        token_expires_at: float | None = None,
        last_error: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        now = time.time()
        payload_json = json.dumps(payload, sort_keys=True) if payload is not None else None
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO registration_ledger (
                    registration_key,
                    vm_uid,
                    org_id,
                    vmcloudspace,
                    vmpool,
                    vm_name,
                    omni_cluster,
                    token_id,
                    token_expires_at,
                    status,
                    last_error,
                    payload_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(registration_key) DO UPDATE SET
                    vm_uid=excluded.vm_uid,
                    org_id=excluded.org_id,
                    vmcloudspace=excluded.vmcloudspace,
                    vmpool=excluded.vmpool,
                    vm_name=excluded.vm_name,
                    omni_cluster=excluded.omni_cluster,
                    token_id=excluded.token_id,
                    token_expires_at=excluded.token_expires_at,
                    status=excluded.status,
                    last_error=excluded.last_error,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    registration_key,
                    vm_uid,
                    org_id,
                    vmcloudspace,
                    vmpool,
                    vm_name,
                    omni_cluster,
                    token_id,
                    token_expires_at,
                    status,
                    last_error,
                    payload_json,
                    now,
                ),
            )
            self._conn.commit()

    def registration_get(self, registration_key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT registration_key, vm_uid, org_id, vmcloudspace, vmpool, vm_name,
                       omni_cluster, token_id, token_expires_at, status, last_error,
                       payload_json, updated_at
                FROM registration_ledger
                WHERE registration_key = ?
                """,
                (registration_key,),
            ).fetchone()

        if row is None:
            return None
        payload = json.loads(row[11]) if row[11] else None
        return {
            "registration_key": str(row[0]),
            "vm_uid": str(row[1]),
            "org_id": str(row[2]) if row[2] is not None else None,
            "vmcloudspace": str(row[3]) if row[3] is not None else None,
            "vmpool": str(row[4]) if row[4] is not None else None,
            "vm_name": str(row[5]) if row[5] is not None else None,
            "omni_cluster": str(row[6]) if row[6] is not None else None,
            "token_id": str(row[7]) if row[7] is not None else None,
            "token_expires_at": float(row[8]) if row[8] is not None else None,
            "status": str(row[9]),
            "last_error": str(row[10]) if row[10] is not None else None,
            "payload": payload,
            "updated_at": float(row[12]),
        }

    def registration_list(self, *, status: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        capped = max(1, min(limit, 5000))
        with self._lock:
            if status is None:
                rows = self._conn.execute(
                    """
                    SELECT registration_key
                    FROM registration_ledger
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (capped,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT registration_key
                    FROM registration_ledger
                    WHERE status = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (status, capped),
                ).fetchall()

        output: list[dict[str, Any]] = []
        for row in rows:
            record = self.registration_get(str(row[0]))
            if record is not None:
                output.append(record)
        return output


def default_state_path(config_path: str | Path | None) -> Path:
    if config_path is None:
        return (Path.home() / ".config" / "rsspot" / "state.db").expanduser().resolve()

    cfg = Path(config_path).expanduser()
    return (cfg.parent / "state.db").resolve()
