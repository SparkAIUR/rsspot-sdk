# Changelog

All notable changes to `rsspot` are documented in this file.

The format is based on Keep a Changelog, and this project follows semantic versioning.

## [Unreleased]

## [0.3.0] - 2026-02-26

### Added
- `rsspot pricing build` command for multi-strategy pool/region recommendations with:
  - `--nodes`, `--gen`, `--risk`, `--balanced`
  - optional `--regions`, `--classes`, `--min-hour`, `--max-hour`, `--min-month`, `--max-month`
- Internal pricing optimizer module (`src/rsspot/pricing_optimizer.py`) with:
  - normalized CPU/RAM/price parsing
  - derived capacity/value metrics using CPU, RAM, and generation multiplier
  - structured scenario outputs for `max_performance`, `max_value`, and `balanced`

### Changed
- `rsspot pricing list` now supports:
  - `--nodes` multiplier
  - `--min-cpu`, `--max-cpu`, `--class`, `--gen` filters
- `pricing list` and `pricing build` now default to rich table output unless `--output` is explicitly set to `json`/`yaml`.
- CLI/docs examples updated for pricing filters and recommendation workflows.

## [0.2.0] - 2026-02-26

### Added
- Unified client architecture in `src/rsspot/client/`:
  - `AsyncSpotClient` async core
  - `SpotClient` unified sync/async wrapper
  - singleton/context helpers (`configure`, `get_client`, `get_async_client`, `use_*`)
- Persistent sqlite state subsystem in `src/rsspot/state/`:
  - preferences
  - HTTP cache
  - redacted CLI command history
  - VM registration ledger
- Transport subsystem in `src/rsspot/http/` with explicit retry/cache policies.
- VM registration workflow primitives in `src/rsspot/workflows/registration.py`.
- CLI config/history commands:
  - `rsspot config info`
  - `rsspot config set-default-profile|org|region`
  - `rsspot config history info|clear`
- `CHANGELOG.md` and docs page linkage.

### Changed
- **Breaking:** `SpotClient` is now a unified sync/async client surface.
- **Breaking:** public client module moved from `src/rsspot/client.py` to `src/rsspot/client/*` package layout.
- Config canonical path changed to `~/.config/rsspot/config.yml` search set.
- Config loading now supports runtime dict/model precedence and explicit resolution source metadata.
- Legacy `~/.spot_config` is now auto-migrated to canonical config path.
- Version bumped to `0.2.0`.

### Removed
- Legacy monolithic client module `src/rsspot/client.py`.
- Old `get_client(..., singleton=...)` construction mode.

### Fixed
- Sync wrapper now safely closes coroutine objects when called from an active event loop guard path.

### Tests
- Updated test suite for unified client behavior/config migration.
- Added state persistence tests and registration workflow tests.

## [0.1.0] - 2026-02-25

### Added
- Initial async-first Rackspace Spot SDK + CLI.
- Profile-based config management and typed service/models.
- Basic singleton helper cache and core auth/retry flow.
