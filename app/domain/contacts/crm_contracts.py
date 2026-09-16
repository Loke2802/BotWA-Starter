from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Classification = Literal["lead", "customer", "inactive"]
ServiceInterest = Literal["undecided", "luri", "site", "marketing", "other"]


class CustomerEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    display_name: str = Field(min_length=2, max_length=200)
    classification: Classification = "lead"
    service_interest: ServiceInterest = "undecided"
    assigned_user_id: UUID | None = None
    next_follow_up_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("next_follow_up_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timezone required")
        return value


class CustomerCreate(CustomerEdit):
    whatsapp: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")


class CustomerUpdate(CustomerEdit):
    version: int = Field(ge=0)


class CustomerItem(BaseModel):
    id: UUID
    display_name: str | None
    channel_type: str
    status: str
    classification: str
    service_interest: str
    assigned_user_id: UUID | None
    next_follow_up_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class CustomerDetail(CustomerItem):
    external_identifier: str | None
    notes: str | None
    can_edit: bool
    can_read_sensitive: bool


class CustomerList(BaseModel):
    items: list[CustomerItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class CrmAssignee(BaseModel):
    id: UUID
    name: str


class CrmSummary(BaseModel):
    leads: int
    customers: int
    inactive: int
    follow_ups_due: int
    can_edit: bool
    can_create: bool
    can_archive: bool
