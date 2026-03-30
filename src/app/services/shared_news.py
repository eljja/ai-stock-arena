from __future__ import annotations

from datetime import UTC, datetime, timedelta
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AdminSetting, ExecutionEvent, SharedNewsBatch, SharedNewsItem
from app.news.alpha_vantage import AlphaVantageNewsClient
from app.news.marketaux import MarketauxNewsClient
from app.news.naver import NaverNewsClient
from app.services.admin import get_runtime_settings, get_scheduler_status
from app.services.execution_events import create_execution_event

NEWS_STATE_KEY = "shared_news_state"
DEFAULT_NEWS_REFRESH_INTERVAL_MINUTES = 30
RECENT_DEDUPE_HOURS = 24
CONTEXT_LOOKBACK_MINUTES = 60
DEFAULT_NEWS_MODE = "shared_multi_provider"
DEVELOPMENT_FALLBACK = "development_fallback"
LIVE_STRICT = "live_strict"
PROVIDER_SPECS = {
    "marketaux": {"cadence_minutes": 15, "target_count": 3, "markets": {"KR", "US"}},
    "naver": {"cadence_minutes": 30, "target_count": 5, "markets": {"KR"}},
    "alpha_vantage": {"cadence_minutes": 30, "target_count": 5, "markets": {"US"}},
}


def get_shared_news_state(session: Session) -> dict:
    setting = session.scalar(select(AdminSetting).where(AdminSetting.key == NEWS_STATE_KEY))
    if setting is None:
        state = {"markets": {}}
        setting = AdminSetting(key=NEWS_STATE_KEY, value_json=state)
        session.add(setting)
        session.flush()
        return state
    value = setting.value_json or {}
    if "markets" not in value:
        value = {"markets": {**value.get("markets", {})}}
        setting.value_json = value
        session.flush()
    return value


def update_shared_news_state(
    session: Session,
    market_code: str,
    *,
    last_started_at: datetime | None = None,
    last_completed_at: datetime | None = None,
    last_status: str | None = None,
    last_message: str | None = None,
) -> dict:
    state = get_shared_news_state(session)
    markets = state.setdefault("markets", {})
    entry = {**markets.get(market_code, {})}
    if last_started_at is not None:
        entry["last_started_at"] = _serialize_datetime(last_started_at)
    if last_completed_at is not None:
        entry["last_completed_at"] = _serialize_datetime(last_completed_at)
    if last_status is not None:
        entry["last_status"] = last_status
    if last_message is not None:
        entry["last_message"] = last_message
    markets[market_code] = entry
    setting = session.scalar(select(AdminSetting).where(AdminSetting.key == NEWS_STATE_KEY))
    if setting is None:
        setting = AdminSetting(key=NEWS_STATE_KEY, value_json=state)
        session.add(setting)
    else:
        setting.value_json = state
        setting.updated_at = datetime.now(UTC)
    session.flush()
    return entry


def run_due_news_refreshes(session: Session) -> list[str]:
    runtime_settings = get_runtime_settings(session)
    if not runtime_settings.get("news_enabled", False):
        return []

    scheduler_status = get_scheduler_status(session)
    enabled_providers = {**{"marketaux": True, "naver": True, "alpha_vantage": True}, **(runtime_settings.get("news_providers", {}) or {})}
    results: list[str] = []
    for market in scheduler_status.get("markets", []):
        if not market.get("enabled"):
            continue
        market_code = str(market["market_code"]).upper()
        for provider in _providers_for_market(market_code, enabled_providers):
            cadence_minutes = _provider_cadence_minutes(provider)
            if not _is_provider_due(session, provider, market_code, cadence_minutes=cadence_minutes):
                continue
            try:
                results.append(refresh_shared_news_for_provider(session, market_code, provider, trigger_source="scheduler"))
                session.commit()
            except Exception as exc:
                session.rollback()
                message = f"{provider} refresh failed for {market_code}: {exc}"
                update_shared_news_state(
                    session,
                    market_code,
                    last_completed_at=datetime.now(UTC),
                    last_status="error",
                    last_message=message,
                )
                create_execution_event(
                    session,
                    event_type="news",
                    target_type="provider",
                    market_code=market_code,
                    trigger_source="scheduler",
                    status="error",
                    code=_provider_event_code(provider),
                    message=message,
                )
                session.commit()
                results.append(message)
    return results


