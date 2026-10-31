"""One-off private owner setup for the explicitly identified replacement staging.

Default is read-only. Password entry and --apply are for the human owner only.
This helper is not part of the application image or a public bootstrap endpoint.
"""

import argparse
import getpass
import json
import os
import sys
import warnings
from uuid import uuid4

from app.application.organizations.service import OrganizationService
from app.application.plans.service import PlanEnforcementService
from app.application.users.service import UserService
from app.domain.organization.contracts import OrganizationCreate
from app.domain.user.contracts import UserCreate
from app.infrastructure.database import SessionLocal, engine
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from app.infrastructure.repositories.user_repository import UserRepository
from app.infrastructure.settings import get_settings
from app.observability.context import correlation_context
from app.security.passwords import PasswordService
from sqlalchemy import text

EXPECTED_HOST = os.environ.get("LURI_OPS_DB_HOST", "")
EXPECTED_SHA = "6163751304a261e9a1faf1ad10554951626dcfbe"
OWNER_EMAIL = os.environ.get("LURI_OPS_OWNER_EMAIL", "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if (
        not EXPECTED_HOST
        or not OWNER_EMAIL
        or engine.url.host != EXPECTED_HOST
        or engine.url.database != "defaultdb"
        or engine.url.query.get("sslmode") != "require"
        or settings.build_sha != EXPECTED_SHA
        or settings.environment.value != "production"
        or settings.public_bootstrap_enabled
        or settings.ai_enabled
        or settings.ai_pilot_scopes
        or settings.ai_openai_api_key
    ):
        raise SystemExit("Wrong target or unsafe configuration; no changes made")

    with SessionLocal() as session, correlation_context():
        if session.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() != ("20260921_0026"):
            raise SystemExit("Unexpected schema; no changes made")
        organization_repository = OrganizationRepository(session)
        user_repository = UserRepository(session)
        if user_repository.find_by_email(OWNER_EMAIL) is not None:
            print(json.dumps({"status": "owner_already_exists_no_changes"}))
            return 0
        organizations = organization_repository.list_ordered()
        if len(organizations) > 1 or any(
            item.slug != "kalivur" or item.status != "active" for item in organizations
        ):
            raise SystemExit("Unexpected organizations; no changes made")
        if session.execute(text("SELECT count(*) FROM app_user")).scalar_one() != 0:
            raise SystemExit("Existing users; no changes made")
        if not args.apply:
            print(json.dumps({"status": "ready_for_private_owner_setup"}))
            return 0
        if not sys.stdin.isatty():
            raise SystemExit("A private interactive terminal is required")
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = getpass.getpass("Nueva contraseña (mínimo 12 caracteres): ")
        confirmation = getpass.getpass("Confirma la contraseña: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match; no changes made")
        if (
            not settings.auth_password_min_length
            <= len(password)
            <= (settings.auth_password_max_length)
        ):
            raise SystemExit("Invalid password length; no changes made")

        audit_writer = SqlAlchemyAuditRepository(session)
        plan_repository = SqlAlchemyPlanRepository(session)
        organization = (
            OrganizationService(
                organization_repository, session, audit_writer, plan_repository
            ).get(organizations[0].id)
            if organizations
            else OrganizationService(
                organization_repository, session, audit_writer, plan_repository
            ).create(OrganizationCreate(name="Kalivur", slug="kalivur"))
        )
        request = UserCreate(
            organization_id=organization.id,
            email=OWNER_EMAIL,
            password=password,
        )
        user = UserService(
            user_repository,
            organization_repository,
            PasswordService(max_length=settings.auth_password_max_length),
            session,
            audit_writer,
            PlanEnforcementService(plan_repository),
        ).create(request)
        del password, confirmation, request
        if user.role != "organization_owner":
            raise SystemExit("Unexpected owner role; review before proceeding")
        print(
            json.dumps(
                {
                    "status": "owner_created",
                    "organization_id": str(organization.id),
                    "user_id": str(user.id),
                    "role": user.role,
                    "operation_id": str(uuid4()),
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
