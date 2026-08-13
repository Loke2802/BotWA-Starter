import hashlib
import hmac
import threading
from datetime import UTC, datetime

from app.domain.security.contracts import (
    RateLimitDecision,
    RateLimitRepository,
    SecurityRateLimitScope,
)


class RateLimitService:
    def __init__(self, repository: RateLimitRepository, *, hmac_key: str) -> None:
        self.repository = repository
        self._hmac_key = hmac_key.encode("utf-8")

    def check(
        self,
        *,
        scope: SecurityRateLimitScope,
        identity: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        normalized = " ".join(identity.strip().lower().split())
        key_hash = hmac.new(
            self._hmac_key,
            f"{scope}:{normalized}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return self.repository.consume(
            scope=scope,
            key_hash=key_hash,
            limit=limit,
            window_seconds=window_seconds,
        )


class InMemoryRateLimitRepository:
    """Development/test convenience; production composition always uses PostgreSQL."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[tuple[str, str, int], int] = {}

    def consume(
        self,
        *,
        scope: SecurityRateLimitScope,
        key_hash: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        epoch = int(datetime.now(UTC).timestamp())
        window_epoch = epoch - (epoch % window_seconds)
        key = (scope, key_hash, window_epoch)
        with self._lock:
            count = self._counts.get(key, 0) + 1
            self._counts[key] = count
        return RateLimitDecision(
            allowed=count <= limit,
            retry_after_seconds=(
                0 if count <= limit else window_seconds - epoch % window_seconds
            ),
        )

    def clear(self) -> None:
        with self._lock:
            self._counts.clear()
