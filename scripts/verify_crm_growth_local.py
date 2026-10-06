"""Normal HTTP authentication against a named synthetic localhost rehearsal."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if urlsplit(args.base_url).hostname not in {"127.0.0.1", "localhost"}:
        parser.error("localhost only")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest["environment"] != "disposable local PostgreSQL":
        parser.error("synthetic rehearsal only")
    org, foreign = manifest["organization_id"], manifest["other_organization_id"]
    base = f"/organizations/{org}/crm"
    state = (
        json.loads(args.state.read_text(encoding="utf-8"))
        if args.state.exists()
        else {"organization_id": org}
    )
    assert state["organization_id"] == org
    roles = []
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        assert client.get(base + "/duplicates").status_code == 401
        assert client.get(base + "/sales-metrics").status_code == 401
        for role, email in manifest["accounts"].items():
            response = client.post(
                "/auth/login", json={"email": email, "password": "SyntheticCRM2026!"}
            )
            assert response.status_code == 200
            headers = {"Authorization": "Bearer " + response.json()["access_token"]}
            if role == "organization_owner":
                me = client.get("/auth/me", headers=headers).json()["user"]
                if "source_id" not in state:
                    for field, phone, note in [
                        ("source_id", "+12025550151", "Nota original sintética"),
                        ("target_id", "+12025550152", "Nota principal sintética"),
                    ]:
                        created = client.post(
                            base + "/customers",
                            headers=headers,
                            json={
                                "display_name": "Cliente duplicado de prueba HTTP",
                                "whatsapp": phone,
                                "notes": note,
                            },
                        )
                        assert created.status_code == 201, created.text
                        state[field] = created.json()["id"]
                    args.state.parent.mkdir(parents=True, exist_ok=True)
                    args.state.write_text(
                        json.dumps(state, indent=2) + "\n", encoding="utf-8"
                    )
                payload = {
                    "contact_id": state["source_id"],
                    "title": "Cierre sintético para métricas",
                    "assigned_user_id": me["id"],
                    "stage_code": "new",
                    "no_action_reason": "Esperar revisión",
                    "amount": "80.00",
                    "currency": "PEN",
                }
                created = client.post(
                    base + "/opportunities",
                    headers={**headers, "Idempotency-Key": "growth-http-op"},
                    json=payload,
                )
                assert created.status_code == 201, created.text
                op = created.json()
                if op["stage_kind"] == "open":
                    updated = client.patch(
                        base + f"/opportunities/{op['id']}",
                        headers=headers,
                        json={
                            k: v
                            for k, v in {
                                **payload,
                                "version": op["version"],
                                "stage_code": "won",
                                "no_action_reason": None,
                                "close_reason": "Aceptada en prueba sintética",
                            }.items()
                            if k != "contact_id"
                        },
                    )
                    assert updated.status_code == 200, updated.text
                before = client.get(
                    base + f"/opportunities/{op['id']}/history", headers=headers
                ).json()
                if "review_token" not in state:
                    review = client.get(
                        base + f"/merge-preview?source_id={state['source_id']}"
                        f"&target_id={state['target_id']}",
                        headers=headers,
                    )
                    assert review.status_code == 200, review.text
                    state["review_token"] = review.json()["token"]
                    args.state.write_text(
                        json.dumps(state, indent=2) + "\n", encoding="utf-8"
                    )
                request = {
                    k: state[k] for k in ("source_id", "target_id", "review_token")
                }
                for _ in range(2):
                    merged = client.post(
                        base + "/customer-merges", headers=headers, json=request
                    )
                    assert merged.status_code == 200, merged.text
                assert merged.json()["replayed"]
                assert (
                    client.get(
                        base + f"/opportunities/{op['id']}/history", headers=headers
                    ).json()
                    == before
                )
                workspace = client.get(
                    base + f"/customers/{state['target_id']}/workspace", headers=headers
                ).json()
                assert workspace["opportunities"]["total"] == 1
                assert workspace["merged_origins"][0]["id"] == state["source_id"]
                for ident, note in [
                    (state["source_id"], "Nota original sintética"),
                    (state["target_id"], "Nota principal sintética"),
                ]:
                    assert (
                        client.get(
                            base + f"/customers/{ident}", headers=headers
                        ).json()["notes"]
                        == note
                    )
                assert (
                    client.get(
                        base + f"/customers/{state['source_id']}/workspace",
                        headers=headers,
                    ).json()["contact_id"]
                    == state["target_id"]
                )
                report = client.get(base + "/sales-metrics", headers=headers)
                assert report.status_code == 200, report.text
                assert any(
                    r["won"] >= 1 and r["won_amount"] == "80.00"
                    for r in report.json()["closings"]
                )
                suggestion = client.get(
                    base + f"/opportunities/{op['id']}/suggestions/"
                    f"{manifest['conversation_id']}",
                    headers=headers,
                )
                assert suggestion.status_code == 404  # another customer's conversation
            elif role in {"operator", "viewer"}:
                assert (
                    client.get(base + "/duplicates", headers=headers).status_code == 403
                )
                assert (
                    client.post(
                        base + "/customer-merges",
                        headers=headers,
                        json={
                            k: state[k]
                            for k in ("source_id", "target_id", "review_token")
                        },
                    ).status_code
                    == 403
                )
                report = client.get(base + "/sales-metrics", headers=headers)
                assert report.status_code == 200
                if role == "viewer":
                    assert all(
                        r["won_amount"] is None and r["currency"] is None
                        for r in report.json()["closings"]
                    )
            else:
                assert (
                    client.get(base + "/sales-metrics", headers=headers).status_code
                    == 403
                )
                assert (
                    client.get(base + "/duplicates", headers=headers).status_code == 403
                )
                own = client.get(
                    f"/organizations/{foreign}/crm/sales-metrics", headers=headers
                )
                assert own.status_code == 200 and own.json()["closings"] == []
            roles.append(role)
    args.output.write_text(
        json.dumps(
            {
                "environment": "authenticated localhost PostgreSQL",
                "roles": roles,
                "merge_replay": True,
                "history_and_notes_preserved": True,
                "metrics_from_closing_history": True,
                "cross_customer_ai_denied": True,
                "no_external_calls": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("PASS reviewed merge, preserved history, historical metrics and scoped IA")


if __name__ == "__main__":
    main()
