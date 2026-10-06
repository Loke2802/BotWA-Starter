from datetime import UTC, datetime, timedelta

import pytest
from app.api.dependencies import require_authenticated_user
from app.application.crm.follow_up import FollowUpService
from app.domain.crm.contracts import OpportunityCreate, OpportunityUpdate
from app.infrastructure.models.organization import OrganizationModel

from tests.crm_opportunity_support import opportunity_service, payload, seed
from tests.test_crm_opportunities import crm_opportunities as crm_opportunities


@pytest.mark.parametrize(
    "zone,instant,start,end",
    [
        (
            "America/Lima",
            "2026-10-06T02:00:00+00:00",
            "2026-10-05T05:00:00+00:00",
            "2026-10-06T05:00:00+00:00",
        ),
        (
            "Europe/Madrid",
            "2026-03-29T12:00:00+00:00",
            "2026-03-28T23:00:00+00:00",
            "2026-03-29T22:00:00+00:00",
        ),
    ],
)
def test_agenda_day_boundaries(crm_opportunities, zone, instant, start, end):  # type: ignore[no-untyped-def]
    _, session, actor, other, contact, conversation = crm_opportunities
    org = session.get(OrganizationModel, actor.organization_id)
    assert org
    org.settings = {**org.settings, "timezone": zone}
    session.commit()
    svc = opportunity_service(session)
    data = payload(actor, contact, conversation)
    dates = [
        datetime.fromisoformat(start) - timedelta(seconds=1),
        datetime.fromisoformat(start),
        datetime.fromisoformat(end) - timedelta(seconds=1),
        datetime.fromisoformat(end),
    ]
    ids = []
    for i, date in enumerate(dates):
        row = svc.create(
            actor.organization_id,
            actor,
            OpportunityCreate.model_validate(
                {
                    **data,
                    "next_action": {
                        "description": "Acción por fecha",
                        "due_at": date.isoformat(),
                    },
                }
            ),
            f"agenda-{i}",
        )
        ids.append(row.id)
    queue = FollowUpService(session, svc.cipher)
    now = datetime.fromisoformat(instant)
    today = queue.list(
        actor.organization_id, actor, due="today", as_of=now, page_size=1
    )
    assert today.day_start == datetime.fromisoformat(start)
    assert today.day_end == datetime.fromisoformat(end)
    assert today.total == 2 and today.has_next and today.items[0].id == ids[1]
    assert today.summary.future == 1
    tomorrow = queue.list(actor.organization_id, actor, due="future", as_of=now)
    assert [item.id for item in tomorrow.items] == [ids[3]]
    assert (
        queue.list(
            actor.organization_id,
            actor,
            due="today",
            assigned_user_id=other.id,
            as_of=now,
        ).total
        == 0
    )
    update = {
        k: v for k, v in data.items() if k not in {"contact_id", "conversation_id"}
    }
    svc.update(
        actor.organization_id,
        ids[1],
        actor,
        OpportunityUpdate.model_validate(
            {
                **update,
                "version": 1,
                "complete_previous_action": True,
                "next_action": {"description": "Mañana", "due_at": end},
            }
        ),
    )
    assert queue.list(actor.organization_id, actor, due="today", as_of=now).total == 1
    assert queue.list(actor.organization_id, actor, due="future", as_of=now).total == 2


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
        "today": 0,
        "future": 1,
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
