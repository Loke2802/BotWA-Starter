import os

import pytest
from app.infrastructure.integrations.google_calendar import GoogleCalendarAdapter

REQUIRED_ENV = (
    "BOTWA_GOOGLE_OAUTH_CLIENT_ID",
    "BOTWA_GOOGLE_OAUTH_CLIENT_SECRET",
    "BOTWA_GOOGLE_OAUTH_REDIRECT_URI",
    "BOTWA_PRD013_GOOGLE_REFRESH_TOKEN",
)

pytestmark = pytest.mark.skipif(
    not all(os.getenv(name) for name in REQUIRED_ENV),
    reason="explicit Google development credentials are required",
)


def test_manual_google_calendar_read_only_health_and_metadata() -> None:
    adapter = GoogleCalendarAdapter(
        client_id=os.environ["BOTWA_GOOGLE_OAUTH_CLIENT_ID"],
        client_secret=os.environ["BOTWA_GOOGLE_OAUTH_CLIENT_SECRET"],
        redirect_uri=os.environ["BOTWA_GOOGLE_OAUTH_REDIRECT_URI"],
        timeout_seconds=10,
    )
    refresh_token = os.environ["BOTWA_PRD013_GOOGLE_REFRESH_TOKEN"]
    adapter.get_health(refresh_token)
    calendars = adapter.list_calendars(refresh_token)
    assert isinstance(calendars, list)
