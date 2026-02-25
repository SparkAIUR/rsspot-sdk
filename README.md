# rsspot

`rsspot` is an async-first Python SDK and CLI for Rackspace Spot.

## Highlights

- Async-native client built on `httpx.AsyncClient`
- Strong typing via `pydantic` models
- Multi-account profile switching (`yaml` / `json` / `toml`)
- Global singleton client (`get_client`) plus explicit clients
- `uv`-managed project and tooling
- OpenAPI sync/index scripts for upstream tracking

## Quickstart

```bash
uv sync
uv run rsspot organizations list --output table
```

## Configuration

Default config path: `~/.spot_config`

Supports:
- flat schema (`org`, `refreshToken`, `accessToken`, `region`)
- profile schema (`active_profile`, `profiles.<name>.*`)
- file formats: YAML / JSON / TOML (`~/.spot_config` extensionless is supported)

## Basic SDK usage

```python
import asyncio
from rsspot import get_client


async def main() -> None:
    client = get_client(profile="default")
    orgs = await client.organizations.list()
    print([org.name for org in orgs.organizations])


asyncio.run(main())
```

## CLI examples

```bash
uv run rsspot configure --profile prod --org songzcorp --region us-central-dfw-1 --refresh-token "$SPOT_REFRESH_TOKEN"
uv run rsspot profiles list
uv run rsspot server-classes list --region us-central-dfw-1 --output table
uv run rsspot inventory vmcloudspaces --org songzcorp
```

## OpenAPI tracking

```bash
uv run python scripts/sync_openapi.py
uv run python scripts/generate_openapi_index.py
```

## Development

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -q
```

Additional docs:
- `docs/configuration.md`
- `docs/openapi.md`
