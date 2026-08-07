from dataclasses import dataclass
from uuid import UUID


class ContactIdentityError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedContactIdentity:
    channel_type: str
    normalized_identifier: str


class ContactIdentityNormalizer:
    def normalize(
        self, channel_type: str, external_identifier: str
    ) -> NormalizedContactIdentity:
        if channel_type != "whatsapp":
            raise ContactIdentityError("unsupported contact channel")
        if not external_identifier.strip():
            raise ContactIdentityError("invalid WhatsApp contact identifier")
        allowed_formatting = {"+", "-", " ", "(", ")"}
        if any(
            character not in allowed_formatting and character not in "0123456789"
            for character in external_identifier
        ):
            raise ContactIdentityError("invalid WhatsApp contact identifier")
        normalized = "".join(
            character for character in external_identifier if character in "0123456789"
        )
        if not 8 <= len(normalized) <= 32:
            raise ContactIdentityError("invalid WhatsApp contact identifier")
        return NormalizedContactIdentity(
            channel_type=channel_type,
            normalized_identifier=normalized,
        )


@dataclass(frozen=True)
class ContactIdentity:
    organization_id: UUID
    channel_type: str
    external_identifier_hash: str
    normalized_identifier: str
