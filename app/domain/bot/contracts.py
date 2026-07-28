import re
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

BotStatus = Literal["active", "inactive"]

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_LANGUAGE_PATTERN = re.compile(r"^[a-z]{2}(?:-[A-Z]{2})?$")


def normalize_slug(value: str) -> str:
    return re.sub(r"[\s_]+", "-", value.strip().lower()).strip("-")


def validate_slug(value: str) -> str:
    slug = normalize_slug(value)
    if not slug or _SLUG_PATTERN.fullmatch(slug) is None:
        raise ValueError("slug must be URL-safe")
    return slug


def validate_language(value: str) -> str:
    language = value.strip()
    if _LANGUAGE_PATTERN.fullmatch(language) is None:
        raise ValueError("default_language must be a simple locale")
    return language


def validate_timezone(value: str) -> str:
    timezone = value.strip()
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be a valid IANA name") from exc
    return timezone


class Bot(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    name: str = Field(min_length=1)
    slug: str
    description: str | None = None
    status: BotStatus = "inactive"
    default_language: str = "es"
    timezone: str = "America/Lima"
    welcome_message: str | None = None
    away_message: str | None = None
    settings: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    activated_at: datetime | None = None
    deactivated_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("name cannot be empty")
        return name

    @field_validator("slug")
    @classmethod
    def normalize_and_validate_slug(cls, value: str) -> str:
        return validate_slug(value)

    @field_validator("default_language")
    @classmethod
    def validate_default_language(cls, value: str) -> str:
        return validate_language(value)

    @field_validator("timezone")
    @classmethod
    def validate_bot_timezone(cls, value: str) -> str:
        return validate_timezone(value)


class BotCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    organization_id: UUID | None = None
    name: str = Field(min_length=1)
    slug: str
    description: str | None = None
    default_language: str = "es"
    timezone: str = "America/Lima"
    welcome_message: str | None = None
    away_message: str | None = None
    settings: dict[str, object] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("name cannot be empty")
        return name

    @field_validator("slug")
    @classmethod
    def normalize_and_validate_slug(cls, value: str) -> str:
        return validate_slug(value)

    @field_validator("default_language")
    @classmethod
    def validate_default_language(cls, value: str) -> str:
        return validate_language(value)

    @field_validator("timezone")
    @classmethod
    def validate_bot_timezone(cls, value: str) -> str:
        return validate_timezone(value)


class BotUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    organization_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1)
    slug: str | None = None
    description: str | None = None
    default_language: str | None = None
    timezone: str | None = None
    welcome_message: str | None = None
    away_message: str | None = None
    settings: dict[str, object] | None = None

    @field_validator("name")
    @classmethod
    def validate_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not name:
            raise ValueError("name cannot be empty")
        return name

    @field_validator("slug")
    @classmethod
    def normalize_optional_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_slug(value)

    @field_validator("default_language")
    @classmethod
    def validate_optional_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_language(value)

    @field_validator("timezone")
    @classmethod
    def validate_optional_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_timezone(value)


class BotResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    bot: Bot


class BotListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    bots: list[Bot]
    total: int
