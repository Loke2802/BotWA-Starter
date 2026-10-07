"""Compare all PostgreSQL rows without exporting their private contents."""

import hashlib

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def fingerprint(engine: Engine) -> dict[str, str]:
    with engine.connect() as connection:
        return {
            table: hashlib.sha256(
                "\n".join(
                    sorted(
                        connection.scalars(
                            text(f'SELECT row_to_json(t)::text FROM "{table}" AS t')
                        )
                    )
                ).encode()
            ).hexdigest()
            for table in inspect(connection).get_table_names()
        }
