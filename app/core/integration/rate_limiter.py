import asyncio
import time


class TokenBucket:
    def __init__(self, capacity: float, refill_rate: float) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if refill_rate <= 0:
            raise ValueError("refill_rate must be positive")
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._tokens = capacity
        self._last_refill = time.monotonic()

    @property
    def capacity(self) -> float:
        return self._capacity

    @property
    def refill_rate(self) -> float:
        return self._refill_rate

    @property
    def tokens(self) -> float:
        self._refill()
        return self._tokens

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

    def acquire(self, tokens: float = 1.0) -> bool:
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    async def acquire_async(self, tokens: float = 1.0, timeout: float = 0.0) -> bool:
        deadline = time.monotonic() + timeout if timeout > 0 else 0.0
        while True:
            if self.acquire(tokens):
                return True
            if timeout > 0 and time.monotonic() >= deadline:
                return False
            await asyncio.sleep(min(0.05, timeout / 10 if timeout > 0 else 0.05))


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, TokenBucket] = {}

    def get_or_create(
        self, key: str, capacity: float, refill_rate: float
    ) -> TokenBucket:
        if key not in self._buckets:
            self._buckets[key] = TokenBucket(capacity=capacity, refill_rate=refill_rate)
        return self._buckets[key]

    def acquire(self, key: str, tokens: float = 1.0) -> bool:
        bucket = self._buckets.get(key)
        if bucket is None:
            return True
        return bucket.acquire(tokens)

    async def acquire_async(
        self, key: str, tokens: float = 1.0, timeout: float = 0.0
    ) -> bool:
        bucket = self._buckets.get(key)
        if bucket is None:
            return True
        return await bucket.acquire_async(tokens, timeout)

    def get_token_count(self, key: str) -> float | None:
        bucket = self._buckets.get(key)
        if bucket is None:
            return None
        return bucket.tokens
