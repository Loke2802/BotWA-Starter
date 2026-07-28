from uuid import uuid4

import pytest
from app.domain.user.contracts import (
    ChangePasswordRequest,
    LoginRequest,
    User,
    UserCreate,
)
from pydantic import ValidationError


def test_user_email_is_normalized() -> None:
    user = User(
        organization_id=uuid4(),
        email=" Owner@Example.COM ",
    )

    assert user.email == "owner@example.com"


def test_user_create_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        UserCreate(
            organization_id=uuid4(),
            email="not-an-email",
            password="valid-password-123",
        )


def test_user_create_rejects_weak_password() -> None:
    with pytest.raises(ValidationError):
        UserCreate(
            organization_id=uuid4(),
            email="owner@example.com",
            password="short",
        )


def test_login_request_normalizes_email() -> None:
    request = LoginRequest(email=" Owner@Example.COM ", password="password")

    assert request.email == "owner@example.com"


def test_change_password_rejects_weak_new_password() -> None:
    with pytest.raises(ValidationError):
        ChangePasswordRequest(
            current_password="valid-password-123",
            new_password="short",
        )
