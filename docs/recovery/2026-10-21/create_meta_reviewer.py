"""Exact staging reviewer setup; default reads, owner enters password privately.

--apply requires action-time owner approval before starting. It never sends
credentials to Meta; no credential is accepted through arguments or environment.
"""

import argparse
import getpass
import json
import sys
import warnings

from app.application.plans.service import PlanEnforcementService
from app.application.users.service import UserService
from app.domain.user.contracts import UserCreate
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from app.infrastructure.repositories.user_repository import UserRepository
from app.observability.context import correlation_context
from app.security.passwords import PasswordService
from inspect_meta_reviewer import ORGANIZATION_ID, REVIEW_EMAIL, inspect
from load_meta_test_access_token import SessionLocal, get_settings, validate_target

EXPECTED_COUNTS = {
    "app_user": 1,
    "bot": 1,
    "contact": 1,
    "conversation": 1,
    "knowledge_entry": 0,
    "whatsapp_channel_configuration": 1,
    "integration_connection": 0,
    "managed_automation_definition": 0,
    "business_calendar": 0,
}


def validate_scope(report):
    if (
        report.get("email") != REVIEW_EMAIL
        or report.get("organization_id") != str(ORGANIZATION_ID)
        or report.get("ai_enabled") is not False
        or report.get("transport") != "disabled"
        or report.get("owner_role") != "organization_owner"
        or report.get("candidate_role") != "operator"
    ):
        raise ValueError("unexpected access target")
    existing = report.get("existing_accounts")
    if existing:
        if len(existing) == 1 and (
            existing[0].get("same_organization") is True
            and existing[0].get("role") == "operator"
            and existing[0].get("status") == "active"
        ):
            return "reviewer_already_exists_no_changes"
        raise ValueError("account collision")
    if (
        existing != []
        or report.get("counts_in_organization") != EXPECTED_COUNTS
        or report.get("conversation_identity_counts")
        != {"other_bot": 0, "other_customer": 0}
        or report.get("contacts_without_owner_test_conversation") != 0
        or report.get("active_users") != 1
    ):
        raise ValueError("scope changed; inspect before granting access")
    limit = report.get("user_limit", {})
    if limit.get("kind") != "unlimited" and not (
        limit.get("kind") == "limited"
        and type(limit.get("value")) is int
        and limit["value"] > report["active_users"]
    ):
        raise ValueError("insufficient user capacity")
    return "ready_for_private_reviewer_setup"


def read_password(minimum, maximum):
    if not sys.stdin.isatty():
        raise ValueError("private terminal required")
    print(f"La contrasena debe tener entre {minimum} y {maximum} caracteres.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        for attempt in range(3):
            password = getpass.getpass("Nueva contrasena EXCLUSIVA de Luri (oculta): ")
            confirmation = getpass.getpass("Repite la contrasena (oculta): ")
            if password == confirmation and minimum <= len(password) <= maximum:
                accepted_password = password
                break
            if password != confirmation:
                print("Las contrasenas no coinciden. No se guardo ninguna cuenta.")
            else:
                print("Longitud no valida. No se guardo ninguna cuenta.")
            del password, confirmation
            if attempt < 2:
                print(f"Repite ambas entradas; intento {attempt + 2} de 3.")
        else:
            raise ValueError("password entry attempts exhausted")
    if input("Para crear solo esta cuenta de staging escribe CREAR REVISION: ") != (
        "CREAR REVISION"
    ):
        raise ValueError("cancelled")
    return accepted_password


def main(apply=False):
    report = inspect()  # Read-only transaction closed before password input.
    status = validate_scope(report)
    if not apply or status == "reviewer_already_exists_no_changes":
        print(
            json.dumps(
                {
                    "status": status,
                    "email": REVIEW_EMAIL,
                    "role": "operator",
                    "scope": "Kalivur staging; whole organization",
                    "additional_edit_access": [
                        "contacts",
                        "knowledge",
                        "whatsapp_configuration",
                    ],
                    "ai_enabled": False,
                    "transport": "disabled",
                    "account_created": False,
                }
            )
        )
        return
    print("Destino: luri-staging / Kalivur; correo: " + REVIEW_EMAIL)
    print("Rol operator: toda la organizacion de staging, no un bot aislado.")
    print("Permite atender y editar contactos, conocimiento y configuracion WhatsApp.")
    print("No comparte credenciales con Meta; IA y transporte permanecen apagados.")
    settings = get_settings()
    password = read_password(
        max(12, settings.auth_password_min_length), settings.auth_password_max_length
    )
    fresh = inspect()
    if validate_scope(fresh) != "ready_for_private_reviewer_setup":
        raise ValueError("account changed during private input")
    with SessionLocal() as session, correlation_context():
        owner, _, _ = validate_target(
            session,
            for_update=True,
            allow_webhook_secrets=True,
            allow_receiving_channel=True,
        )
        organization_repository = OrganizationRepository(session)
        plan_repository = SqlAlchemyPlanRepository(session)
        request = UserCreate(
            organization_id=ORGANIZATION_ID,
            email=REVIEW_EMAIL,
            password=password,
            first_name="Meta",
            last_name="Review",
            role="operator",
        )
        user = UserService(
            UserRepository(session),
            organization_repository,
            PasswordService(max_length=settings.auth_password_max_length),
            session,
            SqlAlchemyAuditRepository(session),
            PlanEnforcementService(plan_repository),
        ).create(request, actor=owner)
        del password, request
        if user.role != "operator" or user.organization_id != ORGANIZATION_ID:
            raise ValueError("unexpected result; inspect before proceeding")
        print(
            json.dumps(
                {
                    "status": "reviewer_created_in_staging",
                    "user_id": str(user.id),
                    "email": user.email,
                    "organization_id": str(user.organization_id),
                    "role": user.role,
                    "account_created": True,
                    "credentials_shared_with_meta": False,
                }
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        main(apply=args.apply)
    except (Exception, KeyboardInterrupt):
        raise SystemExit(
            "Reviewer setup stopped; details omitted. Inspect before any retry."
        ) from None
