from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.loader import load_runtime_config, load_settings, parse_default_model_ids
from app.db.base import Base
from app.db.models import AdminSetting, LLMDecisionLog, LLMModel, MarketSetting, ModelMarketPrompt, Portfolio, RunRequest
from app.db.session import engine
from app.llm.openrouter import OpenRouterClient, OpenRouterModel
from app.services.admin import create_or_update_model_profile, get_runtime_settings, is_model_api_enabled
from app.services.db_maintenance import ensure_operational_indexes
from app.services.execution_events import create_execution_event

FREE_MODEL_SYNC_STATE_KEY = "free_model_sync_state"
INACTIVE_MODEL_DAYS = 5

MARKET_LABELS = {
    "KR": "Korea Equity Market",
    "US": "United States Equity Market",
}


@dataclass(slots=True)
class BootstrapSummary:
    synced_models: int
    selected_models: int
    market_settings_upserted: int
    portfolios_created: int
    prompt_placeholders_created: int


@dataclass(slots=True)
class ModelProbeResult:
    model_id: str
    success: bool
    detail: str


def create_schema() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_operational_indexes(engine)


def bootstrap_database(session: Session, sync_openrouter_models: bool = True) -> BootstrapSummary:
    runtime_config = load_runtime_config()
    settings = load_settings()
    selected_model_ids = set(parse_default_model_ids(settings))
    get_runtime_settings(session)

    synced_models = 0
    if sync_openrouter_models:
        synced_models = sync_models_from_openrouter(session, selected_model_ids)

    market_settings_upserted = upsert_market_settings(session, runtime_config.app.max_positions_per_market)
    session.flush()
    portfolios_created, prompt_placeholders_created = initialize_selected_model_state(session)
    selected_models = count_selected_models(session)

    session.commit()
    return BootstrapSummary(
        synced_models=synced_models,
        selected_models=selected_models,
        market_settings_upserted=market_settings_upserted,
        portfolios_created=portfolios_created,
        prompt_placeholders_created=prompt_placeholders_created,
    )


def sync_models_from_openrouter(session: Session, selected_model_ids: set[str]) -> int:
    client = OpenRouterClient()
    synced = 0
    for external_model in client.list_models():
        upsert_openrouter_model(session, external_model, selected_model_ids)
        synced += 1
    return synced


def probe_and_select_free_models(
    session: Session,
    target_count: int = 10,
    candidate_limit: int = 30,
    sort_by: str = "popular",
) -> list[ModelProbeResult]:
    client = OpenRouterClient()
    raw_catalog = client.catalog(sort_by=sort_by, free_mode="only")
    deduped_catalog: list[OpenRouterModel] = []
    seen_model_ids: set[str] = set()
    for model in raw_catalog:
        if model.model_id in seen_model_ids:
            continue
        deduped_catalog.append(model)
        seen_model_ids.add(model.model_id)
    catalog = deduped_catalog[:candidate_limit]

    free_model_ids = {model.model_id for model in catalog}
    for existing in session.scalars(select(LLMModel).where(LLMModel.model_id.in_(free_model_ids))).all():
        existing.is_selected = False

    results: list[ModelProbeResult] = []
    selected_count = 0
    for external_model in catalog:
        record = upsert_openrouter_model(session, external_model, selected_model_ids=set())
        success, detail = client.probe_model(external_model.model_id)
        record.is_available = success
        record.metadata_json = {
            **(record.metadata_json or {}),
            "probe": {"success": success, "detail": detail},
            "probe_detail": detail,
            "is_free_like": external_model.is_free_like,
        }
        if success and selected_count < target_count:
            record.is_selected = True
            selected_count += 1
        else:
            record.is_selected = False
        results.append(ModelProbeResult(record.model_id, success, detail))

    session.flush()
    initialize_selected_model_state(session)
    session.commit()
    return results


def probe_and_add_free_models(
    session: Session,
    additional_count: int = 10,
    candidate_limit: int = 40,
    sort_by: str = "popular",
) -> list[ModelProbeResult]:
    return _probe_and_add_candidate_models(
        session,
        additional_count=additional_count,
        candidate_limit=candidate_limit,
        sort_by=sort_by,
    )


