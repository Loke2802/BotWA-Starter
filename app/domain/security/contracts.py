from dataclasses import dataclass
from typing import Literal, Protocol

SecurityRateLimitScope = Literal[
    "auth_login",
    "public_bootstrap",
    "whatsapp_webhook",
    "billing_webhook",
]


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int


class RateLimitRepository(Protocol):
    def consume(
        self,
        *,
        scope: SecurityRateLimitScope,
        key_hash: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision: ...
