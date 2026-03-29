from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config.loader import load_settings
from app.db.models import (
    AdminSetting,
    LLMDecisionLog,
    LLMModel,
    MarketSetting,
    ModelMarketPrompt,
    PerformanceSnapshot,
    Portfolio,
    Position,
    RunRequest,
    SharedNewsBatch,
    SharedNewsItem,
    Trade,
)
from app.services.execution_events import create_execution_event
from app.services.setup_helpers import ensure_model_market_state, resolve_profile_prompt

RUNTIME_SETTINGS_KEY = "runtime_controls"
SCHEDULER_STATE_KEY = "scheduler_state"
MARKET_TIMEZONES = {
    "KR": "Asia/Seoul",
    "US": "America/New_York",
}

DEFAULT_RUNTIME_SETTINGS = {
    "decision_interval_minutes": 60,
    "active_weekdays": [0, 1, 2, 3, 4],
    "markets": {
        "KR": {"enabled": True, "window_start": "08:00", "window_end": "16:00", "window_start_utc": "23:00", "window_end_utc": "07:00"},
        "US": {"enabled": True, "window_start": "08:00", "window_end": "17:00", "window_start_utc": "12:00", "window_end_utc": "22:00"},
    },
    "news_enabled": False,
    "news_mode": "shared_off",
    "news_collection_policy": "development_fallback",
    "news_refresh_interval_minutes": 30,
}

DEFAULT_SCHEDULER_ENTRY = {
    "last_started_at": None,
    "last_completed_at": None,
    "last_status": None,
    "last_message": None,
}




def _derive_news_mode(news_enabled: bool, refresh_minutes: int) -> str:
    if not news_enabled:
        return "shared_off"
    return f"shared_marketaux_{int(refresh_minutes)}m"


def default_news_collection_policy() -> str:
    settings = load_settings()
    return "development_fallback" if settings.database_url.startswith("sqlite") else "live_strict"


def get_runtime_settings(session: Session) -> dict:
    setting = session.scalar(select(AdminSetting).where(AdminSetting.key == RUNTIME_SETTINGS_KEY))
    if setting is None:
        default_settings = {**DEFAULT_RUNTIME_SETTINGS, "news_collection_policy": default_news_collection_policy()}
        setting = AdminSetting(key=RUNTIME_SETTINGS_KEY, value_json=default_settings)
        session.add(setting)
        session.flush()
        return {**default_settings}

    value = {**DEFAULT_RUNTIME_SETTINGS, **(setting.value_json or {})}
    value["news_refresh_interval_minutes"] = int(value.get("news_refresh_interval_minutes") or 30)
    value["news_collection_policy"] = value.get("news_collection_policy") or default_news_collection_policy()
    value["news_mode"] = _derive_news_mode(bool(value.get("news_enabled", False)), int(value.get("news_refresh_interval_minutes") or 30))
    markets = {**DEFAULT_RUNTIME_SETTINGS.get("markets", {}), **(value.get("markets", {}))}
    changed = False
    us_window = markets.get("US", {})
    if us_window.get("window_start") == "08:30" and us_window.get("window_end") == "16:30":
        markets["US"] = {**us_window, "window_start": "08:00", "window_end": "17:00"}
        changed = True
    for market_code, defaults in DEFAULT_RUNTIME_SETTINGS.get("markets", {}).items():
        market_config = {**defaults, **markets.get(market_code, {})}
        market_config["window_start_utc"] = market_config.get("window_start_utc") or defaults.get("window_start_utc")
        market_config["window_end_utc"] = market_config.get("window_end_utc") or defaults.get("window_end_utc")
        markets[market_code] = market_config
    value["markets"] = markets
    if changed:
        setting.value_json = value
        setting.updated_at = datetime.now(UTC)
        session.flush()
    return value


def update_runtime_settings(session: Session, payload: dict) -> dict:
    current = get_runtime_settings(session)
    merged = {**current, **payload}
    merged["news_refresh_interval_minutes"] = int(merged.get("news_refresh_interval_minutes") or 30)
    merged["news_collection_policy"] = merged.get("news_collection_policy") or default_news_collection_policy()
    merged["news_mode"] = _derive_news_mode(bool(merged.get("news_enabled", False)), int(merged.get("news_refresh_interval_minutes") or 30))
    if "markets" in payload:
        merged["markets"] = {**current.get("markets", {}), **payload["markets"]}
    setting = session.scalar(select(AdminSetting).where(AdminSetting.key == RUNTIME_SETTINGS_KEY))
    if setting is None:
        setting = AdminSetting(key=RUNTIME_SETTINGS_KEY, value_json=merged)
        session.add(setting)
    else:
        setting.value_json = merged
        setting.updated_at = datetime.now(UTC)
    session.flush()
    return merged