def probe_and_add_all_free_models(
    session: Session,
    candidate_limit: int = 250,
    sort_by: str = "popular",
) -> list[ModelProbeResult]:
    return _probe_and_add_candidate_models(
        session,
        additional_count=None,
        candidate_limit=candidate_limit,
        sort_by=sort_by,
    )


def _probe_and_add_candidate_models(
    session: Session,
    additional_count: int | None,
    candidate_limit: int,
    sort_by: str,
) -> list[ModelProbeResult]:
    client = OpenRouterClient()
    raw_catalog = client.catalog(sort_by=sort_by, free_mode="only")
    deduped_catalog: list[OpenRouterModel] = []
    seen_model_ids: set[str] = set()
    for model in raw_catalog:
        if model.model_id in seen_model_ids:
            continue
        deduped_catalog.append(model)
        seen_model_ids.add(model.model_id)

    selected_model_ids = {
        model.model_id
        for model in session.scalars(select(LLMModel).where(LLMModel.is_selected.is_(True))).all()
    }

    catalog = [model for model in deduped_catalog if model.model_id not in selected_model_ids][:candidate_limit]

    results: list[ModelProbeResult] = []
    added_count = 0
    for external_model in catalog:
        success, detail = client.probe_model(external_model.model_id)
        if not success:
            existing = session.scalar(select(LLMModel).where(LLMModel.model_id == external_model.model_id))
            if existing is not None:
                existing.is_available = False
                metadata = existing.metadata_json or {}
                metadata.update({"probe": {"success": success, "detail": detail}, "probe_detail": detail})
                existing.metadata_json = metadata
            results.append(ModelProbeResult(external_model.model_id, success, detail))
            continue

        create_or_update_model_profile(
            session,
            profile_id=external_model.model_id,
            request_model_id=external_model.model_id,
            display_name=external_model.display_name,
            provider="openrouter",
            search_mode="off",
            select_profile=True,
            prompt_price_per_million=external_model.prompt_price_per_million,
            completion_price_per_million=external_model.completion_price_per_million,
            context_length=external_model.context_length,
            api_enabled=True,
        )
        model_record = session.scalar(select(LLMModel).where(LLMModel.model_id == external_model.model_id))
        if model_record is not None:
            metadata = model_record.metadata_json or {}
            metadata.update({
                "probe": {"success": success, "detail": detail},
                "probe_detail": detail,
                "is_free_like": external_model.is_free_like,
                "pricing_label": external_model.pricing_label,
                "status_note": metadata.get("status_note") if not metadata.get("auto_disabled_inactive") else None,
            })
            metadata.pop("auto_disabled_inactive", None)
            metadata.pop("inactive_since", None)
            model_record.metadata_json = metadata
            model_record.is_available = True
            model_record.is_selected = True
        results.append(ModelProbeResult(external_model.model_id, success, detail))
        added_count += 1
        if additional_count is not None and added_count >= additional_count:
            break

    session.flush()
    initialize_selected_model_state(session)
    session.commit()
    return results


def upsert_openrouter_model(
    session: Session,
    external_model: OpenRouterModel,
    selected_model_ids: set[str],
) -> LLMModel:
    existing = session.scalar(select(LLMModel).where(LLMModel.model_id == external_model.model_id))
    if existing is None:
        existing = LLMModel(
            provider="openrouter",
            model_id=external_model.model_id,
            display_name=external_model.display_name,
        )
        session.add(existing)
    existing.display_name = external_model.display_name
    existing.context_length = external_model.context_length
    existing.prompt_price_per_million = external_model.prompt_price_per_million
    existing.completion_price_per_million = external_model.completion_price_per_million
    previous_metadata = existing.metadata_json or {}
    existing.metadata_json = {
        **previous_metadata,
        **external_model.metadata_json,
        "request_model_id": external_model.model_id,
        "base_model_id": external_model.model_id.replace(":online", ""),
        "search_mode": previous_metadata.get("search_mode", "off"),
        "is_free_like": external_model.is_free_like,
        "pricing_label": external_model.pricing_label,
        "probe_detail": previous_metadata.get("probe_detail"),
    }
    existing.is_available = True
    existing.is_selected = (
        external_model.model_id in selected_model_ids if selected_model_ids else existing.is_selected
    )
    return existing


