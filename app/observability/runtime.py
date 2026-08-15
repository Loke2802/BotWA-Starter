from dataclasses import dataclass

from app.infrastructure.settings import Settings
from app.observability.health import DatabaseReadinessProbe
from app.observability.metrics import ObservabilityMetrics


@dataclass
class ObservabilityRuntime:
    metrics: ObservabilityMetrics
    readiness: DatabaseReadinessProbe

    @classmethod
    def build(cls, settings: Settings) -> "ObservabilityRuntime":
        return cls(
            metrics=ObservabilityMetrics(),
            readiness=DatabaseReadinessProbe(
                settings.database_url,
                timeout_seconds=settings.health_db_timeout_seconds,
                enabled=settings.use_database,
            ),
        )

    def close(self) -> None:
        self.readiness.close()
