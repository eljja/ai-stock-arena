from __future__ import annotations

import html
import json
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import altair as alt
import httpx
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from app.api.query_service import (
    get_overview,
    get_runtime_settings_response,
    get_scheduler_status_response,
    list_llm_logs,
    list_market_instruments,
    list_market_price_history,
    list_models,
    list_news_batches,
    list_news_items,
    list_portfolios,
    list_positions,
    list_run_requests,
    list_execution_events,
    get_rankings_with_meta,
    list_snapshots,
    list_trades,
)
from app.config.loader import load_settings
from app.db.session import SessionLocal
from app.news.dedup import normalize_title_fingerprint
from app.services.admin import (
    create_or_update_model_profile,
    delete_model_profile,
    list_market_fee_settings,
    reset_simulation,
    run_manual_news_refreshes,
    run_manual_trade_cycles,
    update_market_fee_settings,
    update_model_runtime,
    update_runtime_settings,
)
from app.services.runtime_secrets import get_runtime_secrets, update_runtime_secrets

settings = load_settings()
WEEKDAY_OPTIONS = [
    (0, "Mon"),
    (1, "Tue"),
    (2, "Wed"),
    (3, "Thu"),
    (4, "Fri"),
    (5, "Sat"),
    (6, "Sun"),
]
PERIOD_OPTIONS = ["Since inception", "1 month", "1 week", "1 day"]
PERIOD_MAP = {
    "Since inception": "current_return_pct",
    "1 month": "return_1m_pct",
    "1 week": "return_1w_pct",
    "1 day": "return_1d_pct",
}

APP_ICON = Image.open(ROOT / "assets" / "brand" / "favicon.png")
st.set_page_config(
    page_title="AI Stock Arena",
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="collapsed",
)


_WARM_CACHE_LOCK = threading.Lock()
_WARM_CACHE_LAST_RUN: dict[tuple, float] = {}
_WARM_CACHE_TTL_SECONDS = 25.0


@st.cache_data(ttl=30, show_spinner=False)
def load_base_data(api_base_url: str | None, selected_only: bool) -> dict[str, object]:
    if api_base_url:
        warnings: list[str] = []
        defaults: dict[str, object] = {
            "overview": {"markets": [], "top_models": [], "headline_metrics": {}},
            "settings": {},
            "scheduler": {"markets": []},
            "models": [],
            "rankings": [],
            "portfolios": [],
            "positions": [],
            "trades": [],
            "snapshots": [],
            "logs": [],
            "__rankings_stale_at": None,
        }
        request_specs = {
            "overview": ("/overview", {"selected_only": str(selected_only).lower()}, 10.0),
            "settings": ("/runtime-settings", None, 8.0),
            "scheduler": ("/scheduler-status", None, 8.0),
            "models": ("/models", {"selected_only": "false"}, 8.0),
            "rankings": ("/rankings", {"selected_only": str(selected_only).lower()}, 18.0),
            "portfolios": ("/portfolios", {"selected_only": str(selected_only).lower()}, 10.0),
            "positions": ("/positions", {"selected_only": str(selected_only).lower()}, 10.0),
            "trades": ("/trades", {"selected_only": str(selected_only).lower(), "limit": 200}, 12.0),
            "snapshots": ("/snapshots", {"selected_only": str(selected_only).lower(), "limit": 2000}, 15.0),
            "logs": ("/llm-logs", {"limit": 200}, 10.0),
        }
        with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
            payload: dict[str, object] = {}
            for key, (path, params, timeout_seconds) in request_specs.items():
                try:
                    response = client.get(path, params=params, timeout=timeout_seconds)
                    response.raise_for_status()
                    payload[key] = response.json()
                    if key == "rankings":
                        cache_status = response.headers.get("X-Rankings-Cache-Status", "").strip().lower()
                        cache_updated_at = response.headers.get("X-Rankings-Cache-Updated-At", "").strip()
                        if cache_status == "stale":
                            payload["__rankings_stale_at"] = cache_updated_at or None
                            warnings.append("rankings: stale cache")
                except Exception as exc:
                    payload[key] = defaults[key]
                    warnings.append(f"{key}: {exc.__class__.__name__}")
            payload["__warnings__"] = warnings
            return payload

    with SessionLocal() as session:
        rankings_payload, rankings_meta = get_rankings_with_meta(session=session, selected_only=selected_only)
        local_warnings: list[str] = []
        rankings_stale_at = None
        if rankings_meta.get("cache_status") == "stale":
            rankings_stale_at = rankings_meta.get("cache_updated_at")
            local_warnings.append("rankings: stale cache")
        return {
            "overview": get_overview(session=session, selected_only=selected_only).model_dump(mode="json"),
            "settings": get_runtime_settings_response(session=session).model_dump(mode="json"),
            "scheduler": get_scheduler_status_response(session=session).model_dump(mode="json"),
            "models": [item.model_dump(mode="json") for item in list_models(session=session, selected_only=False)],
            "rankings": [item.model_dump(mode="json") for item in rankings_payload],
            "portfolios": [item.model_dump(mode="json") for item in list_portfolios(session=session, selected_only=selected_only)],
            "positions": [item.model_dump(mode="json") for item in list_positions(session=session, selected_only=selected_only)],
            "trades": [item.model_dump(mode="json") for item in list_trades(session=session, selected_only=selected_only, limit=200)],
            "snapshots": [item.model_dump(mode="json") for item in list_snapshots(session=session, selected_only=selected_only, limit=2000)],
            "logs": [item.model_dump(mode="json") for item in list_llm_logs(session=session, limit=200)],
            "__warnings__": local_warnings,
            "__rankings_stale_at": rankings_stale_at,
        }


@st.cache_data(ttl=30, show_spinner=False)
def load_model_logs(api_base_url: str | None, model_id: str | None, market_code: str | None) -> list[dict]:
    if not model_id:
        return []
    if api_base_url:
        with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
            return client.get(
                "/llm-logs",
                params={"model_id": model_id, "market_code": market_code, "limit": 20},
            ).json()
    with SessionLocal() as session:
        return [
            item.model_dump(mode="json")
            for item in list_llm_logs(session=session, model_id=model_id, market_code=market_code, limit=20)
        ]


@st.cache_data(ttl=30, show_spinner=False)
def load_news_batches(api_base_url: str | None, limit: int = 10) -> list[dict]:
    if api_base_url:
        try:
            with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=8.0) as client:
                response = client.get("/news", params={"limit": limit})
                response.raise_for_status()
                payload = response.json()
                return payload if isinstance(payload, list) else []
        except httpx.HTTPError:
            return []
    with SessionLocal() as session:
        return [item.model_dump(mode="json") for item in list_news_batches(session=session, limit=limit)]


@st.cache_data(ttl=30, show_spinner=False)
def load_news_preview_items(api_base_url: str | None, limit: int = 40) -> list[dict]:
    if api_base_url:
        try:
            with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=8.0) as client:
                response = client.get("/news-items", params={"limit": limit})
                response.raise_for_status()
                payload = response.json()
                return payload if isinstance(payload, list) else []
        except httpx.HTTPError:
            return []
    with SessionLocal() as session:
        return [item.model_dump(mode="json") for item in list_news_items(session=session, limit=limit)]


@st.cache_data(ttl=30, show_spinner=False)
def load_model_runs(api_base_url: str | None, model_id: str | None, market_code: str | None, limit: int = 100) -> list[dict]:
    if not model_id:
        return []
    if api_base_url:
        with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
            return client.get(
                "/run-requests",
                params={"model_id": model_id, "market_code": market_code, "limit": limit},
            ).json()
    with SessionLocal() as session:
        return [
            item.model_dump(mode="json")
            for item in list_run_requests(session=session, model_id=model_id, market_code=market_code, limit=limit)
        ]


@st.cache_data(ttl=30, show_spinner=False)
def load_model_trades(api_base_url: str | None, model_id: str | None, market_code: str | None, limit: int = 500) -> list[dict]:
    if not model_id:
        return []
    if api_base_url:
        with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
            return client.get(
                "/trades",
                params={"model_id": model_id, "market_code": market_code, "limit": limit},
            ).json()
    with SessionLocal() as session:
        return [
            item.model_dump(mode="json")
            for item in list_trades(session=session, model_id=model_id, market_code=market_code, limit=limit)
        ]


@st.cache_data(ttl=30, show_spinner=False)
def load_market_history(api_base_url: str | None, market_code: str, selected_only: bool, top_n: int = 20, limit_per_ticker: int = 0, tickers: tuple[str, ...] | None = None) -> list[dict]:
    if api_base_url:
        with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
            return client.get(
                "/market-price-history",
                params={
                    "market_code": market_code,
                    "selected_only": str(selected_only).lower(),
                    "top_n": top_n,
                    "limit_per_ticker": limit_per_ticker,
                    "tickers": ",".join(tickers) if tickers else None,
                },
            ).json()
    with SessionLocal() as session:
        return [
            item.model_dump(mode="json")
            for item in list_market_price_history(
                session=session,
                market_code=market_code,
                selected_only=selected_only,
                top_n=top_n,
                limit_per_ticker=limit_per_ticker,
                tickers=list(tickers) if tickers else None,
            )
        ]


@st.cache_data(ttl=30, show_spinner=False)
def load_market_instrument_registry(api_base_url: str | None, market_code: str) -> list[dict]:
    if api_base_url:
        with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
            return client.get("/market-instruments", params={"market_code": market_code}).json()
    with SessionLocal() as session:
        return [
            item.model_dump(mode="json")
            for item in list_market_instruments(session=session, market_code=market_code, active_only=False)
        ]


@st.cache_data(ttl=30, show_spinner=False)
def load_execution_events(api_base_url: str | None, limit: int, offset: int = 0) -> list[dict]:
    if api_base_url:
        with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
            return client.get("/execution-events", params={"limit": limit, "offset": offset}).json()
    with SessionLocal() as session:
        return [
            item.model_dump(mode="json")
            for item in list_execution_events(session=session, limit=limit, offset=offset)
        ]


