"""Long rehearsals must verify every history page and reject unbounded work."""

from typing import Any, cast

import pytest
from scripts.crm_concurrency_workload import complete_history
from scripts.rehearse_crm_sustained_local import validate_bounds
from scripts.verify_crm_journey_local import Journey


class HistoryApi:
    def __init__(self, versions: int, duplicate: bool = False) -> None:
        self.versions = versions
        self.duplicate = duplicate
        self.paths: list[str] = []

    def request(self, method: str, path: str) -> list[dict[str, Any]]:
        self.paths.append(path)
        page = int(path.split("page=")[1].split("&")[0])
        result = [
            dict(version=i)
            for i in range(
                max(1, self.versions - page * 100 + 1),
                self.versions - (page - 1) * 100 + 1,
            )
        ]
        if self.duplicate and page == 3:
            result = [dict(version=201)]
        return result


def test_long_history_reads_every_page() -> None:
    api = HistoryApi(201)
    result = complete_history(cast(Journey, api), "/history", 201)
    assert len(result) == 201 and len(api.paths) == 3
    assert all("page_size=100" in path for path in api.paths)


def test_long_history_rejects_duplicate_version() -> None:
    with pytest.raises(AssertionError):
        complete_history(cast(Journey, HistoryApi(201, True)), "/history", 201)


@pytest.mark.parametrize(
    "rounds,seconds", [(0, 900), (1001, 900), (200, 59), (200, 3601), (20, 3600)]
)
def test_sustained_bounds(rounds: int, seconds: int) -> None:
    with pytest.raises(ValueError):
        validate_bounds(rounds, seconds)
