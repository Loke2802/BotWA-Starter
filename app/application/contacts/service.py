from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.contacts.identity import ContactIdentityHasher
from app.application.contacts.repository import ContactRepository
from app.domain.contacts.contracts import ContactIdentity
from app.infrastructure.models.contact import ContactModel
from app.security.secret_cipher import SecretCipher
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
        if contact.status == "archived":
            contact.status = "active"
            contact.updated_at = datetime.now(UTC)
            self._commit()
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
            self._commit()
            return contact
        except IntegrityError as exc:
            if not _is_identity_conflict(exc):
                raise
            self._session.rollback()
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
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            raise


def _is_identity_conflict(exc: IntegrityError) -> bool:
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if constraint is not None:
        return bool(constraint == "uq_contact_organization_channel_identity")
    return (
        "UNIQUE constraint failed: contact.organization_id, contact.channel_type, "
        "contact.external_identifier_hash" in str(exc.orig)
    )
