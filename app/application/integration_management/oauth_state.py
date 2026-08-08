import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt


class OAuthStateInvalidError(ValueError):
    pass


class OAuthStateExpiredError(OAuthStateInvalidError):
    pass


@dataclass(frozen=True)
class OAuthStateClaims:
    organization_id: UUID
    integration_id: UUID
    provider: str
    nonce: str
    expires_at: datetime

    @property
    def nonce_hash(self) -> str:
        return hashlib.sha256(self.nonce.encode("utf-8")).hexdigest()


class OAuthStateSigner:
    def __init__(
        self,
        *,
        secret_key: str,
        algorithm: str = "HS256",
        ttl_seconds: int = 600,
    ) -> None:
        if len(secret_key) < 32:
            raise ValueError("oauth state signing key is not configured")
        if ttl_seconds < 60 or ttl_seconds > 3600:
            raise ValueError("oauth state ttl is invalid")
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._ttl_seconds = ttl_seconds

    def issue(
        self,
        *,
        organization_id: UUID,
        integration_id: UUID,
        provider: str,
    ) -> tuple[str, OAuthStateClaims]:
        now = datetime.now(UTC)
        claims = OAuthStateClaims(
            organization_id=organization_id,
            integration_id=integration_id,
            provider=provider,
            nonce=secrets.token_urlsafe(32),
            expires_at=now + timedelta(seconds=self._ttl_seconds),
        )
        token = jwt.encode(
            {
                "org": str(claims.organization_id),
                "integration": str(claims.integration_id),
                "provider": claims.provider,
                "nonce": claims.nonce,
                "iat": now,
                "exp": claims.expires_at,
            },
            self._secret_key,
            algorithm=self._algorithm,
        )
        return token, claims

    def decode(self, state: str) -> OAuthStateClaims:
        try:
            payload = jwt.decode(
                state,
                self._secret_key,
                algorithms=[self._algorithm],
                options={"require": ["org", "integration", "provider", "nonce", "exp"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise OAuthStateExpiredError("oauth state expired") from exc
        except jwt.PyJWTError as exc:
            raise OAuthStateInvalidError("oauth state invalid") from exc
        try:
            organization_id = UUID(self._required_string(payload, "org"))
            integration_id = UUID(self._required_string(payload, "integration"))
            provider = self._required_string(payload, "provider")
            nonce = self._required_string(payload, "nonce")
            expires_at = datetime.fromtimestamp(float(payload["exp"]), UTC)
        except (KeyError, TypeError, ValueError) as exc:
            raise OAuthStateInvalidError("oauth state invalid") from exc
        return OAuthStateClaims(
            organization_id=organization_id,
            integration_id=integration_id,
            provider=provider,
            nonce=nonce,
            expires_at=expires_at,
        )

    @staticmethod
    def _required_string(payload: dict[str, object], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise OAuthStateInvalidError("oauth state invalid")
        return value
