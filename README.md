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

### Pricing Explorer + Builder

```bash
# default output is a rich table when --output is not explicitly set
uv run rsspot pricing list --region us-central-dfw-1 --class gp,ch --min-cpu 4 --gen 2 --nodes 5

# explicit machine-readable output stays json/yaml
uv run rsspot -o json pricing list --class gp --max-cpu 8 --nodes 10

# generate 3 recommendation strategies (max_performance, max_value, balanced)
uv run rsspot pricing build --nodes 5 --risk med --classes gp,ch,mh

# spread balanced strategy across multiple pools and constrain cluster hourly spend
uv run rsspot pricing build --nodes 5 --balanced --risk low --max-hour 0.25

# constrain by total cluster monthly spend
uv run rsspot pricing build --nodes 5 --min-month 50 --max-month 180
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

Expected schema is identical across `config.yaml`, `config.toml`, and `config.json`.

### `config.yaml`

```yaml
version: "2"
default_profile: prod
active_profile: prod
state_path: /Users/you/.config/rsspot/state.db

profiles:
  prod:
    org: sparkai
    region: us-central-dfw-1
    refresh_token: replace-me
    base_url: https://spot.rackspace.com
    oauth_url: https://spot.rackspace.com
    request_timeout_seconds: 30
    verify_ssl: true

preferences:
  default_profile: prod
  default_org: sparkai
  default_region: us-central-dfw-1

retry:
  max_attempts: 4
  base_delay: 0.2
  max_delay: 2.5
  jitter: 0.2

cache:
  enabled: true
  default_ttl: 5
  max_entries: 1000
  backend: sqlite
```

### `config.toml`

```toml
version = "2"
default_profile = "prod"
active_profile = "prod"
state_path = "/Users/you/.config/rsspot/state.db"

[profiles.prod]
org = "sparkai"
region = "us-central-dfw-1"
refresh_token = "replace-me"
base_url = "https://spot.rackspace.com"
oauth_url = "https://spot.rackspace.com"
request_timeout_seconds = 30
verify_ssl = true

[preferences]
default_profile = "prod"
default_org = "sparkai"
default_region = "us-central-dfw-1"

[retry]
max_attempts = 4
base_delay = 0.2
max_delay = 2.5
jitter = 0.2

[cache]
enabled = true
default_ttl = 5
max_entries = 1000
backend = "sqlite"
```

### `config.json`

```json
{
  "version": "2",
  "default_profile": "prod",
  "active_profile": "prod",
  "state_path": "/Users/you/.config/rsspot/state.db",
  "profiles": {
    "prod": {
      "org": "sparkai",
      "region": "us-central-dfw-1",
      "refresh_token": "replace-me",
      "base_url": "https://spot.rackspace.com",
      "oauth_url": "https://spot.rackspace.com",
      "request_timeout_seconds": 30,
      "verify_ssl": true
    }
  },
  "preferences": {
    "default_profile": "prod",
    "default_org": "sparkai",
    "default_region": "us-central-dfw-1"
  },
  "retry": {
    "max_attempts": 4,
    "base_delay": 0.2,
    "max_delay": 2.5,
    "jitter": 0.2
  },
  "cache": {
    "enabled": true,
    "default_ttl": 5,
    "max_entries": 1000,
    "backend": "sqlite"
  }
}
```

Notes:
- `profiles.<name>` is where profile-specific credentials/selectors live.
- Top-level `retry`/`cache` are defaults; profile-level `retry`/`cache` can override them.
- Legacy aliases like `refreshToken`, `clientId`, and `baseUrl` are still accepted.

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
