# OpenAPI Workflow

`rsspot` tracks Rackspace Spot API drift with a pinned schema snapshot and generated operation index.

## 1. Sync schema

```bash
uv run python scripts/sync_openapi.py
```

Optional overrides:

```bash
RSSPOT_OPENAPI_URL=https://spot.rackspace.com/openapi/v2 \
RSSPOT_ACCESS_TOKEN=<id_token> \
uv run python scripts/sync_openapi.py
```

Generated files:

- `openapi/openapi.json`
- `openapi/metadata.json`

## 2. Generate operation index

```bash
uv run python scripts/generate_openapi_index.py
```

Generated file:

- `src/rsspot/generated/openapi_index.py`

This index provides a low-cost way to diff new/removed endpoints during reviews. For now, models are still curated by hand to preserve readability and typing quality.
