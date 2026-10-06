from datetime import UTC, datetime

import pytest
from app.api.dependencies import require_authenticated_user
from app.application.crm.follow_up import FollowUpService
from app.domain.crm.contracts import OpportunityCreate, OpportunityUpdate
from app.infrastructure.models.organization import OrganizationModel

from tests.crm_opportunity_support import opportunity_service, payload, seed
from tests.test_crm_opportunities import crm_opportunities as crm_opportunities


def test_queue_counts_deadline_buckets_current_actions_and_closed(crm_opportunities):  # type: ignore[no-untyped-def]
    client, session, actor, _, contact, conversation = crm_opportunities
    service = opportunity_service(session)
    data = payload(actor, contact, conversation)
    due = {
        **data,
        "next_action": {
            "description": "Overdue private action",
            "due_at": "2000-01-01T00:00:00Z",
        },
    }
    overdue = service.create(
        actor.organization_id, actor, OpportunityCreate.model_validate(due), "due"
    )
    future = service.create(
        actor.organization_id, actor, OpportunityCreate.model_validate(data), "future"
    )
    update = {
        k: v for k, v in data.items() if k not in {"contact_id", "conversation_id"}
    }
    service.update(
        actor.organization_id,
        future.id,
        actor,
        OpportunityUpdate.model_validate(
            {
                **update,
                "version": 1,
                "next_action": {
                    "description": "Future",
                    "due_at": "2099-01-01T00:00:00Z",
                },
            }
        ),
    )
    service.create(
        actor.organization_id,
        actor,
        OpportunityCreate.model_validate(
            {
                **data,
                "next_action": None,
                "no_action_reason": "Waiting for customer decision",
            }
        ),
        "no-action",
    )
    closed = service.create(
        actor.organization_id, actor, OpportunityCreate.model_validate(due), "closed"
    )
    service.update(
        actor.organization_id,
        closed.id,
        actor,
        OpportunityUpdate.model_validate(
            {
                **update,
                "version": 1,
                "stage_code": "won",
                "next_action": None,
                "close_reason": "Accepted proposal",
            }
        ),
    )
    other, _, other_contact, other_conversation = seed(session)
    service.create(
        other.organization_id,
        other,
        OpportunityCreate.model_validate(
            payload(other, other_contact, other_conversation)
        ),
        "foreign",
    )
    base = f"/organizations/{actor.organization_id}/crm/follow-up"
    result = client.get(base).json()
    assert result["summary"] == {
        "open": 3,
        "overdue": 1,
        "upcoming": 1,
        "without_action": 1,
    }
    assert result["total"] == 3
    assert result["timezone"] == "America/Lima"
    assert result["items"][0]["id"] == str(overdue.id)
    assert client.get(base + "?due=overdue").json()["total"] == 1
    assert client.get(base + "?due=without_action").json()["total"] == 1
    assert client.get(base + "?due=upcoming").json()["total"] == 1
    page = client.get(base + "?page_size=1&page=2").json()
    assert page["total"] == 3 and page["has_next"]
    assert client.get(base + "?assigned_user_id=" + str(other.id)).json()["total"] == 0
    assert client.get(base + "?stage_code=won").json()["summary"]["open"] == 0
    assert client.get(base + "?due=invalid").status_code == 422
    assert client.get(base + "?page_size=101").status_code == 422


def test_deadline_equality_and_old_cancelled_action_do_not_count(crm_opportunities):  # type: ignore[no-untyped-def]
    _, session, actor, _, contact, conversation = crm_opportunities
    svc = opportunity_service(session)
    data = payload(actor, contact, conversation)
    data["next_action"] = {
        "description": "Exact deadline",
        "due_at": "2026-10-06T15:00:00Z",
    }
    svc.create(
        actor.organization_id, actor, OpportunityCreate.model_validate(data), "boundary"
    )
    queue = FollowUpService(session, svc.cipher)
    result = queue.list(
        actor.organization_id, actor, as_of=datetime(2026, 10, 6, 15, tzinfo=UTC)
    )
    assert result.summary.overdue == 0 and result.summary.upcoming == 1


@pytest.mark.parametrize(
    "role", ["organization_owner", "organization_admin", "operator", "viewer"]
)
def test_follow_up_roles_and_tenant_authorization(crm_opportunities, role):  # type: ignore[no-untyped-def]
    client, session, actor, other, contact, conversation = crm_opportunities
    created = opportunity_service(session).create(
        actor.organization_id,
        actor,
        OpportunityCreate.model_validate(payload(actor, contact, conversation)),
        "role-case",
    )
    principal = actor.model_copy(update={"role": role})
    client.app.dependency_overrides[require_authenticated_user] = lambda: principal
    base = f"/organizations/{actor.organization_id}/crm"
    response = client.get(base + "/follow-up")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert (item["title"] == "Oportunidad") == (role == "viewer")
    assert (item["need"] is None) == (role == "viewer")
    assert (
        client.get(f"/organizations/{other.organization_id}/crm/follow-up").status_code
        == 403
    )
    assert (
        client.get(
            f"/organizations/{other.organization_id}/crm/opportunities/{created.id}"
        ).status_code
        == 403
    )
    if role == "viewer":
        assert item["next_action"]["description"] == "Contenido restringido"
        assert (
            client.post(
                base + "/opportunities",
                json=payload(actor, contact, conversation),
                headers={"Idempotency-Key": "viewer-write"},
            ).status_code
            == 403
        )
    org = session.get(OrganizationModel, actor.organization_id)
    assert org is not None
    org.status = "suspended"
    session.commit()
    assert client.get(base + "/follow-up").status_code == 404
