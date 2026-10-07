"""Encrypted synthetic volume fixture for local rehearsals and regression tests."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from app.application.contacts.identity import ContactIdentityHasher
from app.infrastructure.models.contact import ContactModel
from app.security.secret_cipher import SecretCipher
from sqlalchemy import insert
from sqlalchemy.orm import Session


def seed_search_dataset(
    session: Session,
    org: UUID,
    cipher: SecretCipher,
    hasher: ContactIdentityHasher,
    *,
    count: int = 10000,
) -> dict[str, Any]:
    if count < 2100:
        raise ValueError("The volume fixture must cross the old 2000-contact limit")
    base_time = datetime.now(UTC) - timedelta(days=2)
    late: list[str] = []
    group: list[str] = []
    batch = []
    for index in range(count):
        ident = uuid4()
        name = f"Contacto volumen {index:05d}"
        registration = None
        if index in {2001, 2002}:
            name = "José Pérez tardío" if index == 2001 else "JOSE PEREZ TARDIO"
            registration = cipher.encrypt(json.dumps({"email": "TARDIO@example.test"}))
            late.append(str(ident))
        if 2030 <= index <= 2052:
            name = "Marta Grupo paginado"
            group.append(str(ident))
        identity = hasher.identify(org, "whatsapp", f"+1203{index:07d}")
        batch.append(
            {
                "id": ident,
                "organization_id": org,
                "channel_type": "whatsapp",
                "external_identifier_hash": identity.external_identifier_hash,
                "external_identifier_ciphertext": cipher.encrypt(
                    identity.normalized_identifier
                ),
                "display_name_ciphertext": cipher.encrypt(name),
                "registration_ciphertext": registration,
                "status": "active",
                "created_at": base_time + timedelta(seconds=index),
                "updated_at": base_time + timedelta(seconds=index),
            }
        )
        if len(batch) == 500:
            session.execute(insert(ContactModel), batch)
            batch = []
    if batch:
        session.execute(insert(ContactModel), batch)
    session.commit()
    return {
        "count": count,
        "late_ids": late,
        "group_ids": group,
        "phone": "+1 (203) 000-2001",
        "email": "tardio@example.test",
    }
