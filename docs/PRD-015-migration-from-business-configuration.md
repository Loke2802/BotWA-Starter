# PRD-015 Migration from PRD-005 Business Configuration

## Purpose

This runbook defines the safe transition from the legacy `business_hours` field
owned by PRD-005 to the tenant-scoped operational calendar introduced by
PRD-015. It does not perform an automatic migration and does not change
PRD-005 behavior.

PRD-015 is the only Source of Truth for calls to the new business-hours resolver.
The legacy field is not read, merged, or inferred by that resolver. Existing
consumers are not switched automatically by this implementation.

## Preconditions

- Identify the organization and optional bot explicitly.
- Select a valid IANA timezone; do not translate abbreviations or fixed offsets.
- Inventory all legacy intervals and decide how dates, holidays, partial
  closures, and temporary overrides should be represented.
- Obtain the required PRD-015 administrative permissions.
- Assign a stable, tenant-scoped `Idempotency-Key` to every creation command.

## Deterministic conversion

1. Create a PRD-015 calendar in `draft` state with the selected timezone and
   optional same-tenant bot association.
2. Convert each legacy weekday to ISO weekdays `1..7` and explicit `[start,
   end)` intervals.
3. Split every midnight-crossing interval into two normalized segments on
   consecutive local weekdays. Never submit `start >= end`.
4. Replace the full weekly schedule atomically using the calendar's current
   `expected_version`.
5. Add explicit date exceptions and tenant-managed holidays. Do not infer a
   global holiday catalog.
6. Resolve representative instants in UTC, including exact boundaries and any
   applicable DST transitions, while the calendar remains in `draft`.
7. Activate the calendar only after the normalized results are accepted.
8. Switch each consumer to the PRD-015 resolver in its own authorized change.
   Do not combine PRD-005 and PRD-015 decisions.

## Rollback

Before a consumer switch, leave the new calendar `draft` or `inactive`. After a
switch, deactivate the PRD-015 calendar and revert that consumer through its
normal deployment process. Do not delete calendars, rules, receipts, or audit
history. PRD-005 data remains untouched by this runbook.

## Verification checklist

- Calendar, bot, actor, and all rules belong to the same organization.
- Weekly intervals are non-overlapping and midnight-normalized.
- Exception > holiday > weekly precedence matches the approved examples.
- Active overrides take precedence and reveal the underlying result after
  expiration or revocation.
- Resolution inputs are timezone-aware and outputs retain timezone, local date,
  local time, fold, provenance, version, and next known state change.
- Replayed creation commands do not duplicate resources or audit events.
- No Google Calendar, OAuth, provider payload, or credential is involved.
