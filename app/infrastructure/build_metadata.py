"""The immutable image revision takes precedence over mutable environment metadata."""

import re
from pathlib import Path

BUILD_FILE = Path(__file__).resolve().parents[1] / "_build_sha"


def image_build_sha() -> str | None:
    if not BUILD_FILE.exists():
        return None
    value = BUILD_FILE.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("invalid immutable image revision")
    return value
