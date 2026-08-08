# PRD-015 Migration from PRD-005 Business Configuration

## Purpose

This runbook defines the safe transition from the legacy `business_hours` field
owned by PRD-005 to the tenant-scoped operational calendar introduced by
PRD-015. It does not perform an automatic migration and does not change
PRD-005 behavior.

An active applicable PRD-015 calendar is the Source of Truth. Resolution selects
an active bot-specific calendar first and then an active organization-wide
calendar. If neither exists, the PRD-012 `business_hours_state` calculation falls
back temporarily to the PRD-005 field. Draft, inactive, and archived calendars do
not disable that fallback.

The two rule sets are never merged or copied implicitly. If an active PRD-015
calendar cannot be resolved, the result is `unknown`, not a silent PRD-005
decision. Organizations therefore retain legacy behavior until they explicitly
activate an applicable PRD-015 calendar.

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
8. PRD-012 switches automatically at activation through the compatibility
   contract: PRD-015 `open` becomes `inside` and `closed` becomes `outside`.
   Switch any other consumer in its own authorized change. Do not combine
   PRD-005 and PRD-015 decisions.

## Fallback retirement

The fallback is transitional. Retire it only after every applicable tenant has a
validated active PRD-015 calendar, consumer telemetry confirms no legacy reads,
and a separate product change approves PRD-005 deprecation. Removing the fallback
must not reinterpret or delete legacy data silently.

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
