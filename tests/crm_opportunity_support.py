import base64
from uuid import UUID, uuid4

from app.application.contacts.crm import CrmService
from app.application.contacts.identity import ContactIdentityHasher
from app.application.crm.service import OpportunityService
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.domain.contacts.crm_contracts import CustomerCreate
from app.domain.user.contracts import User
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.security.secret_cipher import EnvironmentSecretCipher
from sqlalchemy.orm import Session


def opportunity_service(session: Session) -> OpportunityService:
    return OpportunityService(
        session,
        EnvironmentSecretCipher(base64.urlsafe_b64encode(b"o" * 32).decode()),
        "opportunity-test-key-at-least-thirty-two-characters",
    )


def seed(session: Session) -> tuple[User, User, UUID, UUID]:
    actors = [
        User(
            id=uuid4(),
            organization_id=uuid4(),
            email=f"{uuid4()}@example.test",
            role="organization_admin",
        )
        for _ in range(2)
    ]
    for actor in actors:
        session.add(
            OrganizationModel(
                id=actor.organization_id,
                name="Synthetic CRM",
                slug=f"test-{actor.organization_id}",
                status="active",
                settings={"timezone": "America/Lima"},
            )
        )
        session.flush()
        session.add(
            UserModel(
                id=actor.id,
                organization_id=actor.organization_id,
                email=actor.email,
                password_hash="test-only",
                role=actor.role,
                status="active",
            )
        )
    session.commit()
    actor, other = actors
    service = opportunity_service(session)
    crm = CrmService(
        session,
        service.cipher,
        ContactIdentityHasher(service.digest_key, ContactIdentityNormalizer()),
    )
    contact = crm.create(
        actor.organization_id,
        actor,
        CustomerCreate(display_name="Synthetic client", whatsapp="+12025550147"),
    )
    bot = BotModel(
        id=uuid4(),
        organization_id=actor.organization_id,
        name="Synthetic",
        slug="test",
        status="active",
    )
    session.add(bot)
    session.flush()
    conversation = ConversationModel(
        id=uuid4(),
        organization_id=actor.organization_id,
        bot_id=bot.id,
        contact_id=contact.id,
        company_id=str(actor.organization_id),
        customer_id="synthetic",
        channel="whatsapp",
        management_status="open",
        masked_customer_identifier="***0147",
    )
    session.add(conversation)
    session.commit()
    return actor, other, contact.id, conversation.id


def payload(
    actor: User, contact_id: UUID, conversation_id: UUID | None
) -> dict[str, object]:
    return {
        "contact_id": str(contact_id),
        "conversation_id": str(conversation_id) if conversation_id else None,
        "title": "Synthetic proposal",
        "need": "Private commercial need",
        "stage_code": "new",
        "assigned_user_id": str(actor.id),
        "next_action": {
            "description": "Call about proposal",
            "due_at": "2026-10-08T10:00:00-05:00",
        },
    }
