"""Read-only durable worker telemetry; no prompts or customer content."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.generative_ai.service import utc
from app.infrastructure.database import SessionLocal
from app.infrastructure.models.ai_generation import (
    AIAttemptModel,
    AIJobModel,
    AIResponseCheckpointModel,
)
from app.infrastructure.models.managed_automation import ManagedAutomationExecutionModel


def summary(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    return {
        "count": len(values),
        "mean": sum(values) / len(values) if values else 0,
        "p95": (
            ordered[min(int(len(ordered) * 0.95), len(ordered) - 1)] if ordered else 0
        ),
        "max": ordered[-1] if ordered else 0,
    }


def snapshot(session: Session) -> dict[str, Any]:
    now = datetime.now(UTC)
    counts = {
        row[0]: row[1]
        for row in session.execute(
            select(AIJobModel.status, func.count()).group_by(AIJobModel.status)
        )
    }
    oldest = session.scalar(
        select(func.min(AIJobModel.created_at)).where(
            AIJobModel.status.in_(("pending", "retry", "running", "ready"))
        )
    )
    jobs = session.scalars(
        select(AIJobModel)
        .where(AIJobModel.created_at >= now - timedelta(days=1))
        .order_by(AIJobModel.created_at.desc())
        .limit(10000)
    ).all()
    attempts = session.scalars(
        select(AIAttemptModel)
        .where(AIAttemptModel.started_at >= now - timedelta(days=1))
        .order_by(AIAttemptModel.started_at.desc())
        .limit(20000)
    ).all()
    capped = len(jobs) == 10000 or len(attempts) == 20000
    reservations = sum(a.result == "reserved" for a in attempts)
    attempts = [a for a in attempts if a.result not in {"reserved", "released"}]
    checkpoints = session.scalars(
        select(AIResponseCheckpointModel)
        .join(AIJobModel)
        .where(AIJobModel.created_at >= now - timedelta(days=1))
        .limit(10000)
    ).all()
    stages = {}
    for stage in ("discovery", "adviser", "conversational_render", "semantic_review"):
        rows = [a for a in attempts if a.stage == stage]
        stages[stage] = {
            "calls": len(rows),
            "input_tokens": sum(a.input_tokens or 0 for a in rows),
            "output_tokens": sum(a.output_tokens or 0 for a in rows),
            "usage_unknown": sum(a.input_tokens is None for a in rows),
            "latency_seconds": summary(
                [a.duration_ms / 1000 for a in rows if a.duration_ms is not None]
            ),
            "errors": sum(a.result not in {"success", "unknown"} for a in rows),
        }
    sent_jobs = {j.id for j in jobs if j.status == "sent"}
    reasons: dict[str, int] = {}
    resumptions: dict[str, int] = {}
    for cp in checkpoints:
        if cp.reason_code:
            reasons[cp.reason_code] = reasons.get(cp.reason_code, 0) + 1
        if cp.resumed_from:
            resumptions[cp.resumed_from] = resumptions.get(cp.resumed_from, 0) + 1
    automation_due = session.scalar(
        select(func.min(ManagedAutomationExecutionModel.available_at)).where(
            ManagedAutomationExecutionModel.status == "pending",
            ManagedAutomationExecutionModel.available_at <= now,
        )
    )
    return {
        "stages": stages,
        "reserved_calls": reservations,
        "response_jobs": len(checkpoints),
        "response_approved": sum(c.outcome == "approved" for c in checkpoints),
        "response_fallback": sum(c.outcome == "fallback" for c in checkpoints),
        "response_decided": sum(
            c.outcome in {"approved", "fallback"} for c in checkpoints
        ),
        "response_review_rejected": sum(
            (c.reason_code or "").startswith("REVIEW_") for c in checkpoints
        ),
        "response_fallback_sent": sum(
            c.outcome == "fallback" and c.job_id in sent_jobs for c in checkpoints
        ),
        "response_reasons": reasons,
        "resumed_from": resumptions,
        "window_hours": 24,
        "sample_capped": capped or len(checkpoints) == 10000,
        "jobs_by_status": counts,
        "oldest_pending_seconds": (now - utc(oldest)).total_seconds() if oldest else 0,
        "queue_seconds": summary(
            [
                (utc(j.started_at) - utc(j.created_at)).total_seconds()
                for j in jobs
                if j.started_at
            ]
        ),
        "generation_seconds": summary(
            [a.duration_ms / 1000 for a in attempts if a.duration_ms is not None]
        ),
        "message_to_sent_seconds": summary(
            [
                (utc(j.sent_at) - utc(j.created_at)).total_seconds()
                for j in jobs
                if j.sent_at
            ]
        ),
        "errors": sum(a.result not in {"success", "unknown"} for a in attempts),
        "jobs_with_error": sum(j.error_code is not None for j in jobs),
        "unknown_attempt_outcomes": sum(a.result == "unknown" for a in attempts),
        "retries": sum(max(j.attempts - 1, 0) for j in jobs),
        "input_tokens": sum(a.input_tokens or 0 for a in attempts),
        "output_tokens": sum(a.output_tokens or 0 for a in attempts),
        "usage_unknown_attempts": sum(a.input_tokens is None for a in attempts),
        "ai_lane_capacity": 1,
        "ai_running": counts.get("running", 0),
        "automation_due_lag_seconds": (
            (now - utc(automation_due)).total_seconds() if automation_due else 0
        ),
    }


def main() -> None:
    with SessionLocal() as session:
        print(json.dumps(snapshot(session), indent=2))


if __name__ == "__main__":
    main()
