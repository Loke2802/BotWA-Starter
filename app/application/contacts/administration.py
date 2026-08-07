from datetime import UTC, datetime
from uuid import UUID

from app.application.contacts.identity import ContactIdentityHasher
from app.application.contacts.repository import ContactRepository
from app.domain.contacts.api_contracts import ContactDetailResponse, ContactResponse
from app.domain.user.contracts import User
from app.infrastructure.models.contact import ContactModel
from app.security.authorization import AuthorizationError, require_scoped_permission
from app.security.secret_cipher import SecretCipher
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


class ContactAdministrationError(ValueError):
    pass


class ContactAdministrationForbiddenError(ContactAdministrationError):
    pass


class ContactAdministrationNotFoundError(ContactAdministrationError):
    pass


class ContactAdministrationService:
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

    def list(
        self,
        organization_id: UUID,
        actor: User,
        *,
        contact_status: str | None,
        channel_type: str | None,
        bot_id: UUID | None,
        identifier: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ContactResponse], int]:
        self._authorize(actor, "contacts.read", organization_id)
        identifier_hash = None
        if identifier is not None:
            self._authorize(actor, "contacts.read_sensitive", organization_id)
            if channel_type is None:
                raise ContactAdministrationError("channel type is required")
            identifier_hash = self._identity_hasher.identify(
                organization_id, channel_type, identifier
            ).external_identifier_hash
        models, total = self._repository.list_scoped(
            organization_id,
            status=contact_status or "active",
            channel_type=channel_type,
            bot_id=bot_id,
            external_identifier_hash=identifier_hash,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return [_response(model, self._cipher) for model in models], total

    def get(
        self, organization_id: UUID, contact_id: UUID, actor: User
    ) -> ContactDetailResponse:
        self._authorize(actor, "contacts.read", organization_id)
        contact = self._contact(contact_id, organization_id)
        sensitive = self._can_read_sensitive(actor, organization_id)
        return _detail(contact, self._cipher, sensitive)

    def update(
        self,
        organization_id: UUID,
        contact_id: UUID,
        actor: User,
        *,
        display_name: str | None,
        notes: str | None,
    ) -> ContactResponse:
        self._authorize(actor, "contacts.update", organization_id)
        contact = self._contact(contact_id, organization_id)
        if display_name is not None:
            contact.display_name_ciphertext = self._cipher.encrypt(display_name)
        if notes is not None:
            contact.notes_ciphertext = self._cipher.encrypt(notes)
        contact.updated_by_user_id = actor.id
        contact.updated_at = datetime.now(UTC)
        self._commit()
        return _response(contact, self._cipher)

    def set_status(
        self,
        organization_id: UUID,
        contact_id: UUID,
        actor: User,
        target: str,
    ) -> ContactResponse:
        self._authorize(actor, "contacts.archive", organization_id)
        contact = self._contact(contact_id, organization_id)
        if contact.status != target:
            contact.status = target
            contact.updated_by_user_id = actor.id
            contact.updated_at = datetime.now(UTC)
            self._commit()
        return _response(contact, self._cipher)

    def _contact(self, contact_id: UUID, organization_id: UUID) -> ContactModel:
        contact = self._repository.get_scoped(contact_id, organization_id)
        if contact is None:
            raise ContactAdministrationNotFoundError("contact not found")
        return contact

    def _authorize(self, actor: User, permission: str, organization_id: UUID) -> None:
        try:
            require_scoped_permission(actor, permission, organization_id)  # type: ignore[arg-type]
        except AuthorizationError as exc:
            raise ContactAdministrationForbiddenError("permission denied") from exc

    def _can_read_sensitive(self, actor: User, organization_id: UUID) -> bool:
        try:
            require_scoped_permission(actor, "contacts.read_sensitive", organization_id)
        except AuthorizationError:
            return False
        return True

    def _commit(self) -> None:
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise ContactAdministrationError("contact update conflict") from exc


def _response(contact: ContactModel, cipher: SecretCipher) -> ContactResponse:
    return ContactResponse(
        id=contact.id,
        organization_id=contact.organization_id,
        channel_type=contact.channel_type,
        display_name=(
            cipher.decrypt(contact.display_name_ciphertext)
            if contact.display_name_ciphertext is not None
            else None
        ),
        status=contact.status,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
    )


def _detail(
    contact: ContactModel, cipher: SecretCipher, sensitive: bool
) -> ContactDetailResponse:
    return ContactDetailResponse(
        **_response(contact, cipher).model_dump(),
        external_identifier=(
            cipher.decrypt(contact.external_identifier_ciphertext)
            if sensitive
            else None
        ),
        notes=(
            cipher.decrypt(contact.notes_ciphertext)
            if contact.notes_ciphertext and sensitive
            else None
        ),
    )
