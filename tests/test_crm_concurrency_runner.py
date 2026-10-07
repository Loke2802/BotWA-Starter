"""A load rehearsal must reject false wins and mismatched synthetic evidence."""

import pytest
from scripts.crm_concurrency_workload import edit_winner
from scripts.rehearse_crm_concurrency_local import validate_source

from tests.test_crm_journey_runner import manifest


@pytest.mark.parametrize("statuses", [[200, 200], [409, 409], [200, 500]])
def test_conflicting_edits_require_one_winner(statuses: list[int]) -> None:
    with pytest.raises(AssertionError, match="exactly one winner"):
        edit_winner(
            [
                (f"edit_{i}", status, {"version": 2})
                for i, status in enumerate(statuses)
            ],
            2,
        )


def test_winning_edit_must_persist_the_next_version() -> None:
    with pytest.raises(AssertionError, match="version"):
        edit_winner(
            [("edit_owner", 200, {"version": 1}), ("edit_operator", 409, {})], 2
        )


@pytest.mark.parametrize("change", ["status", "company", "volume", "index"])
def test_source_evidence_must_be_complete_and_match_company(change: str) -> None:
    m = manifest()
    report = {
        "status": "passed",
        "organization_id": m["organization_id"],
        "search_dataset": {"count": 10000},
        "index_rebuild": {"contacts": 10003},
    }
    if change == "status":
        report["status"] = "failed"
    elif change == "company":
        report["organization_id"] = m["other_organization_id"]
    elif change == "volume":
        report["search_dataset"] = {"count": 100}
    else:
        report["index_rebuild"] = {}
    with pytest.raises(ValueError):
        validate_source(m, report)