@st.cache_data(ttl=30, show_spinner=False)
def load_market_fee_settings(api_base_url: str | None, admin_token: str) -> list[dict]:
    if api_base_url:
        with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
            return client.get("/admin/market-fees", headers={"X-Admin-Token": admin_token}).json()
    with SessionLocal() as session:
        return list_market_fee_settings(session)


def refresh_all() -> None:
    load_base_data.clear()
    load_model_logs.clear()
    load_news_batches.clear()
    load_news_preview_items.clear()
    load_model_runs.clear()
    load_model_trades.clear()
    load_execution_events.clear()
    load_market_fee_settings.clear()
    load_admin_secrets.clear()




def _frame_with_columns(rows: object, columns: list[str]) -> pd.DataFrame:
    frame = pd.DataFrame(rows or [])
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.Series(dtype="object")
    return frame


def _money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.2f}"


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


def _weekday_labels(values: list[int]) -> str:
    mapping = dict(WEEKDAY_OPTIONS)
    return ", ".join(mapping.get(value, str(value)) for value in values)


def _news_preview_rows(news_batches: list[dict], limit: int = 50) -> str:
    flattened: list[dict[str, str]] = []
    seen_fingerprints: set[str] = set()
    for batch in news_batches or []:
        if not isinstance(batch, dict):
            continue
        source_items = batch.get("items")
        if source_items is None and "title" in batch:
            source_items = [batch]
        for item in source_items or []:
            if not isinstance(item, dict):
                continue
            title = html.unescape(str(item.get("title") or "Untitled"))
            fp = normalize_title_fingerprint(title)
            if fp and fp in seen_fingerprints:
                continue
            if fp:
                seen_fingerprints.add(fp)

            published = str(item.get("published_at") or "")
            source = html.unescape(str(item.get("source") or "Unknown source"))
            summary = html.unescape(str(item.get("summary") or ""))
            tickers = ", ".join(item.get("tickers") or [])
            detail = " | ".join(part for part in [title, summary, source, tickers] if part)
            flattened.append(
                {
                    "published_at": published,
                    "time_label": published[2:16].replace("T", " ") if published else "No time",
                    "line": title,
                    "detail": detail,
                }
            )
    flattened.sort(key=lambda row: row["published_at"], reverse=True)
    rows = flattened[:limit]
    if not rows:
        placeholder = html.escape(
            "No shared news loaded yet. This area is reserved for the latest 40 normalized headlines."
        )
        return f'<div class="asa-news-row"><div class="asa-news-time">pending</div><div class="asa-news-line" title="{placeholder}">{placeholder}</div></div>'
    html_rows = []
    for row in rows:
        line = html.escape(row["line"])
        detail = html.escape(row["detail"] or row["line"])
        time_label = html.escape(row["time_label"])
        html_rows.append(
            f'<div class="asa-news-row"><div class="asa-news-time">{time_label}</div><div class="asa-news-line" title="{detail}">{line}</div></div>'
        )
    return "".join(html_rows)


def _is_admin(token: str) -> bool:
    return bool(settings.admin_token and token and token == settings.admin_token)


def _mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * max(len(value) - 8, 4)}{value[-4:]}"


@st.cache_data(ttl=30, show_spinner=False)
def load_admin_secrets(api_base_url: str | None, admin_token: str) -> dict[str, str | None]:
    if api_base_url:
        with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
            return client.get("/admin/secrets", headers={"X-Admin-Token": admin_token}).json()
    with SessionLocal() as session:
        return get_runtime_secrets(session)


def _utc_string(value: object) -> str:
    if value in (None, "", float("nan")):
        return ""
    try:
        parsed = pd.to_datetime(value, utc=True, format="ISO8601", errors="coerce")
    except TypeError:
        parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d %H:%M:%S UTC")


