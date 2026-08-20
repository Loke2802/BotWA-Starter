# Database backup and recovery runbook

The hosting/database provider is not frozen, so provider-specific commands do
not belong in this repository. Production must define encrypted backups or
snapshots, retention, access control, restore destination, and ownership.

Before a risky migration, record a successful backup/snapshot. Periodically
restore into an isolated environment; a backup is not operationally sufficient
until restore is tested. After restore, verify connectivity, required extensions,
schema integrity, one Alembic head, `alembic current`, safe application reads,
and audit/log evidence. Never test restore against production in place.

Recovery also depends on the matching secret/key inventory. Loss of persisted
data encryption keys may make restored encrypted content unreadable. Keys must
be recoverable from an approved external secret backup, never this repository.
RPO and RTO have no approved value and remain a business/operations decision.