def get_scheduler_state(session: Session) -> dict:
    runtime_settings = get_runtime_settings(session)
    market_codes = list(runtime_settings.get("markets", {}).keys())
    setting = session.scalar(select(AdminSetting).where(AdminSetting.key == SCHEDULER_STATE_KEY))
    if setting is None:
        state = {"markets": {code: DEFAULT_SCHEDULER_ENTRY.copy() for code in market_codes}}
        setting = AdminSetting(key=SCHEDULER_STATE_KEY, value_json=state)
        session.add(setting)
        session.flush()
        return state

    state = {"markets": {**(setting.value_json or {}).get("markets", {})}}
    changed = False
    for code in market_codes:
        if code not in state["markets"]:
            state["markets"][code] = DEFAULT_SCHEDULER_ENTRY.copy()
            changed = True
    for code in list(state["markets"].keys()):
        if code not in market_codes:
            del state["markets"][code]
            changed = True
    if changed:
        setting.value_json = state
        setting.updated_at = datetime.now(UTC)
        session.flush()
    return state


def update_market_scheduler_state(
    session: Session,
    market_code: str,
    *,
    last_started_at: datetime | None = None,
    last_completed_at: datetime | None = None,
    last_status: str | None = None,
    last_message: str | None = None,
) -> dict:
    state = get_scheduler_state(session)
    markets = state.setdefault("markets", {})
    entry = {**DEFAULT_SCHEDULER_ENTRY, **markets.get(market_code, {})}
    if last_started_at is not None:
        entry["last_started_at"] = _serialize_datetime(last_started_at)
    if last_completed_at is not None:
        entry["last_completed_at"] = _serialize_datetime(last_completed_at)
    if last_status is not None:
        entry["last_status"] = last_status
    if last_message is not None:
        entry["last_message"] = last_message
    markets[market_code] = entry

    setting = session.scalar(select(AdminSetting).where(AdminSetting.key == SCHEDULER_STATE_KEY))
    if setting is None:
        setting = AdminSetting(key=SCHEDULER_STATE_KEY, value_json=state)
        session.add(setting)
    else:
        setting.value_json = state
        setting.updated_at = datetime.now(UTC)
    session.flush()
    return entry


def get_scheduler_status(session: Session, now: datetime | None = None) -> dict:
    current_utc = now.astimezone(UTC) if now is not None else datetime.now(UTC)
    runtime_settings = get_runtime_settings(session)
    state = get_scheduler_state(session)
    cadence_minutes = int(runtime_settings.get("decision_interval_minutes", 60))
    active_weekdays = runtime_settings.get("active_weekdays", [0, 1, 2, 3, 4])

    markets_payload = []
    for market_code, config in runtime_settings.get("markets", {}).items():
        timezone_name = MARKET_TIMEZONES.get(market_code, "UTC")
        timezone = ZoneInfo(timezone_name)
        local_now = current_utc.astimezone(timezone)
        enabled = bool(config.get("enabled", True))
        entry = {**DEFAULT_SCHEDULER_ENTRY, **state.get("markets", {}).get(market_code, {})}
        last_started_at = _deserialize_datetime(entry.get("last_started_at"))
        last_completed_at = _deserialize_datetime(entry.get("last_completed_at"))
        in_active_window = enabled and _is_market_active(current_utc, local_now, config, active_weekdays)
        cadence_delta = timedelta(minutes=cadence_minutes)
        is_due = in_active_window and (last_started_at is None or current_utc >= (last_started_at + cadence_delta))
        next_run_at = _compute_next_run(
            now_utc=current_utc,
            timezone=timezone,
            config=config,
            active_weekdays=active_weekdays,
            cadence_delta=cadence_delta,
            last_started_at=last_started_at,
        )
        markets_payload.append(
            {
                "market_code": market_code,
                "market_timezone": timezone_name,
                "window_label_utc": _utc_window_label(config, timezone_name),
                "enabled": enabled,
                "in_active_window": in_active_window,
                "is_due": is_due,
                "last_started_at": last_started_at,
                "last_completed_at": last_completed_at,
                "last_status": entry.get("last_status"),
                "last_message": entry.get("last_message"),
                "next_run_at": next_run_at,
            }
        )

    return {
        "cadence_minutes": cadence_minutes,
        "active_weekdays": active_weekdays,
        "markets": markets_payload,
    }




