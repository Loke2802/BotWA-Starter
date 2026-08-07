from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.contacts.repository import ContactRepository
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel


class SqlAlchemyContactRepository(ContactRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_identity(
        self, organization_id: UUID, channel_type: str, external_identifier_hash: str
    ) -> ContactModel | None:
        return self._session.scalars(
            select(ContactModel).where(
                ContactModel.organization_id == organization_id,
                ContactModel.channel_type == channel_type,
                ContactModel.external_identifier_hash == external_identifier_hash,
            )
        ).one_or_none()

    def get_scoped(
        self, contact_id: UUID, organization_id: UUID
    ) -> ContactModel | None:
        return self._session.scalars(
            select(ContactModel).where(
                ContactModel.id == contact_id,
                ContactModel.organization_id == organization_id,
            )
        ).one_or_none()

    def add(self, contact: ContactModel) -> ContactModel:
        self._session.add(contact)
        self._session.flush()
        return contact

    def list_scoped(
        self,
        organization_id: UUID,
        *,
        status: str | None,
        channel_type: str | None,
        bot_id: UUID | None,
        external_identifier_hash: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ContactModel], int]:
        filters = [ContactModel.organization_id == organization_id]
        if status is not None:
            filters.append(ContactModel.status == status)
        if channel_type is not None:
            filters.append(ContactModel.channel_type == channel_type)
        if external_identifier_hash is not None:
            filters.append(
                ContactModel.external_identifier_hash == external_identifier_hash
            )
        if bot_id is not None:
            contact_ids = select(ConversationModel.contact_id).where(
                ConversationModel.organization_id == organization_id,
                ConversationModel.bot_id == bot_id,
                ConversationModel.contact_id.is_not(None),
            )
            filters.append(ContactModel.id.in_(contact_ids))
        stmt = (
            select(ContactModel)
            .where(*filters)
            .order_by(ContactModel.created_at.desc(), ContactModel.id)
            .offset(offset)
            .limit(limit)
        )
        total_stmt = select(func.count()).select_from(ContactModel).where(*filters)
        return list(self._session.scalars(stmt).all()), int(
            self._session.execute(total_stmt).scalar_one()
        )
