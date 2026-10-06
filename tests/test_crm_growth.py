# ruff: noqa: F811
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.api.dependencies import require_authenticated_user
from app.application.crm.duplicates import DuplicateService
from app.application.crm.sales_metrics import SalesMetricsService
from app.domain.crm.contracts import OpportunityCreate, OpportunityUpdate
from app.domain.crm.growth_contracts import MergeInput
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.crm_contact_merge import ContactMergeModel
from app.infrastructure.models.crm_customer_activity import CrmCustomerActivityModel
from app.infrastructure.models.crm_opportunity import (
    OpportunityConversationModel,
    OpportunityHistoryModel,
    OpportunityModel,
)
from app.infrastructure.models.customer_profile import CustomerProfileModel
from app.security.secret_cipher import SecretCipher
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.crm_opportunity_support import opportunity_service, payload
from tests.test_crm_opportunities import crm_opportunities  # noqa: F401


def target(session: Session, org: UUID, cipher: SecretCipher) -> ContactModel:
    row = ContactModel(
        id=uuid4(),
        organization_id=org,
        channel_type="email",
        external_identifier_hash=uuid4().hex * 2,
        external_identifier_ciphertext=cipher.encrypt("client@example.test"),
        display_name_ciphertext=cipher.encrypt("Synthetic client"),
        notes_ciphertext=cipher.encrypt("Notas del principal"),
        status="active",
    )
    session.add(row)
    session.commit()
    return row


def test_merge_preserves_history_and_replay(crm_opportunities):  # type: ignore[no-untyped-def]
    client, session, actor, _, contact, conversation = crm_opportunities
    svc = opportunity_service(session)
    base = f"/organizations/{actor.organization_id}/crm"
    principal = target(session, actor.organization_id, svc.cipher)
    source = session.get(ContactModel, contact)
    transport = session.get(ConversationModel, conversation)
    transport_before = {
        c.name: getattr(transport, c.name)
        for c in transport.__table__.columns
        if c.name != "contact_id"
    }
    source.notes_ciphertext = svc.cipher.encrypt("Notas originales")
    source.registration_ciphertext = svc.cipher.encrypt(
        json.dumps({"email": "CLIENT@example.test"})
    )
    session.commit()
    op = client.post(
        base + "/opportunities",
        json=payload(actor, contact, conversation),
        headers={"Idempotency-Key": "merge-op"},
    ).json()
    activity = {
        "kind": "call",
        "description": "Llamada conservada",
        "occurred_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        "opportunity_id": op["id"],
    }
    path = f"{base}/customers/{contact}/activities"
    journal = client.post(
        path, json=activity, headers={"Idempotency-Key": "merge-call"}
    ).json()
    history_before = client.get(f"{base}/opportunities/{op['id']}/history").json()
    candidates = client.get(base + "/duplicates").json()
    assert candidates["items"][0]["reasons"] == ["correo", "nombre"]
    review = client.get(
        base + f"/merge-preview?source_id={contact}&target_id={principal.id}"
    ).json()
    assert review["source"]["notes"] == "Notas originales"
    body = {
        "source_id": str(contact),
        "target_id": str(principal.id),
        "review_token": review["token"],
    }
    result = client.post(base + "/customer-merges", json=body)
    assert result.status_code == 200, result.text
    assert client.post(base + "/customer-merges", json=body).json()["replayed"]
    session.expire_all()
    transport = session.get(ConversationModel, conversation)
    assert {
        c.name: getattr(transport, c.name)
        for c in transport.__table__.columns
        if c.name != "contact_id"
    } == transport_before
    workspace = client.get(f"{base}/customers/{principal.id}/workspace").json()
    assert (
        workspace["opportunities"]["total"] == 1
        and workspace["conversation_total"] == 1
    )
    assert workspace["opportunities"]["items"][0]["contact_id"] == str(principal.id)
    assert (
        client.get(f"{base}/opportunities/{op['id']}/history").json() == history_before
    )
    assert client.get(path).json()["items"][0]["id"] == journal["id"]
    assert (
        client.post(
            path, json=activity, headers={"Idempotency-Key": "merge-call"}
        ).json()["id"]
        == journal["id"]
    )
    session.expire_all()
    assert session.get(ContactModel, contact).status == "archived"
    assert (
        svc.cipher.decrypt(session.get(ContactModel, contact).notes_ciphertext)
        == "Notas originales"
    )
    assert (
        svc.cipher.decrypt(session.get(ContactModel, principal.id).notes_ciphertext)
        == "Notas del principal"
    )
    assert session.get(CustomerProfileModel, contact) is not None
    assert (
        "Notas originales"
        not in session.get(ContactMergeModel, contact).snapshot_ciphertext
    )
    # New CRM commands arriving through an old identity resolve to the principal.
    another = client.post(
        base + "/opportunities",
        json=payload(actor, contact, conversation),
        headers={"Idempotency-Key": "after-merge"},
    )
    assert another.status_code == 201, another.text
    assert another.json()["contact_id"] == str(principal.id)
    assert client.get(base + f"/customers/{contact}/workspace").json()[
        "contact_id"
    ] == str(principal.id)


