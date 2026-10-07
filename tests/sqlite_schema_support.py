"""Copy empty SQLite schemas while keeping a separate durable file per test."""

import hashlib
import shutil
from pathlib import Path
from threading import Lock

from sqlalchemy import MetaData, create_engine, func, select
from sqlalchemy.dialects.sqlite import dialect
from sqlalchemy.schema import CreateIndex, CreateTable


class SqliteSchemaTemplates:
    def __init__(self, root: Path, metadata: MetaData) -> None:
        self.root = root
        self.metadata = metadata
        self.root.mkdir(parents=True, exist_ok=True)
        self._templates: dict[str, Path] = {}
        self._lock = Lock()

    def _signature(self) -> str:
        sqlite = dialect()
        statements = []
        for table in sorted(self.metadata.tables.values(), key=lambda item: item.key):
            statements.append(str(CreateTable(table).compile(dialect=sqlite)))
            statements.extend(
                sorted(
                    str(CreateIndex(index).compile(dialect=sqlite))
                    for index in table.indexes
                )
            )
        return hashlib.sha256("\0".join(statements).encode()).hexdigest()

    def prepare(self, destination: Path) -> None:
        # Never replace an existing test database, including a retained failure.
        if destination.exists():
            raise FileExistsError(destination)
        with self._lock:
            signature = self._signature()
            if signature not in self._templates:
                template = self.root / f"{signature}.sqlite"
                if template.exists():
                    raise FileExistsError(template)
                engine = create_engine(f"sqlite:///{template}")
                try:
                    self.metadata.create_all(engine)
                    with engine.connect() as connection:
                        for table in self.metadata.tables.values():
                            if connection.scalar(
                                select(func.count()).select_from(table)
                            ):
                                raise ValueError(
                                    "A SQLite schema template must contain no rows"
                                )
                finally:
                    engine.dispose()
                self._templates[signature] = template
            template = self._templates[signature]
            # Exclusive creation also protects against a concurrent destination.
            with template.open("rb") as source, destination.open("xb") as target:
                shutil.copyfileobj(source, target)
