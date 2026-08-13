from collections.abc import Generator

from app.api.whatsapp_configuration_dependencies import get_whatsapp_secret_cipher
from app.application.contacts.administration import ContactAdministrationService
from app.application.contacts.identity import ContactIdentityHasher
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.infrastructure.database import get_session
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.contact_repository import (
    SqlAlchemyContactRepository,
)
from app.infrastructure.settings import get_settings


def get_contact_administration_service() -> Generator[ContactAdministrationService]:
    session_generator = get_session()
    session = next(session_generator)
    try:
        yield ContactAdministrationService(
            SqlAlchemyContactRepository(session),
            ContactIdentityHasher(
                get_settings().contact_identity_hmac_key,
                ContactIdentityNormalizer(),
            ),
            get_whatsapp_secret_cipher(),
            session,
            SqlAlchemyAuditRepository(session),
        )
    finally:
        session_generator.close()
