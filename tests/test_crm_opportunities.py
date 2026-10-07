from collections.abc import Generator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from app.api.crm_opportunity_routes import get_opportunity_service
from app.api.crm_routes import get_crm_service
from app.api.dependencies import require_authenticated_user
from app.application.contacts.crm import CrmService
from app.application.contacts.identity import ContactIdentityHasher
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.domain.user.contracts import User
from app.infrastructure.database import Base
from app.infrastructure.models.audit import AuditEventModel
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.crm_opportunity import (
    OpportunityActivityModel,
    OpportunityConversationModel,
    OpportunityHistoryModel,
    OpportunityModel,
)
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.crm_opportunity_support import opportunity_service, payload, seed


@pytest.fixture
def crm_opportunities(
    tmp_path: Path,
) -> Generator[tuple[TestClient, Session, User, User, UUID, UUID]]:
    # File database: verify persistence after connection/session replacement.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'crm.sqlite'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):  # type: ignore[no-untyped-def]
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        actor, other, contact_id, conversation_id = seed(session)
        app = create_app()
        app.dependency_overrides[require_authenticated_user] = lambda: actor

        def service():  # type: ignore[no-untyped-def]
            with Session(engine) as independent:
                yield opportunity_service(independent)

        def crm_service():  # type: ignore[no-untyped-def]
            with Session(engine) as independent:
                service = opportunity_service(independent)
                yield CrmService(
                    independent,
                    service.cipher,
                    ContactIdentityHasher(
                        service.digest_key, ContactIdentityNormalizer()
                    ),
                )

        app.dependency_overrides[get_opportunity_service] = service
        app.dependency_overrides[get_crm_service] = crm_service
        with TestClient(app) as client:
            yield client, session, actor, other, contact_id, conversation_id
    engine.dispose()


def test_conversation_customer_create_reload_and_duplicate(crm_opportunities):  # type: ignore[no-untyped-def]
    client, session, actor, _, contact, conversation = crm_opportunities
    base = f"/organizations/{actor.organization_id}"
    context = client.get(f"{base}/conversations/{conversation}/commercial-context")
    assert context.status_code == 200, context.text
    assert context.json()["contact_id"] == str(contact)
    assert context.json()["timezone"] == "America/Lima"
    assert client.get(f"{base}/crm/customers/{contact}").status_code == 200
    data = payload(actor, contact, conversation)
    headers = {"Idempotency-Key": "create-1"}
    response = client.post(f"{base}/crm/opportunities", json=data, headers=headers)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["next_action"]["due_at"] == "2026-10-08T15:00:00Z"
    assert client.get(f"{base}/crm/opportunities/{created['id']}").json() == created
    assert (
        client.post(f"{base}/crm/opportunities", json=data, headers=headers).json()
        == created
    )
    assert (
        client.post(
            f"{base}/crm/opportunities",
            json={**data, "title": "Changed"},
            headers=headers,
        ).status_code
        == 409
    )
    assert (
        client.get(f"{base}/crm/opportunities?conversation_id={conversation}").json()[
            "total"
        ]
        == 1
    )
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(OpportunityModel)) == 1
    assert (
        session.scalar(select(func.count()).select_from(OpportunityActivityModel)) == 1
    )
    assert (
        session.scalar(select(func.count()).select_from(OpportunityHistoryModel)) == 1
    )
    row = session.scalar(select(OpportunityModel))
    assert "Synthetic proposal" not in row.title_ciphertext
    assert "Private commercial need" not in row.need_ciphertext


def test_update_versions_multiple_opportunities_and_history(crm_opportunities):  # type: ignore[no-untyped-def]
    client, session, actor, _, contact, conversation = crm_opportunities
    base = f"/organizations/{actor.organization_id}/crm/opportunities"
    data = payload(actor, contact, conversation)
    first = client.post(base, json=data, headers={"Idempotency-Key": "first"}).json()
    second = client.post(base, json=data, headers={"Idempotency-Key": "second"}).json()
    update = {
        k: v for k, v in data.items() if k not in {"contact_id", "conversation_id"}
    }
    update.update(
        {"version": 1, "stage_code": "offer", "complete_previous_action": True}
    )
    result = client.patch(f"{base}/{first['id']}", json=update)
    assert result.status_code == 200, result.text
    assert result.json()["version"] == 2
    assert client.patch(f"{base}/{first['id']}", json=update).status_code == 409
    assert client.get(f"{base}/{second['id']}").json()["stage_code"] == "new"
    history = client.get(f"{base}/{first['id']}/history").json()
    assert [h["version"] for h in history] == [2, 1]
    assert history[1]["snapshot"]["stage_code"] == "new"
    session.expire_all()
    previous = session.scalar(
        select(OpportunityActivityModel).where(
            OpportunityActivityModel.opportunity_id == UUID(first["id"]),
            OpportunityActivityModel.version == 1,
        )
    )
    assert previous.status == "completed" and previous.resolved_at is not None
    contact_row = session.get(ContactModel, contact)
    assert contact_row.status == "active"
    assert session.get(ConversationModel, conversation).management_status == "open"