def upsert_market_settings(session: Session, max_positions: int) -> int:
    runtime_config = load_runtime_config()
    configured_market_codes = set(runtime_config.markets.keys())

    for existing in session.scalars(select(MarketSetting)).all():
        if existing.market_code not in configured_market_codes:
            existing.enabled = False

    upserted = 0
    for market_code, market_config in runtime_config.markets.items():
        existing = session.scalar(select(MarketSetting).where(MarketSetting.market_code == market_code))
        if existing is None:
            existing = MarketSetting(
                market_code=market_code,
                market_name=MARKET_LABELS.get(market_code, market_code),
                currency=market_config.currency,
                initial_cash=market_config.initial_cash,
            )
            session.add(existing)
        existing.market_name = MARKET_LABELS.get(market_code, market_code)
        existing.currency = market_config.currency
        existing.enabled = market_config.enabled
        existing.initial_cash = market_config.initial_cash
        existing.buy_commission_rate = market_config.buy_commission_rate
        existing.sell_commission_rate = market_config.sell_commission_rate
        existing.sell_tax_rate = market_config.sell_tax_rate
        existing.sell_regulatory_fee_rate = market_config.sell_regulatory_fee_rate
        existing.max_positions = max_positions
        upserted += 1
    return upserted


def initialize_selected_model_state(session: Session) -> tuple[int, int]:
    market_settings = session.scalars(select(MarketSetting).where(MarketSetting.enabled.is_(True))).all()
    selected_models = session.scalars(select(LLMModel).where(LLMModel.is_selected.is_(True))).all()

    portfolios_created = 0
    prompt_placeholders_created = 0
    for model in selected_models:
        for market_setting in market_settings:
            portfolio = session.scalar(
                select(Portfolio).where(
                    Portfolio.model_id == model.model_id,
                    Portfolio.market_code == market_setting.market_code,
                )
            )
            if portfolio is None:
                session.add(
                    Portfolio(
                        model_id=model.model_id,
                        market_code=market_setting.market_code,
                        currency=market_setting.currency,
                        initial_cash=market_setting.initial_cash,
                        available_cash=market_setting.initial_cash,
                        invested_value=0.0,
                        total_equity=market_setting.initial_cash,
                        total_realized_pnl=0.0,
                        total_unrealized_pnl=0.0,
                    )
                )
                portfolios_created += 1

            prompt = session.scalar(
                select(ModelMarketPrompt).where(
                    ModelMarketPrompt.model_id == model.model_id,
                    ModelMarketPrompt.market_code == market_setting.market_code,
                    ModelMarketPrompt.version == 1,
                )
            )
            if prompt is None:
                session.add(
                    ModelMarketPrompt(
                        model_id=model.model_id,
                        market_code=market_setting.market_code,
                        version=1,
                        prompt_content="PENDING_GENERATION",
                        source_meta_prompt=_default_meta_prompt(market_setting.market_code),
                        is_active=True,
                    )
                )
                prompt_placeholders_created += 1

    return portfolios_created, prompt_placeholders_created


def count_selected_models(session: Session) -> int:
    return len(session.scalars(select(LLMModel).where(LLMModel.is_selected.is_(True))).all())


def _default_meta_prompt(market_code: str) -> str:
    return (
        f"You are designing the best possible trading prompt for the {market_code} market. "
        "Prioritize the last 1 hour of price action, use the last 24 hours of news as supporting "
        "context, keep the portfolio under 10 positions, and account for market-specific fees and taxes. "
        "Return a production-ready prompt that will later be used for hourly virtual trading decisions."
    )




