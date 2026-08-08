from threading import Lock


class BusinessCalendarMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._resolutions = 0
        self._open = 0
        self._closed = 0
        self._version_conflicts = 0
        self._validation_errors = 0
        self._active_overrides = 0
        self._external_imports = 0
        self._latency_ms_total = 0

    def record_resolution(self, state: str, latency_ms: int) -> None:
        with self._lock:
            self._resolutions += 1
            self._latency_ms_total += latency_ms
            if state == "open":
                self._open += 1
            else:
                self._closed += 1

    def record_version_conflict(self) -> None:
        with self._lock:
            self._version_conflicts += 1

    def record_validation_error(self) -> None:
        with self._lock:
            self._validation_errors += 1

    def set_active_overrides(self, value: int) -> None:
        with self._lock:
            self._active_overrides = max(0, value)

    def record_external_import(self) -> None:
        with self._lock:
            self._external_imports += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "resolutions": self._resolutions,
                "open": self._open,
                "closed": self._closed,
                "version_conflicts": self._version_conflicts,
                "validation_errors": self._validation_errors,
                "active_overrides": self._active_overrides,
                "external_imports": self._external_imports,
                "latency_ms_total": self._latency_ms_total,
            }
