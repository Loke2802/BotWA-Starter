from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

_ALLOWED_ALGORITHMS = frozenset({"HS256"})


class TokenError(ValueError):
    pass


class AccessTokenPayload:
    def __init__(
        self,
        user_id: UUID,
        auth_version: int,
        expires_at: datetime,
    ) -> None:
        self.user_id = user_id
        self.auth_version = auth_version
        self.expires_at = expires_at


class AccessTokenService:
    def __init__(
        self,
        secret_key: str,
        algorithm: str,
        expires_minutes: int,
    ) -> None:
        if algorithm not in _ALLOWED_ALGORITHMS:
            raise ValueError("unsupported token algorithm")
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._expires_minutes = expires_minutes

    @property
    def expires_seconds(self) -> int:
        return self._expires_minutes * 60

    def create(self, user_id: UUID, auth_version: int) -> str:
        expires_at = datetime.now(UTC) + timedelta(minutes=self._expires_minutes)
        payload: dict[str, object] = {
            "sub": str(user_id),
            "auth_version": auth_version,
            "exp": expires_at,
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def decode(self, token: str) -> AccessTokenPayload:
        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],
            )
            subject = payload.get("sub")
            auth_version = payload.get("auth_version")
            expires_at = payload.get("exp")
            if not isinstance(subject, str):
                raise TokenError("invalid token")
            if not isinstance(auth_version, int):
                raise TokenError("invalid token")
            if not isinstance(expires_at, int):
                raise TokenError("invalid token")
            return AccessTokenPayload(
                user_id=UUID(subject),
                auth_version=auth_version,
                expires_at=datetime.fromtimestamp(expires_at, UTC),
            )
        except (ValueError, jwt.InvalidTokenError) as exc:
            raise TokenError("invalid token") from exc