def test_link_is_idempotent_and_rejects_other_contact(crm_opportunities):  # type: ignore[no-untyped-def]
    client, session, actor, _, contact, conversation = crm_opportunities
    base = f"/organizations/{actor.organization_id}/crm/opportunities"
    item = client.post(
        base,
        json=payload(actor, contact, None),
        headers={"Idempotency-Key": "unlinked"},
    ).json()
    url = f"{base}/{item['id']}/conversations/{conversation}"
    assert client.put(url).status_code == 200
    assert client.put(url).status_code == 200
    assert (
        session.scalar(select(func.count()).select_from(OpportunityConversationModel))
        == 1
    )
    different = ConversationModel(
        id=uuid4(),
        organization_id=actor.organization_id,
        bot_id=session.get(ConversationModel, conversation).bot_id,
        contact_id=None,
        company_id=str(actor.organization_id),
        customer_id="unverified",
        management_status="open",
    )
    session.add(different)
    session.commit()
    assert (
        client.put(f"{base}/{item['id']}/conversations/{different.id}").status_code
        == 409
    )


def test_tenants_permissions_and_sensitive_content(crm_opportunities):  # type: ignore[no-untyped-def]
    client, _, actor, other, contact, conversation = crm_opportunities
    base = f"/organizations/{actor.organization_id}"
    data = payload(actor, contact, conversation)
    assert (
        client.post(
            f"{base}/crm/opportunities",
            json={**data, "assigned_user_id": str(other.id)},
            headers={"Idempotency-Key": "bad-assignee"},
        ).status_code
        == 400
    )
    item = client.post(
        f"{base}/crm/opportunities", json=data, headers={"Idempotency-Key": "valid"}
    ).json()
    client.app.dependency_overrides[require_authenticated_user] = lambda: other
    assert client.get(f"{base}/crm/opportunities").status_code == 403
    other_base = f"/organizations/{other.organization_id}"
    assert client.get(f"{other_base}/crm/opportunities/{item['id']}").status_code == 404
    assert client.get(f"{other_base}/crm/opportunities").json()["total"] == 0
    assert (
        client.get(
            f"{other_base}/conversations/{conversation}/commercial-context"
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{other_base}/crm/opportunities",
            json={**data, "assigned_user_id": str(other.id)},
            headers={"Idempotency-Key": "cross-contact"},
        ).status_code
        == 404
    )
    viewer = actor.model_copy(update={"role": "viewer"})
    client.app.dependency_overrides[require_authenticated_user] = lambda: viewer
    detail = client.get(f"{base}/crm/opportunities/{item['id']}").json()
    assert detail["title"] == "Oportunidad" and detail["need"] is None
    assert detail["next_action"]["description"] == "Contenido restringido"
    assert (
        client.get(f"{base}/crm/opportunities/{item['id']}/history").json()[0][
            "snapshot"
        ]["need"]
        is None
    )
    assert (
        client.post(
            f"{base}/crm/opportunities",
            json=data,
            headers={"Idempotency-Key": "viewer"},
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"{base}/crm/opportunities/{item['id']}/conversations/{conversation}"
        ).status_code
        == 403
    )
    assert (
        client.get(f"{base}/crm/customers/{contact}").json()["external_identifier"]
        is None
    )


@pytest.mark.parametrize(
    "change,code",
    [
        ({"next_action": None}, 400),
        ({"stage_code": "not-configured"}, 400),
        ({"stage_code": "won", "close_reason": "Won"}, 400),
        (
            {"next_action": {"description": "Call", "due_at": "2026-10-08T10:00:00"}},
            422,
        ),
        ({"amount": "10.50"}, 422),
        ({"amount": "-1", "currency": "PEN"}, 422),
        ({"title": " "}, 422),
        ({"organization_id": str(uuid4())}, 422),
    ],
)
def test_invalid_creations_leave_no_rows(crm_opportunities, change, code):  # type: ignore[no-untyped-def]
    client, session, actor, _, contact, conversation = crm_opportunities
    response = client.post(
        f"/organizations/{actor.organization_id}/crm/opportunities",
        json={**payload(actor, contact, conversation), **change},
        headers={"Idempotency-Key": "invalid"},
    )
    assert response.status_code == code, response.text
    assert session.scalar(select(func.count()).select_from(OpportunityModel)) == 0


