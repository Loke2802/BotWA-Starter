"""Authenticated conversation-to-sale journey on a guarded synthetic local API."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlencode, urlsplit
from uuid import UUID, uuid4

import httpx
from app.application.contacts.identity import ContactIdentityHasher
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.infrastructure.models.contact import ContactModel
from scripts.crm_search_dataset import seed_search_dataset
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session
from tests.crm_opportunity_support import opportunity_service


def validate_target(base_url: str, manifest: dict[str, Any]) -> None:
    url = urlsplit(base_url)
    if (
        url.scheme != "http"
        or url.hostname not in {"127.0.0.1", "localhost"}
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
        or not url.port
    ):
        raise ValueError("Only an explicit localhost HTTP port is accepted")
    if manifest.get("environment") != "disposable local PostgreSQL" or not re.fullmatch(
        r"luri_rehearsal_[0-9a-f]{10}_after",
        manifest.get("databases", {}).get("after", ""),
    ):
        raise ValueError("Only a synthetic local rehearsal manifest is accepted")
    for key in (
        "organization_id",
        "other_organization_id",
        "contact_id",
        "conversation_id",
    ):
        UUID(manifest[key])
    if set(manifest["accounts"]) != {
        "organization_owner",
        "operator",
        "viewer",
        "other_company",
    }:
        raise ValueError("Four synthetic roles are required")
    if any(
        not email.endswith("@local-crm.example.test")
        for email in manifest["accounts"].values()
    ):
        raise ValueError("Only synthetic test accounts are accepted")
    if not __debug__:
        raise RuntimeError("Verification requires assertions; do not use python -O")


class Journey:
    def __init__(self, base_url: str, manifest: dict[str, Any]) -> None:
        validate_target(base_url, manifest)
        self.base_url, self.manifest = base_url, manifest
        self.client = httpx.Client(
            base_url=base_url, timeout=30, follow_redirects=False
        )
        self.report: dict[str, Any] = {
            "status": "running",
            "environment": "authenticated localhost PostgreSQL",
            "run_id": uuid4().hex,
            "started_at": datetime.now(UTC).isoformat(),
            "organization_id": manifest["organization_id"],
            "checks": [],
            "browser_automation": False,
            "external_calls": False,
        }
        self.headers: dict[str, dict[str, str]] = {}
        self.users: dict[str, dict[str, Any]] = {}

    def request(
        self,
        method: str,
        path: str,
        role: str | None = "organization_owner",
        *,
        status: int = 200,
        body: dict[str, Any] | None = None,
        key: str | None = None,
    ) -> Any:
        headers = dict(self.headers.get(role or "", {}))
        if key:
            headers["Idempotency-Key"] = key
        response = self.client.request(method, path, headers=headers, json=body)
        assert (
            response.status_code == status
        ), f"{method} {path}: expected {status}, got {response.status_code}"
        return response.json()

    def login(self) -> None:
        for role, email in self.manifest["accounts"].items():
            data = self.request(
                "POST",
                "/auth/login",
                None,
                body={"email": email, "password": "SyntheticCRM2026!"},
            )
            self.headers[role] = {"Authorization": "Bearer " + data["access_token"]}
            self.users[role] = self.request("GET", "/auth/me", role)["user"]
            expected = (
                self.manifest["other_organization_id"]
                if role == "other_company"
                else self.manifest["organization_id"]
            )
            assert self.users[role]["organization_id"] == expected

    def passed(self, name: str) -> None:
        self.report["checks"].append({"name": name, "status": "passed"})
        print("PASS " + name, flush=True)

    def execute(self) -> None:
        org = self.manifest["organization_id"]
        contact = self.manifest["contact_id"]
        conversation = self.manifest["conversation_id"]
        base = f"/organizations/{org}/crm"
        workspace_path = base + f"/customers/{contact}/workspace"
        self.request("GET", workspace_path, None, status=401)
        self.login()
        portal = self.client.get("/portal")
        assert portal.status_code == 200 and "customer-workspace.js" in portal.text
        for asset in ("customer-workspace.js", "opportunities.js", "sales-metrics.js"):
            assert self.client.get("/portal/assets/" + asset).status_code == 200
        context = self.request(
            "GET",
            f"/organizations/{org}/conversations/{conversation}/commercial-context",
        )
        assert context["contact_id"] == contact and context["can_write"]
        detail = self.request("GET", base + f"/customers/{contact}")
        assert detail["id"] == contact
        before = self.request("GET", workspace_path)
        assert any(row["id"] == conversation for row in before["conversations"])
        self.passed("conversation_to_existing_customer_and_portal_assets")

        self.report["metric_start"] = datetime.now(UTC).isoformat()
        owner = self.users["organization_owner"]["id"]
        run_id = self.report["run_id"]
        payload = {
            "contact_id": contact,
            "conversation_id": conversation,
            "title": "Recorrido integral local " + run_id[:8],
            "need": "Necesidad ficticia verificable",
            "stage_code": "new",
            "assigned_user_id": owner,
            "amount": "195.75",
            "currency": "PEN",
            "next_action": {
                "description": "Llamar para preparar propuesta",
                "due_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            },
        }
        key = "journey-create-" + run_id
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    self.request,
                    "POST",
                    base + "/opportunities",
                    status=201,
                    body=payload,
                    key=key,
                )
                for _ in range(2)
            ]
            created = [f.result(timeout=45) for f in futures]
        assert created[0]["id"] == created[1]["id"] and created[0]["version"] == 1
        op = created[0]
        path = base + "/opportunities/" + op["id"]
        self.report.update(
            {
                "opportunity_id": op["id"],
                "title": payload["title"],
                "assigned_user_id": owner,
                "contact_id": contact,
                "conversation_id": conversation,
                "create_key": key,
                "create_payload": payload,
            }
        )
        self.request(
            "POST",
            base + "/opportunities",
            status=409,
            body={**payload, "title": "Different request"},
            key=key,
        )
        linked = self.request(
            "GET", base + f"/opportunities?conversation_id={conversation}"
        )
        assert sum(item["id"] == op["id"] for item in linked["items"]) == 1
        assert (
            self.request("GET", workspace_path)["opportunities"]["total"]
            == before["opportunities"]["total"] + 1
        )
        due = self.request(
            "GET",
            base + f"/follow-up?due=overdue&assigned_user_id={owner}&stage_code=new",
        )
        assert any(item["id"] == op["id"] for item in due["items"])
        self.passed("simultaneous_creation_deduplicated_and_action_persisted")

        first_action = op["next_action"]["id"]
        update = {
            k: v
            for k, v in payload.items()
            if k not in {"contact_id", "conversation_id"}
        }
        update.update(
            {
                "version": 1,
                "stage_code": "offer",
                "complete_previous_action": True,
                "next_action": {
                    "description": "Revisar propuesta enviada",
                    "due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                },
            }
        )
        # Two authenticated sessions compete for the same version, one must lose.
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(
                pool.map(
                    lambda role: self.client.patch(
                        path, headers=self.headers[role], json=update
                    ),
                    ("organization_owner", "operator"),
                )
            )
        assert sorted(r.status_code for r in replies) == [200, 409]
        winner = next(r.json() for r in replies if r.status_code == 200)
        assert winner["version"] == 2 and winner["stage_code"] == "offer"
        assert winner["assigned_user_id"] == owner and winner["amount"] == "195.75"
        self.request("PATCH", path, status=409, body=update)
        assert self.request("GET", path) == winner
        self.report["first_action_id"] = first_action
        self.report["second_action_id"] = winner["next_action"]["id"]
        self.passed("authorized_competing_edits_one_winner_and_completed_action")

        activity_path = base + f"/customers/{contact}/activities"
        activity = {
            "kind": "call",
            "description": "Llamada ficticia del recorrido integral",
            "occurred_at": datetime.now(UTC).isoformat(),
            "opportunity_id": op["id"],
        }
        journal = self.request(
            "POST",
            activity_path,
            status=201,
            body=activity,
            key="journey-call-" + run_id,
        )
        assert (
            self.request(
                "POST",
                activity_path,
                status=201,
                body=activity,
                key="journey-call-" + run_id,
            )["id"]
            == journal["id"]
        )
        self.request(
            "POST",
            activity_path,
            status=409,
            body={**activity, "description": "Different call"},
            key="journey-call-" + run_id,
        )
        self.report["activity_id"] = journal["id"]
        self.report["activity_record"] = journal
        self.passed("recorded_call_replay_and_payload_conflict")

        close = {
            **update,
            "version": 2,
            "stage_code": "won",
            "next_action": None,
            "close_reason": "Cliente ficticio acepta propuesta",
        }
        final = self.request("PATCH", path, body=close)
        assert (
            final["version"] == 3
            and final["stage_kind"] == "won"
            and final["next_action"] is None
        )
        self.report["final_record"] = final
        self.check_records()
        self.check_permissions(close, payload, activity)
        self.passed("roles_redaction_and_foreign_company_denied_without_writes")

    def check_records(self) -> None:
        org, op = self.report["organization_id"], self.report["opportunity_id"]
        base = f"/organizations/{org}/crm"
        path = base + "/opportunities/" + op
        assert self.request("GET", path) == self.report["final_record"]
        history = self.request("GET", path + "/history")
        chronological = sorted(history, key=lambda row: row["version"])
        assert [row["version"] for row in chronological] == [1, 2, 3]
        assert [row["snapshot"]["stage_code"] for row in chronological] == [
            "new",
            "offer",
            "won",
        ]
        if "history" in self.report:
            assert history == self.report["history"]
        self.report["history"] = history
        actions = self.request(
            "GET", base + f"/customers/{self.report['contact_id']}/action-history"
        )["items"]
        own = [row for row in actions if row["opportunity_id"] == op]
        assert len(own) == 2 and all(
            row["status"] == "completed" and row["resolved_at"] for row in own
        )
        assert {row["id"] for row in own} == {
            self.report["first_action_id"],
            self.report["second_action_id"],
        }
        metrics_path = (
            base
            + "/sales-metrics?"
            + urlencode({"date_from": self.report["metric_start"]})
        )
        metrics = self.request("GET", metrics_path)
        assert sum(row["won"] for row in metrics["closings"]) == 1
        assert sum(row["lost"] for row in metrics["closings"]) == 0
        assert metrics["closings"][0]["currency"] == "PEN"
        assert Decimal(metrics["closings"][0]["won_amount"]) == Decimal("195.75")
        assert Decimal(metrics["closings"][0]["conversion_percent"]) == 100
        assert {row["stage_code"] for row in metrics["durations"]} >= {"new", "offer"}
        self.report["metrics_closings"] = metrics["closings"]
        activities = self.request(
            "GET", base + f"/customers/{self.report['contact_id']}/activities"
        )["items"]
        assert [
            row for row in activities if row["id"] == self.report["activity_id"]
        ] == [self.report["activity_record"]]
        self.request(
            "POST",
            base + "/opportunities",
            status=201,
            body=self.report["create_payload"],
            key=self.report["create_key"],
        )
        self.passed("closed_sale_history_action_completion_and_historical_metrics")

    def check_permissions(
        self, close: dict[str, Any], payload: dict[str, Any], activity: dict[str, Any]
    ) -> None:
        org, foreign, op = (
            self.manifest["organization_id"],
            self.manifest["other_organization_id"],
            self.report["opportunity_id"],
        )
        base = f"/organizations/{org}/crm"
        path = base + "/opportunities/" + op
        viewer = self.request("GET", path, "viewer")
        assert (
            viewer["title"] == "Oportunidad"
            and viewer["need"] is None
            and viewer["amount"] is None
        )
        for row in self.request("GET", path + "/history", "viewer"):
            assert (
                row["snapshot"]["title"] == "Oportunidad"
                and row["snapshot"]["amount"] is None
            )
        metrics = self.request("GET", base + "/sales-metrics", "viewer")
        assert all(
            row["won_amount"] is None and row["currency"] is None
            for row in metrics["closings"]
        )
        self.request(
            "POST",
            base + "/opportunities",
            "viewer",
            status=403,
            body=payload,
            key="viewer-" + self.report["run_id"],
        )
        self.request("PATCH", path, "viewer", status=403, body={**close, "version": 3})
        self.request(
            "POST",
            base + f"/customers/{self.report['contact_id']}/activities",
            "viewer",
            status=403,
            body=activity,
            key="viewer-call-" + self.report["run_id"],
        )
        for role in self.headers:
            wrong = org if role == "other_company" else foreign
            self.request(
                "GET",
                f"/organizations/{wrong}/crm/opportunities/{op}",
                role,
                status=403,
            )
        self.request("GET", path, "other_company", status=403)
        self.request(
            "PATCH", path, "other_company", status=403, body={**close, "version": 3}
        )
        self.request(
            "GET",
            f"/organizations/{foreign}/crm/opportunities/{op}",
            "other_company",
            status=404,
        )
        own_metrics = self.request(
            "GET", f"/organizations/{foreign}/crm/sales-metrics", "other_company"
        )
        assert not own_metrics["closings"] and not own_metrics["durations"]
        assert self.request("GET", path) == self.report["final_record"]
        assert self.request("GET", path + "/history") == self.report["history"]

    def check_database(self, database_port: int) -> None:
        database = self.manifest["databases"]["after"]
        engine = create_engine(
            f"postgresql+psycopg://botwa:crm_local_test@127.0.0.1:{database_port}/{database}?connect_timeout=5"
        )
        try:
            with engine.connect() as connection:
                assert (
                    connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "20261006_0030"
                )
                assert (
                    connection.scalar(
                        text("SELECT count(*) FROM contact WHERE organization_id=:org"),
                        {"org": UUID(self.report["organization_id"])},
                    )
                    == self.report["search_dataset"]["expected_contacts"]
                )
                assert (
                    connection.scalar(
                        text(
                            "SELECT count(*) FROM contact "
                            "WHERE organization_id=:org AND "
                            "(display_name_ciphertext LIKE '%Pérez%' OR "
                            "registration_ciphertext LIKE '%TARDIO@example.test%')"
                        ),
                        {"org": UUID(self.report["organization_id"])},
                    )
                    == 0
                )
                params = {
                    "op": UUID(self.report["opportunity_id"]),
                    "org": UUID(self.report["organization_id"]),
                }
                row = connection.execute(
                    text(
                        "SELECT contact_id, version, stage_code FROM crm_opportunity "
                        "WHERE id=:op AND organization_id=:org"
                    ),
                    params,
                ).one()
                assert (
                    str(row.contact_id) == self.report["contact_id"]
                    and row.version == 3
                    and row.stage_code == "won"
                )
                for table, expected in (
                    ("crm_opportunity_history", 3),
                    ("crm_activity", 2),
                    ("crm_customer_activity", 1),
                    ("crm_opportunity_conversation", 1),
                ):
                    count = connection.scalar(
                        text(
                            f"SELECT count(*) FROM {table} "
                            "WHERE opportunity_id=:op AND organization_id=:org"
                        ),
                        params,
                    )
                    assert count == expected, (table, count)
                assert (
                    connection.scalar(
                        text(
                            "SELECT count(*) FROM crm_opportunity "
                            "WHERE organization_id=:org "
                            "AND title_ciphertext LIKE '%Recorrido integral local%'"
                        ),
                        params,
                    )
                    == 0
                )
        finally:
            engine.dispose()
        self.passed("postgresql_rows_encrypted_content_and_exact_associations")

    def seed_search(self, database_port: int, count: int) -> None:
        database = self.manifest["databases"]["after"]
        engine = create_engine(
            f"postgresql+psycopg://botwa:crm_local_test@127.0.0.1:{database_port}/{database}?connect_timeout=5"
        )
        try:
            with Session(engine) as session:
                service = opportunity_service(session)
                before = (
                    session.scalar(
                        select(func.count())
                        .select_from(ContactModel)
                        .where(
                            ContactModel.organization_id
                            == UUID(self.manifest["organization_id"])
                        )
                    )
                    or 0
                )
                self.report["search_dataset"] = seed_search_dataset(
                    session,
                    UUID(self.manifest["organization_id"]),
                    service.cipher,
                    ContactIdentityHasher(
                        service.digest_key, ContactIdentityNormalizer()
                    ),
                    count=count,
                )
                self.report["search_dataset"]["expected_contacts"] = before + count
        finally:
            engine.dispose()

    def check_search(self) -> None:
        data = self.report["search_dataset"]
        base = f"/organizations/{self.manifest['organization_id']}/crm"
        timings: dict[str, float] = {}

        def search(
            term: str,
            field: str = "name",
            page: int = 1,
            size: int = 20,
            role: str = "organization_owner",
        ) -> Any:
            started = perf_counter()
            result = self.request(
                "GET",
                base
                + "/customers?"
                + urlencode(
                    {
                        "search": term,
                        "search_by": field,
                        "page": page,
                        "page_size": size,
                    }
                ),
                role,
            )
            timings[f"{field}_{role}_page_{page}"] = round(perf_counter() - started, 3)
            return result

        late = set(data["late_ids"])
        pages = [search("perez josé", page=p, size=1) for p in (1, 2)]
        assert all(p["total"] == 2 for p in pages)
        assert pages[0]["has_next"] and not pages[1]["has_next"]
        assert {p["items"][0]["id"] for p in pages} == late
        assert search(data["phone"], "phone")["items"][0]["id"] == data["late_ids"][0]
        assert {
            r["id"] for r in search(data["email"].upper(), "email")["items"]
        } == late
        group_pages = [search("grupo marta", page=p, size=10) for p in (1, 2, 3)]
        assert [len(p["items"]) for p in group_pages] == [10, 10, 3]
        assert [p["has_next"] for p in group_pages] == [True, True, False]
        assert all(p["total"] == 23 for p in group_pages)
        assert {r["id"] for p in group_pages for r in p["items"]} == set(
            data["group_ids"]
        )
        assert search("grupo marta", page=3, size=10) == group_pages[2]
        assert search("perez", role="viewer")["total"] == 2
        for field, term in (("phone", data["phone"]), ("email", data["email"])):
            self.request(
                "GET",
                base
                + "/customers?"
                + urlencode(
                    {
                        "search": term,
                        "search_by": field,
                    }
                ),
                "viewer",
                status=403,
            )
        self.request(
            "GET", base + "/customers?search=perez", "other_company", status=403
        )
        foreign = (
            f"/organizations/{self.manifest['other_organization_id']}/crm/customers"
        )
        assert (
            self.request("GET", foreign + "?search=perez", "other_company")["total"]
            == 0
        )
        self.passed(
            "global_name_phone_email_search_pagination_roles_and_company_isolation"
        )

        started = perf_counter()
        first = self.request("GET", base + "/duplicates?page=1")
        second = self.request("GET", base + "/duplicates?page=2")
        timings["duplicates_two_pages"] = round(perf_counter() - started, 3)
        assert first["scanned"] >= data["count"] and not first["scan_limited"]
        assert first["has_next"] and not second["has_next"]
        pairs = first["items"] + second["items"]
        assert len(pairs) == first["total"] == second["total"]
        assert len({(p["source_id"], p["target_id"]) for p in pairs}) == len(pairs)
        late_pair = next(p for p in pairs if {p["source_id"], p["target_id"]} == late)
        assert {"nombre", "correo"}.issubset(late_pair["reasons"])
        assert sum(p["source_id"] in data["group_ids"] for p in pairs) == 22
        assert self.request("GET", base + "/duplicates?page=2") == second
        for role in ("viewer", "operator"):
            self.request("GET", base + "/duplicates", role, status=403)
        self.report.setdefault("search_runs", []).append(
            {
                "timings_seconds": timings,
                "scanned": first["scanned"],
                "duplicate_pairs": first["total"],
            }
        )
        self.passed(
            "full_duplicate_scan_beyond_2000_stable_pages_and_review_permissions"
        )

    def save(self, path: Path) -> None:
        # Synthetic records only. Never serialize bearer tokens or passwords.
        path.write_text(
            json.dumps(self.report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
