# ruff: noqa: F811
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.api.dependencies import require_authenticated_user
from app.application.crm.service import OpportunityService
from app.application.crm.suggestions import CommercialSuggestionService
from app.domain.user.contracts import User
from app.infrastructure.models.ai_generation import AIJobModel, AIMemoryModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.crm_customer_activity import CrmCustomerActivityModel
from app.infrastructure.models.crm_opportunity import OpportunityModel
from app.operations.ai_consumer import dispatch_one
from app.security.authorization import AuthorizationError
from sqlalchemy import func, select

from tests.crm_opportunity_support import payload
from tests.test_crm_opportunities import crm_opportunities  # noqa: F401
from tests.test_generative_ai import Runtime, runtime  # noqa: F401
from tests.test_whatsapp_live_processor_repository import cipher


def test_customer_activity_persistence_idempotency_and_tenant(crm_opportunities):  # type: ignore[no-untyped-def]
    client, session, actor, other, contact, conversation = crm_opportunities
    base = f"/organizations/{actor.organization_id}/crm"
    op = client.post(
        f"{base}/opportunities",
        json=payload(actor, contact, conversation),
        headers={"Idempotency-Key": "workspace-op"},
    ).json()
    data = {
        "kind": "call",
        "description": "Llamada privada de prueba",
        "occurred_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        "opportunity_id": op["id"],
    }
    path = f"{base}/customers/{contact}/activities"
    headers = {"Idempotency-Key": "record-call"}
    response = client.post(path, json=data, headers=headers)
    assert response.status_code == 201, response.text
    assert client.post(path, json=data, headers=headers).json() == response.json()
    assert (
        client.post(
            path, json={**data, "description": "Otra actividad"}, headers=headers
        ).status_code
        == 409
    )
    assert client.get(path).json()["total"] == 1
    assert (
        client.get(
            f"/organizations/{other.organization_id}/crm/customers/{contact}/activities"
        ).status_code
        == 403
    )
    workspace = client.get(f"{base}/customers/{contact}/workspace").json()
    assert workspace["opportunities"]["total"] == 1 and workspace["conversations"][0][
        "id"
    ] == str(conversation)
    update = {
        k: v
        for k, v in payload(actor, contact, conversation).items()
        if k not in {"contact_id", "conversation_id"}
    }
    assert (
        client.patch(
            f"{base}/opportunities/{op['id']}",
            json={**update, "version": 1, "complete_previous_action": True},
        ).status_code
        == 200
    )
    actions = client.get(f"{base}/customers/{contact}/action-history").json()
    assert actions["total"] == 2 and {a["status"] for a in actions["items"]} == {
        "pending",
        "completed",
    }
    completed = next(a for a in actions["items"] if a["status"] == "completed")
    assert completed["resolved_at"] is not None
    session.expire_all()
    row = session.scalar(select(CrmCustomerActivityModel))
    assert row and "Llamada privada" not in row.description_ciphertext
    assert (
        session.scalar(select(func.count()).select_from(CrmCustomerActivityModel)) == 1
    )


def test_customer_viewer_redaction_and_denied_writes(crm_opportunities):  # type: ignore[no-untyped-def]
    client, _, actor, _, contact, conversation = crm_opportunities
    base = f"/organizations/{actor.organization_id}/crm"
    op = client.post(
        f"{base}/opportunities",
        json=payload(actor, contact, conversation),
        headers={"Idempotency-Key": "viewer-customer"},
    ).json()
    data = {
        "kind": "note",
        "description": "Notas privadas",
        "occurred_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
    }
    path = f"{base}/customers/{contact}/activities"
    assert (
        client.post(
            path, json=data, headers={"Idempotency-Key": "private-note"}
        ).status_code
        == 201
    )
    client.app.dependency_overrides[require_authenticated_user] = (
        lambda: actor.model_copy(update={"role": "viewer"})
    )
    result = client.get(f"{base}/customers/{contact}/workspace").json()
    assert (
        not result["can_write"]
        and result["opportunities"]["items"][0]["title"] == "Oportunidad"
    )
    assert client.get(path).json()["items"][0]["description"] == "Contenido restringido"
    assert (
        client.post(
            path, json=data, headers={"Idempotency-Key": "viewer-note"}
        ).status_code
        == 403
    )
    assert (
        client.get(f"{base}/customers/{contact}/suggestions/{conversation}").status_code
        == 403
    )
    assert client.get(f"{base}/opportunities/{op['id']}").json()["need"] is None


