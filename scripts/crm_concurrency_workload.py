"""Eight real authenticated sessions: reads, competing edits and action completion."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from math import ceil
from statistics import median
from threading import Barrier
from time import perf_counter
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
from app.infrastructure.models.crm_opportunity import (
    OpportunityActivityModel,
    OpportunityConversationModel,
    OpportunityHistoryModel,
    OpportunityModel,
)
from scripts.verify_crm_journey_local import Journey
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session


def edit_winner(replies: list[tuple[str, int, Any]], version: int) -> dict[str, Any]:
    edits = [
        (status, body) for kind, status, body in replies if kind.startswith("edit_")
    ]
    assert sorted(status for status, _ in edits) == [
        200,
        409,
    ], "Competing edits must have exactly one winner"
    winner = next(body for status, body in edits if status == 200)
    assert winner["version"] == version, "A competing edit lost or duplicated a version"
    return cast(dict[str, Any], winner)


class ConcurrentJourney:
    def __init__(self, journey: Journey, source_report: dict[str, Any]) -> None:
        self.journey, self.source = journey, source_report
        self.timings: dict[str, list[float]] = {}
        self.requests: list[dict[str, Any]] = []

    def wave(self, tasks: list[dict[str, Any]]) -> list[tuple[str, int, Any]]:
        assert len(tasks) == 8
        ready = Barrier(8)

        def execute(task: dict[str, Any]) -> tuple[str, int, Any, float]:
            with httpx.Client(
                base_url=self.journey.base_url, timeout=60, follow_redirects=False
            ) as client:
                headers = dict(self.journey.headers[task["role"]])
                if task.get("key"):
                    headers["Idempotency-Key"] = task["key"]
                ready.wait(timeout=30)
                started = perf_counter()
                response = client.request(
                    task.get("method", "GET"),
                    task["path"],
                    headers=headers,
                    params=task.get("params"),
                    json=task.get("body"),
                )
                seconds = perf_counter() - started
                assert (
                    response.status_code in task["statuses"]
                ), f"{task['kind']}: unexpected HTTP {response.status_code}"
                body = response.json()
                if "total" in task:
                    assert (
                        body["total"] == task["total"]
                    ), f"{task['kind']}: wrong count"
                if "ids" in task:
                    assert {r["id"] for r in body["items"]} == set(
                        task["ids"]
                    ), f"{task['kind']}: wrong identities"
                return task["kind"], response.status_code, body, seconds

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(execute, tasks))
        # Collect metrics outside worker threads, without serializing credentials.
        for kind, status, _, seconds in results:
            self.timings.setdefault(kind, []).append(seconds)
            self.requests.append(
                dict(kind=kind, status=status, seconds=round(seconds, 4))
            )
        return [(kind, status, body) for kind, status, body, _ in results]

    def read_tasks(self) -> list[dict[str, Any]]:
        org = self.journey.manifest["organization_id"]
        base = f"/organizations/{org}/crm"
        data = self.source["search_dataset"]

        def search(
            kind: str, term: str, field: str, role: str, ids: list[str]
        ) -> dict[str, Any]:
            return dict(
                kind=kind,
                path=base + "/customers",
                params=dict(search=term, search_by=field),
                role=role,
                statuses=[200],
                total=len(ids),
                ids=ids,
            )

        return [
            search(
                "name", "perez jose", "name", "organization_owner", data["late_ids"]
            ),
            search(
                "phone",
                data["phone"],
                "phone",
                "organization_owner",
                [data["late_ids"][0]],
            ),
            search(
                "email",
                data["email"].upper(),
                "email",
                "organization_owner",
                data["late_ids"],
            ),
            dict(
                kind="duplicates",
                path=base + "/duplicates",
                role="organization_owner",
                statuses=[200],
                total=self.source["search_runs"][-1]["duplicate_pairs"],
            ),
            search("viewer_name", "perez jose", "name", "viewer", data["late_ids"]),
            dict(
                kind="foreign_denied",
                path=base + "/customers",
                role="other_company",
                statuses=[403],
            ),
        ]

    def execute(self, rounds: int, database_port: int) -> dict[str, Any]:
        j = self.journey
        j.login()
        org = j.manifest["organization_id"]
        base = f"/organizations/{org}/crm"
        for role in ("operator", "viewer"):
            j.request(
                "GET",
                base + "/customers?search_by=phone&search=%2B12030002001",
                role,
                status=403,
            )
        owner = j.users["organization_owner"]["id"]
        run = uuid4().hex
        payload = dict(
            contact_id=j.manifest["contact_id"],
            conversation_id=j.manifest["conversation_id"],
            title="Concurrencia local " + run[:8],
            need="Datos ficticios",
            stage_code="new",
            assigned_user_id=owner,
            amount="49.50",
            currency="PEN",
            next_action=dict(
                description="Acción inicial de prueba",
                due_at=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
            ),
        )
        create = [
            dict(
                kind="create_session_" + str(number),
                path=base + "/opportunities",
                method="POST",
                body=payload,
                key="load-create-" + run,
                role="organization_owner",
                statuses=[201],
            )
            for number in (1, 2)
        ]
        results = self.wave(self.read_tasks() + create)
        created = [body for kind, _, body in results if kind.startswith("create_")]
        assert created[0]["id"] == created[1]["id"] and created[0]["version"] == 1
        current = created[0]
        original = j.request(
            "GET", base + "/opportunities/" + self.source["opportunity_id"] + "/history"
        )
        actions = [current["next_action"]["id"]]
        winners = []
        for round_number in range(rounds):
            body = {
                k: v
                for k, v in payload.items()
                if k not in {"contact_id", "conversation_id"}
            }
            body.update(
                version=current["version"],
                stage_code="offer",
                complete_previous_action=True,
            )
            edits = []
            for role in ("organization_owner", "operator"):
                update = {
                    **body,
                    "next_action": dict(
                        description=f"Acción ronda {round_number+1} por {role}",
                        due_at=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
                    ),
                }
                edits.append(
                    dict(
                        kind="edit_" + role,
                        path=base + "/opportunities/" + current["id"],
                        method="PATCH",
                        body=update,
                        role=role,
                        statuses=[200, 409],
                    )
                )
            current = edit_winner(
                self.wave(self.read_tasks() + edits), round_number + 2
            )
            actions.append(current["next_action"]["id"])
            winners.append(
                dict(
                    version=current["version"],
                    description=current["next_action"]["description"],
                )
            )
            assert j.request("GET", base + "/opportunities/" + current["id"]) == current
        history = j.request(
            "GET", base + "/opportunities/" + current["id"] + "/history"
        )
        assert sorted(row["version"] for row in history) == list(range(1, rounds + 2))
        assert (
            j.request(
                "GET",
                base + "/opportunities/" + self.source["opportunity_id"] + "/history",
            )
            == original
        )
        j.request(
            "PATCH",
            base + "/opportunities/" + current["id"],
            "viewer",
            status=403,
            body={**body, "version": current["version"]},
        )
        foreign = (
            f"/organizations/{j.manifest['other_organization_id']}/crm/opportunities/"
            + current["id"]
        )
        j.request("GET", foreign, "other_company", status=404)
        engine = create_engine(
            f"postgresql+psycopg://botwa:crm_local_test@127.0.0.1:{database_port}/{j.manifest['databases']['after']}?connect_timeout=15"
        )
        try:
            with Session(engine) as session:
                ident, tenant = UUID(current["id"]), UUID(org)
                records = session.scalars(
                    select(OpportunityModel).where(
                        OpportunityModel.organization_id == tenant,
                        OpportunityModel.idempotency_key == "load-create-" + run,
                    )
                ).all()
                assert (
                    len(records) == 1
                    and records[0].id == ident
                    and records[0].version == rounds + 1
                )
                count = session.scalar(
                    select(func.count())
                    .select_from(OpportunityHistoryModel)
                    .where(
                        OpportunityHistoryModel.organization_id == tenant,
                        OpportunityHistoryModel.opportunity_id == ident,
                    )
                )
                assert count == rounds + 1
                activity = session.scalars(
                    select(OpportunityActivityModel).where(
                        OpportunityActivityModel.organization_id == tenant,
                        OpportunityActivityModel.opportunity_id == ident,
                    )
                ).all()
                assert {str(row.id) for row in activity} == set(actions)
                assert (
                    sum(
                        row.status == "completed" and row.resolved_at is not None
                        for row in activity
                    )
                    == rounds
                )
                assert sum(row.status == "pending" for row in activity) == 1
                links = session.scalar(
                    select(func.count())
                    .select_from(OpportunityConversationModel)
                    .where(
                        OpportunityConversationModel.organization_id == tenant,
                        OpportunityConversationModel.opportunity_id == ident,
                    )
                )
                assert links == 1
        finally:
            engine.dispose()
        metrics = {
            kind: dict(
                samples=len(values),
                median_seconds=round(median(values), 4),
                p95_seconds=round(sorted(values)[ceil(len(values) * 0.95) - 1], 4),
                max_seconds=round(max(values), 4),
            )
            for kind, values in self.timings.items()
        }
        return dict(
            status="passed",
            environment="authenticated localhost PostgreSQL",
            sessions=8,
            rounds=rounds,
            wave_requests=len(self.requests),
            requests=self.requests,
            timings=metrics,
            opportunity_id=current["id"],
            final_record=current,
            idempotent_creation_count=1,
            history_versions=rounds + 1,
            completed_actions=rounds,
            pending_actions=1,
            conversation_links=1,
            conflicts=rounds,
            winners=winners,
            original_sale_history_unchanged=True,
            external_calls=False,
        )
