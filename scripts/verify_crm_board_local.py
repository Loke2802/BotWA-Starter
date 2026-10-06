"""Verify board permissions and stale stage writes on a synthetic localhost demo."""

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
    if urlsplit(args.base_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Only localhost is accepted")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest["environment"] != "disposable local PostgreSQL":
        parser.error("Only the synthetic rehearsal manifest is accepted")
    org, other = manifest["organization_id"], manifest["other_organization_id"]
    results = []
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        assert client.get(f"/organizations/{org}/crm/stages").status_code == 401
        assert client.get(f"/organizations/{org}/crm/opportunities").status_code == 401
        for role, email in manifest["accounts"].items():
            login = client.post(
                "/auth/login", json={"email": email, "password": "SyntheticCRM2026!"}
            )
            assert login.status_code == 200
            headers = {"Authorization": "Bearer " + login.json()["access_token"]}
            own, foreign = (other, org) if role == "other_company" else (org, other)
            base = f"/organizations/{own}/crm"
            response = client.get(f"{base}/stages", headers=headers)
            assert response.status_code == 200
            stages = response.json()
            assert (
                client.get(
                    f"/organizations/{foreign}/crm/stages", headers=headers
                ).status_code
                == 403
            )
            assert (
                client.get(
                    f"/organizations/{foreign}/crm/opportunities", headers=headers
                ).status_code
                == 403
            )
            total = 0
            for stage in stages:
                column = client.get(
                    f"{base}/opportunities",
                    params={"stage_code": stage["code"], "page_size": 10},
                    headers=headers,
                )
                assert column.status_code == 200
                rows = column.json()
                total += rows["total"]
                assert all(row["stage_code"] == stage["code"] for row in rows["items"])
                if role == "viewer":
                    assert all(
                        row["title"] == "Oportunidad" and row["need"] is None
                        for row in rows["items"]
                    )
            assert total == (0 if role == "other_company" else 3)
            if role in {"viewer", "operator"}:
                assert (
                    client.put(
                        f"{base}/stages",
                        json={"stages": stages, "expected_stages": stages},
                        headers=headers,
                    ).status_code
                    == 403
                )
            if role == "organization_owner":
                stale = [dict(s) for s in stages]
                stale[0]["name"] = "Synthetic stale snapshot"
                rejected = client.put(
                    f"{base}/stages",
                    json={"stages": stages, "expected_stages": stale},
                    headers=headers,
                )
                assert rejected.status_code == 409
                assert client.get(f"{base}/stages", headers=headers).json() == stages
                detail = client.get(
                    f"{base}/opportunities/{manifest['opportunity_id']}",
                    headers=headers,
                ).json()
                history = client.get(
                    f"{base}/opportunities/{manifest['opportunity_id']}/history",
                    headers=headers,
                ).json()
                assert detail["stage_code"] == "decision" and detail["version"] == 6
                assert (
                    history[0]["version"] == 6
                    and history[1]["snapshot"]["stage_code"] == "offer"
                )
            results.append(
                {
                    "role": role,
                    "columns_scoped": True,
                    "total": total,
                    "foreign_access_denied": True,
                }
            )
    args.output.write_text(
        json.dumps(
            {
                "environment": "authenticated localhost with PostgreSQL",
                "unauthenticated_denied": True,
                "stale_stage_snapshot_rejected": True,
                "board_change_persisted_with_history": True,
                "roles": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        "PASS authenticated board, stage conflicts, persistence and tenant permissions"
    )


if __name__ == "__main__":
    main()
