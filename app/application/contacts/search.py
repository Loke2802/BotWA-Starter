"""Transient normalization of encrypted contacts; no plaintext search index."""

import json
import re
import unicodedata
from contextlib import suppress
from typing import Literal

from app.infrastructure.models.contact import ContactModel
from app.security.secret_cipher import SecretCipher

SearchField = Literal["name", "phone", "email"]


def normalized_name(value: str) -> str:
    folded = "".join(
        c
        for c in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(c)
    )
    return " ".join(re.findall(r"\w+", folded))


def phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if not 8 <= len(digits) <= 15 or any(c.isalpha() for c in value):
        raise ValueError("Use a complete international phone number")
    return digits


def email(value: str) -> str:
    value = value.strip().casefold()
    if "@" not in value or any(c.isspace() for c in value):
        raise ValueError("Use a complete email address")
    return value


def identities(contact: ContactModel, cipher: SecretCipher) -> list[tuple[str, str]]:
    result = []
    identifier = cipher.decrypt(contact.external_identifier_ciphertext)
    if contact.channel_type in {"whatsapp", "phone", "sms"}:
        # Historical non-phone identities must not block a tenant scan.
        with suppress(ValueError):
            result.append(("teléfono", phone(identifier)))
    if contact.channel_type == "email":
        with suppress(ValueError):
            result.append(("correo", email(identifier)))
    if contact.registration_ciphertext:
        registration = json.loads(cipher.decrypt(contact.registration_ciphertext))
        if isinstance(registration, dict):
            for key in ("email", "correo"):
                value = registration.get(key)
                if isinstance(value, str):
                    with suppress(ValueError):
                        result.append(("correo", email(value)))
    return list(dict.fromkeys(result))


class ContactSearch:
    def __init__(self, term: str, field: SearchField, cipher: SecretCipher) -> None:
        self.field, self.cipher = field, cipher
        if field == "name":
            self.term = normalized_name(term)
            if len(self.term) < 2:
                raise ValueError("Use at least two name characters")
        else:
            self.term = phone(term) if field == "phone" else email(term)

    def matches(self, contact: ContactModel) -> bool:
        if self.field == "name":
            name = (
                normalized_name(self.cipher.decrypt(contact.display_name_ciphertext))
                if contact.display_name_ciphertext
                else ""
            )
            return all(word in name for word in self.term.split())
        kind = "teléfono" if self.field == "phone" else "correo"
        return (kind, self.term) in identities(contact, self.cipher)