def _utc_frame(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    clone = df.copy()
    for column in columns:
        if column in clone.columns:
            clone[column] = clone[column].apply(_utc_string)
    return clone


def _warm_lazy_sections(api_base_url: str | None, selected_only: bool, top_model_id: str | None, admin_token: str | None) -> None:
    cache_key = (api_base_url or "", bool(selected_only), top_model_id or "", bool(admin_token))
    now = time.time()
    with _WARM_CACHE_LOCK:
        last_run = _WARM_CACHE_LAST_RUN.get(cache_key, 0.0)
        if now - last_run < _WARM_CACHE_TTL_SECONDS:
            return
        _WARM_CACHE_LAST_RUN[cache_key] = now

    def worker() -> None:
        try:
            load_news_preview_items(api_base_url, limit=40)
        except Exception:
            pass
        for market_code in ("KR", "US"):
            try:
                load_market_history(api_base_url, market_code, selected_only, top_n=20, limit_per_ticker=0)
            except Exception:
                pass
            try:
                load_market_instrument_registry(api_base_url, market_code)
            except Exception:
                pass
        if top_model_id:
            for market_code in ("KR", "US"):
                try:
                    load_model_logs(api_base_url, top_model_id, market_code)
                except Exception:
                    pass
                try:
                    load_model_runs(api_base_url, top_model_id, market_code, limit=100)
                except Exception:
                    pass
                try:
                    trades = load_model_trades(api_base_url, top_model_id, market_code, limit=500)
                except Exception:
                    trades = []
                if trades:
                    ticker_tuple = tuple(sorted({str(item.get("ticker")) for item in trades if item.get("ticker")}))
                    if ticker_tuple:
                        try:
                            load_market_history(api_base_url, market_code, False, top_n=max(20, min(len(ticker_tuple), 50)), limit_per_ticker=0, tickers=ticker_tuple)
                        except Exception:
                            pass
        if admin_token:
            try:
                load_execution_events(api_base_url, 31, 0)
            except Exception:
                pass
            try:
                load_admin_secrets(api_base_url, admin_token)
            except Exception:
                pass
            try:
                load_market_fee_settings(api_base_url, admin_token)
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True, name="dashboard-lazy-warmup").start()


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
        .stApp {
            background: radial-gradient(circle at top right, rgba(255,102,102,0.16), transparent 28%), radial-gradient(circle at bottom left, rgba(59,130,246,0.16), transparent 28%), linear-gradient(180deg, #07111f 0%, #0d1526 48%, #111827 100%);
            color: #eef2ff;
            font-family: 'IBM Plex Sans', sans-serif;
        }
        h1, h2, h3, [data-testid="stMarkdownContainer"] h1, [data-testid="stMarkdownContainer"] h2 {
            font-family: 'Space Grotesk', sans-serif;
            letter-spacing: -0.03em;
            color: #f8fafc;
        }
        .stApp a { color: #93c5fd; }
        [data-testid="stSidebar"] {
            background: rgba(10, 15, 28, 0.96);
            border-right: 1px solid rgba(148, 163, 184, 0.18);
            min-width: 17rem !important;
        }
        [data-testid="stSidebar"] > div:first-child {
            width: min(20rem, 28vw) !important;
        }
        [data-baseweb="tag"] {
            width: 100% !important;
            justify-content: space-between !important;
            background: rgba(244, 63, 94, 0.16) !important;
            border: 1px solid rgba(251, 113, 133, 0.28) !important;
        }
        [data-baseweb="tag"] span {
            max-width: none !important;
        }
        .stSelectbox [data-baseweb="select"] > div,
        .stMultiSelect [data-baseweb="select"] > div,
        .stTextInput [data-baseweb="input"] > div,
        .stTextInput input,
        .stNumberInput [data-baseweb="input"] > div,
        .stNumberInput input,
        .stTextArea textarea,
        .stDateInput [data-baseweb="input"] > div,
        .stDateInput input,
        [data-testid="stDataEditor"] [data-baseweb="input"] > div,
        [data-testid="stDataEditor"] input,
        [data-testid="stDataEditor"] textarea {
            background: rgba(15, 23, 42, 0.92) !important;
            border: 1px solid rgba(148, 163, 184, 0.22) !important;
            color: #eef2ff !important;
        }
        [data-baseweb="popover"],
        [role="listbox"] {
            background: rgba(15, 23, 42, 0.98) !important;
            color: #eef2ff !important;
            border: 1px solid rgba(148, 163, 184, 0.22) !important;
        }
        [role="option"] {
            background: transparent !important;
            color: #e2e8f0 !important;
        }
        [role="option"][aria-selected="true"] {
            background: rgba(59, 130, 246, 0.18) !important;
        }
        .stButton > button,
        .stDownloadButton > button,
        .stFormSubmitButton > button,
        [data-testid="baseButton-secondary"],
        [data-testid="baseButton-primary"],
        [data-testid="stBaseButton-secondary"],
        [data-testid="stBaseButton-primary"] {
            background: linear-gradient(180deg, rgba(30, 41, 59, 0.96), rgba(15, 23, 42, 0.96)) !important;
            color: #f8fafc !important;
            border: 1px solid rgba(148, 163, 184, 0.24) !important;
            box-shadow: none !important;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover,
        .stFormSubmitButton > button:hover,
        [data-testid="baseButton-secondary"]:hover,
        [data-testid="baseButton-primary"]:hover,
        [data-testid="stBaseButton-secondary"]:hover,
        [data-testid="stBaseButton-primary"]:hover {
            border-color: rgba(96, 165, 250, 0.45) !important;
            color: #ffffff !important;
        }
        .stCheckbox label,
        .stRadio label,
        .stToggle label,
        .stSlider label,
        .stSelectbox label,
        .stMultiSelect label,
        .stTextInput label,
        .stNumberInput label,
        .stTextArea label,
        .stDateInput label {
            color: #dbeafe !important;
        }
        [data-testid="stDataEditor"],
        [data-testid="stDataEditor"] [role="grid"],
        [data-testid="stDataEditor"] [role="rowgroup"],
        [data-testid="stDataEditor"] [role="row"],
        [data-testid="stDataEditor"] [role="columnheader"],
        [data-testid="stDataEditor"] [role="gridcell"],
        [data-testid="stDataEditor"] [data-testid="stDataFrameResizable"] {
            background: rgba(15, 23, 42, 0.94) !important;
            color: #e2e8f0 !important;
            border-color: rgba(148, 163, 184, 0.12) !important;
        }
        [data-testid="stDataEditor"] [role="columnheader"] {
            background: rgba(30, 41, 59, 0.96) !important;
            color: #f8fafc !important;
        }
        [data-testid="stDataFrameGlideDataEditor"] * {
            color: inherit !important;
        }
        [data-testid="stDataFrame"],
        [data-testid="stTable"] {
            background: rgba(15, 23, 42, 0.58) !important;
            border: 1px solid rgba(148, 163, 184, 0.16) !important;
            border-radius: 16px !important;
        }
        [data-testid="stDataFrame"] [role="grid"],
        [data-testid="stDataFrame"] [role="rowgroup"],
        [data-testid="stDataFrame"] [role="row"],
        [data-testid="stDataFrame"] [role="columnheader"],
        [data-testid="stDataFrame"] [role="gridcell"] {
            background: rgba(15, 23, 42, 0.92) !important;
            color: #e2e8f0 !important;
            border-color: rgba(148, 163, 184, 0.12) !important;
        }
        [data-testid="stDataFrame"] [role="columnheader"] {
            background: rgba(30, 41, 59, 0.95) !important;
            color: #f8fafc !important;
        }
        .asa-signature { color: #94a3b8; font: 500 0.92rem 'IBM Plex Sans', sans-serif; white-space: nowrap; }
        [data-testid="stTabs"] button {
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 700;
        }
        .asa-hero {
            padding: 28px 30px;
            border-radius: 28px;
            border: 1px solid rgba(22,18,16,0.1);
            background: linear-gradient(135deg, rgba(12, 23, 40, 0.98), rgba(19, 34, 56, 0.92));
            box-shadow: 0 24px 60px rgba(2, 6, 23, 0.45);
            margin: 6px 0 18px 0;
        }
        .asa-eyebrow {
            font: 700 0.78rem 'Space Grotesk', sans-serif;
            text-transform: uppercase;
            letter-spacing: 0.18em;
            color: #67e8f9;
            margin-bottom: 10px;
        }
        .asa-headline {
            font: 700 clamp(2rem, 4vw, 3.8rem) 'Space Grotesk', sans-serif;
            line-height: 0.95;
            margin: 0;
        }
        .asa-subhead {
            color: #94a3b8;
            max-width: 52rem;
            margin-top: 14px;
            font-size: 1rem;
            line-height: 1.5;
        }
        .asa-hero-grid {
            display: grid;
            grid-template-columns: minmax(240px, 0.9fr) minmax(0, 2.1fr);
            gap: 16px;
            margin-top: 20px;
            align-items: stretch;
        }
        .asa-stat-stack {
            display: grid;
            grid-template-columns: minmax(0, 1fr);
            gap: 12px;
        }
        .asa-stat {
            padding: 14px 16px;
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid rgba(148, 163, 184, 0.16);
            border-radius: 18px;
        }
        .asa-news-wall {
            padding: 16px 18px;
            background: linear-gradient(180deg, rgba(9, 18, 33, 0.88), rgba(13, 27, 45, 0.8));
            border: 1px solid rgba(148, 163, 184, 0.16);
            border-radius: 18px;
            min-height: 276px;
        }
        .asa-news-meta {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: baseline;
            margin-bottom: 10px;
        }
        .asa-news-title {
            font: 700 0.95rem 'Space Grotesk', sans-serif;
            color: #f8fafc;
        }
        .asa-news-subtitle {
            color: #94a3b8;
            font-size: 0.82rem;
        }
        .asa-news-list {
            max-height: 230px;
            overflow-y: auto;
            display: grid;
            grid-template-columns: minmax(0, 1fr);
            gap: 2px;
            padding-right: 4px;
        }
        .asa-news-row {
            display: grid;
            grid-template-columns: 96px minmax(0, 1fr);
            gap: 8px;
            align-items: start;
            padding: 2px 0;
            border-bottom: none;
        }
        .asa-news-row:last-child {
            border-bottom: none;
        }
        .asa-news-time {
            color: #67e8f9;
            font: 600 0.74rem 'IBM Plex Sans', sans-serif;
            white-space: nowrap;
            padding-top: 1px;
        }
        .asa-news-line {
            color: #dbeafe;
            font-size: 0.82rem;
            line-height: 1.18;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .asa-legend-preview {
            display: flex;
            flex-wrap: wrap;
            gap: 8px 10px;
            margin: 8px 0 14px 0;
        }
        .asa-legend-chip {
            display: inline-flex;
            align-items: center;
            min-height: 38px;
            padding: 8px 16px;
            border-radius: 999px;
            border: 1px solid rgba(148, 163, 184, 0.22);
            background: rgba(15, 23, 42, 0.55);
            font: 500 0.95rem 'IBM Plex Sans', sans-serif;
            transition: color 120ms ease, border-color 120ms ease, opacity 120ms ease;
        }
        .asa-stat-label {
            font: 600 0.76rem 'Space Grotesk', sans-serif;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: #94a3b8;
        }
        .asa-stat-value {
            font: 700 1.25rem 'Space Grotesk', sans-serif;
            margin-top: 6px;
            color: #f8fafc;
        }
        .asa-stat-value-compact {
            font-size: 0.98rem;
            line-height: 1.45;
        }
        .asa-stat-value-main {
            display: block;
        }
        .asa-stat-value-sub {
            display: block;
            margin-top: 6px;
            font: 700 0.95rem 'IBM Plex Sans', sans-serif;
            color: #93c5fd;
        }
        .asa-podium {
            padding: 18px;
            border-radius: 22px;
            background: rgba(15, 23, 42, 0.82);
            border: 1px solid rgba(148, 163, 184, 0.18);
            min-height: 196px;
        }
        .asa-podium-rank {
            font: 700 0.74rem 'Space Grotesk', sans-serif;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: #fb7185;
        }
        .asa-podium-title {
            font: 700 1.12rem 'Space Grotesk', sans-serif;
            margin-top: 8px;
        }
        .asa-podium-id {
            color: #94a3b8;
            font-size: 0.82rem;
            margin-top: 4px;
            word-break: break-word;
        }
        .asa-podium-metric {
            font: 700 2rem 'Space Grotesk', sans-serif;
            margin-top: 18px;
        }
        .asa-podium-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
            margin-top: 16px;
            color: #94a3b8;
            font-size: 0.84rem;
        }
        .asa-section-label {
            font: 700 0.84rem 'Space Grotesk', sans-serif;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: #67e8f9;
            margin-bottom: 8px;
        }
        .asa-warning {
            padding: 14px 16px;
            border-radius: 16px;
            background: rgba(207,79,47,0.08);
            border: 1px solid rgba(207,79,47,0.16);
            color: #f8fafc;
        }
        .stDataFrame, [data-testid="stMetric"] { background: transparent !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(settings_payload: dict, scheduler_payload: dict, rankings_df: pd.DataFrame, news_batches: list[dict]) -> None:
    market_windows = settings_payload.get("markets", {})
    utc_windows = {
        item.get("market_code"): item.get("window_label_utc", "n/a")
        for item in scheduler_payload.get("markets", [])
    }
    windows_lines = "<br>".join(f"{code}: {utc_windows.get(code, 'n/a')}" for code in market_windows)
    leader_name = "No active model"
    leader_return = "n/a"
    if not rankings_df.empty:
        leader = rankings_df.sort_values(by=["current_return_pct"], ascending=False, na_position="last").iloc[0]
        leader_name = html.escape(str(leader.get("display_name") or leader.get("model_id")))
        leader_return = _pct(leader.get("current_return_pct"))
    news_rows = _news_preview_rows(news_batches, limit=40)
    current_utc = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")
    st.markdown(
        f"""
        <section class="asa-hero">
            <div class="asa-eyebrow">Pure Model Benchmark</div>
            <div style="display:flex; align-items:flex-end; justify-content:space-between; gap:14px; flex-wrap:wrap;">
                <div style="display:flex; align-items:flex-end; gap:14px; flex-wrap:wrap;">
                    <h1 class="asa-headline">AI Stock Arena</h1>
                    <div class="asa-signature">eljja1@gmail.com</div>
                </div>
                <div class="asa-signature">{html.escape(current_utc)}</div>
            </div>
            <div class="asa-subhead">Rank LLMs by fee-adjusted return, drawdown, and execution cost. Same markets, same cadence, same rules.</div>
            <div class="asa-hero-grid">
                <div class="asa-stat-stack">
                    <div class="asa-stat"><div class="asa-stat-label">Cadence</div><div class="asa-stat-value">Every {settings_payload.get('decision_interval_minutes', 60)} min</div></div>
                    <div class="asa-stat"><div class="asa-stat-label">Windows (UTC)</div><div class="asa-stat-value asa-stat-value-compact">{windows_lines}</div></div>
                    <div class="asa-stat"><div class="asa-stat-label">Current Leader</div><div class="asa-stat-value"><span class="asa-stat-value-main">{leader_name}</span><span class="asa-stat-value-sub">{leader_return}</span></div></div>
                </div>
                <div class="asa-news-wall">
                    <div class="asa-news-meta">
                        <div>
                            <div class="asa-stat-label">Shared News Preview</div>
                        </div>
                    </div>
                    <div class="asa-news-list">{news_rows}</div>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def model_allocation_frame(model_id: str, positions_df: pd.DataFrame, portfolios_df: pd.DataFrame, top_n: int = 6) -> pd.DataFrame:
    if positions_df.empty or portfolios_df.empty:
        return pd.DataFrame(columns=["ticker_label", "ticker", "instrument_name", "weight_pct"])
    if "model_id" not in positions_df.columns or "model_id" not in portfolios_df.columns:
        return pd.DataFrame(columns=["ticker_label", "ticker", "instrument_name", "weight_pct"])
    model_positions = positions_df[positions_df["model_id"] == model_id].copy()
    model_portfolios = portfolios_df[portfolios_df["model_id"] == model_id].copy()
    rows: list[dict[str, float | str]] = []
    for _, portfolio in model_portfolios.iterrows():
        market_code = str(portfolio["market_code"])
        total_equity = float(portfolio.get("total_equity") or 0.0)
        if total_equity <= 0:
            continue
        cash_weight = (float(portfolio.get("available_cash") or 0.0) / total_equity) * 100
        if cash_weight > 0:
            rows.append({"ticker_label": f"[{market_code}] CASH", "ticker": "CASH", "instrument_name": f"{market_code} cash", "weight_pct": cash_weight})
        market_positions = model_positions[model_positions["market_code"] == market_code]
        for _, position in market_positions.iterrows():
            market_value = float(position.get("market_value") or 0.0)
            if market_value <= 0:
                continue
            rows.append({"ticker_label": f"[{market_code}] {position['ticker']}", "ticker": str(position['ticker']), "instrument_name": position.get("instrument_name") or str(position['ticker']), "weight_pct": (market_value / total_equity) * 100})
    if not rows:
        return pd.DataFrame(columns=["ticker_label", "ticker", "instrument_name", "weight_pct"])
    allocation_df = pd.DataFrame(rows).sort_values("weight_pct", ascending=False).head(top_n)
    return allocation_df


COLOR_RANGE = ["#00c2ff", "#2d7ff9", "#5a4bff", "#845ef7", "#b84cff", "#ff4ecd", "#ff5d8f", "#ff6b6b", "#ff7f50", "#ff9f1c", "#ffbf00", "#e9c46a", "#b8de29", "#7ad151", "#22c55e", "#00c49a", "#00b8d9", "#48cae4", "#4cc9f0", "#70d6ff", "#a78bfa", "#f472b6", "#fb7185", "#f97316"]


def allocation_chart(allocation_df: pd.DataFrame) -> alt.Chart:
    if allocation_df.empty:
        return alt.Chart(pd.DataFrame({"ticker_label": [], "weight_pct": []})).mark_bar()
    return _apply_chart_theme(
        alt.Chart(allocation_df)
        .mark_bar(cornerRadiusEnd=5)
        .encode(
            x=alt.X("weight_pct:Q", title="Weight %"),
            y=alt.Y("ticker_label:N", sort="-x", title=None),
            color=alt.Color("ticker_label:N", scale=alt.Scale(range=COLOR_RANGE), legend=None),
            tooltip=[
                alt.Tooltip("ticker:N", title="Ticker"),
                alt.Tooltip("instrument_name:N", title="Instrument"),
                alt.Tooltip("weight_pct:Q", title="Weight %", format=".2f"),
            ],
        )
        .properties(height=240)
    )



def position_value_history_frame(price_history_df: pd.DataFrame, trades_df: pd.DataFrame, *, top_n: int = 8) -> pd.DataFrame:
    trade_required = {"ticker", "side", "quantity", "created_at"}
    price_required = {"ticker", "as_of", "current_price"}
    if trades_df.empty or price_history_df.empty or not trade_required.issubset(trades_df.columns) or not price_required.issubset(price_history_df.columns):
        return pd.DataFrame(columns=["as_of", "ticker", "instrument_name", "value"])

    trades = trades_df.copy()
    trades["created_at"] = pd.to_datetime(trades["created_at"], errors="coerce", utc=True)
    trades["quantity"] = pd.to_numeric(trades["quantity"], errors="coerce").fillna(0.0)
    trades["signed_quantity"] = trades["quantity"]
    trades.loc[trades["side"].astype(str).str.upper() != "BUY", "signed_quantity"] *= -1
    trades = trades.dropna(subset=["created_at"])
    if trades.empty:
        return pd.DataFrame(columns=["as_of", "ticker", "instrument_name", "value"])

    prices = price_history_df.copy()
    prices["as_of"] = pd.to_datetime(prices["as_of"], errors="coerce", utc=True)
    prices["current_price"] = pd.to_numeric(prices["current_price"], errors="coerce").fillna(0.0)
    prices = prices.dropna(subset=["as_of"])
    if prices.empty:
        return pd.DataFrame(columns=["as_of", "ticker", "instrument_name", "value"])

    frames: list[pd.DataFrame] = []
    for ticker, ticker_prices in prices.groupby("ticker"):
        ticker_trades = trades[trades["ticker"] == ticker].sort_values("created_at")
        if ticker_trades.empty:
            continue
        quantity_events = ticker_trades.groupby("created_at", as_index=False)["signed_quantity"].sum().sort_values("created_at")
        quantity_events["quantity"] = quantity_events["signed_quantity"].cumsum()
        merged = pd.merge_asof(
            ticker_prices.sort_values("as_of")[["as_of", "current_price", "instrument_name"]],
            quantity_events[["created_at", "quantity"]].rename(columns={"created_at": "as_of"}),
            on="as_of",
            direction="backward",
        )
        merged["quantity"] = merged["quantity"].fillna(0.0)
        merged["value"] = merged["quantity"] * merged["current_price"]
        merged["ticker"] = ticker
        frames.append(merged)

    if not frames:
        return pd.DataFrame(columns=["as_of", "ticker", "instrument_name", "value"])

    history = pd.concat(frames, ignore_index=True)
    history = history[history["value"] > 0]
    if history.empty:
        return pd.DataFrame(columns=["as_of", "ticker", "instrument_name", "value"])

    unique_points = history["as_of"].nunique()
    bucket_freq = "D" if unique_points > 120 else "6H" if unique_points > 48 else "H"
    history["bucket"] = history["as_of"].dt.floor(bucket_freq)
    history = (
        history.sort_values("as_of")
        .groupby(["bucket", "ticker"], as_index=False)
        .tail(1)
        .drop(columns=["as_of"])
        .rename(columns={"bucket": "as_of"})
    )

    top_tickers = history.groupby("ticker")["value"].max().sort_values(ascending=False).head(top_n).index.tolist()
    history["ticker"] = history["ticker"].where(history["ticker"].isin(top_tickers), "OTHER")
    history["instrument_name"] = history["instrument_name"].fillna(history["ticker"])
    history.loc[history["ticker"] == "OTHER", "instrument_name"] = "Other positions"

    collapsed = history.groupby(["as_of", "ticker"], as_index=False).agg(
        instrument_name=("instrument_name", "last"),
        value=("value", "sum"),
    )
    return collapsed.sort_values(["as_of", "value"], ascending=[True, False])



def position_value_history_chart(history_df: pd.DataFrame, currency: str) -> alt.Chart | None:
    if history_df.empty or not {"as_of", "ticker", "instrument_name", "value"}.issubset(history_df.columns):
        return None
    ticker_domain = list(dict.fromkeys(history_df["ticker"].dropna().tolist()))
    color_scale = alt.Scale(domain=ticker_domain, range=COLOR_RANGE[: max(len(ticker_domain), 1)])
    return _apply_chart_theme(
        alt.Chart(history_df)
        .mark_bar()
        .encode(
            x=alt.X("as_of:T", axis=alt.Axis(title=None, format="%y%m%d", labelAngle=-25, labelLimit=120)),
            y=alt.Y("value:Q", stack="zero", title=f"Position value ({currency})"),
            color=alt.Color("ticker:N", scale=color_scale, legend=alt.Legend(orient="bottom", direction="horizontal")),
            tooltip=[
                alt.Tooltip("ticker:N", title="Ticker"),
                alt.Tooltip("instrument_name:N", title="Instrument"),
                alt.Tooltip("as_of:T", title="Time"),
                alt.Tooltip("value:Q", title="Value", format=",.2f"),
            ],
        )
        .properties(height=260)
    )


def _model_color_map(model_ids: list[str]) -> dict[str, str]:
    domain = [str(model_id) for model_id in dict.fromkeys(model_ids) if str(model_id)]
    if not domain:
        domain = ["default"]
    palette = [COLOR_RANGE[index % len(COLOR_RANGE)] for index in range(len(domain))]
    return dict(zip(domain, palette, strict=False))


def _model_color_scale(model_ids: list[str]) -> alt.Scale:
    color_map = _model_color_map(model_ids)
    return alt.Scale(domain=list(color_map.keys()), range=list(color_map.values()))


def _style_performance_legend_controls(color_map: dict[str, str], selected_models: list[str]) -> None:
    selected = {str(model_id) for model_id in selected_models}
    script = f"""
    <script>
    const colorMap = {json.dumps(color_map)};
    const selected = new Set({json.dumps(sorted(selected))});
    const inactiveColor = '#64748b';
    const inactiveBorder = 'rgba(148, 163, 184, 0.22)';
    function labelOf(node) {{
      return (node.innerText || node.textContent || '').trim();
    }}
    function applyLegendColors() {{
      const doc = window.parent.document;
      const nodes = [...doc.querySelectorAll('button, [data-baseweb="tag"]')];
      for (const node of nodes) {{
        const label = labelOf(node);
        if (!Object.prototype.hasOwnProperty.call(colorMap, label)) continue;
        const active = selected.has(label);
        const color = active ? colorMap[label] : inactiveColor;
        node.style.setProperty('color', color, 'important');
        node.style.setProperty('border-color', active ? color : inactiveBorder, 'important');
        node.style.setProperty('box-shadow', active ? `inset 0 0 0 1px ${{color}}` : 'none', 'important');
        node.style.setProperty('opacity', active ? '1' : '0.78', 'important');
        node.querySelectorAll('*').forEach((child) => child.style.setProperty('color', color, 'important'));
      }}
    }}
    requestAnimationFrame(() => applyLegendColors());
    setTimeout(applyLegendColors, 60);
    setTimeout(applyLegendColors, 250);
    </script>
    """
    st.html(script)


def _legend_highlight_selection(field_name: str) -> alt.SelectionParameter:
    return alt.selection_point(fields=[field_name], bind="legend")


def _adaptive_bottom_legend(*, label_limit: int = 220, symbol_limit: int | None = None) -> alt.Legend:
    legend_kwargs = {"orient": "bottom", "direction": "horizontal", "labelLimit": label_limit}
    if symbol_limit is not None:
        legend_kwargs["symbolLimit"] = symbol_limit
    return alt.Legend(**legend_kwargs)


def _normalize_fx_rates(raw_rates: dict | None) -> dict[str, float]:
    rates = {"USDKRW": 1500.0}
    if isinstance(raw_rates, dict):
        for key, value in raw_rates.items():
            try:
                rates[str(key).upper()] = float(value)
            except (TypeError, ValueError):
                continue
    if rates["USDKRW"] <= 0:
        rates["USDKRW"] = 1500.0
    return rates


def _market_fx_rate(market_code: str, fx_rates: dict[str, float] | None) -> float:
    rates = _normalize_fx_rates(fx_rates)
    return 1.0 if str(market_code).upper() == "US" else 1.0 / rates["USDKRW"]


def _aggregate_all_market_snapshots(chart_df: pd.DataFrame, fx_rates: dict[str, float] | None = None) -> pd.DataFrame:
    required = {"model_id", "market_code", "created_at", "total_equity", "total_return_pct"}
    if chart_df.empty or not required.issubset(chart_df.columns):
        return chart_df
    work = chart_df.copy()
    work["created_at"] = pd.to_datetime(work["created_at"], errors="coerce")
    work["total_equity"] = pd.to_numeric(work["total_equity"], errors="coerce")
    work["total_return_pct"] = pd.to_numeric(work["total_return_pct"], errors="coerce")
    work = work.dropna(subset=["created_at", "total_equity"])
    if work.empty:
        return work
    work["bucket"] = work["created_at"].dt.floor("h")
    work["fx_rate"] = work["market_code"].map(lambda market: _market_fx_rate(market, fx_rates))
    work["total_equity_usd"] = work["total_equity"] * work["fx_rate"]

    frames: list[pd.DataFrame] = []
    for model_id, model_df in work.groupby("model_id"):
        buckets = pd.Index(sorted(model_df["bucket"].dropna().unique()))
        if buckets.empty:
            continue
        market_frames: list[pd.DataFrame] = []
        for market_code, market_df in model_df.groupby("market_code"):
            latest_market = (
                market_df.sort_values(["bucket", "created_at"])
                .groupby("bucket", as_index=False)
                .tail(1)[["bucket", "total_equity_usd", "total_return_pct"]]
                .sort_values("bucket")
                .set_index("bucket")
                .reindex(buckets)
                .ffill()
            )
            latest_market["market_code"] = market_code
            latest_market["model_id"] = model_id
            latest_market = latest_market.reset_index().rename(columns={"index": "bucket"})
            market_frames.append(latest_market)
        if not market_frames:
            continue
        expanded = pd.concat(market_frames, ignore_index=True)
        combined = expanded.groupby(["model_id", "bucket"], as_index=False).agg(
            total_equity=("total_equity_usd", "sum"),
            total_return_pct=("total_return_pct", "mean"),
        )
        combined["market_code"] = "All"
        combined["created_at"] = combined["bucket"]
        frames.append(combined[["model_id", "market_code", "created_at", "total_return_pct", "total_equity"]])
    if not frames:
        return pd.DataFrame(columns=["model_id", "market_code", "created_at", "total_return_pct", "total_equity"])
    return pd.concat(frames, ignore_index=True)


def _padded_domain(values: pd.Series, pad_ratio: float = 0.05) -> list[float] | None:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return None
    lower = float(numeric.min())
    upper = float(numeric.max())
    if lower == upper:
        baseline = abs(lower) if lower != 0 else 1.0
        padding = baseline * pad_ratio
        return [lower - padding, upper + padding]
    span = upper - lower
    padding = span * pad_ratio
    return [lower - padding, upper + padding]



def _apply_chart_theme(chart):
    return (
        chart
        .configure(background="transparent")
        .configure_view(fill="transparent", stroke=None)
        .configure_axis(
            labelColor="#cbd5e1",
            titleColor="#94a3b8",
            domainColor="rgba(148,163,184,0.35)",
            gridColor="rgba(148,163,184,0.12)",
            tickColor="rgba(148,163,184,0.35)",
        )
        .configure_legend(
            labelColor="#e2e8f0",
            titleColor="#94a3b8",
            symbolStrokeColor="#e2e8f0",
        )
        .configure_title(color="#f8fafc")
    )


def performance_chart(chart_df: pd.DataFrame, metric_name: str, selected_models: list[str], *, market_filter: str = "All", x_zoom: alt.SelectionParameter | None = None, legend_selection: alt.SelectionParameter | None = None, color_domain_models: list[str] | None = None) -> alt.Chart:
    model_count = max(len(chart_df["model_id"].dropna().unique()), 1)
    color_scale = _model_color_scale(color_domain_models or selected_models or chart_df["model_id"].dropna().tolist())
    selection = legend_selection or _legend_highlight_selection("model_id")
    y_domain = _padded_domain(chart_df[metric_name])
    y_title = metric_name.replace("_", " ").title()
    if metric_name == "total_equity" and market_filter == "All":
        y_title = "Total Equity (USD equiv.)"
    base = alt.Chart(chart_df).encode(
        x=alt.X("created_at:T", axis=alt.Axis(title=None, format="%y%m%d %H:%M", labelAngle=-25, labelLimit=120)),
        y=alt.Y(f"{metric_name}:Q", title=y_title, scale=alt.Scale(domain=y_domain, zero=False)),
        color=alt.Color(
            "model_id:N",
            legend=None,
            scale=color_scale,
        ),
        tooltip=[
            alt.Tooltip("model_id:N", title="Model"),
            alt.Tooltip("market_code:N", title="Market"),
            alt.Tooltip("created_at:T", title="Time"),
            alt.Tooltip(f"{metric_name}:Q", title="Value", format=".4f"),
        ],
    )
    if chart_df["market_code"].nunique() > 1:
        base = base.encode(strokeDash=alt.StrokeDash("market_code:N", legend=None))
    line_opacity = alt.condition(selection, alt.value(1.0), alt.value(0.15)) if legend_selection is not None else alt.value(1.0)
    point_opacity = alt.condition(selection, alt.value(1.0), alt.value(0.15)) if legend_selection is not None else alt.value(1.0)
    line = base.mark_line(strokeWidth=2.4, interpolate="linear").encode(opacity=line_opacity)
    points = base.mark_point(size=56, filled=True).encode(opacity=point_opacity)
    chart = (line + points).properties(height=260)
    if x_zoom is not None:
        chart = chart.add_params(x_zoom)
    return chart


def buy_sell_chart(trades_df: pd.DataFrame, market_filter: str, selected_models: list[str], *, fx_rates: dict[str, float] | None = None, x_zoom: alt.SelectionParameter | None = None, legend_selection: alt.SelectionParameter | None = None, color_domain_models: list[str] | None = None) -> alt.Chart | None:
    required = {"model_id", "market_code", "created_at", "side", "gross_amount"}
    if trades_df.empty or not required.issubset(trades_df.columns):
        return None
    filtered_trades = trades_df.copy()
    if market_filter != "All":
        filtered_trades = filtered_trades[filtered_trades["market_code"] == market_filter]
    filtered_trades = filtered_trades[filtered_trades["model_id"].isin(selected_models)]
    if filtered_trades.empty:
        return None

    trades = filtered_trades.copy()
    trades["created_at"] = pd.to_datetime(trades["created_at"])
    trades["gross_amount"] = pd.to_numeric(trades["gross_amount"], errors="coerce").fillna(0.0)
    if market_filter == "All":
        trades["gross_amount"] = trades["gross_amount"] * trades["market_code"].map(lambda market: _market_fx_rate(market, fx_rates))
    trades["bucket"] = trades["created_at"].dt.floor("h")
    grouped = trades.groupby(["bucket", "model_id", "side"], as_index=False)["gross_amount"].sum()
    grouped["metric"] = grouped["side"].map({"BUY": "Buy", "SELL": "Sell"}).fillna(grouped["side"])
    grouped = grouped.rename(columns={"bucket": "created_at", "gross_amount": "value"})
    color_scale = _model_color_scale(color_domain_models or selected_models or grouped["model_id"].dropna().tolist())
    selection = legend_selection or _legend_highlight_selection("model_id")
    y_domain = _padded_domain(grouped["value"])
    line_opacity = alt.condition(selection, alt.value(1.0), alt.value(0.15)) if legend_selection is not None else alt.value(1.0)
    chart = (
        alt.Chart(grouped)
        .mark_line(point=True, strokeWidth=2.2, interpolate="linear")
        .encode(
            x=alt.X("created_at:T", axis=alt.Axis(title=None, format="%y%m%d %H:%M", labelAngle=-25, labelLimit=120)),
            y=alt.Y("value:Q", title=("Buy / sell notional (USD equiv.)" if market_filter == "All" else "Buy / sell notional"), scale=alt.Scale(domain=y_domain, zero=False)),
            color=alt.Color("model_id:N", scale=color_scale, legend=None),
            strokeDash=alt.StrokeDash("metric:N", legend=None, sort=["Buy", "Sell"]),
            opacity=line_opacity,
            tooltip=[
                alt.Tooltip("model_id:N", title="Model"),
                alt.Tooltip("metric:N", title="Metric"),
                alt.Tooltip("created_at:T", title="Time"),
                alt.Tooltip("value:Q", title="Value", format=".4f"),
            ],
        )
        .properties(height=150)
    )
    if x_zoom is not None:
        chart = chart.add_params(x_zoom)
    return chart


def overhead_chart(trades_df: pd.DataFrame, logs_df: pd.DataFrame, market_filter: str, selected_models: list[str], *, fx_rates: dict[str, float] | None = None, x_zoom: alt.SelectionParameter | None = None, legend_selection: alt.SelectionParameter | None = None, color_domain_models: list[str] | None = None) -> alt.Chart | None:
    trade_required = {"model_id", "market_code", "created_at", "commission_amount", "tax_amount", "regulatory_fee_amount"}
    log_required = {"model_id", "market_code", "created_at", "estimated_cost_usd"}
    frames: list[pd.DataFrame] = []
    filtered_trades = trades_df.copy() if trade_required.issubset(trades_df.columns) else pd.DataFrame()
    filtered_logs = logs_df.copy() if (not logs_df.empty and log_required.issubset(logs_df.columns)) else pd.DataFrame()
    if market_filter != "All":
        filtered_trades = filtered_trades[filtered_trades["market_code"] == market_filter]
        if not filtered_logs.empty:
            filtered_logs = filtered_logs[filtered_logs["market_code"] == market_filter]
    filtered_trades = filtered_trades[filtered_trades["model_id"].isin(selected_models)]
    if not filtered_logs.empty:
        filtered_logs = filtered_logs[filtered_logs["model_id"].isin(selected_models)]

    if not filtered_trades.empty:
        trades = filtered_trades.copy()
        trades["created_at"] = pd.to_datetime(trades["created_at"])
        trades[["commission_amount", "tax_amount", "regulatory_fee_amount"]] = trades[["commission_amount", "tax_amount", "regulatory_fee_amount"]].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        trades["trade_overhead"] = trades[["commission_amount", "tax_amount", "regulatory_fee_amount"]].sum(axis=1)
        if market_filter == "All":
            trades["trade_overhead"] = trades["trade_overhead"] * trades["market_code"].map(lambda market: _market_fx_rate(market, fx_rates))
        trades["bucket"] = trades["created_at"].dt.floor("h")
        fees = trades.groupby(["bucket", "model_id"], as_index=False)["trade_overhead"].sum()
        fees["metric"] = "Trade overhead"
        fees = fees.rename(columns={"bucket": "created_at", "trade_overhead": "value"})[["created_at", "model_id", "metric", "value"]]
        frames.append(fees)
    if not filtered_logs.empty:
        logs = filtered_logs.copy()
        logs["created_at"] = pd.to_datetime(logs["created_at"])
        logs["bucket"] = logs["created_at"].dt.floor("h")
        logs["estimated_cost_usd"] = pd.to_numeric(logs["estimated_cost_usd"], errors="coerce").fillna(0.0)
        if market_filter == "All":
            logs["estimated_cost_usd"] = logs["estimated_cost_usd"] * _market_fx_rate("US", fx_rates)
        token_cost = logs.groupby(["bucket", "model_id"], as_index=False)["estimated_cost_usd"].sum()
        token_cost["metric"] = "LLM overhead"
        token_cost = token_cost.rename(columns={"bucket": "created_at", "estimated_cost_usd": "value"})[["created_at", "model_id", "metric", "value"]]
        frames.append(token_cost)
    if not frames:
        return None
    cost_df = pd.concat(frames, ignore_index=True)
    color_scale = _model_color_scale(color_domain_models or selected_models or cost_df["model_id"].dropna().tolist())
    selection = legend_selection or _legend_highlight_selection("model_id")
    y_domain = _padded_domain(cost_df["value"])
    line_opacity = alt.condition(selection, alt.value(1.0), alt.value(0.15)) if legend_selection is not None else alt.value(1.0)
    chart = (
        alt.Chart(cost_df)
        .mark_line(point=True, strokeWidth=2.2, interpolate="linear")
        .encode(
            x=alt.X("created_at:T", axis=alt.Axis(title=None, format="%y%m%d %H:%M", labelAngle=-25, labelLimit=120)),
            y=alt.Y("value:Q", title=("Overhead (USD equiv.)" if market_filter == "All" else "Overhead"), scale=alt.Scale(domain=y_domain, zero=False)),
            color=alt.Color("model_id:N", scale=color_scale, legend=None),
            strokeDash=alt.StrokeDash("metric:N", legend=None, sort=["Trade overhead", "LLM overhead"]),
            opacity=line_opacity,
            tooltip=[
                alt.Tooltip("model_id:N", title="Model"),
                alt.Tooltip("metric:N", title="Metric"),
                alt.Tooltip("created_at:T", title="Time"),
                alt.Tooltip("value:Q", title="Value", format=".4f"),
            ],
        )
        .properties(height=150)
    )
    if x_zoom is not None:
        chart = chart.add_params(x_zoom)
    return chart


def market_pulse_chart(history_df: pd.DataFrame) -> alt.Chart:
    instrument_count = max(len(history_df["ticker"].dropna().unique()), 1)
    ticker_domain = list(dict.fromkeys(history_df["ticker"].dropna().tolist()))
    color_scale = alt.Scale(domain=ticker_domain, range=COLOR_RANGE[:instrument_count])
    selection = alt.selection_point(fields=["ticker"], on="click", toggle=True, empty=True)
    legend_df = (
        history_df[["ticker", "display_name"]]
        .dropna(subset=["ticker"])
        .drop_duplicates(subset=["ticker"], keep="last")
        .copy()
        .reset_index(drop=True)
    )
    legend_df["legend_row"] = legend_df.index // 10
    legend_df["legend_col"] = legend_df.index % 10
    legend_df["legend_y"] = 0
    row_domain = sorted(legend_df["legend_row"].unique().tolist()) if not legend_df.empty else [0]
    legend_base = alt.Chart(legend_df).encode(
        x=alt.X("legend_col:O", sort=list(range(10)), axis=None),
        y=alt.Y("legend_row:O", sort=row_domain, axis=None),
        opacity=alt.condition(selection, alt.value(1.0), alt.value(0.35)),
        tooltip=[
            alt.Tooltip("ticker:N", title="Ticker"),
            alt.Tooltip("display_name:N", title="Instrument"),
        ],
    )
    legend_hitbox = legend_base.mark_circle(size=360, opacity=0).encode(color=alt.value("#000000"))
    legend_points = legend_base.mark_circle(size=100, filled=True).encode(
        color=alt.Color("ticker:N", scale=color_scale, legend=None),
    )
    legend_text = legend_base.mark_text(align="left", baseline="middle", dx=12, fontSize=12, fontWeight=600).encode(
        text=alt.Text("ticker:N"),
        color=alt.condition(selection, alt.Color("ticker:N", scale=color_scale, legend=None), alt.value("#64748b")),
    )
    legend_chart = (legend_hitbox + legend_points + legend_text).add_params(selection).properties(height=max(42, len(row_domain) * 34))

    main_chart = (
        alt.Chart(history_df)
        .mark_line(point=True, strokeWidth=2.2)
        .encode(
            x=alt.X("as_of:T", axis=alt.Axis(title=None, format="%y%m%d %H:%M", labelAngle=-25, labelLimit=120)),
            y=alt.Y("return_1h_pct:Q", title="Hourly move %"),
            color=alt.Color("ticker:N", scale=color_scale, legend=None),
            opacity=alt.condition(selection, alt.value(1.0), alt.value(0.15)),
            tooltip=[
                alt.Tooltip("ticker:N", title="Ticker"),
                alt.Tooltip("display_name:N", title="Instrument"),
                alt.Tooltip("as_of:T", title="Time"),
                alt.Tooltip("return_1h_pct:Q", title="1h %", format=".3f"),
                alt.Tooltip("return_1d_pct:Q", title="1d %", format=".3f"),
                alt.Tooltip("current_price:Q", title="Price", format=".4f"),
            ],
        )
        .properties(height=460)
    )
    return _apply_chart_theme(alt.vconcat(legend_chart, main_chart, spacing=10).add_params(selection))


def render_podium_card(row: pd.Series, label: str, period_label: str, period_column: str) -> str:
    return f"""
    <div class=\"asa-podium\">
        <div class=\"asa-podium-rank\">{html.escape(label)}</div>
        <div class=\"asa-podium-title\">{html.escape(str(row.get('display_name') or row.get('model_id')))}</div>
        <div class=\"asa-podium-id\">{html.escape(str(row.get('model_id')))}</div>
        <div class=\"asa-podium-metric\">{html.escape(_pct(row.get(period_column)))}</div>
        <div>{html.escape(period_label)}</div>
        <div class=\"asa-podium-grid\">
            <div>KR: {html.escape(_pct(row.get('kr_return_pct')))}</div>
            <div>US: {html.escape(_pct(row.get('us_return_pct')))}</div>
            <div>MDD: {html.escape(_pct(row.get('max_drawdown')))}</div>
            <div>Win: {html.escape(_pct(row.get('win_rate')))}</div>
            <div>LLM: ${(row.get('llm_cost_usd') or 0):.4f}</div>
            <div>Fees: ${(row.get('trade_fee_cost') or 0):.4f}</div>
        </div>
    </div>
    """


inject_styles()

if "dashboard_api_base_url" not in st.session_state:
    st.session_state["dashboard_api_base_url"] = settings.api_base_url or ""
if "dashboard_selected_only" not in st.session_state:
    st.session_state["dashboard_selected_only"] = True
if "dashboard_admin_token" not in st.session_state:
    st.session_state["dashboard_admin_token"] = ""
if "dashboard_models" not in st.session_state:
    st.session_state["dashboard_models"] = []
if "dashboard_execution_event_limit" not in st.session_state:
    st.session_state["dashboard_execution_event_limit"] = 30

api_base_url = str(st.session_state.get("dashboard_api_base_url", ""))
selected_only = bool(st.session_state.get("dashboard_selected_only", True))

payload = load_base_data(api_base_url or None, selected_only)
dashboard_load_warnings = payload.pop("__warnings__", [])
rankings_stale_at = payload.pop("__rankings_stale_at", None)
overview = payload["overview"]
settings_payload = payload["settings"] or {
    "decision_interval_minutes": 60,
    "active_weekdays": [0, 1, 2, 3, 4],
    "markets": {
        "KR": {"enabled": True, "window_start": "08:00", "window_end": "16:00"},
        "US": {"enabled": True, "window_start": "08:00", "window_end": "17:00"},
    },
    "news_enabled": False,
    "news_mode": "shared_off",
    "news_refresh_interval_minutes": 30,
    "news_dedup_enabled": True,
    "dashboard_auto_refresh_enabled": True,
    "dashboard_auto_refresh_minutes": 15,
    "fx_rates": {"USDKRW": 1500.0},
}
scheduler_payload = payload.get("scheduler") or {"markets": []}
market_windows = settings_payload.get("markets", {})
auto_refresh_enabled = bool(settings_payload.get("dashboard_auto_refresh_enabled", True))
auto_refresh_minutes = max(5, min(60, int(settings_payload.get("dashboard_auto_refresh_minutes", 15) or 15)))
if auto_refresh_enabled:
    components.html(f"<script>setTimeout(function(){{ window.parent.location.reload(); }}, {auto_refresh_minutes * 60 * 1000});</script>", height=0, width=0)

models_df = _frame_with_columns(payload["models"], ["model_id", "display_name", "is_selected", "api_enabled"])
rankings_df = _frame_with_columns(
    payload["rankings"],
    [
        "model_id",
        "display_name",
        "current_return_pct",
        "kr_return_pct",
        "us_return_pct",
        "max_drawdown",
        "win_rate",
        "trade_count",
        "llm_cost_usd",
        "trade_fee_cost",
        "pricing_label",
    ],
)
portfolios_df = _frame_with_columns(payload["portfolios"], ["model_id", "market_code", "currency", "available_cash", "total_equity"])
positions_df = _frame_with_columns(payload["positions"], ["model_id", "market_code", "ticker", "instrument_name", "quantity", "market_value", "avg_entry_price", "current_price"])
trades_df = _frame_with_columns(payload["trades"], ["model_id", "market_code", "created_at", "ticker", "side", "gross_amount", "commission_amount", "tax_amount", "regulatory_fee_amount"])
snapshots_df = _frame_with_columns(payload["snapshots"], ["model_id", "market_code", "created_at", "total_return_pct", "total_equity"])
news_preview_batches = load_news_preview_items(api_base_url or None, limit=40)
logs_all_df = _frame_with_columns(payload.get("logs", []), ["model_id", "market_code", "created_at", "estimated_cost_usd"])

model_options = models_df["model_id"].tolist() if not models_df.empty else []
default_models = models_df.loc[models_df["is_selected"], "model_id"].tolist() if not models_df.empty else []
detail_model_options = model_options.copy()
if not rankings_df.empty and {"model_id", "current_return_pct"}.issubset(rankings_df.columns):
    ranking_order = (
        rankings_df.assign(current_return_pct=pd.to_numeric(rankings_df["current_return_pct"], errors="coerce"))
        .sort_values(by=["current_return_pct", "model_id"], ascending=[False, True], na_position="last")["model_id"]
        .dropna()
        .tolist()
    )
    seen_detail_models: set[str] = set()
    detail_model_options = []
    for model_id in ranking_order + model_options:
        if model_id in seen_detail_models:
            continue
        seen_detail_models.add(model_id)
        detail_model_options.append(model_id)
if not st.session_state.get("dashboard_models"):
    st.session_state["dashboard_models"] = default_models or model_options
chosen_models = [model_id for model_id in st.session_state.get("dashboard_models", []) if model_id in model_options]
if not chosen_models and model_options:
    chosen_models = default_models or model_options
    st.session_state["dashboard_models"] = chosen_models
if chosen_models:
    if "model_id" in rankings_df.columns:
        rankings_df = rankings_df[rankings_df["model_id"].isin(chosen_models)]
    if "model_id" in portfolios_df.columns:
        portfolios_df = portfolios_df[portfolios_df["model_id"].isin(chosen_models)]
    if "model_id" in positions_df.columns:
        positions_df = positions_df[positions_df["model_id"].isin(chosen_models)]
    if "model_id" in trades_df.columns:
        trades_df = trades_df[trades_df["model_id"].isin(chosen_models)]
    if "model_id" in snapshots_df.columns:
        snapshots_df = snapshots_df[snapshots_df["model_id"].isin(chosen_models)]
    if "model_id" in models_df.columns:
        models_df = models_df[models_df["model_id"].isin(chosen_models)]
    if not logs_all_df.empty and "model_id" in logs_all_df.columns:
        logs_all_df = logs_all_df[logs_all_df["model_id"].isin(chosen_models)]

warm_top_model_id = None
if not rankings_df.empty and "current_return_pct" in rankings_df.columns and "model_id" in rankings_df.columns:
    _ranked_for_warmup = rankings_df.copy()
    _ranked_for_warmup["current_return_pct"] = pd.to_numeric(_ranked_for_warmup["current_return_pct"], errors="coerce")
    _ranked_for_warmup = _ranked_for_warmup.sort_values(by=["current_return_pct", "model_id"], ascending=[False, True], na_position="last")
    if not _ranked_for_warmup.empty:
        warm_top_model_id = str(_ranked_for_warmup.iloc[0]["model_id"])
_warm_lazy_sections(api_base_url or None, selected_only, warm_top_model_id, str(st.session_state.get("dashboard_admin_token", "")) or None)

render_hero(settings_payload, scheduler_payload, rankings_df, news_preview_batches)
if dashboard_load_warnings:
    st.warning("Dashboard loaded with partial API failures: " + ", ".join(dashboard_load_warnings))
if rankings_stale_at:
    st.caption(f"Rankings stale as of {rankings_stale_at}.")

scheduler_df = pd.DataFrame(scheduler_payload.get("markets", []))

sections = ["Ranking", "Performance", "Market Pulse", "Model Detail", "Shared News"]
if hasattr(st, "segmented_control"):
    active_section = st.segmented_control("Section", sections, default=st.session_state.get("dashboard_section", "Ranking"), key="dashboard_section")
else:
    active_section = st.radio("Section", sections, index=sections.index(st.session_state.get("dashboard_section", "Ranking")), horizontal=True, key="dashboard_section")
active_section = active_section or "Ranking"

if active_section == "Ranking":
    st.markdown('<div class="asa-section-label">League Table</div>', unsafe_allow_html=True)
    period_label = st.selectbox("Ranking period", PERIOD_OPTIONS, index=0)
    sort_column = PERIOD_MAP[period_label]
    if rankings_df.empty:
        st.info("No ranking data available.")
    else:
        ranked = rankings_df.copy()
        ranked[sort_column] = pd.to_numeric(ranked[sort_column], errors="coerce")
        ranked = ranked.sort_values(by=[sort_column, "current_return_pct"], ascending=[False, False], na_position="last")
        ranked.index = range(1, len(ranked) + 1)
        ranking_columns = [
            "model_id",
            "search_mode",
            "is_free_like",
            sort_column,
            "kr_return_pct",
            "us_return_pct",
            "win_rate",
            "trade_count",
            "llm_cost_usd",
            "trade_fee_cost",
            "pricing_label",
        ]
        rename_map = {
            "model_id": "Model ID",
            "search_mode": "Search",
            "is_free_like": "Free",
            sort_column: period_label,
            "kr_return_pct": "KR return %",
            "us_return_pct": "US return %",
            "win_rate": "Win rate",
            "trade_count": "Trades",
            "llm_cost_usd": "LLM cost (USD)",
            "trade_fee_cost": "Trade fees (USD equiv.)",
            "pricing_label": "Pricing",
        }
        if sort_column != "current_return_pct":
            ranking_columns.insert(5, "current_return_pct")
            rename_map["current_return_pct"] = "Since inception"
        top_rows = [row for _, row in ranked.head(3).iterrows()]
        podium_labels = ["Champion", "Pressure", "Pursuer"]
        podium_cols = st.columns(3)
        for idx, column in enumerate(podium_cols):
            if idx < len(top_rows):
                column.markdown(render_podium_card(top_rows[idx], podium_labels[idx], period_label, sort_column), unsafe_allow_html=True)
                allocation_df = model_allocation_frame(str(top_rows[idx]["model_id"]), positions_df, portfolios_df)
                if allocation_df.empty:
                    column.caption("No current holdings")
                else:
                    column.caption("Current allocation")
                    column.altair_chart(allocation_chart(allocation_df), use_container_width=True)
            else:
                column.empty()
        st.markdown(' <div class="asa-section-label">Full Ranking</div> ' , unsafe_allow_html=True)
        st.dataframe(
            ranked[ranking_columns].rename(columns=rename_map),
            use_container_width=True,
            hide_index=True,
        )

if active_section == "Performance":
    st.markdown('<div class="asa-section-label">Trajectory</div>', unsafe_allow_html=True)
    metric_name = st.selectbox("Chart metric", ["total_return_pct", "total_equity"], index=0)
    performance_market = st.selectbox("Performance market", ["All", "KR", "US"], index=0)
    performance_default_models = chosen_models or model_options
    performance_color_map = _model_color_map(model_options)
    if hasattr(st, "pills"):
        performance_models = st.pills(
            "Legend models",
            model_options,
            default=performance_default_models,
            selection_mode="multi",
            key="performance_legend_models",
        ) or []
        _style_performance_legend_controls(performance_color_map, performance_models)
    else:
        performance_models = st.multiselect(
            "Legend models",
            model_options,
            default=performance_default_models,
            key="performance_legend_models_fallback",
        )
        _style_performance_legend_controls(performance_color_map, performance_models)
    if snapshots_df.empty:
        st.info("No performance snapshots found.")
    else:
        chart_df = snapshots_df.copy()
        fx_rates = _normalize_fx_rates(settings_payload.get("fx_rates"))
        if performance_market != "All":
            chart_df = chart_df[chart_df["market_code"] == performance_market]
        else:
            chart_df = _aggregate_all_market_snapshots(chart_df, fx_rates)
        chart_df = chart_df[chart_df["model_id"].isin(performance_models)]
        if chart_df.empty:
            st.caption("No performance rows match the current filters.")
        else:
            chart_df["created_at"] = pd.to_datetime(chart_df["created_at"])
            x_zoom = alt.selection_interval(encodings=["x"], bind="scales")
            charts = [performance_chart(chart_df, metric_name, performance_models, market_filter=performance_market, x_zoom=x_zoom, legend_selection=None, color_domain_models=model_options)]
            buy_sell = buy_sell_chart(trades_df, performance_market, performance_models, fx_rates=fx_rates, x_zoom=x_zoom, legend_selection=None, color_domain_models=model_options)
            if buy_sell is not None:
                st.markdown("**Buy / Sell:** Solid line = Buy, dashed line = Sell.")
                charts.append(buy_sell)
            overhead = overhead_chart(trades_df, logs_all_df, performance_market, performance_models, fx_rates=fx_rates, x_zoom=x_zoom, legend_selection=None, color_domain_models=model_options)
            if overhead is not None:
                st.markdown("**Overhead:** Solid line = Trade overhead, dashed line = LLM overhead.")
                charts.append(overhead)
            performance_bundle = _apply_chart_theme(alt.vconcat(*charts, spacing=18).add_params(x_zoom))
            chart_col, _ = st.columns([5, 1])
            chart_col.altair_chart(performance_bundle, use_container_width=True)

if active_section == "Market Pulse":
    st.markdown('<div class="asa-section-label">Market Pulse</div>', unsafe_allow_html=True)
    pulse_controls = st.columns([1.1, 1.1, 2.2])
    pulse_market = pulse_controls[0].selectbox("Market pulse market", ["KR", "US"], index=0)
    pulse_window = pulse_controls[1].selectbox("History window", ["3M", "6M", "1Y", "All"], index=0)
    pulse_controls[2].caption("Default view loads the latest 3 months. Use a wider window to explore older hourly history.")
    price_history = pd.DataFrame(load_market_history(api_base_url or None, pulse_market, selected_only, top_n=20, limit_per_ticker=0))
    instrument_registry = pd.DataFrame(load_market_instrument_registry(api_base_url or None, pulse_market))
    if price_history.empty:
        st.info("No tracked hourly market price history is stored yet for this market.")
    else:
        price_history["as_of"] = pd.to_datetime(price_history["as_of"], format="ISO8601", utc=True, errors="coerce")
        price_history = price_history.dropna(subset=["as_of"])
        now_utc = pd.Timestamp.now(tz="UTC")
        window_days = {"3M": 92, "6M": 183, "1Y": 366, "All": None}
        history_days = window_days.get(pulse_window)
        if history_days is not None:
            cutoff = now_utc - pd.Timedelta(days=history_days)
            price_history = price_history[price_history["as_of"] >= cutoff]
        price_history["display_name"] = price_history["instrument_name"].fillna(price_history["ticker"])
        if not instrument_registry.empty:
            instrument_registry = instrument_registry[instrument_registry["ticker"].isin(price_history["ticker"].unique())].copy()
            instrument_registry["display_name"] = instrument_registry["instrument_name"].fillna(instrument_registry["ticker"])
        st.altair_chart(market_pulse_chart(price_history), use_container_width=True)
        latest_rows = (
            price_history.sort_values(["ticker", "as_of"]).groupby("ticker", as_index=False).tail(1)
            .sort_values(["return_1h_pct", "return_1d_pct"], ascending=[False, False])
        )
        st.markdown("**Latest tracked LLM movers**")
        st.dataframe(
            latest_rows[["display_name", "ticker", "current_price", "return_1h_pct", "return_1d_pct", "intraday_volatility_pct", "latest_volume", "is_active"]].rename(
                columns={
                    "display_name": "Instrument",
                    "ticker": "Ticker",
                    "current_price": "Price",
                    "return_1h_pct": "1h %",
                    "return_1d_pct": "1d %",
                    "intraday_volatility_pct": "Volatility %",
                    "latest_volume": "Latest volume",
                    "is_active": "Active",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
    st.markdown("**Instrument registry**")
    if instrument_registry.empty:
        st.caption("No tracked instruments for this market yet.")
    else:
        st.dataframe(
            instrument_registry[["display_name", "ticker", "is_active", "first_seen_at", "last_seen_at", "delisted_at"]].rename(
                columns={
                    "display_name": "Instrument",
                    "ticker": "Ticker",
                    "is_active": "Active",
                    "first_seen_at": "First seen",
                    "last_seen_at": "Last seen",
                    "delisted_at": "Delisted at",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
if active_section == "Shared News":
    st.markdown('<div class="asa-section-label">Shared News</div>', unsafe_allow_html=True)
    news_batches = load_news_batches(api_base_url or None, limit=10)
    if not settings_payload.get("news_enabled", False):
        st.markdown('<div class="asa-warning">Shared news is disabled. This league is running as a pure model benchmark with no external news context.</div>', unsafe_allow_html=True)
    if not news_batches:
        st.caption("No shared news batches stored yet.")
    for batch in news_batches:
        with st.expander(f"{batch['market_code']} | {batch['batch_key']} | {batch['created_at']}"):
            if batch.get("summary"):
                st.write(html.unescape(str(batch["summary"])))
            items = pd.DataFrame(batch.get("items", []))
            if items.empty:
                st.caption("No items in this batch.")
            else:
                if "title" in items.columns:
                    items["title"] = items["title"].fillna("").map(lambda v: html.unescape(str(v)))
                if "summary" in items.columns:
                    items["summary"] = items["summary"].fillna("").map(lambda v: html.unescape(str(v)))
                st.dataframe(items, use_container_width=True, hide_index=True)

if active_section == "Model Detail":
    st.markdown('<div class="asa-section-label">Model Drilldown</div>', unsafe_allow_html=True)
    if not model_options:
        st.info("No models available.")
    else:
        detail_model = st.selectbox("Model", detail_model_options, index=0)
        detail_market = st.selectbox("Market", ["KR", "US"], index=0)
        model_logs = load_model_logs(api_base_url or None, detail_model, detail_market)
        model_runs = pd.DataFrame(load_model_runs(api_base_url or None, detail_model, detail_market, limit=100))
        model_portfolios = portfolios_df[(portfolios_df["model_id"] == detail_model) & (portfolios_df["market_code"] == detail_market)] if {"model_id", "market_code"}.issubset(portfolios_df.columns) else pd.DataFrame()
        model_positions = positions_df[(positions_df["model_id"] == detail_model) & (positions_df["market_code"] == detail_market)] if {"model_id", "market_code"}.issubset(positions_df.columns) else pd.DataFrame()
        model_trades = pd.DataFrame(load_model_trades(api_base_url or None, detail_model, detail_market, limit=500))
        if not model_portfolios.empty:
            row = model_portfolios.iloc[0]
            detail_metrics = st.columns(4)
            detail_metrics[0].metric("Total equity", _money(float(row["total_equity"])))
            detail_metrics[1].metric("Available cash", _money(float(row["available_cash"])))
            detail_metrics[2].metric("Return", _pct(float(row["total_return_pct"])))
            detail_metrics[3].metric("Positions", int(row["position_count"]))
        detail_tickers = sorted({str(ticker) for ticker in model_positions.get("ticker", pd.Series(dtype="object")).dropna().tolist()} | {str(ticker) for ticker in model_trades.get("ticker", pd.Series(dtype="object")).dropna().tolist()})
        if detail_tickers:
            detail_price_history = pd.DataFrame(load_market_history(api_base_url or None, detail_market, False, top_n=max(20, min(len(detail_tickers), 50)), limit_per_ticker=0, tickers=tuple(detail_tickers)))
            position_history_df = position_value_history_frame(detail_price_history, model_trades)
            position_history_chart_obj = position_value_history_chart(position_history_df, str(model_portfolios.iloc[0].get("currency") or detail_market) if not model_portfolios.empty else detail_market)
            if position_history_chart_obj is not None:
                st.markdown("**Position value history**")
                st.altair_chart(position_history_chart_obj, use_container_width=True)
            else:
                st.caption("No historical position value data available yet for this model/market.")
        st.markdown("**Open positions**")
        if model_positions.empty:
            st.caption("No open positions.")
        else:
            st.dataframe(model_positions, use_container_width=True, hide_index=True)
        st.markdown("**Recent trades**")
        if model_trades.empty:
            st.caption("No trades.")
        else:
            st.dataframe(model_trades.head(30), use_container_width=True, hide_index=True)
        st.markdown("**Recent run activity**")
        if model_runs.empty:
            st.caption("No run requests yet.")
        else:
            st.dataframe(
                model_runs[[
                    "requested_at",
                    "status",
                    "trigger_source",
                    "candidate_count",
                    "summary_message",
                    "error_message",
                ]].rename(
                    columns={
                        "requested_at": "Requested at",
                        "status": "Status",
                        "trigger_source": "Trigger",
                        "candidate_count": "Candidates",
                        "summary_message": "Summary",
                        "error_message": "Error",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
        st.markdown("**Latest LLM input/output**")
        logs_df = pd.DataFrame(model_logs)
        if logs_df.empty:
            st.caption("No LLM decision logs yet.")
        else:
            latest_log = logs_df.iloc[0]
            usage_cols = st.columns(4)
            usage_cols[0].metric("Prompt tokens", latest_log.get("prompt_tokens") or 0)
            usage_cols[1].metric("Completion tokens", latest_log.get("completion_tokens") or 0)
            usage_cols[2].metric("Total tokens", latest_log.get("total_tokens") or 0)
            usage_cols[3].metric("Estimated LLM cost", _money(latest_log.get("estimated_cost_usd")))
            st.text_area("Prompt text", latest_log.get("prompt_text") or "", height=180)
            st.json(latest_log.get("input_payload") or {})
            st.text_area("Raw output", latest_log.get("raw_output_text") or latest_log.get("error_message") or "", height=180)
            st.json(latest_log.get("parsed_output") or {})
            st.markdown("**Recent log entries**")
            st.dataframe(
                logs_df[
                    [
                        "created_at",
                        "status",
                        "market_code",
                        "request_model_id",
                        "prompt_tokens",
                        "completion_tokens",
                        "total_tokens",
                        "estimated_cost_usd",
                    ]
                ].rename(
                    columns={
                        "created_at": "Created at",
                        "status": "Status",
                        "market_code": "Market",
                        "request_model_id": "Request model",
                        "prompt_tokens": "Prompt tokens",
                        "completion_tokens": "Completion tokens",
                        "total_tokens": "Total tokens",
                        "estimated_cost_usd": "Estimated cost (USD)",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )







