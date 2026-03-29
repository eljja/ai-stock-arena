from __future__ import annotations

import time
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import LLMModel, RunRequest
from app.db.session import SessionLocal
from app.market_data.provider import YahooMarketDataProvider
from app.market_data.screener import MarketScreener
from app.orchestration.trading_cycle import TradingCycleService
from app.services.admin import get_scheduler_status, is_model_api_enabled, update_market_scheduler_state
from app.services.bootstrap import create_schema
from app.services.market_history import record_market_snapshot
from app.services.run_requests import create_run_request, mark_run_request_finished, mark_run_request_started


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
        with SessionLocal() as session:
            status = get_scheduler_status(session)
        due_markets = [item["market_code"] for item in status["markets"] if item["enabled"] and item["is_due"]]
        messages: list[str] = []
        for market_code in due_markets:
            messages.append(self.run_market_cycle(market_code))
        return messages

    def run_market_cycle(self, market_code: str) -> str:
        started_at = datetime.now(UTC)
        with SessionLocal() as session:
            update_market_scheduler_state(
                session,
                market_code,
                last_started_at=started_at,
                last_status="running",
                last_message=f"Started scheduled run for {market_code}.",
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
                    trigger_source="scheduler",
                    candidate_count=len(candidates),
                    snapshot_as_of=snapshot.as_of,
                    summary_message=f"Queued scheduler run for {model_id} / {market_code}.",
                )
                session.commit()
                run_id = run.id

            try:
                with SessionLocal() as session:
                    run = session.get(RunRequest, run_id)
                    if run is not None:
                        mark_run_request_started(session, run, message=f"Running scheduler cycle for {model_id} / {market_code}.")
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
                    summary = f"Scheduler run finished for {model_id} / {market_code}: {len(messages)} actions executed."
                    if run is not None:
                        mark_run_request_finished(session, run, status="success", message=summary)
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
                            message=f"Scheduler run failed for {model_id} / {market_code}.",
                            error_message=str(exc),
                        )
                    session.commit()
                error_count += 1

        final_status = "success" if error_count == 0 else "partial" if success_count > 0 else "error"
        message = (
            f"Scheduled run finished for {market_code}: "
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
            session.commit()
        return message


