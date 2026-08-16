"""Smoke a PRD-023 application image without exposing runtime secrets."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import cast
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        capture_output=capture,
        text=True,
    )


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=2) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, dict):
        raise ValueError("container endpoint did not return a JSON object")
    return cast(dict[str, object], payload)


def _wait_for(url: str, timeout_seconds: float = 90) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            return _json(url)
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            time.sleep(0.5)
    raise RuntimeError(f"container endpoint did not become ready: {url}")


def smoke(image: str, build_sha: str, database_url: str) -> None:
    name = f"botwa-prd023-{uuid4().hex[:12]}"
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    try:
        _run(
            "docker",
            "run",
            "--detach",
            "--name",
            name,
            "--add-host",
            "host.docker.internal:host-gateway",
            "--publish",
            f"127.0.0.1:{port}:8000",
            "--env",
            "BOTWA_ENVIRONMENT=test",
            "--env",
            "BOTWA_USE_DATABASE=true",
            "--env",
            f"BOTWA_DATABASE_URL={database_url}",
            image,
        )
        live = _wait_for(f"{base_url}/health/live")
        ready = _wait_for(f"{base_url}/health/ready")
        version = _wait_for(f"{base_url}/version")
        if live != {"status": "alive"}:
            raise RuntimeError("unexpected liveness response")
        if ready != {"status": "ready"}:
            raise RuntimeError("unexpected readiness response")
        if version.get("build_sha") != build_sha:
            raise RuntimeError("container build SHA does not match")
        uid = _run("docker", "exec", name, "id", "-u", capture=True).stdout.strip()
        if uid != "10001":
            raise RuntimeError(f"container runs with unexpected uid {uid}")
        _run("docker", "stop", "--timeout", "10", name)
        exit_code = _run(
            "docker",
            "inspect",
            "--format={{.State.ExitCode}}",
            name,
            capture=True,
        ).stdout.strip()
        if exit_code != "0":
            raise RuntimeError(f"SIGTERM shutdown returned exit code {exit_code}")
    finally:
        subprocess.run(
            ["docker", "rm", "--force", name],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--build-sha", required=True)
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    smoke(args.image, args.build_sha, args.database_url)
    print("container smoke passed")


if __name__ == "__main__":
    main()
