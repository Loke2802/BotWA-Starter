import re
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ConfigurationStatus = Literal["configured"]

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_URL_PATTERN = re.compile(r"^https?://[^\s/$.?#].[^\s]*$")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def validate_timezone(value: str) -> str:
    timezone = value.strip()
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be a valid IANA name") from exc
    return timezone


def validate_email(value: str) -> str:
    email = value.strip().lower()
    if _EMAIL_PATTERN.fullmatch(email) is None:
        raise ValueError("email must be valid")
    return email


def validate_website(value: str) -> str:
    website = value.strip()
    if _URL_PATTERN.fullmatch(website) is None:
        raise ValueError("website must be a valid http(s) URL")
    return website


def validate_time(value: str) -> str:
    time_value = value.strip()
    if _TIME_PATTERN.fullmatch(time_value) is None:
        raise ValueError("time must use HH:MM format")
    return time_value


def _clean_non_empty(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty")
    return cleaned


class BusinessDayHours(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool
    open_time: str | None = None
    close_time: str | None = None

    @field_validator("open_time", "close_time")
    @classmethod
    def validate_optional_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_time(value)

    @model_validator(mode="after")
    def validate_interval(self) -> "BusinessDayHours":
        if not self.enabled:
            return self
        if self.open_time is None or self.close_time is None:
            raise ValueError("enabled days require open_time and close_time")
        if self.open_time >= self.close_time:
            raise ValueError("open_time must be before close_time")
        return self


class BusinessHours(BaseModel):
    model_config = ConfigDict(frozen=True)

    monday: BusinessDayHours
    tuesday: BusinessDayHours
    wednesday: BusinessDayHours
    thursday: BusinessDayHours
    friday: BusinessDayHours
    saturday: BusinessDayHours
    sunday: BusinessDayHours


class BusinessService(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    active: bool = True
    price: float | None = Field(default=None, ge=0)
    currency: str | None = None
    duration_minutes: int | None = Field(default=None, gt=0, le=1440)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _clean_non_empty(value, "service name")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        currency = value.strip().upper()
        if _CURRENCY_PATTERN.fullmatch(currency) is None:
            raise ValueError("currency must be an ISO 4217 code")
        return currency


class BusinessPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    active: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _clean_non_empty(value, "policy name")

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        return _clean_non_empty(value, "policy description")


class BusinessConfigurationBase(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = None
    website: str | None = None
    address: str | None = Field(default=None, max_length=500)
    timezone: str = "America/Lima"
    business_hours: BusinessHours
    services: list[BusinessService] = Field(min_length=1, max_length=50)
    payment_methods: list[str] = Field(min_length=1, max_length=30)
    policies: list[BusinessPolicy] = Field(default_factory=list, max_length=50)
    service_instructions: str = Field(min_length=1, max_length=4000)
    handoff_enabled: bool = False
    handoff_message: str | None = Field(default=None, max_length=1000)
    handoff_keywords: list[str] = Field(default_factory=list, max_length=30)
    handoff_outside_business_hours: bool = False

    @field_validator("business_name")
    @classmethod
    def validate_business_name(cls, value: str) -> str:
        return _clean_non_empty(value, "business_name")

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        return _clean_non_empty(value, "description")

    @field_validator("email")
    @classmethod
    def validate_optional_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_email(value)

    @field_validator("website")
    @classmethod
    def validate_optional_website(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_website(value)

    @field_validator("timezone")
    @classmethod
    def validate_business_timezone(cls, value: str) -> str:
        return validate_timezone(value)

    @field_validator("payment_methods")
    @classmethod
    def validate_payment_methods(cls, value: list[str]) -> list[str]:
        cleaned = [_clean_non_empty(item, "payment method") for item in value]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("payment_methods cannot contain duplicates")
        return cleaned

    @field_validator("service_instructions")
    @classmethod
    def validate_service_instructions(cls, value: str) -> str:
        return _clean_non_empty(value, "service_instructions")

    @field_validator("handoff_keywords")
    @classmethod
    def validate_handoff_keywords(cls, value: list[str]) -> list[str]:
        cleaned = [_clean_non_empty(item, "handoff keyword") for item in value]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("handoff_keywords cannot contain duplicates")
        return cleaned


class BusinessConfiguration(BusinessConfigurationBase):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    bot_id: UUID
    status: ConfigurationStatus = "configured"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BusinessConfigurationCreate(BusinessConfigurationBase):
    model_config = ConfigDict(frozen=True)


class BusinessConfigurationUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    bot_id: UUID | None = None
    business_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=1000)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = None
    website: str | None = None
    address: str | None = Field(default=None, max_length=500)
    timezone: str | None = None
    business_hours: BusinessHours | None = None
    services: list[BusinessService] | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    payment_methods: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=30,
    )
    policies: list[BusinessPolicy] | None = Field(default=None, max_length=50)
    service_instructions: str | None = Field(
        default=None,
        min_length=1,
        max_length=4000,
    )
    handoff_enabled: bool | None = None
    handoff_message: str | None = Field(default=None, max_length=1000)
    handoff_keywords: list[str] | None = Field(default=None, max_length=30)
    handoff_outside_business_hours: bool | None = None

    @field_validator("business_name")
    @classmethod
    def validate_optional_business_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_non_empty(value, "business_name")

    @field_validator("description")
    @classmethod
    def validate_optional_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_non_empty(value, "description")

    @field_validator("email")
    @classmethod
    def validate_optional_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_email(value)

    @field_validator("website")
    @classmethod
    def validate_optional_website(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_website(value)

    @field_validator("timezone")
    @classmethod
    def validate_optional_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_timezone(value)

    @field_validator("payment_methods")
    @classmethod
    def validate_optional_payment_methods(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
        if value is None:
            return None
        return BusinessConfigurationBase.validate_payment_methods(value)

    @field_validator("service_instructions")
    @classmethod
    def validate_optional_service_instructions(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        return _clean_non_empty(value, "service_instructions")

    @field_validator("handoff_keywords")
    @classmethod
    def validate_optional_handoff_keywords(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
        if value is None:
            return None
        return BusinessConfigurationBase.validate_handoff_keywords(value)


class BusinessConfigurationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    business_configuration: BusinessConfiguration
