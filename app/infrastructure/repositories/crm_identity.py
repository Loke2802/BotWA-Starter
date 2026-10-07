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
    links = redirects(session, org)
    root = resolve(links, contact)
    return [root, *(s for s in links if resolve(links, s) == root)]


def redirects(session: Session, org: UUID) -> dict[UUID, UUID]:
    return {
        row.source_id: row.target_id
        for row in session.execute(
            select(ContactMergeModel.source_id, ContactMergeModel.target_id).where(
                ContactMergeModel.organization_id == org
            )
        )
    }


def resolve(links: dict[UUID, UUID], contact: UUID) -> UUID:
    seen: set[UUID] = set()
    while contact in links:
        if contact in seen:
            raise CrmConflict("La cadena de clientes unidos es inválida.")
        seen.add(contact)
        contact = links[contact]
    return contact
