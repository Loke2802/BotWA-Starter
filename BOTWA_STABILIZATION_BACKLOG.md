# BOTWA Stabilization Backlog

Sprint objective: recover a reliable green quality gate after the recent expansion into database-backed knowledge, automation, and integration layers.

Quality snapshot:

- `pytest`: 454 passed, 16 failed
- `ruff`: 9 errors
- `mypy`: 39 errors

## P0 - Test/Runtime Configuration

### Root Cause

The local/test runtime now enables database-backed services by default, while endpoint and webhook tests still assume an isolated local execution path.

Main signal:

- `BOTWA_USE_DATABASE` defaults to `true` in code.
- Documentation still describes `BOTWA_USE_DATABASE=false` as the default.
- Tests instantiate `create_app()` and trigger dependency construction that attempts to connect to PostgreSQL.
- The configured database host resolves to `db` in the failing run, which is valid inside Docker Compose but not from the local test process.

### Affected Areas

- Conversation endpoint tests
- Vertical Slice 1 integration tests
- WhatsApp webhook integration tests
- Knowledge seed loading during dependency creation

### Impact

High. This blocks confidence in the main user-facing flow:

WhatsApp/webhook -> conversation service -> business brain -> knowledge -> response.

The app may work in Docker, but the local quality gate is not environment-independent. This makes regression testing unreliable.

### Error Count

- `pytest`: 16 failures
- `mypy`: indirectly contributes to configuration confusion, but not counted as direct type errors
- `ruff`: 0 direct errors

### Difficulty

Medium.

The fix is conceptually simple, but it touches dependency construction, settings defaults, test setup, and possibly environment contracts.

### Recommended Order

1. Decide the official default for `BOTWA_USE_DATABASE`.
2. Make tests explicitly choose their persistence mode.
3. Ensure endpoint/webhook tests can run without Docker.
4. Add a separate DB integration test path for PostgreSQL/Docker.
5. Update `.env.example` and README to match the decision.

## P1 - SQLAlchemy Typing and ORM Model Definitions

### Root Cause

The new Integration Engine persistence model mixes Python domain types with SQLAlchemy column types in a way that mypy cannot validate.

Main signal:

- `IntegrationEventModel` imports `UUID` from Python's `uuid` module.
- The same name is then used as if it were a SQLAlchemy column type via `UUID(as_uuid=True)`.
- ORM attributes are annotated as plain Python values while assigned `Column(...)` instances.
- Repository filters compare plain typed attributes instead of SQLAlchemy mapped attributes from mypy's perspective.

### Affected Areas

- `IntegrationEventModel`
- `IntegrationEventRepository`
- Integration monitoring/event persistence
- Mypy strict quality gate

### Impact

High. The Integration Engine can appear functionally implemented while its persistence layer remains type-unsafe. This increases the risk of runtime failures once integration events are persisted and queried in production.

### Error Count

- `mypy`: 21 direct errors in `integration_event.py` and `integration_event_repository.py`
- `pytest`: 0 direct failures observed from this root cause in the current run
- `ruff`: 0 direct errors

### Difficulty

Medium.

The correction is localized, but it requires aligning the ORM style with the rest of the project and SQLAlchemy 2 typing conventions.

### Recommended Order

1. Review existing ORM models that already pass mypy.
2. Align `IntegrationEventModel` with the same mapped style.
3. Fix repository query typing after the model is corrected.
4. Run focused mypy on infrastructure models/repositories.
5. Run full mypy.

## P2 - Immutable Contract Testing Patterns

### Root Cause

Several tests validate immutability by assigning to frozen Pydantic models directly. Runtime behavior is intentional, but mypy flags these assignments because the properties are read-only.

Main signal:

- Tests intentionally mutate frozen objects such as provider configs, credentials, requests, and contexts.
- `pytest.raises(Exception)` is used generically in some cases.
- One test uses `assert False` inside exception validation.

### Affected Areas

- Integration contract tests
- Provider resolver tests
- Credential/configuration provider tests
- Gateway tests

### Impact

