# Provider-neutral rollback runbook

1. Stop promotion and keep the environment deployment lock.
2. Identify the previous-known-good OCI digest; never substitute a mutable tag.
3. Compare its application expectations with the database revision already
   committed by the failed deployment.
4. If compatible, redeploy web and Automation Worker from the previous digest.
5. Verify `/health/live`, `/health/ready`, `/version`, safe API smoke, logs,
   metrics, and provider error signals.
6. Record the reason, actor, previous/current SHA and digest, schema revision,
   timing, and result.

Never automate database downgrade. If the previous app is not compatible with
the current schema, freeze traffic as the selected platform allows and escalate
for an explicit data/schema recovery decision. Future migrations should use
expand/contract so the prior artifact remains temporarily compatible.