def run_weekly_free_model_sync_if_due(session: Session, *, candidate_limit: int = 250, sort_by: str = "popular") -> list[str]:
    runtime_config = load_runtime_config()
    local_now = datetime.now(UTC).astimezone(ZoneInfo(runtime_config.app.timezone))
    if local_now.weekday() != 6:
        return []

    state = session.scalar(select(AdminSetting).where(AdminSetting.key == FREE_MODEL_SYNC_STATE_KEY))
    state_value = state.value_json if state is not None and isinstance(state.value_json, dict) else {}
    local_date = local_now.date().isoformat()
    if state_value.get("last_run_date") == local_date:
        return []

    try:
        results = probe_and_add_all_free_models(session, candidate_limit=candidate_limit, sort_by=sort_by)
        successes = [result for result in results if result.success]
        failures = [result for result in results if not result.success]
        message = f"Sunday free/experiment sync added {len(successes)} model(s); failures={len(failures)}."
        payload = {"last_run_date": local_date, "last_status": "success", "last_message": message}
        if state is None:
            state = AdminSetting(key=FREE_MODEL_SYNC_STATE_KEY, value_json=payload)
            session.add(state)
        else:
            state.value_json = payload
            state.updated_at = datetime.now(UTC)
        create_execution_event(session, event_type="model_sync", target_type="catalog", trigger_source="scheduler", status="success", message=message)
        session.flush()
        return [message]
    except Exception as exc:
        message = f"Sunday free/experiment sync failed: {exc}"
        payload = {"last_run_date": local_date, "last_status": "error", "last_message": message}
        if state is None:
            state = AdminSetting(key=FREE_MODEL_SYNC_STATE_KEY, value_json=payload)
            session.add(state)
        else:
            state.value_json = payload
            state.updated_at = datetime.now(UTC)
        create_execution_event(session, event_type="model_sync", target_type="catalog", trigger_source="scheduler", status="error", code=exc.__class__.__name__, message=message)
        session.flush()
        return [message]


def auto_disable_inactive_models(session: Session, *, inactive_days: int = INACTIVE_MODEL_DAYS) -> list[str]:
    now = datetime.now(UTC)
    threshold = now - timedelta(days=inactive_days)
    messages: list[str] = []
    models = session.scalars(select(LLMModel).where(LLMModel.is_selected.is_(True)).order_by(LLMModel.model_id.asc())).all()
    for model in models:
        metadata = model.metadata_json or {}
        if not is_model_api_enabled(model):
            continue
        if not bool(metadata.get("is_free_like", False)):
            continue

        latest_run = session.scalar(
            select(RunRequest).where(RunRequest.model_id == model.model_id, RunRequest.status == "success").order_by(RunRequest.completed_at.desc(), RunRequest.requested_at.desc())
        )
        latest_log = session.scalar(
            select(LLMDecisionLog).where(LLMDecisionLog.model_id == model.model_id).order_by(LLMDecisionLog.created_at.desc())
        )
        candidates = [model.updated_at, model.created_at]
        if latest_run is not None:
            candidates.extend([latest_run.completed_at, latest_run.requested_at])
        if latest_log is not None:
            candidates.append(latest_log.created_at)
        candidates = [value for value in candidates if value is not None]
        last_active_at = max(candidates) if candidates else None
        metadata["last_active_at"] = last_active_at.astimezone(UTC).isoformat() if last_active_at else None

        if last_active_at is not None and last_active_at >= threshold:
            if metadata.get("auto_disabled_inactive"):
                metadata.pop("auto_disabled_inactive", None)
                metadata.pop("inactive_since", None)
                if metadata.get("status_note", "").startswith("Auto-disabled after"):
                    metadata.pop("status_note", None)
            model.metadata_json = metadata
            continue

        metadata["api_enabled"] = False
        metadata["auto_disabled_inactive"] = True
        metadata["inactive_since"] = now.astimezone(UTC).isoformat()
        metadata["status_note"] = f"Auto-disabled after {inactive_days} days without successful use. Re-enable manually to use again."
        model.metadata_json = metadata
        message = f"Auto-disabled inactive model: {model.model_id}"
        create_execution_event(session, event_type="model_maintenance", target_type="model", model_id=model.model_id, trigger_source="scheduler", status="success", message=message)
        messages.append(message)

    session.flush()
    return messages
