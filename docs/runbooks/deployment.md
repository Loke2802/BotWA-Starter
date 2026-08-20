# Provider-neutral deployment runbook

## Preconditions

- Use an approved `master` image from `ghcr.io/loke2802/botwa-starter`.
- Record both `sha-<40-character-merge-sha>` and its immutable digest.
- Confirm the target GitHub Environment, reviewer approval, serialized lock,
  production security profile, runtime configuration, secrets, DB TLS, and
  provider credentials.
- Confirm a successful provider snapshot/backup when schema or data risk exists.
- Never pass application secrets to `docker build` and never deploy `latest`.

## Sequence

1. Acquire the target-environment deployment lock.
2. Verify the selected digest belongs to the approved master SHA and passed CI.
3. Verify configuration names and secret references without printing values.
4. Verify database connectivity and TLS using the target's migration identity.
5. Record the backup/snapshot evidence and previous-known-good digest.
6. Run one `alembic upgrade head` job from the selected image.
7. Verify `alembic current` equals the repository head.
8. Replace the web process with one Uvicorn process per container.
9. Replace the Automation Worker independently using the same digest.
10. Wait for `/health/ready`; use `/health/live` only for process liveness.
11. Verify `/version` returns the approved merge SHA and execute safe API smoke.
12. Verify private `/metrics`, JSON stdout collection, correlation IDs, and alerts.
13. Record deployment actor, environment, SHA, digest, DB revision, and outcome.

Staging and production never share DBs, DB users, secrets, metrics tokens, or
provider credentials. Staging runs `BOTWA_ENVIRONMENT=production` with isolated
staging values so PRD-021 fail-closed validation is identical.

## Failure path

Stop promotion, retain evidence, and use the rollback runbook. Do not run an
automatic Alembic downgrade. Actual provider commands remain undefined until a
hosting target is approved.
