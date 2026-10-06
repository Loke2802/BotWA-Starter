"""Migrate synthetic pre-CRM data and verify two real pg_dump/pg_restore recoveries.

Requires an explicitly named disposable Docker PostgreSQL on localhost.
Creates uniquely named databases. Never drops databases or uses a remote URL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.application.crm.customer_workspace import CustomerWorkspaceService
from app.application.crm.duplicates import DuplicateService
from app.domain.crm.contracts import OpportunityCreate, OpportunityUpdate
from app.domain.crm.customer_contracts import ActivityInput
from app.domain.crm.growth_contracts import MergeInput
from app.infrastructure.models.managed_automation import (
    ManagedAutomationDefinitionModel,
)
from app.infrastructure.models.message import MessageModel
from app.infrastructure.models.user import UserModel
from app.security.passwords import PasswordService
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from tests.crm_opportunity_support import opportunity_service, payload, seed
from tests.test_crm_growth import target

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(engine: Engine) -> dict[str, str]:
    # SQL JSON normalizes datetime/UUID/byte representation; hashing includes
    # ciphertext, history, rows and revisions without exporting private values.
    with engine.connect() as connection:
        return {
            table: hashlib.sha256(
                "\n".join(
                    sorted(
                        connection.scalars(
                            text(f'SELECT row_to_json(t)::text FROM "{table}" AS t')
                        )
                    )
                ).encode()
            ).hexdigest()
            for table in inspect(connection).get_table_names()
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--port", type=int, default=15437)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.container.startswith("luri-crm-local-"):
        parser.error(
            "Only explicitly named luri-crm-local-* disposable containers are accepted"
        )
    info = json.loads(
        subprocess.check_output(["docker", "inspect", args.container], text=True)
    )[0]
    binding = info["NetworkSettings"]["Ports"]["5432/tcp"]
    if not any(
        b["HostIp"] == "127.0.0.1" and int(b["HostPort"]) == args.port for b in binding
    ):
        parser.error(
            "The disposable PostgreSQL must be bound to 127.0.0.1 at the requested port"
        )
    prefix = "luri_rehearsal_" + uuid4().hex[:10]
    databases = {
        key: prefix + "_" + key for key in ["source", "before", "after", "invalid"]
    }

    def docker(*command: str) -> None:
        subprocess.run(
            ["docker", "exec", args.container, *command],
            check=True,
            stdout=subprocess.DEVNULL,
        )

    def url(database: str) -> str:
        return f"postgresql+psycopg://botwa:crm_local_test@127.0.0.1:{args.port}/{database}?connect_timeout=5"

    def migrate(database: str, revision: str) -> None:
        env = {**os.environ, "BOTWA_DATABASE_URL": url(database)}
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", revision],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    for database in databases.values():
        docker("createdb", "-U", "botwa", database)
    migrate(databases["source"], "20260921_0026")
    engine = create_engine(url(databases["source"]))
    with Session(engine) as session:
        actor, other, contact, conversation = seed(session, legacy=True)
        accounts = {}
        for role in ["organization_owner", "operator", "viewer"]:
            user = UserModel(
                id=uuid4(),
                organization_id=actor.organization_id,
                email=f"{role}@local-crm.example.test",
                role=role,
                status="active",
                first_name=role,
                password_hash=PasswordService().hash("SyntheticCRM2026!"),
            )
            session.add(user)
            accounts[role] = user.email
        foreign = session.get(UserModel, other.id)
        assert foreign is not None
        foreign.email = "other-company@local-crm.example.test"
        foreign.password_hash = PasswordService().hash("SyntheticCRM2026!")
        accounts["other_company"] = foreign.email
        bot_id = session.scalar(
            text("SELECT bot_id FROM conversation WHERE id=:id"), {"id": conversation}
        )
        cipher = opportunity_service(session).cipher
        session.add(
            ManagedAutomationDefinitionModel(
                organization_id=actor.organization_id,
                bot_id=bot_id,
                name="Automatización ficticia previa",
                trigger_type="conversation.inbound_received",
                action_type="request_handoff",
                conditions_data={},
                action_data={},
                status="draft",
                created_by_user_id=actor.id,
                updated_by_user_id=actor.id,
            )
        )
        session.add(
            MessageModel(
                conversation_id=conversation,
                organization_id=actor.organization_id,
                bot_id=bot_id,
                role="customer",
                content="[encrypted]",
                direction="inbound",
                channel_type="whatsapp",
                delivery_status="received",
                message_type="text",
                text_ciphertext=cipher.encrypt("Mensaje ficticio previo al CRM"),
                occurred_at=datetime.now(UTC),
            )
        )
        session.commit()
    before = fingerprint(engine)
    pre_dump = f"/tmp/{prefix}_before.dump"
    docker("pg_dump", "-U", "botwa", "-Fc", "-f", pre_dump, databases["source"])
    docker(
        "pg_restore",
        "-U",
        "botwa",
        "--exit-on-error",
        "--dbname",
        databases["invalid"],
        pre_dump,
    )
    invalid_engine = create_engine(url(databases["invalid"]))
    with invalid_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE managed_automation_definition "
                "SET action_type='unsupported_synthetic_action'"
            )
        )
    invalid_before = fingerprint(invalid_engine)
    try:
        migrate(databases["invalid"], "head")
    except subprocess.CalledProcessError as exc:
        assert "Historical automation action is unsupported" in (exc.stderr or "")
        assert (
            fingerprint(invalid_engine) == invalid_before
        ), "Rejected migration changed data"
    else:
        raise AssertionError("Invalid legacy action must block upgrade")
    docker(
        "pg_restore",
        "-U",
        "botwa",
        "--exit-on-error",
        "--dbname",
        databases["before"],
        pre_dump,
    )
    restored_before = create_engine(url(databases["before"]))
    assert fingerprint(restored_before) == before, "Pre-increment restore changed data"
    migrate(databases["before"], "head")
    upgraded = fingerprint(restored_before)
    assert all(
        upgraded[t] == digest for t, digest in before.items() if t != "alembic_version"
    ), "Migration changed existing data"
    with Session(restored_before) as session:
        service = opportunity_service(session)
        data = payload(actor, contact, conversation)
        data["next_action"] = {
            "description": "Seguimiento vencido ficticio",
            "due_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
        }
        created = service.create(
            actor.organization_id,
            actor,
            OpportunityCreate.model_validate(data),
            "recovery-create",
        )
        update = {
            k: v for k, v in data.items() if k not in {"contact_id", "conversation_id"}
        }
        service.update(
            actor.organization_id,
            created.id,
            actor,
            OpportunityUpdate.model_validate(
                {
                    **update,
                    "version": 1,
                    "stage_code": "offer",
                    "complete_previous_action": True,
                }
            ),
        )
        upcoming = {
            **data,
            "title": "Próxima propuesta ficticia",
            "conversation_id": None,
            "next_action": {
                "description": "Enviar propuesta ficticia",
                "due_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
            },
        }
        service.create(
            actor.organization_id,
            actor,
            OpportunityCreate.model_validate(upcoming),
            "recovery-future",
        )
        service.create(
            actor.organization_id,
            actor,
            OpportunityCreate.model_validate(
                {
                    **data,
                    "title": "Esperando decisión ficticia",
                    "next_action": None,
                    "no_action_reason": "Esperar respuesta del cliente",
                }
            ),
            "recovery-no-action",
        )
        assert (
            service.create(
                actor.organization_id,
                actor,
                OpportunityCreate.model_validate(data),
                "recovery-create",
            ).id
            == created.id
        )
        activity_data = ActivityInput(
            kind="call",
            description="Llamada sintética recuperable",
            occurred_at=datetime.now(UTC) - timedelta(minutes=1),
            opportunity_id=created.id,
        )
        activity = CustomerWorkspaceService(service).record_activity(
            actor.organization_id, contact, actor, activity_data, "recovery-activity"
        )
        merge_source = target(session, actor.organization_id, service.cipher)
        merge_target = target(session, actor.organization_id, service.cipher)
        review = DuplicateService(service).preview(
            actor.organization_id, actor, merge_source.id, merge_target.id
        )
        merge_request = MergeInput(
            source_id=merge_source.id,
            target_id=merge_target.id,
            review_token=review.token,
        )
        DuplicateService(service).merge(actor.organization_id, actor, merge_request)
    after = fingerprint(restored_before)
    post_dump = f"/tmp/{prefix}_after.dump"
    docker("pg_dump", "-U", "botwa", "-Fc", "-f", post_dump, databases["before"])
    docker(
        "pg_restore",
        "-U",
        "botwa",
        "--exit-on-error",
        "--dbname",
        databases["after"],
        post_dump,
    )
    restored_after = create_engine(url(databases["after"]))
    assert fingerprint(restored_after) == after, "Post-increment restore changed data"
    with Session(restored_after) as session:
        service = opportunity_service(session)
        assert service.get(actor.organization_id, created.id, actor).version == 2
        assert (
            len(service.history(actor.organization_id, created.id, actor, 1, 20)) == 2
        )
        assert (
            service.create(
                actor.organization_id,
                actor,
                OpportunityCreate.model_validate(data),
                "recovery-create",
            ).id
            == created.id
        )
        journal = CustomerWorkspaceService(service)
        assert journal.activities(actor.organization_id, contact, actor, 1).total == 1
        assert (
            journal.record_activity(
                actor.organization_id,
                contact,
                actor,
                activity_data,
                "recovery-activity",
            ).id
            == activity.id
        )
        assert (
            DuplicateService(service)
            .merge(actor.organization_id, actor, merge_request)
            .replayed
        )
        assert (
            CustomerWorkspaceService(service)
            .workspace(actor.organization_id, merge_request.source_id, actor, 1, 1)
            .contact_id
            == merge_request.target_id
        )
    # The application rollback strategy preserves the schema. This checks
    # that a destructive downgrade is refused rather than deleting CRM data.
    env = {**os.environ, "BOTWA_DATABASE_URL": url(databases["after"])}
    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "20260921_0026"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert downgrade.returncode != 0 and "preserve the schema" in downgrade.stderr
    assert fingerprint(restored_after) == after, "Refused downgrade changed data"
    report = {
        "tested_at": datetime.now(UTC).isoformat(),
        "environment": "disposable local PostgreSQL",
        "databases": databases,
        "table_count_before": len(before),
        "table_count_after": len(after),
        "pre_restore_equal": True,
        "existing_rows_unchanged_after_upgrade": True,
        "post_restore_equal": True,
        "customer_activity_restored_and_replay_deduplicated": True,
        "reviewed_merge_restored_and_replay_deduplicated": True,
        "history_and_idempotency_after_restore": True,
        "destructive_downgrade_refused_without_changes": True,
        "invalid_legacy_configuration_blocks_upgrade_without_changes": True,
        "organization_id": str(actor.organization_id),
        "other_organization_id": str(other.organization_id),
        "contact_id": str(contact),
        "conversation_id": str(conversation),
        "opportunity_id": str(created.id),
        "accounts": accounts,
        "fingerprints_before": before,
        "fingerprints_after": after,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "PASS: both restores, existing-data migration, history, "
        "idempotency and guarded rollback"
    )
    for resource in [engine, restored_before, restored_after, invalid_engine]:
        resource.dispose()


if __name__ == "__main__":
    main()
