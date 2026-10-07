# ruff: noqa: F811
"""Protected partial names and duplicate detection agree with unindexed data."""

from uuid import UUID

import pytest
from app.api.dependencies import require_authenticated_user
from app.application.contacts.identity import ContactIdentityHasher
from app.application.contacts.name_index import ContactNameIndex
from app.application.contacts.search import ContactSearch
from app.application.contacts.search_index import ContactSearchIndex
from app.application.crm.duplicates import DuplicateService
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.contact_name_search import (
    ContactNameStateModel,
    ContactNameTokenModel,
)
from scripts.crm_search_dataset import seed_search_dataset
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from tests.crm_opportunity_support import opportunity_service
from tests.test_crm import crm  # noqa: F401
from tests.test_crm_opportunities import crm_opportunities  # noqa: F401


def test_partial_names_verify_false_grams_unicode_and_word_order(crm):  # type: ignore[no-untyped-def]
    client, session, actor, _, svc = crm
    base = f"/organizations/{actor.organization_id}/crm/customers"
    names = ["José Pérez", "JÓSE PÉREZ", "ab cd", "abbc", "李 小明", "Ana María"]
    ids = []
    for i, name in enumerate(names):
        response = client.post(
            base, json={"display_name": name, "whatsapp": f"+12025550{300+i:03d}"}
        )
        assert response.status_code == 201
        ids.append(response.json()["id"])
    for term, expected in [
        ("perez josé", ids[:2]),
        ("j p", ids[:2]),
        ("bc", [ids[3]]),
        ("abc", []),
        ("李 明", [ids[4]]),
        ("aria", [ids[5]]),
    ]:
        result = client.get(base, params={"search": term, "search_by": "name"}).json()
        assert {row["id"] for row in result["items"]} == set(expected)
    assert session.scalar(
        select(func.count()).select_from(ContactNameStateModel)
    ) == len(names)
    assert all(
        len(token.digest) == 64
        for token in session.scalars(select(ContactNameTokenModel))
    )


def test_name_index_viewer_bounds_decryption_and_detects_sql_changes(crm, monkeypatch):  # type: ignore[no-untyped-def]
    client, session, actor, _, svc = crm
    data = seed_search_dataset(
        session, actor.organization_id, svc.cipher, svc.hasher, count=2105
    )
    svc.rebuild_search_index(actor.organization_id, actor)
    viewer = actor.model_copy(update={"role": "viewer"})
    client.app.dependency_overrides[require_authenticated_user] = lambda: viewer
    reads = []
    decrypt = svc.cipher.decrypt

    def record(value):  # type: ignore[no-untyped-def]
        reads.append(decrypt(value))
        return reads[-1]

    monkeypatch.setattr(svc.cipher, "decrypt", record)
    base = f"/organizations/{actor.organization_id}/crm/customers"
    result = client.get(base, params={"search": "perez jose"}).json()
    assert result["total"] == 2 and len(reads) == 4
    assert set(reads) == {"José Pérez tardío", "JOSE PEREZ TARDIO"}
    reads.clear()
    assert (
        client.get(
            base, params={"search": data["phone"], "search_by": "phone"}
        ).status_code
        == 403
    )
    assert not reads
    broad = client.get(base, params={"search": "co", "page_size": 20}).json()
    assert broad["total"] >= 2000 and len(reads) == 20
    reads.clear()
    session.execute(
        update(ContactModel)
        .where(ContactModel.id == UUID(data["late_ids"][0]))
        .values(display_name_ciphertext=svc.cipher.encrypt("Nombre cambiado"))
    )
    session.commit()
    assert client.get(base, params={"search": "cambiado"}).json()["total"] == 1
    assert client.get(base, params={"search": "perez jose"}).json()["total"] == 1
    rotated = ContactIdentityHasher(
        "new-name-test-key-at-least-thirty-two-characters", ContactIdentityNormalizer()
    )
    index = ContactNameIndex(session, svc.cipher, rotated)
    assert (
        len(
            session.scalars(
                index.matching(
                    actor.organization_id, ContactSearch("cambiado", "name", svc.cipher)
                )
            ).all()
        )
        == 1
    )


def test_indexed_duplicates_match_fallback(crm_opportunities, monkeypatch):  # type: ignore[no-untyped-def]
    client, session, actor, _, original, _ = crm_opportunities
    svc = opportunity_service(session)
    hasher = ContactIdentityHasher(svc.digest_key, ContactIdentityNormalizer())
    seed_search_dataset(session, actor.organization_id, svc.cipher, hasher, count=2105)
    duplicate = DuplicateService(svc)
    before = [
        duplicate.candidates(actor.organization_id, actor, page) for page in (1, 2)
    ]
    ContactSearchIndex(session, svc.cipher, hasher).rebuild(actor.organization_id)
    session.commit()
    reads = []
    decrypt = svc.cipher.decrypt

    def record(value):  # type: ignore[no-untyped-def]
        reads.append(decrypt(value))
        return reads[-1]

    monkeypatch.setattr(svc.cipher, "decrypt", record)
    for page in (1, 2):
        reads.clear()
        assert (
            duplicate.candidates(actor.organization_id, actor, page) == before[page - 1]
        )
        assert len(reads) <= 40 and all(
            "@" not in value and not value.isdigit() for value in reads
        )
    # A direct update invalidates the old name signal and changes the current pairs.
    first = before[0].items[0]
    session.execute(
        update(ContactModel)
        .where(ContactModel.id == first.source_id)
        .values(display_name_ciphertext=svc.cipher.encrypt("Synthetic client"))
    )
    session.commit()
    latest = duplicate.candidates(actor.organization_id, actor, 1)
    affected = [
        r
        for r in latest.items
        if r.source_id == first.source_id and r.target_id == first.target_id
    ]
    assert not affected or "nombre" not in affected[0].reasons
    pairs = latest.items + duplicate.candidates(actor.organization_id, actor, 2).items
    assert any(
        {row.source_id, row.target_id} == {original, first.source_id}
        and "nombre" in row.reasons
        for row in pairs
    )


def test_name_index_rolls_back_and_is_scoped(crm):  # type: ignore[no-untyped-def]
    _, session, actor, other, svc = crm
    row = ContactModel(
        organization_id=actor.organization_id,
        channel_type="email",
        external_identifier_hash="name-rollback",
        external_identifier_ciphertext=svc.cipher.encrypt("x@example.test"),
        display_name_ciphertext=svc.cipher.encrypt("Única confidencial"),
    )
    session.add(row)
    index = ContactNameIndex(session, svc.cipher, svc.hasher)
    index.sync(row)
    assert not session.scalars(
        index.matching(
            other.organization_id, ContactSearch("unica", "name", svc.cipher)
        )
    ).all()
    assert svc.hasher.name_digest(
        actor.organization_id, "gram", "co"
    ) != svc.hasher.name_digest(other.organization_id, "gram", "co")
    for model, values in [
        (
            ContactNameStateModel,
            dict(
                organization_id=other.organization_id,
                contact_id=row.id,
                key_id=svc.hasher.search_key_id,
                name_ciphertext=row.display_name_ciphertext,
            ),
        ),
        (
            ContactNameTokenModel,
            dict(
                organization_id=other.organization_id,
                contact_id=row.id,
                kind="gram",
                digest="f" * 64,
            ),
        ),
    ]:
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(insert(model), values)
    session.rollback()
    assert session.scalar(select(func.count()).select_from(ContactNameTokenModel)) == 0
