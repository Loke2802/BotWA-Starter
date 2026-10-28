# Web chat pilot validation — 28 October 2026

Base: origin/master and local clean base both
6163751304a261e9a1faf1ad10554951626dcfbe after a successful fetch.
Implementation branch: codex/luri-webchat-pilot. The original dirty checkout
and respaldos/ were preserved. No staging or production deployment was performed.

## Executed successfully

- 22 tests: tests/test_webchat.py and tests/test_human_handoff_endpoints.py.
- 19 regressions: test_channel_contracts.py, test_conversation_management.py,
  test_public_contacts.py, test_published_bot_knowledge_retriever.py and
  test_knowledge_management_endpoints.py.
- Ruff: app tests scripts. Black check: app tests scripts.
- mypy: app tests (542 source files).
- scripts/validate_ci_contract.py; scripts/lock_dependencies.py --check;
  scripts/audit_dependencies.py; git diff --check.
- Alembic heads: one, 20260921_0026. No migration introduced.
- Kalivur Web: npm run typecheck, npm run lint, npm run build (static export).
- Real browser → localhost:3004 website → localhost:8008 API: session creation,
  published fixture answer, history recovery after page reload, human handoff
  request and visible waiting state. Checked mobile panel bounds (375 CSS-pixel
  document width); restored viewport. Fixtures contain fictional Example data,
  not an approved Kalivur commercial knowledge base.
- The operator reply round trip and permission/idempotency checks were executed
  through the real handoff API in the local integration tests. They were not
  demonstrated through the deployed staging portal in this increment.

## Not approved / pending

- The full pytest run was started and interrupted after abnormally slow progress;
  no full-suite pass is claimed. Required again in CI before merge/release.
- PostgreSQL concurrency test added to scripts/run_postgresql_tests.py. Not run
  locally: Docker Desktop opened, but its Linux engine pipe was unavailable.
  PostgreSQL migrations/upgrade/downgrade were not executed in this increment.
- Dedicated secret scanner was not available locally. CI gitleaks is pending.
- Container security and image build were not run: local Docker unavailable.
- No public kalivur.com activation, Sites publication, backend deployment,
  configured commercial tenant/bot, retention implementation or paid AI test.
- No Meta permission, WhatsApp sending, model key, infrastructure or existing
  AI flags were changed. No credentials were requested or printed.

## Required before the public pilot

Finish CI/PostgreSQL/container gates, review the independent change, select the
approved pilot environment, confirm the org/bot and plan features, publish
owner-approved knowledge, verify handoff configuration/coverage and retention
process, then execute a visitor/operator round trip on the deployed API with
exact website origins. Only then rebuild/publish the Kalivur site with the web
flag enabled. Keep BOTWA_AI_ENABLED=false and WhatsApp transport unchanged.

This is a functioning local preview with release gates outstanding, not a claim
that Luri is already serving public website visitors or using generative AI.
