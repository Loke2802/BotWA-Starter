"""A merged customer who writes again lands on the principal (audit F-011)."""

# ruff: noqa: F811
from uuid import uuid4

from app.application.contacts.identity import ContactIdentityHasher
from app.application.contacts.service import ContactResolutionService
from app.application.conversation_management.service import (
    ConversationManagementService,
)
from app.application.crm.duplicates import DuplicateService
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.domain.crm.growth_contracts import MergeInput
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.contact_repository import (
    SqlAlchemyContactRepository,
)
from app.infrastructure.repositories.conversation_management_repository import (
    SqlAlchemyConversationManagementRepository,
    SqlAlchemyConversationMessageManagementRepository,
)
from sqlalchemy import text

from tests.crm_opportunity_support import opportunity_service
from tests.test_conversation_management import cipher, inbound
from tests.test_crm_opportunities import crm_opportunities  # noqa: F401


def test_inbound_after_merge_uses_principal_and_keeps_source_archived(
    crm_opportunities,
):  # type: ignore[no-untyped-def]
    _, session, actor, _, principal_id, _ = crm_opportunities
    org = actor.organization_id
    # Receipt and channel rows are outside this test; it covers contact identity.
    session.execute(text("PRAGMA foreign_keys=OFF"))
    crm = opportunity_service(session)
    contacts = ContactResolutionService(
        SqlAlchemyContactRepository(session),
        ContactIdentityHasher(crm.digest_key, ContactIdentityNormalizer()),
        crm.cipher,
        session,
    )
    bot_id = uuid4()
    session.add(
        BotModel(
            id=bot_id, organization_id=org, name="Bot", slug="bot-f011", status="active"
        )
    )
    session.commit()
    audit = SqlAlchemyAuditRepository(session)
    managed = ConversationManagementService(
        SqlAlchemyConversationManagementRepository(session),
        SqlAlchemyConversationMessageManagementRepository(session, audit),
        BotRepository(session),
        cipher(),
        session,
        audit,
    )

    phone = "51911111111"
    source = contacts.resolve(org, "whatsapp", phone)
    first = inbound(org, bot_id, sender=phone, message_id="wamid.before")
    conversation = managed.record_inbound(first, uuid4(), uuid4(), source.id)
    duplicates = DuplicateService(crm)
    review = duplicates.preview(org, actor, source.id, principal_id)
    duplicates.merge(
        org,
        actor,
        MergeInput(
            source_id=source.id, target_id=principal_id, review_token=review.token
        ),
    )
    session.expire_all()

    again = contacts.resolve(org, "whatsapp", phone)
    second = inbound(org, bot_id, sender=phone, message_id="wamid.after")
    recorded = managed.record_inbound(second, uuid4(), uuid4(), again.id)

    assert again.id == principal_id
    assert session.get(ContactModel, source.id).status == "archived"
    assert recorded.id == conversation.id
    assert session.get(ConversationModel, conversation.id).contact_id == principal_id
    assert recorded.message_count == 2
