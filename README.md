# rsspot

`rsspot` is a Python SDK and CLI for Rackspace Spot with unified sync/async ergonomics, sqlite-backed runtime state, and profile-based configuration.

## Highlights

- Unified client API:
  - `SpotClient` for sync + async access on one object
  - `AsyncSpotClient` for explicit async-only usage
- Persistent sqlite state (`state.db`) for:
  - defaults/preferences
  - HTTP cache
  - redacted CLI command history
  - VM registration ledger entries
- Config precedence + migration:
  - new default path: `~/.config/rsspot/config.yml`
  - legacy `~/.spot_config` auto-imported/migrated
- Strong typing via `pydantic` models
- Multi-profile workflows + global singleton helpers
- OpenAPI sync/index scripts for upstream tracking

## Install

```bash
uv sync
```

## Quickstart (CLI)

```bash
uv run rsspot configure \
  --profile default \
  --org <org-name> \
  --region us-central-dfw-1 \
  --refresh-token "$SPOT_REFRESH_TOKEN"

uv run rsspot organizations list --output table
```

## Quickstart (SDK)

### Unified client

```python
from rsspot import SpotClient

client = SpotClient(profile="default")
orgs = client.organizations.list()
print([org.name for org in orgs.organizations])
client.close()
```

```python
import asyncio
from rsspot import SpotClient

async def main() -> None:
    client = SpotClient(profile="default")
    orgs = await client.aorganizations.list()
    print([org.name for org in orgs.organizations])
    await client.aclose()

asyncio.run(main())
```

### Async-only client

```python
import asyncio
from rsspot import AsyncSpotClient

async def main() -> None:
    async with AsyncSpotClient(profile="default") as client:
        regions = await client.regions.list()
        print([r.name for r in regions])

asyncio.run(main())
```

## Configuration

Resolution precedence:
1. Runtime config dict/model passed to client constructor
2. Explicit `config_path=...`
3. Env path (`RSSPOT_CONFIG`, `RSSPOT_CONFIG_FILE`, `SPOT_CONFIG_FILE`)
4. Default search in `~/.config/rsspot/config.{yml,yaml,toml,json}`
5. Legacy fallback `~/.spot_config` (auto-migrated)

## VM Registration Workflow Primitives

`rsspot` includes registration state helpers for composing with external orchestrators (including separate `omni-sdk` scripts) without taking a direct dependency.

Core entrypoint:
- `rsspot.workflows.RegistrationWorkflow`

## OpenAPI Tracking

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

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
