"""Preserve legacy registration evidence before any operator changes notes."""

import json

from app.infrastructure.models.contact import ContactModel
from app.security.secret_cipher import SecretCipher


def preserve_registration(contact: ContactModel, cipher: SecretCipher) -> None:
    if contact.registration_ciphertext or not contact.notes_ciphertext:
        return
    plaintext = cipher.decrypt(contact.notes_ciphertext)
    try:
        data = json.loads(plaintext)
    except (ValueError, TypeError):
        return
    if (
        isinstance(data, dict)
        and data.get("source") == "website"
        and isinstance(data.get("consent"), dict)
        and data["consent"].get("notice_version") == "contact-registration-v1"
    ):
        contact.registration_ciphertext = contact.notes_ciphertext