def _get_model_in_session(session: Session, profile_id: str) -> LLMModel | None:
    for pending in session.new:
        if isinstance(pending, LLMModel) and pending.model_id == profile_id:
            return pending
    for instance in session.identity_map.values():
        if isinstance(instance, LLMModel) and instance.model_id == profile_id:
            return instance
    return session.scalar(select(LLMModel).where(LLMModel.model_id == profile_id))


def reset_simulation(session: Session, reset_prompts: bool = True) -> dict[str, int]:
    deleted_logs = session.execute(delete(LLMDecisionLog)).rowcount or 0
    deleted_run_requests = session.execute(delete(RunRequest)).rowcount or 0
    deleted_positions = session.execute(delete(Position)).rowcount or 0
    deleted_trades = session.execute(delete(Trade)).rowcount or 0
    deleted_snapshots = session.execute(delete(PerformanceSnapshot)).rowcount or 0
    deleted_news_items = session.execute(delete(SharedNewsItem)).rowcount or 0
    deleted_news_batches = session.execute(delete(SharedNewsBatch)).rowcount or 0

    enabled_markets = {
        market.market_code: market
        for market in session.scalars(select(MarketSetting).where(MarketSetting.enabled.is_(True))).all()
    }

    for portfolio in session.scalars(select(Portfolio)).all():
        market = enabled_markets.get(portfolio.market_code)
        if market is None:
            session.delete(portfolio)
            continue
        portfolio.currency = market.currency
        portfolio.initial_cash = market.initial_cash
        portfolio.available_cash = market.initial_cash
        portfolio.invested_value = 0.0
        portfolio.total_equity = market.initial_cash
        portfolio.total_realized_pnl = 0.0
        portfolio.total_unrealized_pnl = 0.0

    if reset_prompts:
        for prompt in session.scalars(select(ModelMarketPrompt)).all():
            if prompt.market_code not in enabled_markets:
                session.delete(prompt)
                continue
            model = session.scalar(select(LLMModel).where(LLMModel.model_id == prompt.model_id))
            custom_prompt = resolve_profile_prompt(model, prompt.market_code)
            if custom_prompt:
                prompt.prompt_content = custom_prompt
                prompt.source_meta_prompt = "Admin custom prompt."
            else:
                prompt.prompt_content = "PENDING_GENERATION"
                prompt.source_meta_prompt = "Pending model-specific prompt generation."

    for model in session.scalars(select(LLMModel).where(LLMModel.is_selected.is_(True))).all():
        for market_code in enabled_markets:
            ensure_model_market_state(
                session,
                model_id=model.model_id,
                market_code=market_code,
                display_name=model.display_name,
            )

    for market_code in enabled_markets:
        update_market_scheduler_state(
            session,
            market_code,
            last_started_at=datetime.now(UTC),
            last_completed_at=datetime.now(UTC),
            last_status="reset",
            last_message="Simulation data reset by admin.",
        )

    session.flush()
    return {
        "deleted_logs": deleted_logs,
        "deleted_run_requests": deleted_run_requests,
        "deleted_positions": deleted_positions,
        "deleted_trades": deleted_trades,
        "deleted_snapshots": deleted_snapshots,
        "deleted_news_items": deleted_news_items,
        "deleted_news_batches": deleted_news_batches,
    }


