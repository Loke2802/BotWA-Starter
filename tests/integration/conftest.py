import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text


@pytest.fixture(autouse=True)
def isolate_prd012_postgresql_data() -> Generator[None]:
    """Keep every PostgreSQL smoke independent while preserving Alembic state."""
    database_url = os.getenv("BOTWA_PRD012_POSTGRES_URL")
    if database_url:
        engine = create_engine(database_url)
        try:
            with engine.begin() as connection:
                connection.execute(text("TRUNCATE TABLE organization CASCADE"))
        finally:
            engine.dispose()
    yield
