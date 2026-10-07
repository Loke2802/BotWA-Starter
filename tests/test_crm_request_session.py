"""Authenticated CRM requests work with one pooled connection and fresh access."""

from types import SimpleNamespace

from app.api import crm_opportunity_routes, crm_routes
from app.api.dependencies import get_access_token_service
from app.infrastructure import database
from app.infrastructure.database import Base
from app.infrastructure.models.user import UserModel
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from tests.crm_opportunity_support import opportunity_service, seed


def test_crm_shares_connection_and_rechecks_access(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    engine = create_engine(
        f"sqlite:///{tmp_path/'one-connection.sqlite'}",
        connect_args={"check_same_thread": False},
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.2,
    )
    pool = engine.pool
    assert isinstance(pool, QueuePool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        actor, other, contact, _ = seed(session)
        service = opportunity_service(session)
        cipher, key = service.cipher, service.digest_key
        model = session.get(UserModel, actor.id)
        assert model is not None
        token = get_access_token_service().create(actor.id, model.auth_version)
    monkeypatch.setattr(
        database, "SessionLocal", sessionmaker(bind=engine, autoflush=False)
    )
    for module in (crm_routes, crm_opportunity_routes):
        monkeypatch.setattr(module, "get_whatsapp_secret_cipher", lambda: cipher)
        monkeypatch.setattr(
            module,
            "get_settings",
            lambda: SimpleNamespace(contact_identity_hmac_key=key),
        )
    app = create_app()
    headers = {"Authorization": "Bearer " + token}
    base = f"/organizations/{actor.organization_id}/crm"
    try:
        with TestClient(app) as client:
            for path in (
                base + "/customers",
                base + "/customers/" + str(contact) + "/workspace",
                base + "/opportunities",
                base + "/duplicates",
            ):
                response = client.get(path, headers=headers)
                assert response.status_code == 200, response.text
                assert pool.checkedout() == 0
            assert (
                client.get(
                    f"/organizations/{other.organization_id}/crm/customers",
                    headers=headers,
                ).status_code
                == 403
            )
            with Session(engine) as session:
                model = session.get(UserModel, actor.id)
                assert model is not None
                model.auth_version += 1
                session.commit()
            assert client.get(base + "/customers", headers=headers).status_code == 401
            assert pool.checkedout() == 0
    finally:
        engine.dispose()
