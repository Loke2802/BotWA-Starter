"""CRM redirects do not replace channel identifiers or messaging recipients."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.crm.contracts import CrmConflict
from app.infrastructure.models.crm_contact_merge import ContactMergeModel


def canonical(session: Session, org: UUID, contact: UUID) -> UUID:
    seen: set[UUID] = set()
    while contact not in seen:
        seen.add(contact)
        row = session.scalar(
            select(ContactMergeModel).where(
                ContactMergeModel.organization_id == org,
                ContactMergeModel.source_id == contact,
            )
        )
        if row is None:
            return contact
        contact = row.target_id
    raise CrmConflict("La cadena de clientes unidos es inválida.")


def family(session: Session, org: UUID, contact: UUID) -> list[UUID]:
    root = canonical(session, org, contact)
    sources = session.scalars(
        select(ContactMergeModel.source_id).where(
            ContactMergeModel.organization_id == org
        )
    ).all()
    return [root, *(s for s in sources if canonical(session, org, s) == root)]
