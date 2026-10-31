from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.contacts.identity import ContactIdentityHasher
from app.application.contacts.repository import ContactRepository
from app.application.contacts.search_index import ContactSearchIndex
from app.domain.contacts.contracts import ContactIdentity
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.repositories.crm_identity import canonical
from app.infrastructure.unit_of_work import commit, rollback
from app.security.secret_cipher import SecretCipher
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


class ContactResolutionError(ValueError):
    pass


class ContactResolutionService:
    def __init__(
        self,
        repository: ContactRepository,
        identity_hasher: ContactIdentityHasher,
        cipher: SecretCipher,
        session: Session,
    ) -> None:
        self._repository = repository
        self._identity_hasher = identity_hasher
        self._cipher = cipher
        self._session = session

    def resolve(
        self, organization_id: UUID, channel_type: str, identifier: str
    ) -> ContactModel:
        identity = self._identity_hasher.identify(
            organization_id, channel_type, identifier
        )
        contact = self._repository.get_by_identity(
            organization_id, identity.channel_type, identity.external_identifier_hash
        )
        if contact is None:
            contact = self._create(identity)
        if contact.organization_id != organization_id:
            raise ContactResolutionError("contact tenant mismatch")
        principal_id = canonical(self._session, organization_id, contact.id)
        if principal_id != contact.id:
            # A reviewed merge keeps the source identity archived and moves its
            # conversations to the principal; reactivating it would undo the merge.
            principal = self._session.get(ContactModel, principal_id)
            if principal is None or principal.organization_id != organization_id:
                raise ContactResolutionError("merged contact principal unavailable")
            contact = principal
        if contact.status == "archived":
            contact.status = "active"
            contact.updated_at = datetime.now(UTC)
            self._commit()
        if self._session.info.get("atomic_transport") and inspect(contact).persistent:
            self._session.refresh(contact, with_for_update=True)
        return contact

    def _create(self, identity: ContactIdentity) -> ContactModel:
        contact = ContactModel(
            id=uuid4(),
            organization_id=identity.organization_id,
            channel_type=identity.channel_type,
            external_identifier_hash=identity.external_identifier_hash,
            external_identifier_ciphertext=self._cipher.encrypt(
                identity.normalized_identifier
            ),
            normalized_identifier_version=1,
            status="active",
        )
        try:
            self._repository.add(contact)
            ContactSearchIndex(self._session, self._cipher, self._identity_hasher).sync(
                contact
            )
            self._commit()
            return contact
        except IntegrityError as exc:
            if self._session.info.get("atomic_transport"):
                raise
            if not _is_identity_conflict(exc):
                raise
            rollback(self._session)
            existing = self._repository.get_by_identity(
                identity.organization_id,
                identity.channel_type,
                identity.external_identifier_hash,
            )
            if existing is None:
                raise ContactResolutionError("contact resolution conflict") from exc
            return existing

    def _commit(self) -> None:
        try:
            commit(self._session)
        except IntegrityError:
            rollback(self._session)
            raise


def _is_identity_conflict(exc: IntegrityError) -> bool:
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if constraint is not None:
        return bool(constraint == "uq_contact_organization_channel_identity")
    return (
        "UNIQUE constraint failed: contact.organization_id, contact.channel_type, "
        "contact.external_identifier_hash" in str(exc.orig)
    )
