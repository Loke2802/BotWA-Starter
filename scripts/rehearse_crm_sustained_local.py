"""Bounded sustained HTTP rehearsal on an independent synthetic PostgreSQL copy."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from time import perf_counter
from typing import Any

from scripts.crm_concurrency_workload import ConcurrentJourney, complete_history
from scripts.crm_volume_recovery import restore_volume
from scripts.rehearse_crm_concurrency_local import validate_source
from scripts.rehearse_crm_journey_local import check_free_port, start, stop
from scripts.verify_crm_journey_local import Journey


class SustainedJourney(ConcurrentJourney):
    """Closed-loop paced waves; latency excludes the intentional pacing interval."""

    def __init__(
        self,
        journey: Journey,
        source: dict[str, Any],
        rounds: int,
        seconds: int,
        checkpoint: Path,
    ) -> None:
        super().__init__(journey, source)
        self.wave_count = 0
        self.duration = seconds
        self.interval = seconds / (rounds + 1)
        self.started = 0.0
        self.checkpoint = checkpoint
        self.idle = Event()

    def wave(self, tasks: list[dict[str, Any]]) -> list[tuple[str, int, Any]]:
        if self.wave_count == 0:
            self.started = perf_counter()
        replies = super().wave(tasks)
        self.wave_count += 1
        self.checkpoint.write_text(
            json.dumps(
                dict(
                    status="running",
                    elapsed_seconds=round(perf_counter() - self.started, 3),
                    waves=self.wave_count,
                    requests=self.requests,
                ),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if self.wave_count == 1 or self.wave_count % 25 == 0:
            print(
                f"SOAK waves={self.wave_count} requests={len(self.requests)} "
                f"elapsed={perf_counter()-self.started:.1f}s",
                flush=True,
            )
        remaining = self.started + self.wave_count * self.interval - perf_counter()
        if remaining > 0:
            self.idle.wait(timeout=remaining)
        return replies


def validate_bounds(rounds: int, seconds: int) -> None:
    if not 20 <= rounds <= 1000 or not 60 <= seconds <= 3600:
        raise ValueError("Use 20..1000 rounds and 60..3600 seconds")
    if seconds / (rounds + 1) > 30:
        raise ValueError("Pacing must stay within 30 seconds per wave")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--database-port", type=int, default=15437)
    parser.add_argument("--server-port", type=int, default=8777)
    parser.add_argument("--rounds", type=int, default=200)
    parser.add_argument("--seconds", type=int, default=900)
    args = parser.parse_args()
    validate_bounds(args.rounds, args.seconds)
    manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    source = json.loads(args.source_report.read_text(encoding="utf-8"))
    validate_source(manifest, source)
    check_free_port(args.server_port)
    output = args.output_dir.resolve() / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True)
    process = None
    journey = None
    workload = None
    proof: dict[str, Any] = dict(status="failed", stage="volume_restore")
    try:
        print(
            "Restoring an independent synthetic database for sustained load", flush=True
        )
        restored, backup = restore_volume(
            args.container, args.database_port, manifest, output / "recovery.json"
        )
        proof["volume_restore"] = backup
        proof["stage"] = "authenticated_sustained_load"
        with (output / "server.log").open("w", encoding="utf-8") as log:
            process = start(
                output / "recovery.json", args.server_port, args.database_port, log
            )
            journey = Journey(f"http://127.0.0.1:{args.server_port}", restored)
            workload = SustainedJourney(
                journey, source, args.rounds, args.seconds, output / "checkpoint.json"
            )
            result = workload.execute(args.rounds, args.database_port)
            elapsed = perf_counter() - workload.started
            assert elapsed >= args.seconds
            proof.update(
                **result,
                stage="restart_persistence",
                duration_seconds=round(elapsed, 3),
                requested_seconds=args.seconds,
                minimum_samples_per_read_kind=args.rounds + 1,
                workload_model="eight HTTP clients per paced closed-loop wave",
                source_report=str(args.source_report),
                manifest=str(output / "recovery.json"),
            )
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
            complete_history(journey, path + "/history", result["history_versions"])
            proof.update(
                status="passed",
                stage="complete",
                server_restart_preserves_concurrent_writes=True,
                finished_at=datetime.now(UTC).isoformat(),
            )
        print(
            "PASS sustained load, all history pages, completed actions and restart",
            flush=True,
        )
    except Exception as exc:
        proof.update(status="failed", error_type=type(exc).__name__)
        if workload:
            proof["requests"] = workload.requests
        raise
    finally:
        (output / "sustained.json").write_text(
            json.dumps(proof, indent=2) + "\n", encoding="utf-8"
        )
        stop(process)
        if journey:
            journey.client.close()
        print("Evidence: " + str(output / "sustained.json"), flush=True)


if __name__ == "__main__":
    main()
