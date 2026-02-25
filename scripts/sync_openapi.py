#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

DEFAULT_URLS = [
    "https://spot.rackspace.com/openapi/v2",
    "https://spot.rackspace.com/openapi.json",
    "https://spot.rackspace.com/swagger.json",
]


def fetch_openapi(url: str, *, token: str | None = None) -> dict[str, Any]:
    headers: dict[str, str] = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("OpenAPI response is not a JSON object")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Rackspace Spot OpenAPI schema")
    parser.add_argument("--url", help="Explicit OpenAPI URL")
    parser.add_argument(
        "--out",
        default="openapi/openapi.json",
        help="Output path for schema snapshot",
    )
    parser.add_argument(
        "--metadata",
        default="openapi/metadata.json",
        help="Output path for fetch metadata",
    )
    args = parser.parse_args()

    urls = [args.url] if args.url else [os.getenv("RSSPOT_OPENAPI_URL", "").strip(), *DEFAULT_URLS]
    urls = [item for item in urls if item]
    if not urls:
        raise RuntimeError("no OpenAPI URL candidates were provided")

    token = os.getenv("RSSPOT_ACCESS_TOKEN") or os.getenv("RACKSPACE_ACCESS_TOKEN")
    errors: list[str] = []
    payload: dict[str, Any] | None = None
    source_url = ""
    for url in urls:
        try:
            payload = fetch_openapi(url, token=token)
            source_url = url
            break
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {exc}")

    if payload is None:
        joined = "\n".join(errors)
        raise RuntimeError(f"failed to fetch OpenAPI schema from all candidates:\n{joined}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    metadata = {
        "source_url": source_url,
        "fetched_at": datetime.now(UTC).isoformat(),
        "version": payload.get("openapi") or payload.get("swagger"),
        "title": payload.get("info", {}).get("title") if isinstance(payload.get("info"), dict) else None,
    }
    metadata_path = Path(args.metadata)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    print(f"saved OpenAPI schema to {out_path} from {source_url}")


if __name__ == "__main__":
    main()
