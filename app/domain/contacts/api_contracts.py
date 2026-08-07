from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContactResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    organization_id: UUID
    channel_type: str
    display_name: str | None = None
    status: Literal["active", "archived"]
    created_at: datetime
    updated_at: datetime


class ContactDetailResponse(ContactResponse):
    external_identifier: str | None = None
    notes: str | None = None


class ContactListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ContactResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_previous: bool


class ContactUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def has_update(self) -> "ContactUpdateRequest":
        if self.display_name is None and self.notes is None:
            raise ValueError("at least one editable field is required")
        return self
