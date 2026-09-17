# Workers and jobs runbook

## Automation Worker

Run `python -m app.operations.automation_worker` as a separate long-running
container from the exact web image digest. Scale and restart it independently;
never run the loop inside web. SIGTERM requests shutdown after the current batch
and before the next claim. If termination is forced, durable leases provide
recovery; monitor failures, stalls, lease expiry, and retry outcomes.

## WhatsApp transport recovery

After migration `20260916_0024`, run `python -m app.operations.whatsapp_worker`
from the same image digest and with the same database, encryption keys, contact
identity key, client mode, recipient allowlist and scoped notification policy as
the API. Docker Compose includes a separate `whatsapp-worker` service. The worker
does not run migrations. `--once --batch-size 20` runs one bounded recovery batch.

It retries recoverable inbox work and committed outbound attempts without
rerunning completed business work. PostgreSQL row locks protect inbox processing;
an atomic ownership token protects each outbound send across processes.
An expired delivery claim (five minutes) or uncertain network result becomes
`DELIVERY_UNKNOWN`; inspect provider records before any manual resend. This
avoids blind duplicates but cannot promise exactly-once delivery at Meta.
Monitor failed receipts, exhausted attempts and unknown delivery outcomes.
Old failed receipts without an encrypted payload need individual review; their
business effects may already exist and they are not automatically replayed.
Migration quarantines existing pending outbound attempts as
`LEGACY_DELIVERY_REVIEW`, retaining their contents. Review them before resending.
Stop old API/sender processes before migrating; do not run mixed transport versions.

Configure `BOTWA_LEAD_NOTIFICATION_SCOPES` as a JSON map from
`organization-uuid:bot-uuid` to a list of international numbers (digits only).
The old global `BOTWA_LEAD_NOTIFICATION_RECIPIENTS` no longer authorizes sends.
An empty map disables lead notifications. Meta recipient allowlisting still
applies, including on retries and human replies. Restart API and worker together
when changing this environment policy.

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
