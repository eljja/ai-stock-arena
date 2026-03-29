from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import RunRequest


def create_run_request(
    session: Session,
    *,
    model_id: str,
    market_code: str,
    trigger_source: str,
    candidate_count: int | None = None,
    snapshot_as_of: datetime | None = None,
    summary_message: str | None = None,
) -> RunRequest:
    run = RunRequest(
        model_id=model_id,
        market_code=market_code,
        trigger_source=trigger_source,
        status="queued",
        candidate_count=candidate_count,
        snapshot_as_of=snapshot_as_of,
        summary_message=summary_message,
    )
    session.add(run)
    session.flush()
    return run


def mark_run_request_started(session: Session, run: RunRequest, message: str | None = None) -> RunRequest:
    run.status = "running"
    run.started_at = datetime.now(UTC)
    if message:
        run.summary_message = message
    session.flush()
    return run


def mark_run_request_finished(
    session: Session,
    run: RunRequest,
    *,
    status: str,
    message: str | None = None,
    error_message: str | None = None,
) -> RunRequest:
    run.status = status
    run.completed_at = datetime.now(UTC)
    run.summary_message = message
    run.error_message = error_message
    session.flush()
    return run
