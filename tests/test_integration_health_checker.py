from unittest.mock import MagicMock

from app.core.integration.health_checker import HealthChecker
from app.core.integration.monitor import IntegrationMonitor
from app.core.integration.provider_registry import IntegrationAdapterRegistry
from app.domain.integration.contracts import Capability


class TestHealthChecker:
    def setup_method(self) -> None:
        self.monitor = IntegrationMonitor()
        self.registry = IntegrationAdapterRegistry()
        self.registry.register(
            Capability.SEND_MESSAGE,
            MagicMock(provider_id="whatsapp", provider_name="WhatsApp"),
        )
        self.checker = HealthChecker(
            registry=self.registry,
            clients={},
            monitor=self.monitor,
        )

    async def test_check_unknown_provider_returns_none(self) -> None:
        result = await self.checker.check_provider("nonexistent")
        assert result is None

    async def test_check_all_returns_empty_for_no_clients(self) -> None:
        results = await self.checker.check_all()
        assert results == []

    async def test_check_all_with_clients(self) -> None:
        self.checker._clients = {
            "whatsapp": MagicMock(provider_id="whatsapp", provider_name="WhatsApp"),
        }
        results = await self.checker.check_all()
        assert isinstance(results, list)

    async def test_start_and_stop_periodic_check(self) -> None:
        await self.checker.start_periodic_check(interval_seconds=0.1)
        assert self.checker._periodic_task is not None
        assert not self.checker._periodic_task.done()
        await self.checker.stop_periodic_check()
        assert self.checker._periodic_task is None

    async def test_start_periodic_check_idempotent(self) -> None:
        await self.checker.start_periodic_check()
        first = self.checker._periodic_task
        await self.checker.start_periodic_check()
        assert self.checker._periodic_task is first
        await self.checker.stop_periodic_check()

    async def test_stop_without_start_no_error(self) -> None:
        await self.checker.stop_periodic_check()

    def test_get_result_returns_none_for_unknown(self) -> None:
        assert self.checker.get_result("nonexistent") is None

    def test_get_all_results_returns_empty_list(self) -> None:
        assert self.checker.get_all_results() == []