def create_or_update_model_profile(
    session: Session,
    profile_id: str,
    request_model_id: str,
    display_name: str,
    provider: str = "openrouter",
    search_mode: str = "off",
    select_profile: bool = True,
    prompt_price_per_million: float | None = None,
    completion_price_per_million: float | None = None,
    context_length: int | None = None,
    custom_prompt: str | None = None,
    api_enabled: bool = True,
) -> LLMModel:
    model = _get_model_in_session(session, profile_id)
    if model is None:
        model = LLMModel(
            provider=provider,
            model_id=profile_id,
            display_name=display_name,
            is_available=True,
            is_selected=select_profile,
            metadata_json={},
        )
        session.add(model)
    model.display_name = display_name
    model.provider = provider
    model.context_length = context_length
    model.prompt_price_per_million = prompt_price_per_million
    model.completion_price_per_million = completion_price_per_million
    model.is_selected = select_profile
    model.is_available = True
    metadata = model.metadata_json or {}
    metadata.update(
        {
            "request_model_id": request_model_id,
            "base_model_id": request_model_id.replace(":online", ""),
            "search_mode": search_mode,
            "pricing_label": _pricing_label(prompt_price_per_million, completion_price_per_million),
            "is_free_like": bool(request_model_id.endswith(":free") or request_model_id.endswith(":free:online")),
            "custom_prompt": (custom_prompt or "").strip() or None,
            "api_enabled": bool(api_enabled),
        }
    )
    model.metadata_json = metadata

    if select_profile:
        for market in session.scalars(select(MarketSetting).where(MarketSetting.enabled.is_(True))).all():
            ensure_model_market_state(session, model_id=profile_id, market_code=market.market_code, display_name=display_name)
            _sync_model_prompt_for_market(session, model, market.market_code)

    session.flush()
    return model


def set_model_selection(session: Session, profile_id: str, is_selected: bool) -> LLMModel:
    model = session.scalar(select(LLMModel).where(LLMModel.model_id == profile_id))
    if model is None:
        raise ValueError(f"Model not found: {profile_id}")
    model.is_selected = is_selected
    session.flush()
    return model


def update_model_runtime(
    session: Session,
    profile_id: str,
    *,
    is_selected: bool | None = None,
    api_enabled: bool | None = None,
    custom_prompt: str | None = None,
) -> LLMModel:
    model = session.scalar(select(LLMModel).where(LLMModel.model_id == profile_id))
    if model is None:
        raise ValueError(f"Model not found: {profile_id}")

    metadata = model.metadata_json or {}
    if is_selected is not None:
        model.is_selected = is_selected
    if api_enabled is not None:
        metadata["api_enabled"] = bool(api_enabled)
    if custom_prompt is not None:
        metadata["custom_prompt"] = custom_prompt.strip() or None
    model.metadata_json = metadata

    if model.is_selected:
        for market in session.scalars(select(MarketSetting).where(MarketSetting.enabled.is_(True))).all():
            ensure_model_market_state(session, model_id=profile_id, market_code=market.market_code, display_name=model.display_name)
            _sync_model_prompt_for_market(session, model, market.market_code)

    session.flush()
    return model


def is_model_api_enabled(model: LLMModel) -> bool:
    metadata = model.metadata_json or {}
    return bool(metadata.get("api_enabled", True))


def delete_model_profile(session: Session, profile_id: str) -> dict[str, int]:
    session.execute(delete(LLMDecisionLog).where(LLMDecisionLog.model_id == profile_id))
    session.execute(delete(RunRequest).where(RunRequest.model_id == profile_id))
    session.execute(delete(Position).where(Position.model_id == profile_id))
    session.execute(delete(Trade).where(Trade.model_id == profile_id))
    session.execute(delete(PerformanceSnapshot).where(PerformanceSnapshot.model_id == profile_id))
    session.execute(delete(Portfolio).where(Portfolio.model_id == profile_id))
    session.execute(delete(ModelMarketPrompt).where(ModelMarketPrompt.model_id == profile_id))
    deleted = session.execute(delete(LLMModel).where(LLMModel.model_id == profile_id)).rowcount or 0
    session.flush()
    return {"deleted_models": deleted}


def _sync_model_prompt_for_market(session: Session, model: LLMModel, market_code: str) -> None:
    prompt = session.scalar(
        select(ModelMarketPrompt).where(
            ModelMarketPrompt.model_id == model.model_id,
            ModelMarketPrompt.market_code == market_code,
            ModelMarketPrompt.is_active.is_(True),
        )
    )
    if prompt is None:
        return
    custom_prompt = resolve_profile_prompt(model, market_code)
    if custom_prompt:
        prompt.prompt_content = custom_prompt
        prompt.source_meta_prompt = "Admin custom prompt."
    elif prompt.source_meta_prompt == "Admin custom prompt.":
        prompt.prompt_content = "PENDING_GENERATION"
        prompt.source_meta_prompt = "Pending model-specific prompt generation."


