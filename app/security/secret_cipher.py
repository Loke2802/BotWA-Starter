from abc import ABC, abstractmethod

from cryptography.fernet import Fernet, InvalidToken

from app.infrastructure.settings import Settings


class SecretCipherError(ValueError):
    pass


class SecretCipherConfigurationError(SecretCipherError):
    pass


class SecretCipherDecryptionError(SecretCipherError):
    pass


class SecretCipher(ABC):
    @abstractmethod
    def encrypt(self, value: str) -> str: ...

    @abstractmethod
    def decrypt(self, value: str) -> str: ...


class EnvironmentSecretCipher(SecretCipher):
    def __init__(
        self,
        primary_key: str,
        *,
        previous_keys: tuple[str, ...] = (),
    ) -> None:
        if not primary_key.strip():
            raise SecretCipherConfigurationError(
                "WhatsApp secret encryption key is not configured",
            )
        try:
            self._primary = Fernet(primary_key.encode("ascii"))
            self._decryptors = (
                self._primary,
                *(Fernet(key.encode("ascii")) for key in previous_keys if key.strip()),
            )
        except (UnicodeEncodeError, ValueError) as exc:
            raise SecretCipherConfigurationError(
                "WhatsApp secret encryption key is invalid",
            ) from exc

    @classmethod
    def from_settings(cls, settings: Settings) -> "EnvironmentSecretCipher":
        previous_keys = tuple(
            key.strip()
            for key in settings.whatsapp_secret_previous_encryption_keys.split(",")
            if key.strip()
        )
        return cls(
            settings.whatsapp_secret_encryption_key,
            previous_keys=previous_keys,
        )

    @classmethod
    def from_integration_settings(cls, settings: Settings) -> "EnvironmentSecretCipher":
        primary_key = (
            settings.integration_secret_encryption_key
            or settings.whatsapp_secret_encryption_key
        )
        previous_raw = (
            settings.integration_secret_previous_encryption_keys
            or settings.whatsapp_secret_previous_encryption_keys
        )
        previous_keys = tuple(
            key.strip() for key in previous_raw.split(",") if key.strip()
        )
        return cls(primary_key, previous_keys=previous_keys)

    def encrypt(self, value: str) -> str:
        if not value:
            raise SecretCipherError("secret cannot be empty")
        return self._primary.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        token = value.encode("ascii")
        for decryptor in self._decryptors:
            try:
                return decryptor.decrypt(token).decode("utf-8")
            except InvalidToken:
                continue
        raise SecretCipherDecryptionError("secret could not be decrypted")

    def __repr__(self) -> str:
        return "EnvironmentSecretCipher(configured=True)"
