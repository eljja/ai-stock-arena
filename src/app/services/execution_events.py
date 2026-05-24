from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import ExecutionEvent

DEFAULT_EXECUTION_EVENT_RETENTION_DAYS = 14
MODEL_MAINTENANCE_EVENT_RETENTION_HOURS = 24


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


def prune_execution_events(
    session: Session,
    *,
    retention_days: int = DEFAULT_EXECUTION_EVENT_RETENTION_DAYS,
    model_maintenance_retention_hours: int = MODEL_MAINTENANCE_EVENT_RETENTION_HOURS,
) -> dict[str, int]:
    now = datetime.now(UTC)
    old_cutoff = now - timedelta(days=retention_days)
    maintenance_cutoff = now - timedelta(hours=model_maintenance_retention_hours)

    latest_model_maintenance_ids = (
        select(func.max(ExecutionEvent.id).label("id"))
        .where(ExecutionEvent.event_type == "model_maintenance")
        .group_by(ExecutionEvent.model_id, ExecutionEvent.message)
        .subquery()
    )
    deleted_duplicate_model_maintenance = (
        session.execute(
            delete(ExecutionEvent)
            .where(ExecutionEvent.event_type == "model_maintenance")
            .where(ExecutionEvent.id.not_in(select(latest_model_maintenance_ids.c.id)))
        ).rowcount
        or 0
    )
    deleted_model_maintenance = (
        session.execute(
            delete(ExecutionEvent)
            .where(ExecutionEvent.event_type == "model_maintenance")
            .where(ExecutionEvent.created_at < maintenance_cutoff)
        ).rowcount
        or 0
    )
    deleted_old = (
        session.execute(
            delete(ExecutionEvent).where(ExecutionEvent.created_at < old_cutoff)
        ).rowcount
        or 0
    )
    session.flush()
    return {
        "duplicate_model_maintenance": deleted_duplicate_model_maintenance,
        "model_maintenance": deleted_model_maintenance,
        "old": deleted_old,
    }
