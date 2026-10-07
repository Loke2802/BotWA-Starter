"""Tenant-scoped candidate IDs without thousands of separately compiled binds."""

import json
from uuid import UUID

from sqlalchemy import Select, cast, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.infrastructure.models.contact import ContactModel


def matching_contact_ids(
    session: Session, org: UUID, ids: list[UUID]
) -> Select[tuple[UUID]]:
    dialect = session.get_bind().dialect.name
    if len(ids) <= 200 or dialect not in {"postgresql", "sqlite"}:
        values = ContactModel.id.in_(ids)
    else:
        # UUID hex matches SQLite's Uuid storage and casts to PostgreSQL UUID.
        # One bound JSON value contains derived IDs, never contact names/identity.
        payload = literal(json.dumps([ident.hex for ident in ids]))
        if dialect == "postgresql":
            expanded = (
                func.jsonb_array_elements_text(cast(payload, JSONB))
                .table_valued("value")
                .render_derived()
            )
        else:
            expanded = func.json_each(payload).table_valued("value")
        values = ContactModel.id.in_(
            select(cast(expanded.c.value, ContactModel.id.type))
        )
    return select(ContactModel.id).where(ContactModel.organization_id == org, values)
