from unittest.mock import Mock
from uuid import uuid4

import pytest
from app.application.whatsapp_configuration.service import (
    WhatsAppConfigurationConflictError,
    WhatsAppConfigurationService,
)
from app.domain.user.contracts import User
from app.domain.whatsapp_configuration.contracts import (
    WhatsAppChannelConfigurationCreate,
)
from app.security.secret_cipher import SecretCipher
from sqlalchemy.exc import IntegrityError

from tests.plan_support import allow_all_plan_enforcement


def test_integrity_error_rolls_back_without_leaking_database_details() -> None:
    repository = Mock()
    bot_repository = Mock()
    organization_repository = Mock()
    cipher = Mock(spec=SecretCipher)
    session = Mock()
    organization_id = uuid4()
    bot_id = uuid4()
    actor = User(
        organization_id=organization_id,
        email="owner@example.com",
        role="organization_owner",
    )
    bot_repository.get.return_value = Mock(organization_id=organization_id)
    organization_repository.get.return_value = Mock(status="active")
    session.commit.side_effect = IntegrityError(
        "insert",
        {},
        Exception("sensitive postgres detail"),
    )
    service = WhatsAppConfigurationService(
        repository,
        bot_repository,
        organization_repository,
        cipher,
        session,
        allow_all_plan_enforcement(),
        Mock(),
    )

    with pytest.raises(
        WhatsAppConfigurationConflictError,
        match="WhatsApp configuration conflict",
    ) as exc_info:
        service.create(
            organization_id,
            bot_id,
            WhatsAppChannelConfigurationCreate(
                display_name="Support",
                phone_number_id="phone-1",
                whatsapp_business_account_id="waba-1",
            ),
            actor,
        )

    assert "sensitive postgres detail" not in str(exc_info.value)
    session.rollback.assert_called_once()
