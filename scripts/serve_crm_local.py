"""Serve the restored synthetic CRM demo on localhost, without auth overrides."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
from pathlib import Path

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--database-port", type=int, default=15437)
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    database = data["databases"]["after"]
    if data["environment"] != "disposable local PostgreSQL" or not re.fullmatch(
        r"luri_rehearsal_[0-9a-f]{10}_after", database
    ):
        parser.error("Only a synthetic local rehearsal manifest is accepted")
    os.environ.update(
        {
            "BOTWA_ENVIRONMENT": "test",
            "BOTWA_USE_DATABASE": "true",
            "BOTWA_AI_ENABLED": "false",
            "BOTWA_DATABASE_URL": (
                f"postgresql+psycopg://botwa:crm_local_test@127.0.0.1:"
                f"{args.database_port}/{database}?connect_timeout=5"
            ),
            "BOTWA_WHATSAPP_SECRET_ENCRYPTION_KEY": base64.urlsafe_b64encode(
                b"o" * 32
            ).decode(),
            "BOTWA_CONTACT_IDENTITY_HMAC_KEY": (
                "opportunity-test-key-at-least-thirty-two-characters"
            ),
        }
    )
    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
