import json
from os import environ
from uuid import UUID

from app.infrastructure.database import SessionLocal, engine
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.settings import get_settings
from sqlalchemy import func, select, text

s = get_settings()
expected_host = environ.get("LURI_OPS_DB_HOST", "")
recipient = environ.get("LURI_OPS_TEST_RECIPIENT", "")
public_webhook_id = environ.get("LURI_OPS_PUBLIC_WEBHOOK_ID", "")
org = UUID("3678150b-2f35-40ab-ad8d-cb45afdeb839")
bot = UUID("2a070ecb-fc5f-46b2-8c9b-77f793726bc4")
config = UUID("0c20eba4-2ee9-4ed8-9fc8-107d612d3ce4")
conv = UUID("998207cc-17b9-5872-907e-f53daafadd47")
owner = UUID("1d7b6b45-3847-44fb-b107-6e5a83bbd37a")
checks = {
    "private_staging_db": bool(expected_host)
    and engine.url.host == expected_host
    and engine.url.database == "defaultdb"
    and engine.url.query.get("sslmode") == "require",
    "expected_sha": s.build_sha == "6163751304a261e9a1faf1ad10554951626dcfbe",
    "transport_disabled": s.whatsapp_live_client_mode == "disabled",
    "recipient_allowlist_exact": s.whatsapp_outbound_allowed_recipients == (recipient,)
    and bool(recipient),
    "ai_off": not s.ai_enabled and not s.ai_pilot_scopes and not s.ai_openai_api_key,
    "bootstrap_off": not s.public_bootstrap_enabled,
}
with SessionLocal() as db:
    db.execute(text("SET TRANSACTION READ ONLY"))
    checks["schema_0026"] = (
        db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        == "20260921_0026"
    )
    b = db.get(BotModel, bot)
    c = db.get(WhatsAppChannelConfigurationModel, config)
    v = db.get(ConversationModel, conv)
    h = db.scalar(
        select(HandoffSessionModel).where(
            HandoffSessionModel.organization_id == org,
            HandoffSessionModel.conversation_id == conv,
        )
    )
    checks["bot_inactive_ai_off"] = (
        b is not None
        and b.organization_id == org
        and b.status == "inactive"
        and b.settings.get("generative_ai") == {"enabled": False}
    )
    checks["channel_exact_active"] = (
        c is not None
        and c.organization_id == org
        and c.bot_id == bot
        and c.phone_number_id == "1354348231086256"
        and c.whatsapp_business_account_id == "974780138964664"
        and c.status == "active"
        and c.webhook_enabled
        and str(c.public_webhook_id) == public_webhook_id
    )
    checks["only_one_receiving_channel"] = (
        db.scalar(
            select(func.count())
            .select_from(WhatsAppChannelConfigurationModel)
            .where(
                WhatsAppChannelConfigurationModel.status == "active",
                WhatsAppChannelConfigurationModel.webhook_enabled.is_(True),
            )
        )
        == 1
    )
    checks["conversation_exact"] = (
        v is not None
        and v.organization_id == org
        and v.bot_id == bot
        and v.channel_configuration_id == config
        and v.external_customer_id == recipient
        and v.inbound_message_count == 2
        and v.outbound_message_count == 1
    )
    checks["human_handoff_active"] = (
        h is not None
        and h.bot_id == bot
        and h.status == "human_active"
        and h.assigned_user_id == owner
    )
    import hashlib
    from collections import Counter

    from app.infrastructure.models.ai_generation import AIJobModel
    from app.infrastructure.models.message import MessageModel
    from app.infrastructure.models.whatsapp_message_transport import (
        InboundMessageReceiptModel,
        OutboundMessageAttemptModel,
    )

    rs = db.scalars(
        select(InboundMessageReceiptModel).where(
            InboundMessageReceiptModel.organization_id == org,
            InboundMessageReceiptModel.bot_id == bot,
            InboundMessageReceiptModel.channel_configuration_id == config,
        )
    ).all()
    os = db.scalars(
        select(OutboundMessageAttemptModel).where(
            OutboundMessageAttemptModel.organization_id == org,
            OutboundMessageAttemptModel.bot_id == bot,
            OutboundMessageAttemptModel.channel_configuration_id == config,
        )
    ).all()
    ms = db.scalars(
        select(MessageModel).where(
            MessageModel.organization_id == org,
            MessageModel.bot_id == bot,
            MessageModel.conversation_id == conv,
        )
    ).all()
    checks["two_processed_receipts"] = len(rs) == 2 and all(
        r.status == "processed" and r.last_error_code is None for r in rs
    )
    checks["one_read_outbound_once"] = (
        len(os) == 1
        and os[0].status == "read"
        and os[0].attempt_count == 1
        and os[0].provider_message_id is not None
        and os[0].last_error_code is None
        and os[0].external_recipient_hash
        == hashlib.sha256(recipient.encode()).hexdigest()
    )
    checks["three_encrypted_history_records"] = len(ms) == 3 and all(
        m.content == "" and m.text_ciphertext for m in ms
    )
    checks["human_author_recorded"] = (
        len([m for m in ms if m.direction == "outbound" and m.author_user_id == owner])
        == 1
    )
    checks["no_ai_jobs"] = (
        db.scalar(
            select(func.count())
            .select_from(AIJobModel)
            .where(AIJobModel.organization_id == org, AIJobModel.bot_id == bot)
        )
        == 0
    )
    print(
        json.dumps(
            {
                "status": (
                    "real_test_completed_transport_disabled"
                    if all(checks.values())
                    else "real_test_final_checks_incomplete"
                ),
                "checks": checks,
                "inbound_count": len(rs),
                "outbound_count": len(os),
                "outbound_states": dict(Counter(o.status for o in os)),
                "outbound_attempt_ids": [str(o.id) for o in os],
                "outbound_attempt_counts": [o.attempt_count for o in os],
                "ai_enabled": False,
                "transport": s.whatsapp_live_client_mode,
            }
        )
    )
