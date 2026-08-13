import re
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.access.contracts import Role

UserStatus = Literal["active", "inactive"]

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    return value.strip().lower()


def validate_email(value: str) -> str:
    email = normalize_email(value)
    if not email or _EMAIL_PATTERN.fullmatch(email) is None:
        raise ValueError("email must be valid")
    return email


class User(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    email: str
    first_name: str | None = None
    last_name: str | None = None
    role: Role = "viewer"
    status: UserStatus = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_login_at: datetime | None = None
    deactivated_at: datetime | None = None

    @field_validator("email")
    @classmethod
    def normalize_and_validate_email(cls, value: str) -> str:
        return validate_email(value)


class UserCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    organization_id: UUID
    email: str
    password: str
    first_name: str | None = None
    last_name: str | None = None
    role: Role | None = None

    @field_validator("email")
    @classmethod
    def normalize_and_validate_email(cls, value: str) -> str:
        return validate_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 12:
            raise ValueError("password must be at least 12 characters")
        if len(value) > 256:
            raise ValueError("password must be at most 256 characters")
        return value


class UserUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    first_name: str | None = None
    last_name: str | None = None
    organization_id: UUID | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    user: User


class UserListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    users: list[User]
    total: int


class LoginRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_and_validate_email(cls, value: str) -> str:
        return validate_email(value)

    @field_validator("password")
    @classmethod
    def validate_password_bound(cls, value: str) -> str:
        if len(value) > 256:
            raise ValueError("password must be at most 256 characters")
        return value


class TokenResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if len(value) < 12:
            raise ValueError("password must be at least 12 characters")
        if len(value) > 256:
            raise ValueError("password must be at most 256 characters")
        return value

    @field_validator("current_password")
    @classmethod
    def validate_current_password_bound(cls, value: str) -> str:
        if len(value) > 256:
            raise ValueError("password must be at most 256 characters")
        return value


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    user: User
