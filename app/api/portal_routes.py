from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["portal"])

_PORTAL_DIRECTORY = Path(__file__).resolve().parents[1] / "portal"
_INDEX_PATH = _PORTAL_DIRECTORY / "index.html"


@router.get("/portal", include_in_schema=False)
@router.get("/portal/", include_in_schema=False)
def portal() -> FileResponse:
    """Serve the tenant-scoped operations portal shell."""
    return FileResponse(_INDEX_PATH, media_type="text/html")
