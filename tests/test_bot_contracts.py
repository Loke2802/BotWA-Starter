from uuid import uuid4

import pytest
from app.domain.bot.contracts import BotCreate, BotUpdate
from pydantic import ValidationError


def test_bot_create_normalizes_slug() -> None:
    request = BotCreate(
        organization_id=uuid4(),
        name="Support Bot",
        slug="Support Bot",
    )

    assert request.slug == "support-bot"


def test_bot_create_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        BotCreate(
            organization_id=uuid4(),
            name="   ",
            slug="support",
        )


def test_bot_create_rejects_invalid_slug() -> None:
    with pytest.raises(ValidationError):
        BotCreate(
            organization_id=uuid4(),
            name="Support",
            slug="Invalid!",
        )


def test_bot_create_rejects_invalid_language_and_timezone() -> None:
    with pytest.raises(ValidationError):
        BotCreate(
            organization_id=uuid4(),
            name="Support",
            slug="support",
            default_language="spanish",
        )

    with pytest.raises(ValidationError):
        BotCreate(
            organization_id=uuid4(),
            name="Support",
            slug="support",
            timezone="Mars/Olympus",
        )


def test_bot_update_rejects_internal_fields() -> None:
    with pytest.raises(ValidationError):
        BotUpdate(id=uuid4())  # type: ignore[call-arg]
