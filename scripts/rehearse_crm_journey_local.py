"""One command: fresh synthetic PostgreSQL, authenticated journey, restart, evidence.

Requires an existing luri-crm-local-* Docker PostgreSQL bound to localhost.
Creates uniquely named databases. Never deletes databases or starts external jobs.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

import httpx
from scripts.verify_crm_journey_local import Journey

ROOT = Path(__file__).resolve().parents[1]


def check_free_port(port: int) -> None:
    if not 1024 <= port <= 65535:
        raise ValueError("Use an unprivileged local port")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))


def stop(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def start(
    manifest: Path, port: int, database_port: int, log: TextIO
) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "scripts.serve_crm_local",
            "--manifest",
            str(manifest),
            "--port",
            str(port),
            "--database-port",
            str(database_port),
        ],
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 45
        with httpx.Client(timeout=2, follow_redirects=False) as client:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Synthetic server exited; inspect server.log")
                try:
                    response = client.get(f"http://127.0.0.1:{port}/auth/me")
                    if response.status_code == 401:
                        return process
                except httpx.TransportError:
                    pass
                time.sleep(0.2)
        raise TimeoutError("Synthetic server did not become ready in 45 seconds")
    except Exception:
        stop(process)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--database-port", type=int, default=15437)
    parser.add_argument("--server-port", type=int, default=8770)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--contact-count", type=int, default=10000)
    args = parser.parse_args()
    if not args.container.startswith("luri-crm-local-"):
        parser.error("Only an explicitly named disposable local container is accepted")
    if args.contact_count < 2100:
        parser.error("Volume verification requires at least 2100 synthetic contacts")
    check_free_port(args.server_port)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Each run retains independent evidence, including failed runs.
    run_dir = output / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir.mkdir()
    manifest_path = run_dir / "recovery.json"
    report_path = run_dir / "journey.json"
    process: subprocess.Popen[str] | None = None
    journey: Journey | None = None
    failed: dict[str, Any] = {"status": "failed", "stage": "preparation"}
    try:
        print(
            "Preparing independent synthetic PostgreSQL and backup rehearsal",
            flush=True,
        )
        with (run_dir / "preparation.log").open("w", encoding="utf-8") as log:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.rehearse_crm_local",
                    "--container",
                    args.container,
                    "--port",
                    str(args.database_port),
                    "--output",
                    str(manifest_path),
                ],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                check=True,
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        journey = Journey(f"http://127.0.0.1:{args.server_port}", manifest)
        failed["stage"] = "volume_seeding"
        print(f"Seeding {args.contact_count} encrypted synthetic contacts", flush=True)
        journey.seed_search(args.database_port, args.contact_count)
        failed["stage"] = "authenticated_journey"
        with (run_dir / "server.log").open("w", encoding="utf-8") as log:
            process = start(manifest_path, args.server_port, args.database_port, log)
            journey.execute()
            journey.check_search()
            journey.check_database(args.database_port)
            journey.save(report_path)
            stop(process)
            process = None
            print(
                "Restarting the owned local server against the same PostgreSQL",
                flush=True,
            )
            failed["stage"] = "restart_persistence"
            process = start(manifest_path, args.server_port, args.database_port, log)
            journey.client.close()
            journey.client = httpx.Client(
                base_url=journey.base_url, timeout=30, follow_redirects=False
            )
            journey.login()  # New normal login; no dependency or auth overrides.
            journey.check_records()
            journey.check_search()
            journey.check_database(args.database_port)
            journey.passed("server_restart_preserves_sale_actions_history_and_metrics")
            journey.report.update(
                {
                    "status": "passed",
                    "finished_at": datetime.now(UTC).isoformat(),
                    "server_restarted": True,
                    "manifest": str(manifest_path),
                }
            )
            journey.save(report_path)
        print("PASS complete journey. Evidence: " + str(report_path), flush=True)
    except Exception as exc:
        failed["error_type"] = type(exc).__name__
        if journey:
            journey.report.update(failed)
            journey.save(report_path)
        else:
            report_path.write_text(
                json.dumps(failed, indent=2) + "\n", encoding="utf-8"
            )
        print("FAIL evidence retained: " + str(report_path), file=sys.stderr)
        raise
    finally:
        stop(process)
        if journey:
            journey.client.close()


if __name__ == "__main__":
    main()
