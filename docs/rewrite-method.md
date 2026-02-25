# rsspot-sdk Docs Rewrite Method

This log captures exactly how the docs rewrite was authored so the same method can be encoded into `sparkify-docs`.

## Pass A: Source Inventory and Fact Extraction

Actions performed:
1. Read current docs set and marked low-value generated sections.
2. Read repository source of truth:
   - CLI surface (`src/rsspot/cli.py`)
   - runtime/config/auth flow (`src/rsspot/client.py`, `src/rsspot/settings.py`, `src/rsspot/config/*`)
   - service endpoints (`src/rsspot/services/*`)
   - OpenAPI scripts (`scripts/sync_openapi.py`, `scripts/generate_openapi_index.py`)
   - tests (`tests/test_*.py`)
   - workflows (`.github/workflows/docs-*.yml`)
3. Extracted concrete facts only when visible in code/tests (flags, defaults, precedence, retry semantics).

Output of pass:
- Evidence map seed (later saved as `rewrite-evidence.json`)
- command catalog for onboarding/recipes
- architecture and failure-mode facts

## Pass B: Audience-First IA and Journey Design

Audience selected: external SDK users first, maintainers second.

Design choices:
1. Move from module-first nav to task-first nav.
2. Promote `configuration` and `openapi` into first-class pages.
3. Keep modules pages but explicitly scope as advanced internals.
4. Add dedicated troubleshooting and usage references.

IA produced:
- Overview: index/getting-started/configuration
- Usage: sdk-usage/cli-reference
- API Lifecycle: openapi
- Internals: architecture/modules/*
- Operations: troubleshooting/contributing

## Pass C: Page Authoring with Claim-to-Source Verification

Authoring rules applied:
1. No generic filler; every operational claim tied to source/tests.
2. All command examples are executable shapes from current CLI.
3. Configuration/env alias tables align to `settings.py` and config models.
4. Error/retry semantics match `client.py` and test assertions.

Technique:
- Write page section skeleton by user task.
- Fill with evidence-backed commands and behavior notes.
- Remove generated marker tags so authored content is preserved.

## Pass D: UX Validation and Visual QA

Validation steps:
1. Ensure `docs/docs.json` nav links map to real files.
2. Confirm page titles and hierarchy are readable (no duplicate title blocks).
3. Launch docs locally via Sparkify dev server and capture screenshots across key routes.
4. Check that onboarding, usage, and internals pages are visibly distinct and task-oriented.

## Reusable Method Principles (for skill backport)

1. Scripts generate scaffolding and evidence; agent owns final authored narrative.
2. Do not ship unchanged boilerplate if source has richer detail.
3. Require explicit `page -> source evidence` mapping for auditability.
4. Keep internals docs opt-in for advanced readers; optimize nav for end-user jobs first.
5. For src-layout repositories, map internals to concrete package modules (for example `modules/rsspot`), never a generic `modules/src`.
