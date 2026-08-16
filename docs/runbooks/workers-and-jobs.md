# Workers and jobs runbook

## Automation Worker

Run `python -m app.operations.automation_worker` as a separate long-running
container from the exact web image digest. Scale and restart it independently;
never run the loop inside web. SIGTERM requests shutdown after the current batch
and before the next claim. If termination is forced, durable leases provide
recovery; monitor failures, stalls, lease expiry, and retry outcomes.

## Billing Due Transitions

Run `python -m app.operations.billing_due_transitions` as a one-shot platform
job from the same digest, approximately once per minute. The scheduler must
prevent overlapping runs. Treat non-zero exit as observable failure and retain
structured logs. GitHub Actions is not the production scheduler.

## Contacts Backfill

Run `python -m app.operations.backfill_contacts --dry-run` manually first.
Review organization scope and processed/updated/skipped/failed counts, then run
the real command with the approved scope and batch size. Observe exit code and
telemetry. Do not schedule this command periodically.

Every process receives environment-specific runtime secrets; none migrates the
database automatically. Deployment performs a single migration job before
starting/replacing runtime processes.
