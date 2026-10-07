"""Reject ambiguous recovery targets before any dump or database creation."""

import json
from pathlib import Path

import pytest
from scripts import crm_volume_recovery as recovery

from tests.test_crm_journey_runner import manifest


@pytest.mark.parametrize("target", ["database", "container"])
def test_recovery_rejects_real_targets_before_calling_docker(
    target: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = manifest()
    container = "luri-crm-local-recovery"
    if target == "database":
        data["databases"]["after"] = "real_customers"
    else:
        container = "production-postgres"

    def forbidden(*args: object, **kwargs: object) -> str:
        pytest.fail("Recovery must reject this target before interacting with Docker")

    monkeypatch.setattr(
        "scripts.crm_volume_recovery.subprocess.check_output", forbidden
    )
    with pytest.raises(ValueError):
        recovery.restore_volume(container, 15437, data, tmp_path / "proof.json")
    assert not (tmp_path / "proof.json").exists()


@pytest.mark.parametrize(
    "ip,port,extra_public",
    [
        ("0.0.0.0", "15437", False),
        ("127.0.0.1", "5432", False),
        ("127.0.0.1", "15437", True),
    ],
)
def test_recovery_rejects_public_or_wrong_database_port(
    ip: str,
    port: str,
    extra_public: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def inspect_only(args: list[str], **kwargs: object) -> str:
        calls.append(args)
        assert args == ["docker", "inspect", "luri-crm-local-recovery"]
        bindings = [{"HostIp": ip, "HostPort": port}]
        if extra_public:
            bindings.append({"HostIp": "0.0.0.0", "HostPort": "15437"})
        return json.dumps([{"NetworkSettings": {"Ports": {"5432/tcp": bindings}}}])

    monkeypatch.setattr(
        "scripts.crm_volume_recovery.subprocess.check_output", inspect_only
    )
    with pytest.raises(ValueError, match="localhost port"):
        recovery.restore_volume(
            "luri-crm-local-recovery", 15437, manifest(), tmp_path / "proof.json"
        )
    assert len(calls) == 1 and not (tmp_path / "proof.json").exists()
