"""Let the transport own the transaction across managed application services."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session


def commit(session: Session) -> None:
    if session.info.get("atomic_transport"):
        session.flush()
    else:
        session.commit()


def rollback(session: Session) -> None:
    if not session.info.get("atomic_transport"):
        session.rollback()


@contextmanager
def atomic_transport(session: Session) -> Iterator[None]:
    previous = session.info.get("atomic_transport")
    session.info["atomic_transport"] = True
    try:
        yield
    finally:
        if previous is None:
            session.info.pop("atomic_transport", None)
        else:
            session.info["atomic_transport"] = previous
