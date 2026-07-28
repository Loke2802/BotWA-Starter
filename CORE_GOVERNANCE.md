# BotWA Core Governance

**Status:** Active for Core v1.0.0  
**Date:** 2026-07-28

## Release Governance

- Core engines are closed and should not be reopened without explicit CTO approval.
- Blueprints and ADRs remain authoritative.
- Phase 3 work must not move responsibilities between Engines.
- Public contracts must remain stable unless a PRD explicitly requires a reviewed contract change.
- Product Development starts from PRD-level scope, not new Engines.

## Quality Gates

Every Core change must keep:

- `pytest` green
- `ruff check app tests` clean
- `black --check app tests` clean
- `mypy app tests` clean

## Infrastructure Gate

Changes affecting persistence, migrations, repositories, or runtime configuration require Docker/PostgreSQL validation before release approval.

## External Validation

WhatsApp real/live validation requires approved credentials or sandbox access. Until credentials exist, local webhook, mapper, sender, and outbound contracts are the enforceable local gate.

## Phase 3 Entry Rule

Phase 3 may begin from `PHASE_3_KICKOFF.md` and `PRD-001_ORGANIZATIONS.md`. Implementation requires explicit CTO approval.

