"""Authenticated HTTP checks against the disposable local rehearsal server."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Only the local synthetic test server is accepted")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    org = manifest["organization_id"]
    other = manifest["other_organization_id"]
    op = manifest["opportunity_id"]
    contact = manifest["contact_id"]
    results = []
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        assert client.get(f"/organizations/{org}/crm/follow-up").status_code == 401
        for role, email in manifest["accounts"].items():
            response = client.post(
                "/auth/login", json={"email": email, "password": "SyntheticCRM2026!"}
            )
            assert response.status_code == 200, (role, response.status_code)
            headers = {"Authorization": "Bearer " + response.json()["access_token"]}
            own = other if role == "other_company" else org
            foreign = org if role == "other_company" else other
            queue = client.get(f"/organizations/{own}/crm/follow-up", headers=headers)
            assert queue.status_code == 200
            assert (
                client.get(
                    f"/organizations/{foreign}/crm/follow-up", headers=headers
                ).status_code
                == 403
            )
            assert (
                client.get(
                    f"/organizations/{foreign}/crm/opportunities/{op}", headers=headers
                ).status_code
                == 403
            )
            if role == "other_company":
                assert queue.json()["total"] == 0
            else:
                assert queue.json()["summary"] == {
                    "open": 3,
                    "overdue": 1,
                    "upcoming": 1,
                    "without_action": 1,
                }
                detail = client.get(
                    f"/organizations/{org}/crm/opportunities/{op}", headers=headers
                ).json()
                history = client.get(
                    f"/organizations/{org}/crm/opportunities/{op}/history",
                    headers=headers,
                ).json()
                customer = client.get(
                    f"/organizations/{org}/crm/customers/{contact}", headers=headers
                ).json()
                if role == "viewer":
                    assert detail["title"] == "Oportunidad" and detail["need"] is None
                    assert (
                        detail["next_action"]["description"] == "Contenido restringido"
                    )
                    assert all(h["snapshot"]["title"] == "Oportunidad" for h in history)
                    assert (
                        not customer["can_edit"] and not customer["can_read_sensitive"]
                    )
                update = {
                    k: detail[k]
                    for k in [
                        "title",
                        "need",
                        "stage_code",
                        "assigned_user_id",
                        "no_action_reason",
                        "close_reason",
                        "amount",
                        "currency",
                        "version",
                    ]
                }
                update["next_action"] = {
                    k: detail["next_action"][k] for k in ["description", "due_at"]
                }
                response = client.patch(
                    f"/organizations/{org}/crm/opportunities/{op}",
                    json=update,
                    headers=headers,
                )
                assert response.status_code == (403 if role == "viewer" else 200)
                if role != "viewer":
                    assert (
                        client.patch(
                            f"/organizations/{org}/crm/opportunities/{op}",
                            json=update,
                            headers=headers,
                        ).status_code
                        == 409
                    )
                stages = client.get(
                    f"/organizations/{org}/crm/stages", headers=headers
                ).json()
                response = client.put(
                    f"/organizations/{org}/crm/stages",
                    json={"stages": stages},
                    headers=headers,
                )
                assert response.status_code == (
                    200 if role == "organization_owner" else 403
                )
            results.append(
                {
                    "role": role,
                    "authenticated": True,
                    "own_scope": True,
                    "foreign_scope_denied": True,
                    "content_redacted": role == "viewer",
                    "write_expected": role in {"organization_owner", "operator"},
                }
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "environment": "local API, bearer authentication, PostgreSQL",
                "unauthenticated_denied": True,
                "roles": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("PASS: four authenticated roles, tenant scope, redaction and stale edits")


if __name__ == "__main__":
    main()
