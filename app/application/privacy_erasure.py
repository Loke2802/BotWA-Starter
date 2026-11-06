"""Conservative, supervised erasure of one proven contact graph.

This maintenance operation deliberately trades availability for a stable graph.
It never guesses ownership from free text or decrypts historical payloads.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import delete, or_, select, text
from sqlalchemy.orm import Session

import app.infrastructure.models  # noqa: F401
from app.infrastructure.database import Base


@dataclass(frozen=True)
class ErasureResult:
    fingerprint: str
    counts: dict[str, int]
    blockers: tuple[str, ...]
    applied: bool


# These legacy stores have no reliable subject key. Their presence blocks erasure,
# rather than leaving a hidden copy while reporting success.
UNATTRIBUTABLE = (
    "knowledge_query_log",
    "automation_execution",
    "automation_task_execution",
    "integration_event",
)
DIRECT = (
    "message",
    "conversation_state_history",
    "handoff_session",
    "conversation_management_event",
    "handoff_cycle",
    "ai_job",
    "ai_memory",
    "business_event",
)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def erase_contact(
    session: Session,
    organization_id: UUID,
    bot_id: UUID,
    contact_id: UUID,
    *,
    mode: Literal["retention", "request"] = "retention",
    now: datetime | None = None,
    expected_fingerprint: str | None = None,
    apply: bool = False,
    max_rows: int = 10000,
) -> ErasureResult:
    """Preview or delete a bounded graph; caller commits, rolls back on errors.

    Must use a fresh session. Apply requires a reviewed preview fingerprint and
    revalidates under database write exclusion. PostgreSQL locks are NOWAIT;
    SQLite uses BEGIN IMMEDIATE. No provider calls or background scheduler.
    """
    if session.in_transaction() or session.new or session.dirty or session.deleted:
        raise ValueError("A fresh session is required")
    if mode not in ("retention", "request") or not 1 <= max_rows <= 100000:
        raise ValueError("Invalid mode or max_rows")
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if apply and not expected_fingerprint:
        raise ValueError("Apply requires the reviewed preview fingerprint")
    dialect = session.get_bind().dialect.name
    tables = Base.metadata.tables
    if dialect == "sqlite":
        session.execute(text("BEGIN IMMEDIATE"))
    elif dialect == "postgresql":
        # Lock the entire known schema in a stable order, including soft-link
        # stores. Row locks cannot prevent new contact/receipt relationships.
        names = ", ".join('"' + name + '"' for name in sorted(tables))
        session.execute(text(f"LOCK TABLE {names} IN SHARE ROW EXCLUSIVE MODE NOWAIT"))
    else:
        raise ValueError("Only SQLite and PostgreSQL are supported")

    graph: dict[str, list[dict[str, Any]]] = {}
    blockers: set[str] = set()

    def rows(name: str, predicate: Any = None) -> list[dict[str, Any]]:
        query = select(tables[name])
        if predicate is not None:
            query = query.where(predicate)
        found = [
            dict(row) for row in session.execute(query.limit(max_rows + 1)).mappings()
        ]
        if len(found) > max_rows:
            blockers.add("row_limit")
        return found

    def add(name: str, predicate: Any) -> list[dict[str, Any]]:
        found = rows(name, predicate)
        graph[name] = found
        for row in found:
            if "organization_id" in row and row["organization_id"] != organization_id:
                blockers.add("scope_conflict:" + name)
            if "bot_id" in row and row["bot_id"] != bot_id:
                blockers.add("scope_conflict:" + name)
        return found

    bot = rows("bot", tables["bot"].c.id == bot_id)
    if not bot or bot[0]["organization_id"] != organization_id:
        blockers.add("invalid_bot_scope")
    contacts = add("contact", tables["contact"].c.id == contact_id)
    convs = add("conversation", tables["conversation"].c.contact_id == contact_id)
    conv_ids = [row["id"] for row in convs]
    if contacts and not convs:
        blockers.add("contact_has_no_proven_bot")
    # An unlinked legacy conversation might belong to this subject. NULL tenant
    # rows cannot safely be attributed even when company_id happens to match.
    legacy = tables["conversation"]
    if rows(
        "conversation",
        or_(
            legacy.c.organization_id.is_(None),
            (legacy.c.organization_id == organization_id)
            & legacy.c.contact_id.is_(None),
        ),
    ):
        blockers.add("unattributed_conversations")
    for name in DIRECT:
        add(name, tables[name].c.conversation_id.in_(conv_ids))
    for name in UNATTRIBUTABLE:
        if rows(name):
            blockers.add("unattributed_store:" + name)
    events = tables["business_event"]
    if rows("business_event", events.c.conversation_id.is_(None)):
        blockers.add("unattributed_business_events")
    automation = tables["managed_automation_event_receipt"]
    if rows(
        "managed_automation_event_receipt",
        automation.c.organization_id == organization_id,
    ):
        blockers.add("unattributed_automation_snapshots")
    add("customer_profile", tables["customer_profile"].c.contact_id == contact_id)
    handoff_ids = [r["id"] for r in graph["handoff_session"]]
    add("handoff_event", tables["handoff_event"].c.handoff_session_id.in_(handoff_ids))
    job_ids = [r["id"] for r in graph["ai_job"]]
    for name in ("ai_attempt", "ai_response_checkpoint"):
        add(name, tables[name].c.job_id.in_(job_ids))

    receipt_ids = {r["receipt_id"] for r in graph["ai_job"]}
    receipt_ids.update(
        r["inbound_receipt_id"] for r in graph["message"] if r["inbound_receipt_id"]
    )
    outbound_ids = {r["outbound_id"] for r in graph["ai_job"] if r["outbound_id"]}
    outbound_ids.update(
        r["outbound_attempt_id"] for r in graph["message"] if r["outbound_attempt_id"]
    )
    outbound = tables["outbound_message_attempt"]
    identity = contacts[0]["external_identifier_hash"] if contacts else None
    attempts = add(
        "outbound_message_attempt",
        or_(
            outbound.c.id.in_(outbound_ids),
            outbound.c.inbound_receipt_id.in_(receipt_ids),
            (
                (outbound.c.organization_id == organization_id)
                & (outbound.c.external_recipient_hash == identity)
                if identity
                else text("false")
            ),
        ),
    )
    outbound_ids.update(r["id"] for r in attempts)
    receipt_ids.update(
        r["inbound_receipt_id"] for r in attempts if r["inbound_receipt_id"]
    )
    receipts = add(
        "inbound_message_receipt",
        tables["inbound_message_receipt"].c.id.in_(receipt_ids),
    )
    # Check reverse links as well: an inconsistent graph must never erase data
    # referenced by another subject, bot or tenant.
    for name, columns in (
        ("message", ("inbound_receipt_id", "outbound_attempt_id")),
        ("ai_job", ("receipt_id", "outbound_id")),
    ):
        table = tables[name]
        linked = rows(
            name,
            or_(
                table.c[columns[0]].in_(receipt_ids),
                table.c[columns[1]].in_(outbound_ids),
            ),
        )
        if any(r["conversation_id"] not in conv_ids for r in linked):
            blockers.add("shared_transport:" + name)
    linked_attempts = rows(
        "outbound_message_attempt", outbound.c.inbound_receipt_id.in_(receipt_ids)
    )
    if any(r["id"] not in outbound_ids for r in linked_attempts):
        blockers.add("shared_transport:outbound")
    known_receipts = select(tables["message"].c.inbound_receipt_id).where(
        tables["message"].c.inbound_receipt_id.is_not(None)
    )
    known_jobs = select(tables["ai_job"].c.receipt_id)
    receipt = tables["inbound_message_receipt"]
    if rows(
        "inbound_message_receipt",
        (receipt.c.organization_id == organization_id)
        & (receipt.c.bot_id == bot_id)
        & ~receipt.c.id.in_(known_receipts)
        & ~receipt.c.id.in_(known_jobs)
        & ~receipt.c.id.in_(receipt_ids),
    ):
        blockers.add("unattributed_receipts")
    # Audit rows with a proven subject resource are included. Generic audit
    # metadata is operational and must be minimized at its producer.
    resource_ids = {
        contact_id,
        *conv_ids,
        *handoff_ids,
        *job_ids,
        *outbound_ids,
        *receipt_ids,
    }
    audit = tables["audit_event"]
    add("audit_event", audit.c.resource_id.in_(resource_ids))

    if any(
        r["status"] not in ("sent", "failed", "cancelled", "handoff")
        or r["token"] is not None
        for r in graph["ai_job"]
    ):
        blockers.add("active_or_uncertain_ai")
    if any(r["status"] != "processed" for r in receipts):
        blockers.add("active_or_failed_receipt")
    if any(
        r["status"] not in ("sent", "delivered", "read")
        or r["delivery_token"] is not None
        for r in attempts
    ):
        blockers.add("active_or_uncertain_outbound")
    if any(
        r["status"] in ("waiting_human", "human_active")
        for r in graph["handoff_session"]
    ):
        blockers.add("active_handoff")
    # Validate incoming FK edges even for future schema additions. A new child
    # table must be explicitly supported before this operation may remove its
    # parent; do not rely on CASCADE or on SQLite FK enforcement being enabled.
    for table in tables.values():
        selected = graph.get(table.name, [])
        selected_keys = {
            tuple(row[column.name] for column in table.primary_key) for row in selected
        }
        for foreign_key in table.foreign_keys:
            target = foreign_key.column
            if target.table.name not in graph or not target.primary_key:
                continue
            parent_values = {row[target.name] for row in graph[target.table.name]}
            linked = rows(table.name, foreign_key.parent.in_(parent_values))
            if any(
                tuple(row[column.name] for column in table.primary_key)
                not in selected_keys
                for row in linked
            ):
                blockers.add("unhandled_reference:" + table.name)
            if any(
                row[foreign_key.parent.name] is not None
                and row[foreign_key.parent.name] not in parent_values
                for row in selected
            ):
                blockers.add("inconsistent_parent:" + table.name)
    if any(row["business_case_id"] is not None for row in convs):
        blockers.add("unattributed_business_case")
    if sum(len(value) for value in graph.values()) > max_rows:
        blockers.add("row_limit")
    if mode == "retention":
        cutoff = instant - timedelta(days=90)
        # Explicit activity clocks: do not call an audit write or AI lease an
        # interaction. Contact edits count as contact activity.
        activity_fields = {
            "contact": ("created_at", "updated_at"),
            "conversation": (
                "started_at",
                "last_message_at",
                "last_inbound_at",
                "last_outbound_at",
            ),
            "message": ("occurred_at", "created_at"),
            "inbound_message_receipt": ("received_at",),
            "outbound_message_attempt": ("sent_at", "created_at"),
            "handoff_session": ("last_activity_at",),
        }
        activity = [
            _utc(row[field])
            for name, fields in activity_fields.items()
            for row in graph[name]
            for field in fields
            if isinstance(row[field], datetime)
        ]
        if contacts and (not activity or max(activity) > cutoff):
            blockers.add("not_inactive_90_days")
        # Recent internal changes remain a separate conservative safety stop;
        # an operator must review them rather than silently extending the clock.
        related_changes = [
            _utc(value)
            for name, found in graph.items()
            for row in found
            for field, value in row.items()
            if isinstance(value, datetime)
            and field not in activity_fields.get(name, ())
        ]
        if related_changes and max(related_changes) > cutoff:
            blockers.add("recent_related_change")
    canonical = {
        "scope": [str(organization_id), str(bot_id), str(contact_id), mode],
        "rows": {
            name: sorted(
                found, key=lambda r: json.dumps(r, default=str, sort_keys=True)
            )
            for name, found in sorted(graph.items())
        },
        "blockers": sorted(blockers),
    }
    fingerprint = sha256(
        json.dumps(canonical, default=str, sort_keys=True).encode()
    ).hexdigest()
    if apply and expected_fingerprint != fingerprint:
        blockers.add("stale_preview")
    applied = apply and not blockers
    if applied:
        # Reverse FK order handles history/handoff/checkpoints before parents.
        # Business events and audit are soft references, already selected above.
        for table in reversed(Base.metadata.sorted_tables):
            for row in graph.get(table.name, []):
                condition = [column == row[column.name] for column in table.primary_key]
                session.execute(delete(table).where(*condition))
    return ErasureResult(
        fingerprint,
        {n: len(r) for n, r in graph.items() if r},
        tuple(sorted(blockers)),
        applied,
    )
