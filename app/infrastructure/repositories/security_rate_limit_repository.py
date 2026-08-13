from datetime import UTC, datetime, timedelta

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.domain.security.contracts import RateLimitDecision, SecurityRateLimitScope
from app.infrastructure.models.security_rate_limit import SecurityRateLimitBucketModel


class SqlAlchemyRateLimitRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def consume(
        self,
        *,
        scope: SecurityRateLimitScope,
        key_hash: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        now = datetime.now(UTC)
        epoch = int(now.timestamp())
        window_epoch = epoch - (epoch % window_seconds)
        window_started_at = datetime.fromtimestamp(window_epoch, UTC)
        blocked_until = window_started_at + timedelta(seconds=window_seconds)
        values = {
            "scope": scope,
            "key_hash": key_hash,
            "window_started_at": window_started_at,
            "attempt_count": 1,
            "blocked_until": None,
            "updated_at": now,
        }
        update_values = {
            "attempt_count": SecurityRateLimitBucketModel.attempt_count + 1,
            "blocked_until": case(
                (
                    SecurityRateLimitBucketModel.attempt_count + 1 > limit,
                    blocked_until,
                ),
                else_=SecurityRateLimitBucketModel.blocked_until,
            ),
            "updated_at": now,
        }
        if self.session.get_bind().dialect.name == "postgresql":
            pg_statement = (
                postgresql_insert(SecurityRateLimitBucketModel)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=("scope", "key_hash", "window_started_at"),
                    set_=update_values,
                )
                .returning(
                    SecurityRateLimitBucketModel.attempt_count,
                    SecurityRateLimitBucketModel.blocked_until,
                )
            )
            count, persisted_blocked_until = self.session.execute(pg_statement).one()
        else:
            sqlite_statement = (
                sqlite_insert(SecurityRateLimitBucketModel)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=("scope", "key_hash", "window_started_at"),
                    set_=update_values,
                )
                .returning(
                    SecurityRateLimitBucketModel.attempt_count,
                    SecurityRateLimitBucketModel.blocked_until,
                )
            )
            count, persisted_blocked_until = self.session.execute(
                sqlite_statement
            ).one()
        self.session.commit()
        allowed = int(count) <= limit
        retry_after = 0
        if not allowed:
            effective_until = persisted_blocked_until or blocked_until
            if effective_until.tzinfo is None:
                effective_until = effective_until.replace(tzinfo=UTC)
            retry_after = max(1, int((effective_until - now).total_seconds()) + 1)
        return RateLimitDecision(allowed=allowed, retry_after_seconds=retry_after)