def test_activities_validate_contact_time_and_key(crm_opportunities):  # type: ignore[no-untyped-def]
    client, _, actor, _, contact, _ = crm_opportunities
    base = f"/organizations/{actor.organization_id}/crm"
    data = {
        "kind": "meeting",
        "description": "Reunión",
        "occurred_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
    }
    path = f"{base}/customers/{contact}/activities"
    assert client.post(path, json=data).status_code == 422
    assert (
        client.post(
            path,
            json={**data, "occurred_at": "2026-10-06T12:00:00"},
            headers={"Idempotency-Key": "naive"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            path,
            json={
                **data,
                "occurred_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
            headers={"Idempotency-Key": "future"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            path,
            json={**data, "opportunity_id": str(uuid4())},
            headers={"Idempotency-Key": "missing-op"},
        ).status_code
        == 404
    )
    assert client.get(f"{base}/customers/{uuid4()}/workspace").status_code == 404
    assert client.get(path + "?page=0").status_code == 422
    assert client.get(path).json()["total"] == 0


def test_commercial_report_counts_currency_period_and_permissions(crm_opportunities):  # type: ignore[no-untyped-def]
    client, _, actor, other, contact, conversation = crm_opportunities
    base = f"/organizations/{actor.organization_id}/crm"
    data = payload(actor, contact, conversation)
    created = []
    for n, (amount, currency) in enumerate(
        [("10.50", "PEN"), ("20.00", "PEN"), ("7.25", "USD"), (None, None)]
    ):
        response = client.post(
            f"{base}/opportunities",
            json={**data, "amount": amount, "currency": currency},
            headers={"Idempotency-Key": f"report-{n}"},
        )
        assert response.status_code == 201, response.text
        created.append(response.json())
    report = client.get(f"{base}/commercial-report").json()
    assert sum(row["count"] for row in report["items"]) == 4
    amounts = {row["currency"]: row["amount"] for row in report["items"]}
    assert amounts == {"PEN": "30.50", "USD": "7.25", None: None}
    for item, stage in [(created[0], "won"), (created[2], "lost")]:
        update = {
            k: item[k]
            for k in ["title", "need", "assigned_user_id", "amount", "currency"]
        }
        assert (
            client.patch(
                f"{base}/opportunities/{item['id']}",
                json={
                    **update,
                    "version": 1,
                    "stage_code": stage,
                    "next_action": None,
                    "close_reason": "Cierre sintético",
                },
            ).status_code
            == 200
        )
    final = client.get(f"{base}/commercial-report").json()
    assert {
        kind: sum(row["count"] for row in final["items"] if row["kind"] == kind)
        for kind in ["open", "won", "lost"]
    } == {"open": 2, "won": 1, "lost": 1}

    assert (
        client.get(
            f"{base}/commercial-report", params={"date_to": created[0]["created_at"]}
        ).json()["items"]
        == []
    )
    assert (
        client.get(
            f"{base}/commercial-report?date_from=2026-10-06T00:00:00"
        ).status_code
        == 400
    )
    assert (
        client.get(
            f"{base}/commercial-report", params={"assigned_user_id": str(other.id)}
        ).json()["items"]
        == []
    )
    assert (
        client.get(
            f"/organizations/{other.organization_id}/crm/commercial-report"
        ).status_code
        == 403
    )
    client.app.dependency_overrides[require_authenticated_user] = (
        lambda: actor.model_copy(update={"role": "viewer"})
    )
    restricted = client.get(f"{base}/commercial-report").json()
    assert not restricted["can_read_amounts"]
    assert (
        sum(row["count"] for row in restricted["items"]) == 4
        and all(row["currency"] is None for row in restricted["items"])
        and all(row["amount"] is None for row in restricted["items"])
    )


async def test_suggestions_reuse_existing_ai_with_evidence_and_no_new_calls(
    runtime: Runtime,
) -> None:
    await runtime.inbound()
    assert await runtime.service.run_once()
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        job.available_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    await dispatch_one(runtime.service)
    calls = len(runtime.provider.calls)
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        assert job.status == "sent"
        conversation = session.get(ConversationModel, job.conversation_id)
        assert conversation and conversation.contact_id
        actor = User(
            id=runtime.channel.created_by_user_id,
            organization_id=job.organization_id,
            email="synthetic@example.test",
            role="organization_admin",
        )
        commercial = OpportunityService(session, cipher(), "synthetic-suggestion-key")
        service = CommercialSuggestionService(commercial, runtime.settings)
        result = service.suggest(
            job.organization_id, conversation.contact_id, conversation.id, actor
        )
        assert result.available and result.need == "5" and result.stage_code == "need"
        assert result.evidence == ["tiene 5 años"] and result.next_action
        assert session.scalar(select(func.count()).select_from(OpportunityModel)) == 0
        assert len(runtime.provider.calls) == calls
        with pytest.raises(AuthorizationError):
            service.suggest(
                job.organization_id,
                conversation.contact_id,
                conversation.id,
                actor.model_copy(update={"role": "viewer"}),
            )
        memory = session.get(AIMemoryModel, conversation.id)
        assert memory
        values = json.loads(cipher().decrypt(memory.ciphertext))
        values["age"]["quote"] = "Una cita inventada"
        memory.ciphertext = cipher().encrypt(json.dumps(values))
        session.commit()
        assert not service.suggest(
            job.organization_id, conversation.contact_id, conversation.id, actor
        ).available
        assert (
            not CommercialSuggestionService(
                commercial, runtime.settings.model_copy(update={"ai_enabled": False})
            )
            .suggest(
                job.organization_id, conversation.contact_id, conversation.id, actor
            )
            .available
        )
        assert len(runtime.provider.calls) == calls


def test_platform_admin_activity_keeps_existing_global_scope(crm_opportunities):  # type: ignore[no-untyped-def]
    client, _, actor, other, contact, _ = crm_opportunities
    client.app.dependency_overrides[require_authenticated_user] = (
        lambda: other.model_copy(update={"role": "platform_admin"})
    )
    response = client.post(
        f"/organizations/{actor.organization_id}/crm/customers/{contact}/activities",
        json={
            "kind": "note",
            "description": "Administración autorizada",
            "occurred_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        },
        headers={"Idempotency-Key": "platform-note"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["actor_user_id"] == str(other.id)
