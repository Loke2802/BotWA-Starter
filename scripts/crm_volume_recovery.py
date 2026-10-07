"""Full-table backup/restore proof for a guarded synthetic local CRM database."""

import json
import re
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

from scripts.crm_recovery_fingerprint import fingerprint
from scripts.verify_crm_journey_local import validate_target
from sqlalchemy import create_engine


def restore_volume(
    container: str, port: int, manifest: dict[str, Any], output: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_target("http://127.0.0.1:8770", manifest)
    if not container.startswith("luri-crm-local-"):
        raise ValueError("An explicitly named synthetic local container is required")
    info = json.loads(
        subprocess.check_output(["docker", "inspect", container], text=True)
    )[0]
    bindings = info["NetworkSettings"]["Ports"].get("5432/tcp") or []
    if not bindings or any(
        b["HostIp"] != "127.0.0.1" or int(b["HostPort"]) != port for b in bindings
    ):
        raise ValueError("PostgreSQL must be bound to the explicit localhost port")
    source = manifest["databases"]["after"]
    target = "luri_rehearsal_" + uuid4().hex[:10] + "_after"
    dump = "/tmp/" + target + "_volume.dump"

    def docker(*args: str) -> str:
        return subprocess.check_output(["docker", "exec", container, *args], text=True)

    def fingerprints(database: str) -> dict[str, str]:
        engine = create_engine(
            f"postgresql+psycopg://botwa:crm_local_test@127.0.0.1:{port}/{database}?connect_timeout=15"
        )
        try:
            return fingerprint(engine)
        finally:
            engine.dispose()

    before = fingerprints(source)
    docker("pg_dump", "-U", "botwa", "-Fc", "-f", dump, source)
    digest = docker("sha256sum", dump).split()[0]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise RuntimeError("Backup digest could not be verified")
    # Only the newly created database can receive pg_restore; no --clean or drops.
    docker("createdb", "-U", "botwa", target)
    docker("pg_restore", "-U", "botwa", "--exit-on-error", "--dbname", target, dump)
    # Dumps omit optimizer statistics. Refresh them before checking query behavior.
    docker("vacuumdb", "-U", "botwa", "--analyze-only", "--dbname", target)
    after = fingerprints(target)
    if before != after or fingerprints(source) != before:
        raise AssertionError("Volume restore differs from source or source changed")
    proof = {
        "source_database": source,
        "restored_database": target,
        "backup_in_local_container": dump,
        "backup_sha256": digest,
        "all_tables_equal": True,
        "source_unchanged": True,
        "optimizer_statistics_refreshed": True,
        "table_count": len(before),
        "fingerprints_source": before,
        "fingerprints_restored": after,
    }
    restored = {
        **manifest,
        "databases": {**manifest["databases"], "after": target},
        "volume_restore": proof,
    }
    output.write_text(json.dumps(restored, indent=2) + "\n", encoding="utf-8")
    return restored, proof
