# ruff: noqa: F811
from uuid import UUID

from app.api.dependencies import require_authenticated_user
from app.application.crm.duplicates import DuplicateService
from app.domain.crm.growth_contracts import MergeInput
from scripts.crm_search_dataset import seed_search_dataset

from tests.crm_opportunity_support import opportunity_service
from tests.test_crm import crm  # noqa: F401
from tests.test_crm_growth import target
from tests.test_crm_opportunities import crm_opportunities  # noqa: F401


def test_global_search_beyond_first_pages_and_scoped_filters(crm):  # type: ignore[no-untyped-def]
    client, session, actor, other, service = crm
    data = seed_search_dataset(
        session, actor.organization_id, service.cipher, service.hasher, count=2105
    )
    base = f"/organizations/{actor.organization_id}/crm/customers"
    late = set(data["late_ids"])
    results = []
    for page in (1, 2):
        response = client.get(
            base,
            params={
                "search": "perez josé",
                "search_by": "name",
                "page_size": 1,
                "page": page,
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["total"] == 2 and result["has_next"] == (page == 1)
        results.append(result["items"][0]["id"])
    assert set(results) == late and len(set(results)) == 2
    for field, term, total in (
        ("phone", data["phone"], 1),
        ("email", data["email"].upper(), 2),
    ):
        result = client.get(base, params={"search": term, "search_by": field}).json()
        assert result["total"] == total
        assert {r["id"] for r in result["items"]}.issubset(late)
        assert all("external_identifier" not in r for r in result["items"])
    assert (
        client.get(base, params={"search": "perez", "due": True}).json()["total"] == 0
    )
    assert (
        client.get(
            base, params={"search": "perez", "classification": "customer"}
        ).json()["total"]
        == 0
    )
    assert (
        client.get(
            f"/organizations/{other.organization_id}/crm/customers",
            params={"search": "perez"},
        ).status_code
        == 403
    )
    client.app.dependency_overrides[require_authenticated_user] = lambda: other
    assert (
        client.get(
            f"/organizations/{other.organization_id}/crm/customers",
            params={"search": "perez"},
        ).json()["total"]
        == 0
    )


def test_viewer_name_search_does_not_decrypt_sensitive_identifiers(crm, monkeypatch):  # type: ignore[no-untyped-def]
    client, _, actor, _, service = crm
    base = f"/organizations/{actor.organization_id}/crm"
    contact = client.post(
        base + "/customers",
        json={
            "display_name": "Ana María",
            "whatsapp": "+12025550201",
            "notes": "Privado",
        },
    ).json()
    viewer = actor.model_copy(update={"role": "viewer"})
    client.app.dependency_overrides[require_authenticated_user] = lambda: viewer
    decrypt = service.cipher.decrypt
    reads = []

    def record(value):  # type: ignore[no-untyped-def]
        reads.append(decrypt(value))
        return reads[-1]

    monkeypatch.setattr(service.cipher, "decrypt", record)
    result = client.get(
        base + "/customers", params={"search": "maria", "search_by": "name"}
    )
    assert (
        result.status_code == 200 and result.json()["items"][0]["id"] == contact["id"]
    )
    assert reads and set(reads) == {"Ana María"}
    assert not client.get(base + "/summary").json()["can_search_sensitive"]
    for field, term in (("phone", "+12025550201"), ("email", "a@example.test")):
        assert (
            client.get(
                base + "/customers", params={"search": term, "search_by": field}
            ).status_code
            == 403
        )
    assert set(reads) == {"Ana María"}


def test_duplicate_scan_crosses_2000_with_stable_disjoint_pages(crm_opportunities):  # type: ignore[no-untyped-def]
    client, session, actor, _, _, _ = crm_opportunities
    svc = opportunity_service(session)
    from app.application.contacts.identity import ContactIdentityHasher
    from app.domain.contacts.contracts import ContactIdentityNormalizer

    data = seed_search_dataset(
        session,
        actor.organization_id,
        svc.cipher,
        ContactIdentityHasher(svc.digest_key, ContactIdentityNormalizer()),
        count=2105,
    )
    base = f"/organizations/{actor.organization_id}/crm/duplicates"
    first = client.get(base).json()
    second = client.get(base, params={"page": 2}).json()
    assert first["scanned"] == 2106 and not first["scan_limited"]
    assert first["total"] == 23 and len(first["items"]) == 20 and first["has_next"]
    assert len(second["items"]) == 3 and not second["has_next"]
    pairs = {(r["source_id"], r["target_id"]) for r in first["items"] + second["items"]}
    assert len(pairs) == 23
    assert any({a, b} == set(data["late_ids"]) for a, b in pairs)
    assert client.get(base).json() == first
    assert not client.get(base, params={"page": 3}).json()["items"]


def test_search_alias_chain_returns_main_and_archived_original(crm_opportunities):  # type: ignore[no-untyped-def]
    client, session, actor, _, original, _ = crm_opportunities
    svc = opportunity_service(session)
    second = target(session, actor.organization_id, svc.cipher).id
    third = target(session, actor.organization_id, svc.cipher).id
    duplicate = DuplicateService(svc)
    for source, principal in ((original, second), (second, third)):
        review = duplicate.preview(actor.organization_id, actor, source, principal)
        duplicate.merge(
            actor.organization_id,
            actor,
            MergeInput(
                source_id=source, target_id=principal, review_token=review.token
            ),
        )
    base = f"/organizations/{actor.organization_id}/crm/customers"
    active = client.get(
        base, params={"search": "+12025550147", "search_by": "phone"}
    ).json()
    assert active["total"] == 1 and UUID(active["items"][0]["id"]) == third
    archived = client.get(
        base,
        params={"search": "+12025550147", "search_by": "phone", "status": "archived"},
    ).json()
    assert archived["total"] == 1 and UUID(archived["items"][0]["id"]) == original
    by_name = client.get(
        base, params={"search": "client synthetic", "search_by": "name"}
    ).json()
    assert by_name["total"] == 1 and UUID(by_name["items"][0]["id"]) == third
    old_names = client.get(
        base,
        params={
            "search": "client synthetic",
            "search_by": "name",
            "status": "archived",
        },
    ).json()
    assert {UUID(row["id"]) for row in old_names["items"]} == {original, second}
