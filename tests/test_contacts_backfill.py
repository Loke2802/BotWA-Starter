import base64
from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from app.application.contacts.backfill import ContactBackfillService
from app.application.contacts.identity import ContactIdentityHasher
from app.application.contacts.service import ContactResolutionService
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.infrastructure.database import Base
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.repositories.contact_repository import (
    SqlAlchemyContactRepository,
)
from app.security.secret_cipher import EnvironmentSecretCipher
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()


def _service(session: Session) -> ContactBackfillService:
    cipher = EnvironmentSecretCipher(base64.urlsafe_b64encode(b"b" * 32).decode())
    hasher = ContactIdentityHasher(
        "backfill-hmac-key-long-enough-for-tests", ContactIdentityNormalizer()
    )
    return ContactBackfillService(
        session,
        ContactResolutionService(
            SqlAlchemyContactRepository(session), hasher, cipher, session
        ),
        hasher,
    )


def _conversation(
    organization_id: UUID, sender: str | None, *, channel: str = "whatsapp"
) -> ConversationModel:
    return ConversationModel(
        id=uuid4(),
        company_id=str(organization_id),
        customer_id=sender or "",
        organization_id=organization_id,
        bot_id=uuid4(),
        external_customer_id=sender,
        channel=channel,
        status="new",
        management_status="open",
    )


def test_backfill_links_reuses_and_is_idempotent(session: Session) -> None:
    organization_id = uuid4()
    session.add(
        OrganizationModel(
            id=organization_id, name="Org", slug="backfill-org", status="active"
        )
    )
    first, second = _conversation(organization_id, "51999999999"), _conversation(
        organization_id, "51999999999"
    )
    session.add_all((first, second))
    session.commit()
    service = _service(session)

    result = service.run(batch_size=1, organization_id=None, dry_run=False)
    repeated = service.run(batch_size=10, organization_id=None, dry_run=False)

    assert result.linked == 2
    assert result.contacts_created == 1
    assert result.contacts_reused == 1
    assert repeated.already_linked == 2
    assert len(list(session.scalars(select(ContactModel)).all())) == 1
    assert first.contact_id == second.contact_id


def test_backfill_dry_run_filters_and_skips_invalid_rows(session: Session) -> None:
    organization_id, other_organization_id = uuid4(), uuid4()
    session.add_all(
        (
            OrganizationModel(
                id=organization_id, name="Org", slug="backfill-filter", status="active"
            ),
            OrganizationModel(
                id=other_organization_id,
                name="Other",
                slug="backfill-other",
                status="active",
            ),
        )
    )
    valid = _conversation(organization_id, "51999999999")
    invalid = _conversation(organization_id, "bad-value")
    missing = _conversation(organization_id, None)
    other = _conversation(other_organization_id, "51888888888")
    session.add_all((valid, invalid, missing, other))
    session.commit()

    dry = _service(session).run(
        batch_size=2, organization_id=organization_id, dry_run=True
    )

    assert dry.scanned == 3
    assert dry.eligible == 1
    assert dry.contacts_created == 1
    assert dry.skipped_invalid_identity == 1
    assert dry.skipped_missing_context == 1
    assert valid.contact_id is None
    assert session.scalars(select(ContactModel)).first() is None


def test_backfill_preserves_existing_link_and_lifecycle(session: Session) -> None:
    organization_id = uuid4()
    session.add(
        OrganizationModel(
            id=organization_id, name="Org", slug="backfill-linked", status="active"
        )
    )
    contact = ContactModel(
        organization_id=organization_id,
        channel_type="whatsapp",
        external_identifier_hash="a" * 64,
        external_identifier_ciphertext="ciphertext",
    )
    session.add(contact)
    session.flush()
    conversation = _conversation(organization_id, "51999999999")
    conversation.contact_id = contact.id
    conversation.management_status = "archived"
    conversation.message_count = 7
    session.add_all((contact, conversation))
    session.commit()

    result = _service(session).run(batch_size=10, organization_id=None, dry_run=False)

    assert result.already_linked == 1
    assert conversation.contact_id == contact.id
    assert conversation.management_status == "archived"
    assert conversation.message_count == 7
