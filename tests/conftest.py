from collections.abc import Generator

import pytest
from app.infrastructure.settings import get_settings


@pytest.fixture(autouse=True)
def force_in_memory_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None]:
    monkeypatch.setenv("BOTWA_USE_DATABASE", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
