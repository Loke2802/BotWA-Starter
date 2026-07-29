from uuid import uuid4

import pytest
from app.domain.business_configuration.contracts import (
    BusinessConfigurationCreate,
    BusinessConfigurationUpdate,
)
from pydantic import ValidationError


def valid_hours() -> dict[str, dict[str, object]]:
    open_day: dict[str, object] = {
        "enabled": True,
        "open_time": "09:00",
        "close_time": "18:00",
    }
    closed_day: dict[str, object] = {"enabled": False}
    return {
        "monday": open_day,
        "tuesday": open_day,
        "wednesday": open_day,
        "thursday": open_day,
        "friday": open_day,
        "saturday": closed_day,
        "sunday": closed_day,
    }


def valid_payload() -> dict[str, object]:
    return {
        "business_name": "Acme Support",
        "description": "Customer support for Acme.",
        "phone": "+51999999999",
        "email": "INFO@EXAMPLE.COM",
        "website": "https://example.com",
        "timezone": "America/Lima",
        "business_hours": valid_hours(),
        "services": [
            {
                "name": "Support",
                "description": "General support",
                "active": True,
                "price": 10,
                "currency": "usd",
                "duration_minutes": 30,
            }
        ],
        "payment_methods": ["cash", "card"],
        "policies": [{"name": "Refunds", "description": "Case by case"}],
        "service_instructions": "Answer politely.",
        "handoff_enabled": True,
        "handoff_message": "A human will help you.",
        "handoff_keywords": ["human", "agent"],
        "handoff_outside_business_hours": True,
    }


def test_business_configuration_create_normalizes_safe_fields() -> None:
    request = BusinessConfigurationCreate(**valid_payload())

    assert request.email == "info@example.com"
    assert request.services[0].currency == "USD"
    assert request.business_hours.monday.open_time == "09:00"


def test_invalid_timezone_email_website_and_hours_are_rejected() -> None:
    for field, value in (
        ("timezone", "Mars/Base"),
        ("email", "invalid"),
        ("website", "ftp://example.com"),
    ):
        payload = valid_payload()
        payload[field] = value
        with pytest.raises(ValidationError):
            BusinessConfigurationCreate(**payload)

    payload = valid_payload()
    hours = valid_hours()
    hours["monday"] = {"enabled": True, "open_time": "18:00", "close_time": "09:00"}
    payload["business_hours"] = hours

    with pytest.raises(ValidationError):
        BusinessConfigurationCreate(**payload)


def test_invalid_service_policy_and_payment_methods_are_rejected() -> None:
    payload = valid_payload()
    payload["services"] = [{"name": "", "active": True}]
    with pytest.raises(ValidationError):
        BusinessConfigurationCreate(**payload)

    payload = valid_payload()
    payload["policies"] = [{"name": "Refunds", "description": ""}]
    with pytest.raises(ValidationError):
        BusinessConfigurationCreate(**payload)

    payload = valid_payload()
    payload["payment_methods"] = ["cash", "cash"]
    with pytest.raises(ValidationError):
        BusinessConfigurationCreate(**payload)


def test_update_rejects_unknown_fields_but_accepts_bot_id_for_service_denial() -> None:
    request = BusinessConfigurationUpdate(bot_id=uuid4())

    assert request.bot_id is not None

    with pytest.raises(ValidationError):
        BusinessConfigurationUpdate(unknown=True)  # type: ignore[call-arg]
