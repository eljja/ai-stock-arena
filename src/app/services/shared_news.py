from __future__ import annotations

from datetime import UTC, datetime, timedelta
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AdminSetting, SharedNewsBatch, SharedNewsItem
from app.news.alpha_vantage import AlphaVantageNewsClient
from app.news.marketaux import MarketauxNewsClient
from app.news.naver import NaverNewsClient
from app.services.admin import get_runtime_settings, get_scheduler_status
from app.services.execution_events import create_execution_event

NEWS_STATE_KEY = "shared_news_state"
DEFAULT_NEWS_REFRESH_INTERVAL_MINUTES = 30
RECENT_DEDUPE_HOURS = 24
CONTEXT_LOOKBACK_MINUTES = 60
DEFAULT_NEWS_MODE = "shared_hybrid_30m"
DEVELOPMENT_FALLBACK = "development_fallback"
LIVE_STRICT = "live_strict"


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
    refresh_interval_minutes = int(runtime_settings.get("news_refresh_interval_minutes") or DEFAULT_NEWS_REFRESH_INTERVAL_MINUTES)
    results: list[str] = []
    for market in scheduler_status.get("markets", []):
        if not market.get("enabled"):
            continue
        market_code = market["market_code"]
        if not _is_news_due(session, market_code, refresh_interval_minutes=refresh_interval_minutes):
            continue
        try:
            results.append(refresh_shared_news_for_market(session, market_code, trigger_source="scheduler"))
            session.commit()
        except Exception as exc:
            update_shared_news_state(
                session,
                market_code,
                last_completed_at=datetime.now(UTC),
                last_status="error",
                last_message=str(exc),
            )
            create_execution_event(session, event_type="news", target_type="market", market_code=market_code, trigger_source="scheduler", status="error", code=exc.__class__.__name__, message=str(exc))
            session.commit()
            results.append(f"Shared news refresh failed for {market_code}: {exc}")
    return results


def refresh_shared_news_for_market(session: Session, market_code: str, *, trigger_source: str = "scheduler") -> str:
    runtime_settings = get_runtime_settings(session)
    collection_policy = runtime_settings.get("news_collection_policy", DEVELOPMENT_FALLBACK)
    enabled_providers = {**{"marketaux": True, "naver": True, "alpha_vantage": True}, **(runtime_settings.get("news_providers", {}) or {})}
    started_at = datetime.now(UTC)
    update_shared_news_state(
        session,
        market_code,
        last_started_at=started_at,
        last_status="running",
        last_message=f"Refreshing shared news for {market_code}.",
    )
    session.flush()

    window_end = datetime.now(UTC)
    recent_keys = _recent_news_keys(session, market_code, now=window_end)
    selected_window_label = f"{DEFAULT_NEWS_REFRESH_INTERVAL_MINUTES}m"
    provider_items: list[object] = []
    provider_status: list[str] = []

    for window_start, window_label in _candidate_news_windows(session, market_code, now=window_end, collection_policy=collection_policy):
        provider_items, provider_status = _collect_news_from_providers(
            session,
            market_code,
            published_after=window_start,
            published_before=window_end,
            existing_keys=recent_keys,
            collection_policy=collection_policy,
            enabled_providers=enabled_providers,
        )
        if provider_items:
            selected_window_label = window_label
            break

    if not provider_items:
        detail = '; '.join(provider_status) if provider_status else 'no providers returned items'
        message = f"No new unique shared news for {market_code} in the refresh windows ({detail})."
        update_shared_news_state(
            session,
            market_code,
            last_completed_at=window_end,
            last_status="empty",
            last_message=message,
        )
        create_execution_event(session, event_type="news", target_type="market", market_code=market_code, trigger_source=trigger_source, status="empty", message=message)
        return message

    provider_items.sort(key=lambda item: ((getattr(item, 'published_at', None) or datetime.min.replace(tzinfo=UTC)), float(getattr(item, 'significance_score', 0.0))), reverse=True)
    batch = _store_news_batch(session, market_code, provider_items[:10], created_at=window_end, window_label=selected_window_label)
    if runtime_settings.get("news_mode") != DEFAULT_NEWS_MODE:
        runtime_settings["news_mode"] = DEFAULT_NEWS_MODE
        setting = session.scalar(select(AdminSetting).where(AdminSetting.key == "runtime_controls"))
        if setting is not None:
            setting.value_json = runtime_settings
            setting.updated_at = datetime.now(UTC)

    message = f"Stored {len(provider_items[:10])} unique shared news items for {market_code} in batch {batch.batch_key} using {selected_window_label} window ({'; '.join(provider_status)})."
    update_shared_news_state(
        session,
        market_code,
        last_completed_at=window_end,
        last_status="success",
        last_message=message,
    )
    create_execution_event(session, event_type="news", target_type="market", market_code=market_code, trigger_source=trigger_source, status="success", message=message)
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
    refresh_interval_minutes = int(runtime_settings.get("news_refresh_interval_minutes") or DEFAULT_NEWS_REFRESH_INTERVAL_MINUTES)
    state = get_shared_news_state(session)
    markets_state = state.get("markets", {})
    payload: dict[str, dict] = {}
    for market in scheduler_status.get("markets", []):
        market_code = market["market_code"]
        entry = markets_state.get(market_code, {})
        payload[market_code] = {
            "news_in_active_window": bool(runtime_settings.get("news_enabled", False)),
            "news_is_due": _is_news_due(session, market_code, refresh_interval_minutes=refresh_interval_minutes) if runtime_settings.get("news_enabled", False) else False,
            "news_last_started_at": _deserialize_datetime(entry.get("last_started_at")),
            "news_last_completed_at": _deserialize_datetime(entry.get("last_completed_at")),
            "news_last_status": entry.get("last_status"),
            "news_last_message": entry.get("last_message"),
        }
    return payload


