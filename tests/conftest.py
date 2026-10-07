from collections.abc import Generator

import pytest
from app.infrastructure.database import Base
from app.infrastructure.settings import get_settings

from tests.sqlite_schema_support import SqliteSchemaTemplates


@pytest.fixture(scope="session")
def sqlite_schema(tmp_path_factory: pytest.TempPathFactory) -> SqliteSchemaTemplates:
    return SqliteSchemaTemplates(
        tmp_path_factory.mktemp("sqlite-schema"), Base.metadata
    )


@pytest.fixture(autouse=True)
def force_in_memory_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None]:
    monkeypatch.setenv("BOTWA_USE_DATABASE", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
