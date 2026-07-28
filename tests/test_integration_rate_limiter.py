import asyncio
import time

from app.core.integration.rate_limiter import RateLimiter, TokenBucket


class TestTokenBucket:
    def test_initial_tokens_equal_capacity(self) -> None:
        bucket = TokenBucket(capacity=10, refill_rate=5.0)
        assert bucket._tokens == 10.0

    def test_acquire_returns_true_when_tokens_available(self) -> None:
        bucket = TokenBucket(capacity=5, refill_rate=10.0)
        assert bucket.acquire() is True

    def test_acquire_returns_false_when_no_tokens(self) -> None:
        bucket = TokenBucket(capacity=1, refill_rate=0.001)
        bucket.acquire()
        assert bucket.acquire() is False

    def test_acquire_consumes_token(self) -> None:
        bucket = TokenBucket(capacity=3, refill_rate=0.001)
        bucket.acquire()
        assert bucket._tokens == 2.0

    def test_refill_over_time(self) -> None:
        bucket = TokenBucket(capacity=5, refill_rate=10.0)
        bucket.acquire(5)
        assert bucket.acquire() is False
        time.sleep(0.15)
        assert bucket.acquire() is True

    def test_acquire_respects_count_parameter(self) -> None:
        bucket = TokenBucket(capacity=10, refill_rate=0.001)
        assert bucket.acquire(tokens=7) is True
        assert bucket._tokens == 3.0

    def test_acquire_returns_false_when_not_enough_tokens(self) -> None:
        bucket = TokenBucket(capacity=5, refill_rate=0.001)
        assert bucket.acquire(tokens=10) is False

    def test_cannot_exceed_capacity(self) -> None:
        bucket = TokenBucket(capacity=10, refill_rate=100.0)
        time.sleep(0.2)
        assert bucket._tokens <= 10.0


class TestRateLimiter:
    def test_get_or_create_creates_new_bucket(self) -> None:
        rl = RateLimiter()
        bucket = rl.get_or_create("key-1", capacity=10, refill_rate=5.0)
        assert bucket is not None
        assert bucket._tokens == 10.0

    def test_get_or_create_returns_existing_bucket(self) -> None:
        rl = RateLimiter()
        b1 = rl.get_or_create("key-1", capacity=10, refill_rate=5.0)
        b2 = rl.get_or_create("key-1", capacity=20, refill_rate=10.0)
        assert b1 is b2
        assert b2._tokens == 10.0

    def test_acquire_single_token(self) -> None:
        rl = RateLimiter()
        rl.get_or_create("key-1", capacity=5, refill_rate=0.001)
        assert rl.acquire("key-1") is True
        assert rl.acquire("key-1") is True
        assert rl.acquire("key-1") is True
        assert rl.acquire("key-1") is True
        assert rl.acquire("key-1") is True
        assert rl.acquire("key-1") is False

    def test_acquire_returns_true_for_missing_key(self) -> None:
        rl = RateLimiter()
        assert rl.acquire("nonexistent") is True

    def test_acquire_async(self) -> None:
        rl = RateLimiter()
        rl.get_or_create("key-1", capacity=10, refill_rate=0.001)
        result = asyncio.run(rl.acquire_async("key-1"))
        assert result is True

    def test_acquire_async_with_timeout(self) -> None:
        rl = RateLimiter()
        rl.get_or_create("key-1", capacity=1, refill_rate=5.0)
        rl.acquire("key-1")
        result = asyncio.run(rl.acquire_async("key-1", timeout=0.3))
        assert result is True

    def test_acquire_async_timeout_exceeded(self) -> None:
        rl = RateLimiter()
        rl.get_or_create("key-1", capacity=1, refill_rate=0.001)
        rl.acquire("key-1")
        result = asyncio.run(rl.acquire_async("key-1", timeout=0.1))
        assert result is False

    def test_multiple_keys_independent(self) -> None:
        rl = RateLimiter()
        rl.get_or_create("key-a", capacity=1, refill_rate=0.001)
        rl.get_or_create("key-b", capacity=3, refill_rate=0.001)
        assert rl.acquire("key-a") is True
        assert rl.acquire("key-a") is False
        assert rl.acquire("key-b") is True
        assert rl.acquire("key-b") is True
        assert rl.acquire("key-b") is True
        assert rl.acquire("key-b") is False
