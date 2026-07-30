import base64

import pytest
from app.infrastructure.settings import Settings
from app.security.secret_cipher import (
    EnvironmentSecretCipher,
    SecretCipherConfigurationError,
    SecretCipherDecryptionError,
)


def key(seed: bytes) -> str:
    return base64.urlsafe_b64encode(seed * 32).decode("ascii")


def test_environment_cipher_encrypts_and_supports_key_rotation() -> None:
    old_cipher = EnvironmentSecretCipher(key(b"a"))
    ciphertext = old_cipher.encrypt("verify-token")
    rotated_cipher = EnvironmentSecretCipher(
        key(b"b"),
        previous_keys=(key(b"a"),),
    )

    assert ciphertext != "verify-token"
    assert rotated_cipher.decrypt(ciphertext) == "verify-token"
    assert rotated_cipher.decrypt(rotated_cipher.encrypt("new-token")) == "new-token"
    assert "verify-token" not in repr(rotated_cipher)


def test_environment_cipher_fails_without_valid_configuration() -> None:
    with pytest.raises(SecretCipherConfigurationError):
        EnvironmentSecretCipher("")
    with pytest.raises(SecretCipherConfigurationError):
        EnvironmentSecretCipher("invalid")

    cipher = EnvironmentSecretCipher(key(b"a"))
    with pytest.raises(SecretCipherDecryptionError):
        cipher.decrypt(EnvironmentSecretCipher(key(b"b")).encrypt("secret"))


def test_environment_cipher_reads_current_and_previous_keys_from_settings() -> None:
    old_ciphertext = EnvironmentSecretCipher(key(b"a")).encrypt("old")
    settings = Settings(
        whatsapp_secret_encryption_key=key(b"b"),
        whatsapp_secret_previous_encryption_keys=f"{key(b'a')},",
    )

    cipher = EnvironmentSecretCipher.from_settings(settings)

    assert cipher.decrypt(old_ciphertext) == "old"
