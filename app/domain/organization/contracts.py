import re
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

OrganizationStatus = Literal["active", "inactive"]

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_slug(value: str) -> str:
    return re.sub(r"[\s_]+", "-", value.strip().lower()).strip("-")


def validate_slug(value: str) -> str:
    slug = normalize_slug(value)
    if not slug or _SLUG_PATTERN.fullmatch(slug) is None:
        raise ValueError("slug must be URL-safe")
    return slug


class OrganizationSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    locale: str = "es"
    timezone: str = "America/Lima"


class Organization(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    slug: str
    status: OrganizationStatus = "active"
    settings: OrganizationSettings = Field(default_factory=OrganizationSettings)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
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


class OrganizationCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    slug: str
    settings: OrganizationSettings = Field(default_factory=OrganizationSettings)

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


class OrganizationUpdate(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None = Field(default=None, min_length=1)
    slug: str | None = None
    settings: OrganizationSettings | None = None

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


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    organization: Organization


class OrganizationListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    organizations: list[Organization]
    total: int