def _pricing_label(prompt_price_per_million: float | None, completion_price_per_million: float | None) -> str:
    if prompt_price_per_million is None or completion_price_per_million is None:
        return "pricing unavailable"
    return f"input=${prompt_price_per_million:.4f}/1M, output=${completion_price_per_million:.4f}/1M"


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


def _deserialize_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_hhmm(value: str) -> time:
    hour_text, minute_text = value.split(":", maxsplit=1)
    return time(hour=int(hour_text), minute=int(minute_text))


def _time_in_window(current_time: time, start_time: time, end_time: time) -> bool:
    if start_time <= end_time:
        return start_time <= current_time <= end_time
    return current_time >= start_time or current_time <= end_time


def _utc_window_times(config: dict) -> tuple[time, time]:
    start_text = config.get("window_start_utc")
    end_text = config.get("window_end_utc")
    if start_text and end_text:
        return _parse_hhmm(start_text), _parse_hhmm(end_text)
    return _parse_hhmm(config.get("window_start", "00:00")), _parse_hhmm(config.get("window_end", "23:59"))


def _is_market_active(now_utc: datetime, local_now: datetime, config: dict, active_weekdays: list[int]) -> bool:
    if local_now.weekday() not in active_weekdays:
        return False
    start_time, end_time = _utc_window_times(config)
    return _time_in_window(now_utc.timetz().replace(tzinfo=None), start_time, end_time)


def _compute_next_run(
    now_utc: datetime,
    timezone: ZoneInfo,
    config: dict,
    active_weekdays: list[int],
    cadence_delta: timedelta,
    last_started_at: datetime | None,
) -> datetime | None:
    if not config.get("enabled", True) or not active_weekdays:
        return None

    earliest = now_utc if last_started_at is None else max(now_utc, last_started_at + cadence_delta)
    start_time, end_time = _utc_window_times(config)
    del start_time, end_time
    candidate = earliest.replace(second=0, microsecond=0)
    for _step in range(0, 14 * 24 * 60, 15):
        local_candidate = candidate.astimezone(timezone)
        if _is_market_active(candidate, local_candidate, config, active_weekdays):
            return candidate.astimezone(UTC)
        candidate = candidate + timedelta(minutes=15)
    return None


def _utc_window_label(config: dict, timezone_name: str) -> str:
    start_time, end_time = _utc_window_times(config)
    return f"{start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')} UTC"


def _minutes_to_hhmm(total_minutes: int) -> str:
    normalized = total_minutes % (24 * 60)
    hour = normalized // 60
    minute = normalized % 60
    return f"{hour:02d}:{minute:02d}"


def list_enabled_market_codes(session: Session) -> list[str]:
    runtime = get_runtime_settings(session)
    return [code for code, config in runtime.get("markets", {}).items() if config.get("enabled", True)]


def run_manual_news_refreshes(session: Session, market_code: str | None = None) -> list[str]:
    from app.services.shared_news import refresh_shared_news_for_market

    market_codes = [market_code] if market_code else list_enabled_market_codes(session)
    messages: list[str] = []
    for code in market_codes:
        try:
            messages.append(refresh_shared_news_for_market(session, code, trigger_source="manual_admin"))
            session.commit()
        except Exception as exc:
            session.rollback()
            create_execution_event(session, event_type="news", target_type="market", market_code=code, trigger_source="manual_admin", status="error", code=exc.__class__.__name__, message=str(exc))
            session.commit()
            messages.append(f"Shared news refresh failed for {code}: {exc}")
    return messages


def run_manual_trade_cycles(session: Session, market_code: str | None = None) -> list[str]:
    from app.services.runtime_scheduler import RuntimeSchedulerService

    market_codes = [market_code] if market_code else list_enabled_market_codes(session)
    service = RuntimeSchedulerService()
    messages: list[str] = []
    for code in market_codes:
        try:
            messages.append(service.run_market_cycle(code, trigger_source="manual_admin"))
        except Exception as exc:
            messages.append(f"Trade cycle failed for {code}: {exc}")
    return messages
