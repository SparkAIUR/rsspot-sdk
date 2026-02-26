"""Transparent caching policy for Spot API calls."""

from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from rsspot.config.models import CacheConfig
from rsspot.state import StateStore


@dataclass(slots=True)
class CacheDecision:
    enabled: bool
    ttl: float = 0.0


class FrontCache:
    """Small in-memory front cache for reducing sqlite roundtrips."""

    def __init__(self, max_entries: int) -> None:
        self.max_entries = max_entries
        self._data: OrderedDict[str, str] = OrderedDict()

    def get(self, key: str) -> str | None:
        if key not in self._data:
            return None
        value = self._data.pop(key)
        self._data[key] = value
        return value

    def set(self, key: str, value: str) -> None:
        if key in self._data:
            self._data.pop(key)
        self._data[key] = value
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)

    def invalidate_prefixes(self, prefixes: list[str]) -> None:
        keys_to_delete = [key for key in self._data if any(key.startswith(p) for p in prefixes)]
        for key in keys_to_delete:
            self._data.pop(key, None)


class CacheController:
    def __init__(self, config: CacheConfig, state: StateStore) -> None:
        self.config = config
        self.state = state
        self.front = FrontCache(max_entries=max(1, min(config.max_entries, 2048)))

    def cache_key(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None,
        json_data: dict[str, Any] | None,
    ) -> str:
        p_json = json.dumps(params or {}, sort_keys=True, separators=(",", ":"))
        d_json = json.dumps(json_data or {}, sort_keys=True, separators=(",", ":"))
        return f"{method.upper()}:{path}:{p_json}:{d_json}"

    def _resolve_ttl(self, method: str, path: str) -> float:
        key = f"{method.upper()}:{path}"
        if key in self.config.ttl_defaults:
            return float(self.config.ttl_defaults[key])

        for candidate, ttl in self.config.ttl_defaults.items():
            if not candidate.endswith("*"):
                continue
            prefix = candidate[:-1]
            if key.startswith(prefix):
                return float(ttl)

        return float(self.config.default_ttl)

    def decision(self, method: str, path: str) -> CacheDecision:
        if not self.config.enabled:
            return CacheDecision(enabled=False)

        if method.upper() != "GET":
            return CacheDecision(enabled=False)

        return CacheDecision(enabled=True, ttl=self._resolve_ttl(method, path))

    def get(self, key: str) -> dict[str, Any] | None:
        front = self.front.get(key)
        if front is not None:
            return json.loads(front)

        payload = self.state.cache_get(key)
        if payload is None:
            return None

        self.front.set(key, payload)
        return json.loads(payload)

    def set(self, key: str, payload: dict[str, Any], ttl: float) -> None:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        self.front.set(key, encoded)
        self.state.cache_set(key, encoded, ttl)
        self.state.cache_prune_to_limit(self.config.max_entries)

    def invalidate_after_mutation(self, path: str) -> None:
        normalized = path.split("?", 1)[0]
        segments = [segment for segment in normalized.split("/") if segment]
        if len(segments) < 3:
            return

        # Keep invalidation conservative by broad API domain prefix.
        prefix = "/" + "/".join(segments[:3])
        self.front.invalidate_prefixes([f"GET:{prefix}"])
        self.state.cache_invalidate_prefixes([f"GET:{prefix}"])