def test_merge_late_failure_rolls_back_all_associations(crm_opportunities, monkeypatch):  # type: ignore[no-untyped-def]
    client, session, actor, _, contact, conversation = crm_opportunities
    svc = opportunity_service(session)
    principal = target(session, actor.organization_id, svc.cipher)
    base = f"/organizations/{actor.organization_id}/crm"
    op = client.post(
        base + "/opportunities",
        json=payload(actor, contact, conversation),
        headers={"Idempotency-Key": "rollback-op"},
    ).json()
    journal = client.post(
        f"{base}/customers/{contact}/activities",
        json={
            "kind": "call",
            "description": "Must survive rollback",
            "occurred_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            "opportunity_id": op["id"],
        },
        headers={"Idempotency-Key": "rollback-call"},
    ).json()
    duplicate = DuplicateService(svc)
    review = duplicate.preview(actor.organization_id, actor, contact, principal.id)

    def fail_commit():  # type: ignore[no-untyped-def]
        session.flush()
        raise RuntimeError("synthetic failure after all writes")

    with monkeypatch.context() as patch:
        patch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="synthetic failure"):
            duplicate.merge(
                actor.organization_id,
                actor,
                MergeInput(
                    source_id=contact, target_id=principal.id, review_token=review.token
                ),
            )
    session.expire_all()
    assert session.get(ContactMergeModel, contact) is None
    assert session.get(ContactModel, contact).status == "active"
    assert session.get(OpportunityModel, UUID(op["id"])).contact_id == contact
    assert session.get(ConversationModel, conversation).contact_id == contact
    link = session.scalar(select(OpportunityConversationModel))
    assert link.contact_id == contact and str(link.opportunity_id) == op["id"]
    activity = session.get(CrmCustomerActivityModel, UUID(journal["id"]))
    assert activity.contact_id == contact and str(activity.opportunity_id) == op["id"]


def test_merge_stale_preview_foreign_and_restricted_roles(crm_opportunities):  # type: ignore[no-untyped-def]
    client, session, actor, other, contact, _ = crm_opportunities
    svc = opportunity_service(session)
    principal = target(session, actor.organization_id, svc.cipher)
    duplicate = DuplicateService(svc)
    review = duplicate.preview(actor.organization_id, actor, contact, principal.id)
    principal.notes_ciphertext = svc.cipher.encrypt("Cambió después de revisar")
    session.commit()
    body = {
        "source_id": str(contact),
        "target_id": str(principal.id),
        "review_token": review.token,
    }
    base = f"/organizations/{actor.organization_id}/crm"
    assert client.post(base + "/customer-merges", json=body).status_code == 409
    assert session.get(ContactMergeModel, contact) is None
    assert (
        client.get(
            base + f"/merge-preview?source_id={contact}&target_id={contact}"
        ).status_code
        == 409
    )
    assert (
        client.get(f"/organizations/{other.organization_id}/crm/duplicates").status_code
        == 403
    )
    for role in ("viewer", "operator"):
        client.app.dependency_overrides[require_authenticated_user] = (
            lambda role=role: actor.model_copy(update={"role": role})
        )
        assert client.get(base + "/duplicates").status_code == 403
        assert client.post(base + "/customer-merges", json=body).status_code == 403


def test_metrics_closure_edits_and_duration(crm_opportunities):  # type: ignore[no-untyped-def]
    client, session, actor, _, contact, conversation = crm_opportunities
    svc = opportunity_service(session)
    data = payload(actor, contact, conversation)
    update = {
        k: v for k, v in data.items() if k not in {"contact_id", "conversation_id"}
    }
    row = svc.create(
        actor.organization_id,
        actor,
        OpportunityCreate.model_validate(
            {**data, "amount": "250.00", "currency": "PEN"}
        ),
        "metric-op",
    )
    svc.update(
        actor.organization_id,
        row.id,
        actor,
        OpportunityUpdate.model_validate(
            {
                **update,
                "version": 1,
                "stage_code": "offer",
                "amount": "250.00",
                "currency": "PEN",
            }
        ),
    )
    closed = {
        **update,
        "stage_code": "won",
        "next_action": None,
        "close_reason": "Ganada",
        "amount": "250.00",
        "currency": "PEN",
    }
    svc.update(
        actor.organization_id,
        row.id,
        actor,
        OpportunityUpdate.model_validate({**closed, "version": 2}),
    )
    svc.update(
        actor.organization_id,
        row.id,
        actor,
        OpportunityUpdate.model_validate(
            {**closed, "version": 3, "close_reason": "Solo cambia la nota"}
        ),
    )
    for history in session.scalars(
        select(OpportunityHistoryModel).order_by(OpportunityHistoryModel.version)
    ):
        history.occurred_at = datetime(2026, 10, history.version, tzinfo=UTC)
    session.commit()
    report = SalesMetricsService(svc).report(
        actor.organization_id,
        actor,
        datetime(2026, 10, 2, 12, tzinfo=UTC),
        datetime(2026, 10, 3, 12, tzinfo=UTC),
        None,
    )
    assert (
        len(report.closings) == 1
        and report.closings[0].won == 1
        and report.closings[0].won_amount == 250
    )
    assert (
        report.durations[0].stage_code == "offer"
        and report.durations[0].total_hours == 12
    )
    assert (
        not SalesMetricsService(svc)
        .report(
            actor.organization_id,
            actor,
            datetime(2026, 10, 4, tzinfo=UTC),
            datetime(2026, 10, 5, tzinfo=UTC),
            None,
        )
        .closings
    )
    viewer = SalesMetricsService(svc).report(
        actor.organization_id,
        actor.model_copy(update={"role": "viewer"}),
        None,
        None,
        None,
    )
    assert viewer.closings[0].currency is None and viewer.closings[0].won_amount is None
    base = f"/organizations/{actor.organization_id}/crm"
    assert (
        client.get(base + "/sales-metrics?date_from=2026-10-01T00:00:00").status_code
        == 400
    )
