from dataclasses import asdict, dataclass
from uuid import UUID

from app.application.contacts.identity import ContactIdentityHasher
from app.application.contacts.service import ContactResolutionService
from app.domain.contacts.contracts import ContactIdentityError
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel
from sqlalchemy import select
from sqlalchemy.orm import Session


@dataclass
class ContactBackfillMetrics:
    scanned: int = 0
    eligible: int = 0
    linked: int = 0
    already_linked: int = 0
    contacts_created: int = 0
    contacts_reused: int = 0
    reactivated: int = 0
    skipped_missing_context: int = 0
    skipped_invalid_identity: int = 0
    failed: int = 0

    def safe_dict(self) -> dict[str, int]:
        return asdict(self)


class ContactBackfillService:
    def __init__(
        self,
        session: Session,
        resolver: ContactResolutionService,
        identity_hasher: ContactIdentityHasher,
    ) -> None:
        self._session = session
        self._resolver = resolver
        self._identity_hasher = identity_hasher

    def run(
        self,
        *,
        batch_size: int,
        organization_id: UUID | None,
        dry_run: bool,
    ) -> ContactBackfillMetrics:
        metrics = ContactBackfillMetrics()
        last_id: UUID | None = None
        while True:
            filters = []
            if organization_id is not None:
                filters.append(ConversationModel.organization_id == organization_id)
            if last_id is not None:
                filters.append(ConversationModel.id > last_id)
            batch = list(
                self._session.scalars(
                    select(ConversationModel)
                    .where(*filters)
                    .order_by(ConversationModel.id)
                    .limit(batch_size)
                ).all()
            )
            if not batch:
                break
            for conversation in batch:
                last_id = conversation.id
                self._process(conversation, dry_run, metrics)
            if not dry_run:
                self._session.commit()
        return metrics

    def _process(
        self,
        conversation: ConversationModel,
        dry_run: bool,
        metrics: ContactBackfillMetrics,
    ) -> None:
        metrics.scanned += 1
        if conversation.contact_id is not None:
            metrics.already_linked += 1
            return
        if (
            conversation.organization_id is None
            or not conversation.channel
            or not conversation.external_customer_id
        ):
            metrics.skipped_missing_context += 1
            return
        try:
            identity = self._identity_hasher.identify(
                conversation.organization_id,
                conversation.channel,
                conversation.external_customer_id,
            )
        except ContactIdentityError:
            metrics.skipped_invalid_identity += 1
            return
        metrics.eligible += 1
        existing = self._session.scalars(
            select(ContactModel).where(
                ContactModel.organization_id == conversation.organization_id,
                ContactModel.channel_type == identity.channel_type,
                ContactModel.external_identifier_hash
                == identity.external_identifier_hash,
            )
        ).one_or_none()
        if dry_run:
            if existing is None:
                metrics.contacts_created += 1
            else:
                metrics.contacts_reused += 1
            return
        try:
            was_archived = existing is not None and existing.status == "archived"
            contact = self._resolver.resolve(
                conversation.organization_id,
                conversation.channel,
                conversation.external_customer_id,
            )
            if contact.organization_id != conversation.organization_id:
                raise RuntimeError("contact tenant mismatch")
            conversation.contact_id = contact.id
            if existing is None:
                metrics.contacts_created += 1
            else:
                metrics.contacts_reused += 1
            if was_archived:
                metrics.reactivated += 1
            metrics.linked += 1
        except ContactIdentityError:
            metrics.skipped_invalid_identity += 1
