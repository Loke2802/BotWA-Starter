from pydantic import BaseModel, ConfigDict, Field


class Profile(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    name: str


class Contact(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile: Profile
    wa_id: str


class Metadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    display_phone_number: str
    phone_number_id: str


class TextMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    body: str


class Message(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    from_: str = Field(alias="from")
    id: str
    timestamp: str
    text: TextMessage | None = None
    type: str

    def get_text_body(self) -> str:
        if self.text is not None:
            return self.text.body
        return ""


class Value(BaseModel):
    model_config = ConfigDict(frozen=True)

    messaging_product: str
    metadata: Metadata
    contacts: list[Contact] = []
    messages: list[Message] = []


class Change(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: Value
    field: str


class Entry(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    changes: list[Change] = []


class WhatsAppWebhookPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    object: str
    entry: list[Entry] = []
