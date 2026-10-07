# ruff: noqa: F811
import json
from uuid import UUID

import pytest
from app.application.contacts.identity import ContactIdentityHasher
from app.application.contacts.search_index import ContactSearchIndex
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.contact_search import (
    ContactSearchStateModel,
    ContactSearchTokenModel,
)
from app.security.authorization import AuthorizationError
from scripts.crm_search_dataset import seed_search_dataset
from sqlalchemy import func, select, update

from tests.test_crm import crm  # noqa: F401


def test_indexed_volume_preserves_rows_and_bounds_decryption(crm, monkeypatch):  # type: ignore[no-untyped-def]
    client, session, actor, _, service = crm
    data = seed_search_dataset(
        session, actor.organization_id, service.cipher, service.hasher, count=2105
    )
    before = {
        row.id: (
            row.updated_at,
            row.external_identifier_ciphertext,
            row.registration_ciphertext,
        )
        for row in session.scalars(select(ContactModel))
    }
    assert service.rebuild_search_index(actor.organization_id, actor) == 2105
    assert before == {
        row.id: (
            row.updated_at,
            row.external_identifier_ciphertext,
            row.registration_ciphertext,
        )
        for row in session.scalars(select(ContactModel))
    }
    state_count = session.scalar(
        select(func.count()).select_from(ContactSearchStateModel)
    )
    token_count = session.scalar(
        select(func.count()).select_from(ContactSearchTokenModel)
    )
    assert service.rebuild_search_index(actor.organization_id, actor) == state_count
    assert (
        session.scalar(select(func.count()).select_from(ContactSearchTokenModel))
        == token_count
    )
    assert all(
        len(t.digest) == 64 and "@" not in t.digest
        for t in session.scalars(select(ContactSearchTokenModel))
    )
    reads = []
    decrypt = service.cipher.decrypt

    def record(value):  # type: ignore[no-untyped-def]
        reads.append(decrypt(value))
        return reads[-1]

    monkeypatch.setattr(service.cipher, "decrypt", record)
    base = f"/organizations/{actor.organization_id}/crm/customers"
    for field, term, count in [
        ("phone", data["phone"], 1),
        ("email", data["email"], 2),
    ]:
        reads.clear()
        response = client.get(base, params={"search": term, "search_by": field})
        assert response.status_code == 200 and response.json()["total"] == count
        assert len(reads) == count and all("P" in name or "p" in name for name in reads)


def test_stale_ciphertext_and_key_rotation_fall_back_without_false_matches(crm):  # type: ignore[no-untyped-def]
    client, session, actor, _, service = crm
    data = client.post(
        f"/organizations/{actor.organization_id}/crm/customers",
        json={
            "display_name": "Cliente índice",
            "whatsapp": "+12025550202",
        },
    ).json()
    contact = UUID(data["id"])
    # Bypass indexing deliberately; ciphertext validation must catch the change.
    session.execute(
        update(ContactModel)
        .where(ContactModel.id == contact)
        .values(
            external_identifier_ciphertext=service.cipher.encrypt("12025550203"),
            registration_ciphertext=service.cipher.encrypt(
                json.dumps(
                    {"email": "nuevo@example.test", "correo": "otro@example.test"}
                )
            ),
        )
    )
    session.commit()
    base = f"/organizations/{actor.organization_id}/crm/customers"
    assert (
        client.get(
            base, params={"search": "+12025550202", "search_by": "phone"}
        ).json()["total"]
        == 0
    )
    for field, term in [
        ("phone", "+12025550203"),
        ("email", "nuevo@example.test"),
        ("email", "otro@example.test"),
    ]:
        assert client.get(base, params={"search": term, "search_by": field}).json()[
            "items"
        ][0]["id"] == str(contact)
    rotated = ContactIdentityHasher(
        "rotated-test-key-at-least-thirty-two-characters", ContactIdentityNormalizer()
    )
    assert rotated.search_key_id != service.hasher.search_key_id
    service.hasher = rotated
    assert (
        client.get(
            base, params={"search": "+12025550203", "search_by": "phone"}
        ).json()["total"]
        == 1
    )
    service.rebuild_search_index(actor.organization_id, actor)
    assert (
        session.scalar(select(ContactSearchStateModel.key_id)) == rotated.search_key_id
    )


def test_hmac_tenant_separation_and_backfill_authorization(crm):  # type: ignore[no-untyped-def]
    _, session, actor, other, service = crm
    assert service.hasher.search_digest(
        actor.organization_id, "email", "a@example.test"
    ) != service.hasher.search_digest(other.organization_id, "email", "a@example.test")
    for org, user in [
        (other.organization_id, actor),
        (actor.organization_id, actor.model_copy(update={"role": "viewer"})),
    ]:
        with pytest.raises(AuthorizationError):
            service.rebuild_search_index(org, user)
    assert (
        session.scalar(select(func.count()).select_from(ContactSearchStateModel)) == 0
    )


def test_index_write_rolls_back_with_contact(crm):  # type: ignore[no-untyped-def]
    _, session, actor, _, service = crm
    row = ContactModel(
        organization_id=actor.organization_id,
        channel_type="email",
        external_identifier_hash="rollback-test",
        external_identifier_ciphertext=service.cipher.encrypt("rollback@example.test"),
    )
    session.add(row)
    ContactSearchIndex(session, service.cipher, service.hasher).sync(row)
    assert (
        session.scalar(select(func.count()).select_from(ContactSearchTokenModel)) == 1
    )
    session.rollback()
    assert (
        session.scalar(select(func.count()).select_from(ContactSearchTokenModel)) == 0
    )
    assert (
        session.scalar(
            select(ContactModel).where(
                ContactModel.external_identifier_hash == "rollback-test"
            )
        )
        is None
    )