def refresh_shared_news_for_market(session: Session, market_code: str, *, trigger_source: str = "scheduler") -> str:
    runtime_settings = get_runtime_settings(session)
    enabled_providers = {**{"marketaux": True, "naver": True, "alpha_vantage": True}, **(runtime_settings.get("news_providers", {}) or {})}
    messages: list[str] = []
    for provider in _providers_for_market(market_code.upper(), enabled_providers):
        try:
            messages.append(refresh_shared_news_for_provider(session, market_code.upper(), provider, trigger_source=trigger_source))
            session.commit()
        except Exception as exc:
            session.rollback()
            message = f"{provider} refresh failed for {market_code.upper()}: {exc}"
            update_shared_news_state(
                session,
                market_code.upper(),
                last_completed_at=datetime.now(UTC),
                last_status="error",
                last_message=message,
            )
            create_execution_event(
                session,
                event_type="news",
                target_type="provider",
                market_code=market_code.upper(),
                trigger_source=trigger_source,
                status="error",
                code=_provider_event_code(provider),
                message=message,
            )
            session.commit()
            messages.append(message)
    return " | ".join(messages) if messages else f"No configured news providers for {market_code.upper()}."


def refresh_shared_news_for_provider(session: Session, market_code: str, provider: str, *, trigger_source: str = "scheduler") -> str:
    runtime_settings = get_runtime_settings(session)
    started_at = datetime.now(UTC)
    cadence_minutes = _provider_cadence_minutes(provider)
    target_count = _provider_target_count(provider)
    update_shared_news_state(
        session,
        market_code,
        last_started_at=started_at,
        last_status="running",
        last_message=f"Refreshing {provider} shared news for {market_code}.",
    )
    session.flush()

    window_end = datetime.now(UTC)
    window_start = window_end - timedelta(minutes=cadence_minutes)
    recent_keys = _recent_news_keys(session, market_code, now=window_end)
    provider_items, provider_status = _collect_provider_news(
        market_code=market_code,
        provider=provider,
        published_after=window_start,
        published_before=window_end,
        existing_keys=recent_keys,
        target_count=target_count,
    )

    if not provider_items:
        message = f"No new unique {provider} shared news for {market_code} in the last {cadence_minutes}m ({provider_status})."
        update_shared_news_state(
            session,
            market_code,
            last_completed_at=window_end,
            last_status="empty",
            last_message=message,
        )
        create_execution_event(
            session,
            event_type="news",
            target_type="provider",
            market_code=market_code,
            trigger_source=trigger_source,
            status="empty",
            code=_provider_event_code(provider),
            message=message,
        )
        return message

    provider_items.sort(key=lambda item: ((getattr(item, 'published_at', None) or datetime.min.replace(tzinfo=UTC)), float(getattr(item, 'significance_score', 0.0))), reverse=True)
    batch = _store_news_batch(session, market_code, provider, provider_items[:target_count], created_at=window_end, window_label=f"{cadence_minutes}m")
    if runtime_settings.get("news_mode") != DEFAULT_NEWS_MODE:
        runtime_settings["news_mode"] = DEFAULT_NEWS_MODE
        setting = session.scalar(select(AdminSetting).where(AdminSetting.key == "runtime_controls"))
        if setting is not None:
            setting.value_json = runtime_settings
            setting.updated_at = datetime.now(UTC)

    message = f"Stored {len(provider_items[:target_count])} {provider} shared news items for {market_code} in batch {batch.batch_key} using {cadence_minutes}m window ({provider_status})."
    update_shared_news_state(
        session,
        market_code,
        last_completed_at=window_end,
        last_status="success",
        last_message=message,
    )
    create_execution_event(
        session,
        event_type="news",
        target_type="provider",
        market_code=market_code,
        trigger_source=trigger_source,
        status="success",
        code=_provider_event_code(provider),
        message=message,
    )
    return message


def recent_news_context(session: Session, market_code: str, *, minutes: int = CONTEXT_LOOKBACK_MINUTES, limit: int = 10) -> list[dict]:
    threshold = datetime.now(UTC) - timedelta(minutes=minutes)
    rows = session.scalars(
        select(SharedNewsItem)
        .where(SharedNewsItem.market_code == market_code)
        .where((SharedNewsItem.published_at >= threshold) | (SharedNewsItem.created_at >= threshold))
        .order_by(SharedNewsItem.published_at.desc(), SharedNewsItem.created_at.desc(), SharedNewsItem.id.desc())
    ).all()
    items: list[dict] = []
    seen_keys: set[str] = set()
    for row in rows:
        key = _row_key(row)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        items.append(
            {
                "title": row.title,
                "summary": row.summary,
                "source": row.source,
                "url": row.url,
                "published_at": row.published_at.isoformat() if row.published_at else None,
                "tickers": list(row.tickers_json or []),
            }
        )
        if len(items) >= limit:
            break
    return items


def get_shared_news_status(session: Session) -> dict[str, dict]:
    scheduler_status = get_scheduler_status(session)
    runtime_settings = get_runtime_settings(session)
    enabled_providers = {**{"marketaux": True, "naver": True, "alpha_vantage": True}, **(runtime_settings.get("news_providers", {}) or {})}
    state = get_shared_news_state(session)
    markets_state = state.get("markets", {})
    payload: dict[str, dict] = {}
    for market in scheduler_status.get("markets", []):
        market_code = market["market_code"]
        entry = markets_state.get(market_code, {})
        payload[market_code] = {
            "news_in_active_window": bool(runtime_settings.get("news_enabled", False)),
            "news_is_due": any(_is_provider_due(session, provider, market_code, cadence_minutes=_provider_cadence_minutes(provider)) for provider in _providers_for_market(market_code, enabled_providers)) if runtime_settings.get("news_enabled", False) else False,
            "news_last_started_at": _deserialize_datetime(entry.get("last_started_at")),
            "news_last_completed_at": _deserialize_datetime(entry.get("last_completed_at")),
            "news_last_status": entry.get("last_status"),
            "news_last_message": entry.get("last_message"),
        }
    return payload