Medium. Product behavior is likely correct, but the tests are written in a way that conflicts with strict static typing and lint rules. This blocks the quality gate without necessarily indicating broken runtime behavior.

### Error Count

- `mypy`: 8 direct errors related to read-only properties and incompatible immutability assertions
- `ruff`: 4 direct errors related to blind exceptions or `assert False`
- `pytest`: 0 direct failures observed from this root cause

### Difficulty

Low.

Most fixes should be test-only changes: assert specific exception types, avoid direct illegal assignments where type checkers object, and use helper functions where needed.

### Recommended Order

1. Identify the exact exception type raised by frozen Pydantic models.
2. Replace `pytest.raises(Exception)` with specific exception assertions.
3. Replace `assert False` with explicit failure or cleaner pytest patterns.
4. Adjust immutability tests so they remain meaningful under mypy strict.
5. Re-run ruff before full pytest.

## P3 - Integration Engine Generic Typing

### Root Cause

The Integration Engine introduces generic request/result contracts, but some tests and factory functions use concrete implementations where invariant generic containers or missing type parameters cause mypy failures.

Main signal:

- Missing type arguments for `ValidatedIntegrationRequest`.
- `dict[str, WhatsAppProviderClient]` passed where `dict[str, ProviderClient]` is expected.
- Some helper functions return overly broad or mismatched mocked types.
- Enum values are compared against raw strings in tests.

### Affected Areas

- Integration factory tests
- Provider resolver tests
- Provider client tests
- Integration contract tests
- Gateway complete tests

### Impact

Medium. The Integration Engine's design depends on generic contracts and provider abstraction. Weak typing here makes it harder to safely add providers beyond WhatsApp.

### Error Count

- `mypy`: 10 direct errors
- `ruff`: 4 direct import errors overlap with these test files
- `pytest`: 0 direct failures observed from this root cause

### Difficulty

Medium.

The errors are spread across tests and factory boundaries. Some fixes may reveal whether the public contract should accept `Mapping` instead of `dict`.

### Recommended Order

1. Add missing generic parameters in tests.
2. Replace raw string comparisons with enum-aware assertions.
3. Review factory input types for variance issues.
4. Tighten mock helper return types.
5. Re-run mypy on integration tests only, then full mypy.

## P4 - Async Lifecycle Typing

### Root Cause

The FastAPI lifespan starts the Integration HealthChecker, but mypy reports that a coroutine returned by `start_periodic_check()` is not being handled correctly.

Main signal:

- `app.main` calls `health_checker.start_periodic_check()` during lifespan startup.
- The current source shows `await`, but mypy still reports an unused coroutine at that line.
- This suggests a mismatch between the method implementation, annotation, or what the method returns internally.

### Affected Areas

- FastAPI application startup
- Integration HealthChecker
- Background health monitoring
- Mypy strict quality gate

### Impact

Medium. If this is only a type annotation mismatch, runtime may be fine. If the health checker internally creates or returns a coroutine incorrectly, background monitoring may silently fail or behave inconsistently.

### Error Count

- `mypy`: 1 direct error
- `pytest`: 0 direct failures observed from this root cause
- `ruff`: 0 direct errors

### Difficulty

Low to Medium.

Likely localized to the health checker method signature or internal task creation.

### Recommended Order

1. Inspect `HealthChecker.start_periodic_check()` signature and implementation.
2. Decide whether it should be a fully awaited async startup method or a synchronous task scheduler.
3. Align the method annotation with actual behavior.
4. Add or adjust a focused lifespan/health-check test.
5. Re-run mypy.

## P5 - Lint Hygiene in New Integration Tests

### Root Cause

The new Integration Engine tests include unused imports and broad exception assertions.

Main signal:

- Unused imports in integration tests.
- Blind `pytest.raises(Exception)`.
- `assert False` used for control flow in a test.

### Affected Areas

- `test_integration_contracts`
- `test_integration_provider_registry`
- `test_integration_provider_resolver`
- `test_integration_configuration_provider`
- `test_integration_credential_provider`
- `test_integration_gateway`

### Impact

