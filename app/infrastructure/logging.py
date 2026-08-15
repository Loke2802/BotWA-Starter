import logging
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import structlog


class SensitiveQueryParameterFilter(logging.Filter):
    _sensitive_parameters = frozenset(
        {
            "hub.verify_token",
            "code",
            "state",
            "access_token",
            "token",
            "secret",
        }
    )

    def filter(self, record: logging.LogRecord) -> bool:
        if not isinstance(record.args, tuple) or len(record.args) < 3:
            return True

        path = record.args[2]
        if not isinstance(path, str) or "?" not in path:
            return True

        parsed = urlsplit(path)
        query = [
            (
                key,
                "[REDACTED]" if key.lower() in self._sensitive_parameters else value,
            )
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        ]
        redacted_path = urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(query),
                parsed.fragment,
            )
        )
        args = list(record.args)
        args[2] = redacted_path
        record.args = tuple(args)
        return True


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        format="%(message)s",
        level=log_level.upper(),
        stream=sys.stdout,
    )
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.disabled = True
    if not any(
        isinstance(log_filter, SensitiveQueryParameterFilter)
        for log_filter in access_logger.filters
    ):
        access_logger.addFilter(SensitiveQueryParameterFilter())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level.upper())
        ),
        cache_logger_on_first_use=True,
    )
