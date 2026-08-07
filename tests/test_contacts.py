import base64
from collections.abc import Generator
from uuid import uuid4

import pytest
from app.application.contacts.identity import ContactIdentityHasher
from app.domain.contacts.contracts import (
    ContactIdentityError,
    ContactIdentityNormalizer,
)
from app.infrastructure.database import Base
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.repositories.contact_repository import (
    SqlAlchemyContactRepository,
)
from app.security.secret_cipher import EnvironmentSecretCipher
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()


def test_whatsapp_identity_is_normalized_and_tenant_scoped() -> None:
    normalizer = ContactIdentityNormalizer()
    hasher = ContactIdentityHasher("contact-hmac-key", normalizer)
    first_organization, second_organization = uuid4(), uuid4()

    first = hasher.identify(first_organization, "whatsapp", "+51 999-999-999")
    repeated = hasher.identify(first_organization, "whatsapp", "51999999999")
    other_tenant = hasher.identify(second_organization, "whatsapp", "51999999999")

    assert first.normalized_identifier == "51999999999"
    assert first.external_identifier_hash == repeated.external_identifier_hash
    assert first.external_identifier_hash != other_tenant.external_identifier_hash


def test_identity_rejects_unsupported_or_invalid_values() -> None:
    normalizer = ContactIdentityNormalizer()

    with pytest.raises(ContactIdentityError):
        normalizer.normalize("telegram", "51999999999")
    with pytest.raises(ContactIdentityError):
        normalizer.normalize("whatsapp", "invalid")
    with pytest.raises(ContactIdentityError):
        ContactIdentityHasher("", normalizer)


def test_repository_enforces_scoped_identity_uniqueness(session: Session) -> None:
    organization_id = uuid4()
    session.add(
        OrganizationModel(id=organization_id, name="Org", slug="org", status="active")
    )
    session.commit()
    cipher = EnvironmentSecretCipher(base64.urlsafe_b64encode(b"c" * 32).decode())
    identity = ContactIdentityHasher(
        "contact-hmac-key", ContactIdentityNormalizer()
    ).identify(organization_id, "whatsapp", "51999999999")
    repository = SqlAlchemyContactRepository(session)
    contact = repository.add(
        ContactModel(
            organization_id=organization_id,
            channel_type=identity.channel_type,
            external_identifier_hash=identity.external_identifier_hash,
            external_identifier_ciphertext=cipher.encrypt(
                identity.normalized_identifier
            ),
        )
    )
    session.commit()

    assert (
        repository.get_by_identity(
            organization_id, "whatsapp", identity.external_identifier_hash
        )
        == contact
    )
    assert repository.get_scoped(contact.id, organization_id) == contact

    session.add(
        ContactModel(
            organization_id=organization_id,
            channel_type=identity.channel_type,
            external_identifier_hash=identity.external_identifier_hash,
            external_identifier_ciphertext=cipher.encrypt(
                identity.normalized_identifier
            ),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_contact_migration_declares_reversible_schema() -> None:
    with open(
        "alembic/versions/20260805_0013_create_contact_table.py", encoding="utf-8"
    ) as migration:
        source = migration.read()

    assert 'revision = "20260805_0013"' in source
    assert 'down_revision = "20260730_0012"' in source
    assert '"contact"' in source
    assert '"contact_id"' in source
    assert "def downgrade()" in source