Low to Medium. These do not imply broken product behavior, but they block the lint gate and reduce test clarity.

### Error Count

- `ruff`: 9 direct errors
- `mypy`: overlaps with P2/P3 in the same area
- `pytest`: 0 direct failures observed from this root cause

### Difficulty

Low.

Most issues are mechanical and test-local.

### Recommended Order

1. Remove unused imports.
2. Replace broad exception assertions with specific exceptions.
3. Replace `assert False` with pytest-native failure patterns.
4. Run `ruff check app tests`.
5. Then continue with mypy cleanup.

## P6 - Documentation Drift

### Root Cause

Documentation reflects Sprint 0, while the codebase now includes major post-Sprint-0 expansion into Automation Engine, Integration Engine, database-backed Knowledge Engine, and new contracts.

Main signal:

- README still describes older modules such as `decision_engine.py`, `policy.py`, `mapper.py`, `orchestrator.py`, and `in_memory_provider.py`, which are deleted or superseded.
- README says `BOTWA_USE_DATABASE=false` is the default, but code defaults to `true`.
- Engineering status report says ENG-004 and ENG-005 are not implemented, while current source contains substantial Automation and Integration implementations.
- Test count in README is stale: README says 82 tests; current suite collects 470 tests.

### Affected Areas

- README
- Engineering status reports
- Sprint planning docs
- Developer onboarding
- Operational runbook

### Impact

Medium. Documentation drift makes it hard to know which architecture is canonical and can lead developers to run the wrong mode or misjudge completion.

### Error Count

- `pytest`: 0 direct failures
- `ruff`: 0 direct errors
- `mypy`: 0 direct errors
- Operational/planning impact: high

### Difficulty

Low to Medium.

The work is mostly editorial, but it should wait until the stabilization decisions are made so the docs do not need to be rewritten twice.

### Recommended Order

1. Stabilize configuration defaults.
2. Stabilize Integration Engine typing.
3. Re-run quality gates and capture final counts.
4. Update README with current modules and commands.
5. Update status reports to distinguish committed Sprint 0 from current uncommitted expansion.

## P7 - Git Hygiene and Release Traceability

### Root Cause

The working tree contains a large uncommitted expansion after `ca9327d`, mixing source changes, deleted legacy modules, new architecture documents, migrations, and tests.

Main signal:

- Current branch: `master...origin/master`.
- Last commit: `ca9327d` - `CTO Update Sprint 0`.
- Working tree contains many modified/deleted/untracked files.
- New engines and migrations are present but not committed.

### Affected Areas

- Release traceability
- Reviewability
- Rollback strategy
- Sprint boundary clarity

### Impact

Medium. The codebase has moved significantly beyond the last committed state, but the changes are not packaged into reviewable milestones. This increases risk when stabilizing because unrelated fixes and feature work are mixed together.

### Error Count

- `pytest`: indirect only
- `ruff`: indirect only
- `mypy`: indirect only
- Git status: large dirty working tree

### Difficulty

Medium.

No code complexity, but requires disciplined grouping of changes after quality gates are restored.

### Recommended Order

1. Do not commit the current state as stable yet.
2. Stabilize P0 through P5.
3. Split remaining changes into logical commits by engine or milestone.
4. Include docs updates after code stabilization.
5. Tag or document the stabilized baseline.

## Recommended Sprint Order

1. P0 - Test/Runtime Configuration
2. P1 - SQLAlchemy Typing and ORM Model Definitions
3. P4 - Async Lifecycle Typing
4. P2 - Immutable Contract Testing Patterns
5. P3 - Integration Engine Generic Typing
6. P5 - Lint Hygiene in New Integration Tests
7. P6 - Documentation Drift
8. P7 - Git Hygiene and Release Traceability

## Stabilization Exit Criteria

- `pytest` passes locally without requiring Docker unless explicitly running DB integration tests.
- `ruff check app tests` returns 0 errors.
- `mypy app tests` returns 0 errors.
- README matches the current architecture and runtime defaults.
- Current work is committed in reviewable, traceable units.
