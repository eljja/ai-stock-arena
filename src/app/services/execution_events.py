from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import ExecutionEvent


def create_execution_event(
    session: Session,
    *,
    event_type: str,
    target_type: str,
    status: str,
    model_id: str | None = None,
    market_code: str | None = None,
    trigger_source: str | None = None,
    code: str | None = None,
    message: str | None = None,
) -> ExecutionEvent:
    event = ExecutionEvent(
        event_type=event_type,
        target_type=target_type,
        status=status,
        model_id=model_id,
        market_code=market_code,
        trigger_source=trigger_source,
        code=code,
        message=message,
    )
    session.add(event)
    session.flush()
    return event
