from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.api.query_service import refresh_rankings_cache
from app.db.models import ExecutionEvent, LLMModel, RunRequest
from app.db.session import SessionLocal
from app.market_data.provider import YahooMarketDataProvider
from app.market_data.screener import MarketScreener
from app.orchestration.trading_cycle import TradingCycleService
from app.services.bootstrap import auto_disable_inactive_models, create_schema, run_weekly_free_model_sync_if_due
from app.services.admin import get_scheduler_status, is_model_api_enabled, update_market_scheduler_state
from app.services.execution_events import create_execution_event
from app.services.market_history import record_market_snapshot
from app.services.run_requests import create_run_request, mark_run_request_finished, mark_run_request_started
from app.services.shared_news import run_due_news_refreshes


RANKINGS_CACHE_REFRESH_MINUTES = 15


class RuntimeSchedulerService:
    def __init__(self) -> None:
        self.provider = YahooMarketDataProvider()
        self.screener = MarketScreener()
        self.trading = TradingCycleService()

    def run_forever(self, poll_seconds: int = 30) -> None:
        create_schema()
        while True:
            self.run_pending_once()
            time.sleep(poll_seconds)

    def run_pending_once(self) -> list[str]:
        create_schema()
        messages: list[str] = []
        messages.extend(self._run_isolated_task("news_refresh", self._run_due_news_refreshes))
        messages.extend(self._run_isolated_task("free_model_sync", self._run_weekly_free_model_sync))
        messages.extend(self._run_isolated_task("inactive_model_cleanup", self._run_inactive_model_cleanup))
        messages.extend(self._run_isolated_task("rankings_cache_refresh", self._refresh_rankings_cache_if_due))
        with SessionLocal() as session:
            status = get_scheduler_status(session)
        due_markets = [item["market_code"] for item in status["markets"] if item["enabled"] and item["is_due"]]
        for market_code in due_markets:
            messages.extend(
                self._run_isolated_task(
                    f"market_cycle_{market_code}",
                    lambda market_code=market_code: [self.run_market_cycle(market_code)],
                )
            )
        return messages

    def _run_isolated_task(self, task_name: str, task: Callable[[], list[str]]) -> list[str]:
        try:
            return task()
        except Exception as exc:
            message = f"{task_name} failed: {exc}"
            try:
                with SessionLocal() as session:
                    create_execution_event(
                        session,
                        event_type="scheduler",
                        target_type="maintenance",
                        trigger_source="scheduler",
                        status="error",
                        code=exc.__class__.__name__,
                        message=message,
                    )
                    session.commit()
            except Exception as log_exc:
                return [f"{message}; failed to record scheduler event: {log_exc}"]
            return [message]

    def _run_due_news_refreshes(self) -> list[str]:
        with SessionLocal() as session:
            messages = run_due_news_refreshes(session)
            session.commit()
            return messages

    def _run_weekly_free_model_sync(self) -> list[str]:
        with SessionLocal() as session:
            messages = run_weekly_free_model_sync_if_due(session)
            session.commit()
            return messages

    def _run_inactive_model_cleanup(self) -> list[str]:
        with SessionLocal() as session:
            messages = auto_disable_inactive_models(session)
            session.commit()
            return messages

    def _refresh_rankings_cache_if_due(self) -> list[str]:
        with SessionLocal() as session:
            latest = session.scalar(
                select(ExecutionEvent.created_at)
                .where(ExecutionEvent.event_type == "scheduler")
                .where(ExecutionEvent.target_type == "maintenance")
                .where(ExecutionEvent.code == "RANKINGS_CACHE")
                .where(ExecutionEvent.status == "success")
                .order_by(ExecutionEvent.created_at.desc())
                .limit(1)
            )
            threshold = datetime.now(UTC) - timedelta(minutes=RANKINGS_CACHE_REFRESH_MINUTES)
            if latest is not None and latest > threshold:
                return []
            refresh_rankings_cache(session)
            create_execution_event(
                session,
                event_type="scheduler",
                target_type="maintenance",
                trigger_source="scheduler",
                status="success",
                code="RANKINGS_CACHE",
                message="Refreshed rankings cache.",
            )
            session.commit()
            return ["Refreshed rankings cache."]

    def run_market_cycle(self, market_code: str, *, trigger_source: str = "scheduler") -> str:
        started_at = datetime.now(UTC)
        run_label = "manual" if trigger_source == "manual_admin" else "scheduled"
        with SessionLocal() as session:
            update_market_scheduler_state(
                session,
                market_code,
                last_started_at=started_at,
                last_status="running",
                last_message=f"Started {run_label} run for {market_code}.",
            )
            session.commit()

        try:
            snapshot = self.provider.fetch_market_snapshot(market_code)
            with SessionLocal() as session:
                record_market_snapshot(session, snapshot)
                session.commit()
            candidates = self.screener.screen(snapshot)
            if not candidates:
                raise RuntimeError(f"No screened candidates for {market_code}.")
        except Exception as exc:
            with SessionLocal() as session:
                update_market_scheduler_state(
                    session,
                    market_code,
                    last_completed_at=datetime.now(UTC),
                    last_status="error",
                    last_message=str(exc),
                )
                session.commit()
            raise

        with SessionLocal() as session:
            selected_models = list(
                session.scalars(
                    select(LLMModel).where(LLMModel.is_selected.is_(True)).order_by(LLMModel.model_id.asc())
                ).all()
            )
            selected_model_ids = [model.model_id for model in selected_models if is_model_api_enabled(model)]
        if not selected_model_ids:
            with SessionLocal() as session:
                update_market_scheduler_state(
                    session,
                    market_code,
                    last_completed_at=datetime.now(UTC),
                    last_status="skipped",
                    last_message="No selected models available for scheduled run.",
                )
                session.commit()
            return f"{market_code}: skipped, no selected models."

        success_count = 0
        error_count = 0
        for model_id in selected_model_ids:
            with SessionLocal() as session:
                run = create_run_request(
                    session,
                    model_id=model_id,
                    market_code=market_code,
                    trigger_source=trigger_source,
                    candidate_count=len(candidates),
                    snapshot_as_of=snapshot.as_of,
                    summary_message=f"Queued {run_label} run for {model_id} / {market_code}.",
                )
                session.commit()
                run_id = run.id

            try:
                with SessionLocal() as session:
                    run = session.get(RunRequest, run_id)
                    if run is not None:
                        mark_run_request_started(session, run, message=f"Running {run_label} cycle for {model_id} / {market_code}.")
                    decision, prompt_text = self.trading.request_decision(
                        session,
                        model_id=model_id,
                        market_code=market_code,
                        snapshot=snapshot,
                        candidates=candidates,
                    )
                    messages = self.trading.execute_decision(
                        session,
                        model_id=model_id,
                        market_code=market_code,
                        decision=decision,
                        snapshot=snapshot,
                        prompt_text=prompt_text,
                    )
                    summary = f"{run_label.capitalize()} run finished for {model_id} / {market_code}: {len(messages)} actions executed."
                    if run is not None:
                        mark_run_request_finished(session, run, status="success", message=summary)
                    create_execution_event(session, event_type="trade", target_type="model", model_id=model_id, market_code=market_code, trigger_source=trigger_source, status="success", message=summary)
                    session.commit()
                success_count += 1
            except Exception as exc:
                with SessionLocal() as session:
                    run = session.get(RunRequest, run_id)
                    if run is not None:
                        mark_run_request_finished(
                            session,
                            run,
                            status="error",
                            message=f"{run_label.capitalize()} run failed for {model_id} / {market_code}.",
                            error_message=str(exc),
                        )
                    create_execution_event(session, event_type="trade", target_type="model", model_id=model_id, market_code=market_code, trigger_source=trigger_source, status="error", code=exc.__class__.__name__, message=str(exc))
                    session.commit()
                error_count += 1

        final_status = "success" if error_count == 0 else "partial" if success_count > 0 else "error"
        message = (
            f"{run_label.capitalize()} run finished for {market_code}: "
            f"{success_count} succeeded, {error_count} failed, {len(candidates)} candidates screened."
        )
        with SessionLocal() as session:
            update_market_scheduler_state(
                session,
                market_code,
                last_completed_at=datetime.now(UTC),
                last_status=final_status,
                last_message=message,
            )
            refresh_rankings_cache(session)
            session.commit()
        return message