def _providers_for_market(market_code: str, enabled_providers: dict[str, bool]) -> list[str]:
    market_code = market_code.upper()
    providers: list[str] = []
    for provider, spec in PROVIDER_SPECS.items():
        if market_code not in spec["markets"]:
            continue
        if not enabled_providers.get(provider, True):
            continue
        providers.append(provider)
    return providers


def _provider_cadence_minutes(provider: str) -> int:
    return int(PROVIDER_SPECS[provider]["cadence_minutes"])


def _provider_target_count(provider: str) -> int:
    return int(PROVIDER_SPECS[provider]["target_count"])


def _provider_event_code(provider: str) -> str:
    return provider.upper()


def _is_provider_due(session: Session, provider: str, market_code: str, *, cadence_minutes: int) -> bool:
    latest = session.scalar(
        select(ExecutionEvent)
        .where(ExecutionEvent.event_type == "news")
        .where(ExecutionEvent.target_type == "provider")
        .where(ExecutionEvent.market_code == market_code.upper())
        .where(ExecutionEvent.code == _provider_event_code(provider))
        .order_by(ExecutionEvent.created_at.desc())
        .limit(1)
    )
    if latest is None or latest.created_at is None:
        return True
    return datetime.now(UTC) >= latest.created_at + timedelta(minutes=cadence_minutes)


def _collect_provider_news(
    *,
    market_code: str,
    provider: str,
    published_after: datetime,
    published_before: datetime,
    existing_keys: set[str],
    target_count: int,
) -> tuple[list[object], str]:
    if provider == "marketaux":
        try:
            items = MarketauxNewsClient().fetch_recent_news(
                market_code,
                published_after=published_after,
                published_before=published_before,
                target_count=target_count,
                max_pages=1,
                existing_keys=existing_keys,
                collection_policy=LIVE_STRICT,
            )
            return items, f"marketaux:{len(items)}"
        except Exception as exc:
            return [], f"marketaux_error:{exc.__class__.__name__}"
    if provider == "naver":
        try:
            items = NaverNewsClient().fetch_recent_news(
                published_after=published_after,
                published_before=published_before,
                target_count=target_count,
                existing_keys=existing_keys,
            )
            return items, f"naver:{len(items)}"
        except Exception as exc:
            return [], f"naver_error:{exc.__class__.__name__}"
    if provider == "alpha_vantage":
        try:
            items = AlphaVantageNewsClient().fetch_recent_news(
                published_after=published_after,
                published_before=published_before,
                target_count=target_count,
                existing_keys=existing_keys,
            )
            return items, f"alpha_vantage:{len(items)}"
        except Exception as exc:
            return [], f"alpha_vantage_error:{exc.__class__.__name__}"
    raise ValueError(f"Unsupported news provider: {provider}")


def _recent_news_keys(session: Session, market_code: str, *, now: datetime) -> set[str]:
    threshold = now - timedelta(hours=RECENT_DEDUPE_HOURS)
    rows = session.scalars(
        select(SharedNewsItem)
        .where(SharedNewsItem.market_code == market_code)
        .where((SharedNewsItem.published_at >= threshold) | (SharedNewsItem.created_at >= threshold))
    ).all()
    return {_row_key(row) for row in rows}


def _store_news_batch(session: Session, market_code: str, provider: str, articles: list[object], *, created_at: datetime, window_label: str) -> SharedNewsBatch:
    batch_key = f"{provider}:{market_code}:{created_at.strftime('%Y%m%dT%H%M%S')}"
    batch = SharedNewsBatch(
        batch_key=batch_key,
        market_code=market_code,
        source=provider,
        summary=f"{len(articles)} unique items collected for {market_code} using the {provider} provider and the {window_label} refresh window.",
        is_active=True,
        created_at=created_at,
    )
    session.add(batch)
    for article in articles:
        session.add(
            SharedNewsItem(
                batch_key=batch_key,
                market_code=market_code,
                title=article.title,
                summary=article.summary,
                source=article.source,
                url=article.url,
                published_at=article.published_at,
                tickers_json=article.tickers,
                created_at=created_at,
            )
        )
    session.flush()
    return batch


def _row_key(row: SharedNewsItem) -> str:
    if row.url:
        return f"url::{row.url.strip().lower()}"
    title = re.sub(r"\s+", " ", (row.title or "").strip().lower())
    return f"title::{title}"


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