def test_audit_failure_rolls_back_everything(crm_opportunities, monkeypatch):  # type: ignore[no-untyped-def]
    client, session, actor, _, contact, conversation = crm_opportunities

    def fail(self, draft):  # type: ignore[no-untyped-def]
        raise ValueError("audit failed")

    monkeypatch.setattr(SqlAlchemyAuditRepository, "append", fail)
    response = client.post(
        f"/organizations/{actor.organization_id}/crm/opportunities",
        json=payload(actor, contact, conversation),
        headers={"Idempotency-Key": "audit-fails"},
    )
    assert response.status_code == 400
    for table in [
        OpportunityModel,
        OpportunityActivityModel,
        OpportunityHistoryModel,
        OpportunityConversationModel,
    ]:
        assert session.scalar(select(func.count()).select_from(table)) == 0


def test_database_rejects_cross_company_assignee_and_link(crm_opportunities):  # type: ignore[no-untyped-def]
    client, session, actor, other, contact, conversation = crm_opportunities
    base = f"/organizations/{actor.organization_id}/crm/opportunities"
    item = client.post(
        base,
        json=payload(actor, contact, conversation),
        headers={"Idempotency-Key": "db"},
    ).json()
    row = session.get(OpportunityModel, UUID(item["id"]))
    row.assigned_user_id = other.id
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    link = session.scalar(select(OpportunityConversationModel))
    link.organization_id = other.organization_id
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_closing_does_not_verify_payment_or_change_contact(crm_opportunities):  # type: ignore[no-untyped-def]
    client, session, actor, _, contact, conversation = crm_opportunities
    base = f"/organizations/{actor.organization_id}/crm/opportunities"
    data = payload(actor, contact, conversation)
    item = client.post(base, json=data, headers={"Idempotency-Key": "close"}).json()
    update = {
        k: v for k, v in data.items() if k not in {"contact_id", "conversation_id"}
    }
    update.update(
        version=1, stage_code="won", close_reason="Confirmed by human", next_action=None
    )
    result = client.patch(f"{base}/{item['id']}", json=update)
    assert result.status_code == 200, result.text
    assert result.json()["closed_at"] and result.json()["next_action"] is None
    assert (
        client.get(
            f"/organizations/{actor.organization_id}/crm/customers/{contact}"
        ).json()["classification"]
        == "lead"
    )
    assert session.get(ConversationModel, conversation).management_status == "open"
    assert (
        session.scalar(
            select(func.count())
            .select_from(AuditEventModel)
            .where(AuditEventModel.action == "crm.opportunity_saved")
        )
        == 2
    )


def test_stage_configuration_and_missing_key(crm_opportunities):  # type: ignore[no-untyped-def]
    client, _, actor, _, contact, conversation = crm_opportunities
    base = f"/organizations/{actor.organization_id}/crm"
    assert (
        client.post(
            f"{base}/opportunities", json=payload(actor, contact, conversation)
        ).status_code
        == 422
    )
    stages = client.get(f"{base}/stages").json()
    stages[0]["name"] = "First contact"
    assert client.put(f"{base}/stages", json={"stages": stages}).status_code == 200
    stages[0]["kind"] = "lost"
    assert client.put(f"{base}/stages", json={"stages": stages}).status_code == 409
    operator = actor.model_copy(update={"role": "operator"})
    client.app.dependency_overrides[require_authenticated_user] = lambda: operator
    assert client.put(f"{base}/stages", json={"stages": stages}).status_code == 403
    assert (
        client.post(
            f"{base}/opportunities",
            json=payload(actor, contact, conversation),
            headers={"Idempotency-Key": "operator"},
        ).status_code
        == 201
    )


def test_stage_snapshot_persists_and_rejects_stale(crm_opportunities):  # type: ignore[no-untyped-def]
    client, session, actor, other, contact, conversation = crm_opportunities
    base = f"/organizations/{actor.organization_id}/crm"
    original = client.get(f"{base}/stages").json()
    changed = [dict(s) for s in original]
    changed[0]["name"] = "Primer contacto del equipo"
    changed[0]["position"], changed[1]["position"] = 1, 0
    changed.append(
        {"code": "negotiation", "name": "Negociación", "kind": "open", "position": 6}
    )
    response = client.put(
        f"{base}/stages", json={"stages": changed, "expected_stages": original}
    )
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved[0]["code"] == "need"
    assert client.get(f"{base}/stages").json() == saved
    stale = client.put(
        f"{base}/stages", json={"stages": original, "expected_stages": original}
    )
    assert stale.status_code == 409
    assert client.get(f"{base}/stages").json() == saved
    assert (
        client.put(
            f"/organizations/{other.organization_id}/crm/stages",
            json={"stages": saved, "expected_stages": saved},
        ).status_code
        == 403
    )
    duplicate = [dict(s) for s in saved]
    duplicate[0]["position"] = duplicate[1]["position"]
    assert (
        client.put(
            f"{base}/stages", json={"stages": duplicate, "expected_stages": saved}
        ).status_code
        == 422
    )
    created = client.post(
        f"{base}/opportunities",
        json={**payload(actor, contact, conversation), "stage_code": "negotiation"},
        headers={"Idempotency-Key": "configured-stage"},
    )
    assert created.status_code == 201, created.text
    assert (
        client.get(f"{base}/opportunities?stage_code=negotiation").json()["total"] == 1
    )
    assert client.get(f"{base}/opportunities?stage_code=new").json()["total"] == 0
    session.expire_all()
    assert (
        session.scalar(
            select(func.count())
            .select_from(AuditEventModel)
            .where(AuditEventModel.action == "crm.stages_updated")
        )
        == 1
    )


