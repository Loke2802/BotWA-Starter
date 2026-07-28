# BotWA Core Validation Report

**Date:** 2026-07-28  
**Environment:** Windows PowerShell, Python 3.13.14 virtual environment, Docker Desktop 4.82.0, PostgreSQL 17, repository `D:\BotWA Starter`  
**Phase:** Phase 2 Closure Validation  
**Owner:** Lead Engineer

## Commands Executed

| Command | Result |
|---|---|
| `docker version` | PASS - client/server 29.6.1, Docker Desktop 4.82.0 |
| `docker info` | PASS - daemon available, context `desktop-linux` |
| `docker ps -a` | PASS - initial containers inspected |
| `docker compose build api` | PASS - image `botwastarter-api` built |
| `docker compose up -d db api` | PASS - PostgreSQL healthy, API started |
| `docker compose exec -T api alembic upgrade head` | PASS - upgraded to `20260728_0001` |
| `docker compose exec -T db psql -U botwa -d botwa -c "select current_database(), current_user;"` | PASS - database `botwa`, user `botwa` |
| `docker compose exec -T db psql -U botwa -d botwa -c "select tablename from pg_tables..."` | PASS - 11 public tables present |
| `curl.exe http://localhost:8000/health` | PASS - `{"status":"ok"}` |
| `curl.exe http://localhost:8000/version` | PASS - app `BotWA Starter`, API `v1`, environment `local` |
| `curl.exe POST http://localhost:8000/messages` greeting | PASS - accepted greeting response |
| `curl.exe POST http://localhost:8000/messages` knowledge | PASS - accepted business-hours response |
| `curl.exe POST http://localhost:8000/messages` support | PASS - accepted support response |
| `curl.exe POST http://localhost:8000/messages` unknown | PASS - rejected fallback response |
| `docker compose restart api` | PASS - API restarted |
| PostgreSQL post-restart count queries | PASS - data persisted after restart |
| `docker compose exec -T api pytest tests/test_integration_provider_client.py tests/test_integration_circuit_breaker.py tests/test_integration_gateway.py` | PASS - 35 passed |
| `.\.venv\Scripts\python.exe -m pytest` | PASS - 470 passed, 1 warning |
| `.\.venv\Scripts\python.exe -m ruff check app tests` | PASS - All checks passed |
| `.\.venv\Scripts\python.exe -m black --check app tests` | PASS - 172 files would be left unchanged |
| `.\.venv\Scripts\python.exe -m mypy app tests` | PASS - no issues in 172 source files |

## Validation Cases

| ID | Case | Status | Evidence |
|---|---|---|---|
| V01 | Quality gates | PASS | `pytest`: 470 passed, 1 warning; `ruff`: clean; `black`: clean; `mypy`: clean |
| V02 | API starts in Docker | PASS | `docker compose up -d db api`; API container `Up` |
| V03 | `/health` | PASS | `{"status":"ok"}` |
| V04 | `/version` | PASS | `{"app_name":"BotWA Starter","api_version":"v1","environment":"local"}` |
| V05 | Greeting message pipeline | PASS | `/messages` returned accepted greeting response |
| V06 | Knowledge information query | PASS | `/messages` returned business-hours response |
| V07 | Support flow response | PASS | `/messages` returned support response |
| V08 | Unknown response | PASS | `/messages` returned controlled rejected fallback |
| V09 | Topic Detector enriches context | PASS | 470-test suite includes `tests/test_topic_detector.py`; pipeline inspection confirms detector after ContextBuilder |
| V10 | Business Brain decision | PASS | Business Brain suite passed and Docker smoke produced expected decisions |
| V11 | Response Composer | PASS | Docker smoke returned composed business responses; `tests/test_response_composer.py` passed |
| V12 | Channel Adapter | PASS | Docker smoke returned `ChannelResponse`; `tests/test_channel_adapter.py` passed |
| V13 | Docker Compose infrastructure | PASS | PostgreSQL healthy; API up on port 8000 |
| V14 | PostgreSQL connection | PASS | database `botwa`, user `botwa` |
| V15 | Migrations/tables | PASS | Alembic `20260728_0001`; 11 public tables |
| V16 | PostgreSQL persistence flow | PASS | final smoke persisted 4 conversations, 8 messages, 12 state history rows |
| V17 | Persistence after restart | PASS | same counts confirmed after API restart |
| V18 | Automation Engine DB-backed evidence | PASS | `automation_execution` table created; DB count showed persisted automation executions |
| V19 | Integration Engine controlled HTTP/error behavior | PASS | Container integration suite: 35 passed |
| V20 | WhatsApp realistic/local validation | PASS | Local tests validate webhook, mapper, sender/outbound contracts |
| V21 | WhatsApp real/live validation | BLOCKED | External credentials/sandbox required |

## Defects Corrected During This Pass

| Defect | Root Cause | Correction | Status |
|---|---|---|---|
| Docker POST `/messages` returned 500 on `automation_execution` | Alembic did not create Automation/Integration runtime tables | Added migration `20260728_0001_create_automation_integration_tables.py` | PASS |
| DB-backed conversation transition returned 500 AssertionError | SQLAlchemy `autoflush=False` left newly added conversation unavailable before transition | Flushed session after creating persisted conversation | PASS |
| Integration tests failed inside Docker | `pytest-asyncio` was configured but not declared in `.[dev]` | Added `pytest-asyncio>=0.24.0` to dev dependencies | PASS |

## Residual Risks

- WhatsApp real/live remains `BLOCKED - EXTERNAL CREDENTIALS REQUIRED`.
- CI/CD remains a post-release operational improvement.

## Validation Decision

**Core v1.0.0 - Phase 2 Closed**

Reason: Docker, PostgreSQL, migrations, DB-backed persistence, smoke tests, Integration error handling, and all local quality gates passed. The only remaining blocker is external WhatsApp live validation, which is credential-dependent and documented.
