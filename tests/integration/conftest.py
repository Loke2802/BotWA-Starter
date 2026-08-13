import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, inspect, text


@pytest.fixture(autouse=True)
def isolate_postgresql_smoke_data() -> Generator[None]:
    """Keep every explicit PostgreSQL smoke independent while preserving Alembic."""
    database_url = (
        os.getenv("BOTWA_PRD021_POSTGRES_URL")
        or os.getenv("BOTWA_PRD019_POSTGRES_URL")
        or os.getenv("BOTWA_PRD018_POSTGRES_URL")
        or os.getenv("BOTWA_PRD017_POSTGRES_URL")
        or os.getenv("BOTWA_PRD016_POSTGRES_URL")
        or os.getenv("BOTWA_PRD015_POSTGRES_URL")
        or os.getenv("BOTWA_PRD013_POSTGRES_URL")
        or os.getenv("BOTWA_PRD012_POSTGRES_URL")
    )
    if database_url:
        engine = create_engine(database_url)
        try:
            if inspect(engine).has_table("organization"):
                with engine.begin() as connection:
                    connection.execute(text("TRUNCATE TABLE organization CASCADE"))
        finally:
            engine.dispose()
    yield