def test_board_move_close_and_reopen_preserves_history(crm_opportunities):  # type: ignore[no-untyped-def]
    client, _, actor, other, contact, conversation = crm_opportunities
    base = f"/organizations/{actor.organization_id}/crm"
    data = payload(actor, contact, conversation)
    item = client.post(
        f"{base}/opportunities", json=data, headers={"Idempotency-Key": "board-flow"}
    ).json()
    update = {
        k: v for k, v in data.items() if k not in {"contact_id", "conversation_id"}
    }
    close = {
        **update,
        "version": 1,
        "stage_code": "won",
        "next_action": None,
        "close_reason": "Aceptación confirmada",
    }
    assert (
        client.patch(
            f"{base}/opportunities/{item['id']}", json={**close, "close_reason": None}
        ).status_code
        == 400
    )
    result = client.patch(f"{base}/opportunities/{item['id']}", json=close)
    assert result.status_code == 200, result.text
    assert (
        client.get(f"{base}/opportunities?stage_code=won").json()["items"][0]["id"]
        == item["id"]
    )
    assert client.get(f"{base}/opportunities?stage_code=new").json()["total"] == 0
    assert (
        client.patch(f"{base}/opportunities/{item['id']}", json=close).status_code
        == 409
    )
    assert (
        client.get(
            f"/organizations/{other.organization_id}/crm/opportunities?stage_code=won"
        ).status_code
        == 403
    )
    reopened = client.patch(
        f"{base}/opportunities/{item['id']}",
        json={**update, "version": 2, "stage_code": "offer"},
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["closed_at"] is None
    assert [
        h["snapshot"]["stage_code"]
        for h in client.get(f"{base}/opportunities/{item['id']}/history").json()
    ] == ["offer", "won", "new"]


def test_history_pages_hold_anchor_while_another_edit_arrives(crm_opportunities):  # type: ignore[no-untyped-def]
    client, _, actor, other, contact, conversation = crm_opportunities
    base = f"/organizations/{actor.organization_id}/crm/opportunities"
    data = payload(actor, contact, conversation)
    item = client.post(
        base, json=data, headers={"Idempotency-Key": "history-anchor"}
    ).json()
    patch = {
        k: v for k, v in data.items() if k not in {"contact_id", "conversation_id"}
    }
    for version in range(1, 7):
        response = client.patch(
            f"{base}/{item['id']}", json={**patch, "version": version}
        )
        assert response.status_code == 200, response.text
    history = f"{base}/{item['id']}/history"
    first = client.get(history, params={"page_size": 3}).json()
    assert [row["version"] for row in first] == [7, 6, 5]
    anchor = first[0]["version"]
    response = client.patch(f"{base}/{item['id']}", json={**patch, "version": anchor})
    assert response.status_code == 200 and response.json()["version"] == 8
    subsequent = []
    for page in (2, 3):
        response = client.get(
            history, params={"page": page, "page_size": 3, "through_version": anchor}
        )
        assert response.status_code == 200, response.text
        subsequent.extend(response.json())
    assert [row["version"] for row in first + subsequent] == [7, 6, 5, 4, 3, 2, 1]
    assert client.get(history, params={"page_size": 3}).json()[0]["version"] == 8
    assert [
        row["version"]
        for row in client.get(history, params={"through_version": 1}).json()
    ] == [1]
    assert client.get(history, params={"through_version": 0}).status_code == 422
    viewer = actor.model_copy(update={"role": "viewer"})
    client.app.dependency_overrides[require_authenticated_user] = lambda: viewer
    redacted = client.get(
        history, params={"page": 2, "page_size": 3, "through_version": anchor}
    ).json()
    assert [row["version"] for row in redacted] == [4, 3, 2]
    assert all(row["snapshot"]["need"] is None for row in redacted)
    client.app.dependency_overrides[require_authenticated_user] = lambda: other
    assert (
        client.get(
            f"/organizations/{other.organization_id}/crm/opportunities/{item['id']}/history?through_version={anchor}"
        ).status_code
        == 404
    )
