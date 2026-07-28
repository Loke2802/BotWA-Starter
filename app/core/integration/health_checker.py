import asyncio
import time

from httpx import AsyncClient, Timeout

from app.core.integration.monitor import IntegrationMonitor
from app.core.integration.provider_client import ProviderClient
from app.core.integration.provider_registry import IntegrationAdapterRegistry
from app.domain.integration.contracts import (
    Capability,
    HealthCheckResult,
    ProviderStatus,
)


class HealthChecker:
    def __init__(
        self,
        registry: IntegrationAdapterRegistry,
        clients: dict[str, ProviderClient],
        monitor: IntegrationMonitor | None = None,
        capabilities: dict[str, Capability] | None = None,
    ) -> None:
        self._registry = registry
        self._clients = clients
        self._monitor = monitor
        self._capabilities = capabilities or {}
        self._periodic_task: asyncio.Task[None] | None = None
        self._results: dict[str, HealthCheckResult] = {}

    def get_result(self, provider_id: str) -> HealthCheckResult | None:
        return self._results.get(provider_id)

    def get_all_results(self) -> list[HealthCheckResult]:
        return list(self._results.values())

    async def check_all(self) -> list[HealthCheckResult]:
        results: list[HealthCheckResult] = []
        for provider_id, client in self._clients.items():
            capability = self._capabilities.get(provider_id, Capability.HTTP_REQUEST)
            result = await self._check_single(provider_id, client, capability)
            results.append(result)
        return results

    async def check_provider(self, provider_id: str) -> HealthCheckResult | None:
        client = self._clients.get(provider_id)
        if client is None:
            return None
        capability = self._capabilities.get(provider_id, Capability.HTTP_REQUEST)
        return await self._check_single(provider_id, client, capability)

    async def _check_single(
        self,
        provider_id: str,
        client: ProviderClient,
        capability: Capability,
    ) -> HealthCheckResult:
        start = time.monotonic()
        error: str | None = None
        status = ProviderStatus.ACTIVE

        try:
            async with AsyncClient(timeout=Timeout(5.0)) as http:
                resp = await http.get("https://httpbin.org/status/200")
                if resp.status_code >= 500:
                    status = ProviderStatus.DEGRADED
                    error = f"HTTP {resp.status_code}"
        except Exception as exc:
            status = ProviderStatus.DEGRADED
            error = str(exc)

        latency = int((time.monotonic() - start) * 1000)

        result = HealthCheckResult(
            provider_id=provider_id,
            status=status,
            latency_ms=latency,
            error=error,
        )
        self._results[provider_id] = result

        if self._monitor is not None:
            self._monitor.record_health(provider_id, status, error)

        return result

    async def start_periodic_check(self, interval_seconds: float = 60.0) -> None:
        if self._periodic_task is not None:
            return

        async def _run() -> None:
            while True:
                await self.check_all()
                await asyncio.sleep(interval_seconds)

        self._periodic_task = asyncio.create_task(_run())

    async def stop_periodic_check(self) -> None:
        if self._periodic_task is not None:
            self._periodic_task.cancel()
            self._periodic_task = None
