from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError


class PasswordService:
    def __init__(
        self,
        hasher: PasswordHasher | None = None,
        *,
        max_length: int = 256,
    ) -> None:
        self._hasher = hasher or PasswordHasher()
        self._max_length = max_length
        self._dummy_hash = self._hasher.hash("dummy-password-never-authenticates")

    def hash(self, password: str) -> str:
        if len(password) > self._max_length:
            raise ValueError("password is too long")
        return self._hasher.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        if len(password) > self._max_length:
            return False
        try:
            return self._hasher.verify(password_hash, password)
        except (InvalidHashError, VerifyMismatchError):
            return False

    def verify_dummy(self, password: str) -> None:
        if len(password) > self._max_length:
            return
        self.verify(password, self._dummy_hash)