def _is_news_due(session: Session, market_code: str, *, refresh_interval_minutes: int = DEFAULT_NEWS_REFRESH_INTERVAL_MINUTES) -> bool:
    state = get_shared_news_state(session)
    market_state = state.get("markets", {}).get(market_code, {})
    last_completed_at = _deserialize_datetime(market_state.get("last_completed_at"))
    if last_completed_at is None:
        return True
    return datetime.now(UTC) >= last_completed_at + timedelta(minutes=refresh_interval_minutes)


def _news_window_start(session: Session, market_code: str, *, now: datetime) -> datetime:
    state = get_shared_news_state(session)
    market_state = state.get("markets", {}).get(market_code, {})
    last_completed_at = _deserialize_datetime(market_state.get("last_completed_at"))
    if last_completed_at is None:
        return now - timedelta(minutes=DEFAULT_NEWS_REFRESH_INTERVAL_MINUTES)
    return max(last_completed_at - timedelta(minutes=2), now - timedelta(minutes=DEFAULT_NEWS_REFRESH_INTERVAL_MINUTES))


def _candidate_news_windows(session: Session, market_code: str, *, now: datetime, collection_policy: str) -> list[tuple[datetime, str]]:
    primary_start = _news_window_start(session, market_code, now=now)
    if collection_policy == LIVE_STRICT:
        return [(primary_start, f"{DEFAULT_NEWS_REFRESH_INTERVAL_MINUTES}m")]
    return [
        (primary_start, f"{DEFAULT_NEWS_REFRESH_INTERVAL_MINUTES}m"),
        (now - timedelta(hours=1), "1h"),
        (now - timedelta(hours=6), "6h"),
        (now - timedelta(hours=24), "24h"),
        (now - timedelta(days=7), "7d"),
    ]


def _collect_news_from_providers(
    session: Session,
    market_code: str,
    *,
    published_after: datetime,
    published_before: datetime,
    existing_keys: set[str],
    collection_policy: str,
    enabled_providers: dict[str, bool],
) -> tuple[list[object], list[str]]:
    items: list[object] = []
    status_parts: list[str] = []
    seen_keys = set(existing_keys)

    def add_items(label: str, fetched: list[object]) -> None:
        added = 0
        for item in fetched:
            key = getattr(item, "dedupe_key", None)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            items.append(item)
            added += 1
        status_parts.append(f"{label}:{added}")

    if enabled_providers.get("marketaux", True):
        try:
            marketaux_items = MarketauxNewsClient().fetch_recent_news(
                market_code,
                published_after=published_after,
                published_before=published_before,
                target_count=5,
                max_pages=2 if collection_policy == LIVE_STRICT else 4,
                existing_keys=seen_keys,
                collection_policy=collection_policy,
            )
            add_items("marketaux", marketaux_items)
        except Exception as exc:
            status_parts.append(f"marketaux_error:{exc.__class__.__name__}")
    else:
        status_parts.append("marketaux:disabled")

    if market_code.upper() == "KR":
        if enabled_providers.get("naver", True):
            try:
                naver_items = NaverNewsClient().fetch_recent_news(
                    published_after=published_after,
                    published_before=published_before,
                    target_count=5,
                    existing_keys=seen_keys,
                )
                add_items("naver", naver_items)
            except Exception as exc:
                status_parts.append(f"naver_error:{exc.__class__.__name__}")
        else:
            status_parts.append("naver:disabled")
    elif market_code.upper() == "US":
        if enabled_providers.get("alpha_vantage", True):
            try:
                alpha_items = AlphaVantageNewsClient().fetch_recent_news(
                    published_after=published_after,
                    published_before=published_before,
                    target_count=5,
                    existing_keys=seen_keys,
                )
                add_items("alpha_vantage", alpha_items)
            except Exception as exc:
                status_parts.append(f"alpha_vantage_error:{exc.__class__.__name__}")
        else:
            status_parts.append("alpha_vantage:disabled")

    return items, status_parts


def _recent_news_keys(session: Session, market_code: str, *, now: datetime) -> set[str]:
    threshold = now - timedelta(hours=RECENT_DEDUPE_HOURS)
    rows = session.scalars(
        select(SharedNewsItem)
        .where(SharedNewsItem.market_code == market_code)
        .where((SharedNewsItem.published_at >= threshold) | (SharedNewsItem.created_at >= threshold))
    ).all()
    return {_row_key(row) for row in rows}


def _store_news_batch(session: Session, market_code: str, articles: list[object], *, created_at: datetime, window_label: str) -> SharedNewsBatch:
    batch_key = f"hybrid:{market_code}:{created_at.strftime('%Y%m%dT%H%M%S')}"
    batch = SharedNewsBatch(
        batch_key=batch_key,
        market_code=market_code,
        source="hybrid",
        summary=f"{len(articles)} unique items collected for {market_code} using the {window_label} refresh window from the configured hybrid providers.",
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
