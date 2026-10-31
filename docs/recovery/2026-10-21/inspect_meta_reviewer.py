"""Read-only scope inspection for the exact Luri staging review account."""

import json
import os

from app.domain.access.contracts import ROLE_PERMISSIONS
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from load_meta_test_access_token import (
    BOT_ID,
    EXPECTED_HOST,
    EXPECTED_SHA,
    ORGANIZATION_ID,
    SessionLocal,
    engine,
    get_settings,
    validate_target,
)
from sqlalchemy import text

REVIEW_EMAIL = os.environ.get("LURI_OPS_REVIEWER_EMAIL", "")
TEST_RECIPIENT = os.environ.get("LURI_OPS_TEST_RECIPIENT", "")
TABLES = (
    "app_user",
    "bot",
    "contact",
    "conversation",
    "knowledge_entry",
    "whatsapp_channel_configuration",
    "integration_connection",
    "managed_automation_definition",
    "business_calendar",
)


def inspect():
    if (
        not REVIEW_EMAIL
        or not TEST_RECIPIENT
        or engine.url.host != EXPECTED_HOST
        or engine.url.database != "defaultdb"
        or engine.url.query.get("sslmode") != "require"
        or get_settings().build_sha != EXPECTED_SHA
    ):
        raise ValueError("wrong target")
    with SessionLocal() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        session.execute(text("SET LOCAL statement_timeout = '10s'"))
        owner, _, _ = validate_target(
            session, allow_webhook_secrets=True, allow_receiving_channel=True
        )
        params = {
            "org": ORGANIZATION_ID,
            "bot": BOT_ID,
            "email": REVIEW_EMAIL,
            "recipient": TEST_RECIPIENT,
        }
        existing = (
            session.execute(
                text(
                    "SELECT id, organization_id, role, status FROM app_user "
                    "WHERE email=:email"
                ),
                params,
            )
            .mappings()
            .all()
        )
        counts = {
            table: session.execute(
                text(f"SELECT count(*) FROM {table} WHERE organization_id=:org"), params
            ).scalar_one()
            for table in TABLES
        }
        identity_counts = (
            session.execute(
                text(
                    "SELECT count(*) FILTER (WHERE bot_id IS DISTINCT FROM :bot) "
                    "AS other_bot, count(*) FILTER (WHERE "
                    "regexp_replace(coalesce(external_customer_id,''), "
                    "'[^0-9]', '', 'g') <> :recipient) AS other_customer "
                    "FROM conversation WHERE organization_id=:org"
                ),
                params,
            )
            .mappings()
            .one()
        )
        contacts_without_owner_test_conversation = session.execute(
            text(
                "SELECT count(*) FROM contact c WHERE c.organization_id=:org "
                "AND NOT EXISTS (SELECT 1 FROM conversation v WHERE v.contact_id=c.id "
                "AND v.organization_id=:org AND v.bot_id=:bot AND "
                "regexp_replace(coalesce(v.external_customer_id,''), "
                "'[^0-9]', '', 'g') "
                "= :recipient)"
            ),
            params,
        ).scalar_one()
        repository = SqlAlchemyPlanRepository(session)
        assignment = repository.get_assignment(ORGANIZATION_ID)
        plan = (
            repository.get_plan_by_id(assignment.plan_definition_id)
            if assignment
            else None
        )
        limit = (
            plan.configuration.limits.max_active_users.model_dump() if plan else None
        )
        active_users = session.execute(
            text(
                "SELECT count(*) FROM app_user WHERE organization_id=:org "
                "AND status='active'"
            ),
            params,
        ).scalar_one()
        report = {
            "status": "reviewer_scope_inspected_read_only",
            "email": REVIEW_EMAIL,
            "organization_id": str(ORGANIZATION_ID),
            "existing_accounts": [
                {
                    "id": str(row["id"]),
                    "same_organization": row["organization_id"] == ORGANIZATION_ID,
                    "role": row["role"],
                    "status": row["status"],
                }
                for row in existing
            ],
            "counts_in_organization": counts,
            "conversation_identity_counts": dict(identity_counts),
            "contacts_without_owner_test_conversation": (
                contacts_without_owner_test_conversation
            ),
            "active_users": active_users,
            "user_limit": limit,
            "candidate_role": "operator",
            "candidate_permissions": sorted(ROLE_PERMISSIONS["operator"]),
            "permission_scope": "organization_not_single_bot",
            "owner_role": owner.role,
            "ai_enabled": False,
            "transport": "disabled",
            "writes": 0,
            "account_created": False,
        }
        session.rollback()
    return report


if __name__ == "__main__":
    try:
        print(json.dumps(inspect(), ensure_ascii=True))
    except Exception:
        raise SystemExit(
            "Scope inspection incomplete; details omitted; no account created"
        ) from None
