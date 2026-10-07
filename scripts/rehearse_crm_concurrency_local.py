"""Guarded local load rehearsal; restores its own database and owns its server."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.crm_concurrency_workload import ConcurrentJourney
from scripts.crm_volume_recovery import restore_volume
from scripts.rehearse_crm_journey_local import check_free_port, start, stop
from scripts.verify_crm_journey_local import Journey, validate_target


def validate_source(manifest: dict[str, Any], report: dict[str, Any]) -> None:
    validate_target("http://127.0.0.1:8770", manifest)
    if (
        report.get("status") != "passed"
        or report.get("organization_id") != manifest["organization_id"]
    ):
        raise ValueError("A matching passed synthetic journey is required")
    if report.get("search_dataset", {}).get("count", 0) < 10000 or not report.get(
        "index_rebuild"
    ):
        raise ValueError(
            "An indexed journey with at least 10000 synthetic contacts is required"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--database-port", type=int, default=15437)
    parser.add_argument("--server-port", type=int, default=8775)
    parser.add_argument("--rounds", type=int, default=6)
    args = parser.parse_args()
    if not 1 <= args.rounds <= 20:
        parser.error("Use between 1 and 20 bounded rounds")
    manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    source = json.loads(args.source_report.read_text(encoding="utf-8"))
    validate_source(manifest, source)
    check_free_port(args.server_port)
    output = args.output_dir.resolve() / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True)
    process = None
    journey = None
    proof: dict[str, Any] = {"status": "failed", "stage": "volume_restore"}
    try:
        print(
            "Restoring a separate synthetic database for eight concurrent sessions",
            flush=True,
        )
        restored, backup = restore_volume(
            args.container, args.database_port, manifest, output / "recovery.json"
        )
        proof["volume_restore"] = backup
        proof["stage"] = "authenticated_concurrency"
        with (output / "server.log").open("w", encoding="utf-8") as log:
            process = start(
                output / "recovery.json", args.server_port, args.database_port, log
            )
            journey = Journey(f"http://127.0.0.1:{args.server_port}", restored)
            journey.report["search_dataset"] = source["search_dataset"]
            journey.login()
            print(
                "Rebuilding protected indexes with bounded multi-row writes", flush=True
            )
            journey.rebuild_search_index(args.database_port)
            proof["index_rebuild"] = journey.report["index_rebuild"]
            result = ConcurrentJourney(journey, source).execute(
                args.rounds, args.database_port
            )
            proof = {
                **result,
                "volume_restore": backup,
                "index_rebuild": journey.report["index_rebuild"],
                "manifest": str(output / "recovery.json"),
                "finished_at": datetime.now(UTC).isoformat(),
            }
            stop(process)
            process = start(
                output / "recovery.json", args.server_port, args.database_port, log
            )
            journey.login()
            path = (
                f"/organizations/{restored['organization_id']}/crm/opportunities/"
                + result["opportunity_id"]
            )
            assert journey.request("GET", path) == result["final_record"]
            assert (
                len(journey.request("GET", path + "/history"))
                == result["history_versions"]
            )
            proof["server_restart_preserves_concurrent_writes"] = True
        print(
            "PASS concurrent sessions, versions, actions and tenant isolation",
            flush=True,
        )
    except Exception as exc:
        proof.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        (output / "concurrency.json").write_text(
            json.dumps(proof, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        stop(process)
        if journey:
            journey.client.close()
        print("Evidence: " + str(output / "concurrency.json"), flush=True)


if __name__ == "__main__":
    main()
