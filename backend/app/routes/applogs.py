from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from ..logger import format_github_issue, get_records

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/")
def list_logs(level: str | None = None, limit: int = 200):
    return get_records(level=level, limit=limit)


@router.get("/github-issue", response_class=PlainTextResponse)
def github_issue_export(level: str = "ERROR", limit: int = 100):
    records = get_records(level=level, limit=limit)
    return format_github_issue(records)
