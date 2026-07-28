# BotWA Core Validation Plan

**Date:** 2026-07-27  
**Phase:** Phase 2 Closure Validation  
**Owner:** Lead Engineer  
**Scope:** Verify current Core Platform state before declaring Phase 2 closed or starting Phase 3 Product Development.

## Objective

Validate the real repository state against the expected Core Platform closure criteria.

This plan does not authorize new functionality, architecture changes, Blueprint changes, ADR changes, or Product Development work.

## Validation Matrix

| ID | Case | Method | Required for Phase 2 closure |
|---|---|---|---|
| V01 | Quality gates | `pytest`, `ruff`, `black`, `mypy` | yes |
| V02 | API starts | FastAPI app/TestClient smoke path | yes |
| V03 | `/health` | System endpoint test | yes |
| V04 | `/version` | System endpoint test | yes |
| V05 | Greeting message pipeline | Conversation/VS1 test | yes |
| V06 | Knowledge information query | VS1/Knowledge test | yes |
| V07 | Support flow response | Conversation/Business tests | yes |
| V08 | Topic Detector enrichment | Topic Detector tests and pipeline inspection | yes |
| V09 | Business Brain decision | Business Brain tests | yes |
| V10 | Response Composer output | Response Composer tests | yes |
| V11 | Channel Adapter output | Channel Adapter tests | yes |
| V12 | In-memory persistence/test mode | Local tests with `BOTWA_USE_DATABASE=false` | yes |
| V13 | Docker Compose starts | `docker compose up -d db` | yes |
| V14 | PostgreSQL connects | Docker/PostgreSQL validation | yes |
| V15 | DB migrations/tables available | Alembic/Docker validation | yes |
| V16 | PostgreSQL persistence flow | DB-backed flow validation | yes |
| V17 | Automation Engine controlled scenario | Automation tests | yes |
| V18 | Integration Engine controlled HTTP integration | Integration tests | yes |
| V19 | Timeout/retry/error does not break API | Integration resiliency tests | yes |
| V20 | WhatsApp realistic payload or real config | WhatsApp webhook/outbound tests; live validation if credentials available | yes, but live credentials may be blocked |

## Closure Rule

Phase 2 can be declared closed only when all critical local and infrastructure validation items pass.

If Docker/PostgreSQL cannot be validated, Phase 2 must remain **NOT CLOSED**.

If live WhatsApp credentials or sandbox access are unavailable, the live WhatsApp case may be marked **BLOCKED - EXTERNAL CREDENTIALS REQUIRED**, but local webhook/payload validation must still pass.

## Commands

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m black --check app tests
.\.venv\Scripts\python.exe -m mypy app tests
docker compose up -d db
```

## Expected Evidence

- Exact command outputs or summarized command results.
- PASS / FAIL / BLOCKED per validation case.
- Defects found and corrected.
- Residual risks.
- Phase 2 closure decision.
