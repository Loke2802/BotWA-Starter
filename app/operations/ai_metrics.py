"""Read-only durable worker telemetry; no prompts or customer content."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.generative_ai.service import utc
from app.infrastructure.database import SessionLocal
from app.infrastructure.models.ai_generation import AIAttemptModel, AIJobModel
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
    automation_due = session.scalar(
        select(func.min(ManagedAutomationExecutionModel.available_at)).where(
            ManagedAutomationExecutionModel.status == "pending",
            ManagedAutomationExecutionModel.available_at <= now,
        )
    )
    return {
        "window_hours": 24,
        "sample_capped": len(jobs) == 10000 or len(attempts) == 20000,
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
