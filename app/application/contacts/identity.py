import hmac
from hashlib import sha256
from uuid import UUID

from app.domain.contacts.contracts import (
    ContactIdentity,
    ContactIdentityError,
    ContactIdentityNormalizer,
)


class ContactIdentityHasher:
    def __init__(self, hmac_key: str, normalizer: ContactIdentityNormalizer) -> None:
        if not hmac_key.strip():
            raise ContactIdentityError("contact identity HMAC key is not configured")
        self._key = hmac_key.encode("utf-8")
        self._normalizer = normalizer

    def identify(
        self,
        organization_id: UUID,
        channel_type: str,
        external_identifier: str,
    ) -> ContactIdentity:
        normalized = self._normalizer.normalize(channel_type, external_identifier)
        payload = "|".join(
            (
                str(organization_id),
                normalized.channel_type,
                normalized.normalized_identifier,
            )
        )
        return ContactIdentity(
            organization_id=organization_id,
            channel_type=normalized.channel_type,
            external_identifier_hash=hmac.new(
                self._key, payload.encode("utf-8"), sha256
            ).hexdigest(),
            normalized_identifier=normalized.normalized_identifier,
        )
