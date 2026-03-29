from __future__ import annotations

import html
import sys
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

from app.api.query_service import (
    get_overview,
    get_runtime_settings_response,
    get_scheduler_status_response,
    list_llm_logs,
    list_market_instruments,
    list_market_price_history,
    list_models,
    list_news_batches,
    list_portfolios,
    list_positions,
    list_run_requests,
    list_rankings,
    list_snapshots,
    list_trades,
)
from app.config.loader import load_settings
from app.db.session import SessionLocal
from app.services.admin import (
    create_or_update_model_profile,
    delete_model_profile,
    reset_simulation,
    run_manual_news_refreshes,
    run_manual_trade_cycles,
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

st.set_page_config(page_title="AI Stock Arena", layout="wide", initial_sidebar_state="collapsed")


@st.cache_data(ttl=30, show_spinner=False)
def load_base_data(api_base_url: str | None, selected_only: bool) -> dict[str, object]:
    if api_base_url:
        with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
            return {
                "overview": client.get("/overview", params={"selected_only": str(selected_only).lower()}).json(),
                "settings": client.get("/runtime-settings").json(),
                "scheduler": client.get("/scheduler-status").json(),
                "models": client.get("/models", params={"selected_only": "false"}).json(),
                "rankings": client.get("/rankings", params={"selected_only": str(selected_only).lower()}).json(),
                "portfolios": client.get("/portfolios", params={"selected_only": str(selected_only).lower()}).json(),
                "positions": client.get("/positions", params={"selected_only": str(selected_only).lower()}).json(),
                "trades": client.get("/trades", params={"selected_only": str(selected_only).lower(), "limit": 200}).json(),
                "snapshots": client.get("/snapshots", params={"selected_only": str(selected_only).lower(), "limit": 2000}).json(),
                "news": client.get("/news", params={"limit": 5}).json(),
                "logs": client.get("/llm-logs", params={"limit": 1000}).json(),
                "runs": client.get("/run-requests", params={"selected_only": str(selected_only).lower(), "limit": 300}).json(),
            }

    with SessionLocal() as session:
        return {
            "overview": get_overview(session=session, selected_only=selected_only).model_dump(mode="json"),
            "settings": get_runtime_settings_response(session=session).model_dump(mode="json"),
            "scheduler": get_scheduler_status_response(session=session).model_dump(mode="json"),
            "models": [item.model_dump(mode="json") for item in list_models(session=session, selected_only=False)],
            "rankings": [item.model_dump(mode="json") for item in list_rankings(session=session, selected_only=selected_only)],
            "portfolios": [item.model_dump(mode="json") for item in list_portfolios(session=session, selected_only=selected_only)],
            "positions": [item.model_dump(mode="json") for item in list_positions(session=session, selected_only=selected_only)],
            "trades": [item.model_dump(mode="json") for item in list_trades(session=session, selected_only=selected_only, limit=200)],
            "snapshots": [item.model_dump(mode="json") for item in list_snapshots(session=session, selected_only=selected_only, limit=2000)],
            "news": [item.model_dump(mode="json") for item in list_news_batches(session=session, limit=5)],
            "logs": [item.model_dump(mode="json") for item in list_llm_logs(session=session, limit=1000)],
            "runs": [item.model_dump(mode="json") for item in list_run_requests(session=session, selected_only=selected_only, limit=300)],
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
def load_market_history(api_base_url: str | None, market_code: str, selected_only: bool, top_n: int = 20, limit_per_ticker: int = 0) -> list[dict]:
    if api_base_url:
        with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
            return client.get(
                "/market-price-history",
                params={
                    "market_code": market_code,
                    "selected_only": str(selected_only).lower(),
                    "top_n": top_n,
                    "limit_per_ticker": limit_per_ticker,
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


def refresh_all() -> None:
    load_base_data.clear()
    load_model_logs.clear()


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


def _news_preview_rows(news_batches: list[dict], limit: int = 20) -> str:
    flattened: list[dict[str, str]] = []
    for batch in news_batches or []:
        for item in batch.get("items", []):
            published = str(item.get("published_at") or "")
            source = str(item.get("source") or "Unknown source")
            title = str(item.get("title") or "Untitled")
            summary = str(item.get("summary") or "")
            tickers = ", ".join(item.get("tickers") or [])
            detail = " | ".join(part for part in [title, summary, source, tickers] if part)
            flattened.append(
                {
                    "published_at": published,
                    "time_label": published[2:16].replace("T", " ") if published else "No time",
                    "line": f"[{source}] {title}",
                    "detail": detail,
                }
            )
    flattened.sort(key=lambda row: row["published_at"], reverse=True)
    rows = flattened[:limit]
    if not rows:
        placeholder = html.escape("No shared news loaded yet. This area is reserved for the latest 20 normalized headlines.")
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
        .stNumberInput [data-baseweb="input"] > div,
        .stTextArea textarea,
        .stDateInput [data-baseweb="input"] > div {
            background: rgba(15, 23, 42, 0.86) !important;
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
            min-height: 228px;
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
            max-height: 182px;
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
    news_mode = "OFF" if not settings_payload.get("news_enabled", False) else str(settings_payload.get("news_mode", "shared_on")).upper()
    news_policy = str(settings_payload.get("news_collection_policy", "development_fallback")).replace("_", " ").title()
    news_rows = _news_preview_rows(news_batches, limit=20)
    st.markdown(
        f"""
        <section class="asa-hero">
            <div class="asa-eyebrow">Pure Model Benchmark</div>
            <div style="display:flex; align-items:flex-end; gap:14px; flex-wrap:wrap;">
                <h1 class="asa-headline">AI Stock Arena</h1>
                <div class="asa-signature">eljja1@gmail.com</div>
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
                            <div class="asa-news-title">Latest normalized headlines for the benchmark feed</div>
                        </div>
                        <div class="asa-news-subtitle">Mode: {html.escape(news_mode)} | Policy: {html.escape(news_policy)}</div>
                    </div>
                    <div class="asa-news-list">{news_rows}</div>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Active weekdays: {_weekday_labels(settings_payload.get('active_weekdays', [0, 1, 2, 3, 4]))}")


def model_allocation_frame(model_id: str, positions_df: pd.DataFrame, portfolios_df: pd.DataFrame, top_n: int = 6) -> pd.DataFrame:
    if positions_df.empty or portfolios_df.empty:
        return pd.DataFrame(columns=["label", "weight_pct"])
    if "model_id" not in positions_df.columns or "model_id" not in portfolios_df.columns:
        return pd.DataFrame(columns=["label", "weight_pct"])
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
            rows.append({"label": f"[{market_code}] CASH", "weight_pct": cash_weight})
        market_positions = model_positions[model_positions["market_code"] == market_code]
        for _, position in market_positions.iterrows():
            market_value = float(position.get("market_value") or 0.0)
            if market_value <= 0:
                continue
            rows.append({"label": f"[{market_code}] {position['ticker']}", "weight_pct": (market_value / total_equity) * 100})
    if not rows:
        return pd.DataFrame(columns=["label", "weight_pct"])
    allocation_df = pd.DataFrame(rows).sort_values("weight_pct", ascending=False).head(top_n)
    return allocation_df


COLOR_RANGE = ["#00c2ff", "#2d7ff9", "#5a4bff", "#845ef7", "#b84cff", "#ff4ecd", "#ff5d8f", "#ff6b6b", "#ff7f50", "#ff9f1c", "#ffbf00", "#e9c46a", "#b8de29", "#7ad151", "#22c55e", "#00c49a", "#00b8d9", "#48cae4", "#4cc9f0", "#70d6ff", "#a78bfa", "#f472b6", "#fb7185", "#f97316"]


def allocation_chart(allocation_df: pd.DataFrame) -> alt.Chart:
    if allocation_df.empty:
        return alt.Chart(pd.DataFrame({"label": [], "weight_pct": []})).mark_bar()
    return _apply_chart_theme(
        alt.Chart(allocation_df)
        .mark_bar(cornerRadiusEnd=5)
        .encode(
            x=alt.X("weight_pct:Q", title="Weight %"),
            y=alt.Y("label:N", sort="-x", title=None),
            color=alt.Color("label:N", scale=alt.Scale(range=COLOR_RANGE), legend=None),
            tooltip=[alt.Tooltip("label:N", title="Position"), alt.Tooltip("weight_pct:Q", title="Weight %", format=".2f")],
        )
        .properties(height=240)
    )


def _model_color_scale(model_ids: list[str]) -> alt.Scale:
    domain = list(dict.fromkeys(model_ids))
    palette = COLOR_RANGE[: max(len(domain), 1)]
    return alt.Scale(domain=domain, range=palette)


def _legend_highlight_selection(field_name: str) -> alt.SelectionParameter:
    return alt.selection_point(fields=[field_name], bind="legend")


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


def performance_chart(chart_df: pd.DataFrame, metric_name: str, selected_models: list[str], *, x_zoom: alt.SelectionParameter | None = None, legend_selection: alt.SelectionParameter | None = None) -> alt.Chart:
    model_count = max(len(chart_df["model_id"].dropna().unique()), 1)
    color_scale = _model_color_scale(selected_models or chart_df["model_id"].dropna().tolist())
    selection = legend_selection or _legend_highlight_selection("model_id")
    y_domain = _padded_domain(chart_df[metric_name])
    base = alt.Chart(chart_df).encode(
        x=alt.X("created_at:T", axis=alt.Axis(title=None, format="%y%m%d %H:%M", labelAngle=-25, labelLimit=120)),
        y=alt.Y(f"{metric_name}:Q", title=metric_name.replace("_", " ").title(), scale=alt.Scale(domain=y_domain, zero=False)),
        color=alt.Color(
            "model_id:N",
            legend=alt.Legend(orient="bottom", columns=min(4, model_count), labelLimit=240, symbolLimit=model_count),
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
    line = base.mark_line(strokeWidth=2.4).encode(opacity=alt.condition(selection, alt.value(1.0), alt.value(0.15)))
    points = base.mark_point(size=56, filled=True).encode(opacity=alt.condition(selection, alt.value(1.0), alt.value(0.15)))
    chart = (line + points).properties(height=260)
    if x_zoom is not None:
        chart = chart.add_params(x_zoom)
    return _apply_chart_theme(chart)


def buy_sell_chart(trades_df: pd.DataFrame, market_filter: str, selected_models: list[str], *, x_zoom: alt.SelectionParameter | None = None, legend_selection: alt.SelectionParameter | None = None) -> alt.Chart | None:
    filtered_trades = trades_df.copy()
    if market_filter != "All":
        filtered_trades = filtered_trades[filtered_trades["market_code"] == market_filter]
    if selected_models:
        filtered_trades = filtered_trades[filtered_trades["model_id"].isin(selected_models)]
    if filtered_trades.empty:
        return None

    trades = filtered_trades.copy()
    trades["created_at"] = pd.to_datetime(trades["created_at"])
    trades["bucket"] = trades["created_at"].dt.floor("h")
    grouped = trades.groupby(["bucket", "model_id", "side"], as_index=False)["gross_amount"].sum()
    grouped["metric"] = grouped["side"].map({"BUY": "Buy", "SELL": "Sell"}).fillna(grouped["side"])
    grouped = grouped.rename(columns={"bucket": "created_at", "gross_amount": "value"})
    color_scale = _model_color_scale(selected_models or grouped["model_id"].dropna().tolist())
    selection = legend_selection or _legend_highlight_selection("model_id")
    y_domain = _padded_domain(grouped["value"])
    chart = (
        alt.Chart(grouped)
        .mark_line(point=True, strokeWidth=2.2)
        .encode(
            x=alt.X("created_at:T", axis=alt.Axis(title=None, format="%y%m%d %H:%M", labelAngle=-25, labelLimit=120)),
            y=alt.Y("value:Q", title="Buy / sell notional", scale=alt.Scale(domain=y_domain, zero=False)),
            color=alt.Color("model_id:N", scale=color_scale, legend=None),
            strokeDash=alt.StrokeDash("metric:N", legend=None, sort=["Buy", "Sell"]),
            opacity=alt.condition(selection, alt.value(1.0), alt.value(0.15)),
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
    return _apply_chart_theme(chart)


def overhead_chart(trades_df: pd.DataFrame, logs_df: pd.DataFrame, market_filter: str, selected_models: list[str], *, x_zoom: alt.SelectionParameter | None = None, legend_selection: alt.SelectionParameter | None = None) -> alt.Chart | None:
    frames: list[pd.DataFrame] = []
    filtered_trades = trades_df.copy()
    filtered_logs = logs_df.copy() if not logs_df.empty else pd.DataFrame()
    if market_filter != "All":
        filtered_trades = filtered_trades[filtered_trades["market_code"] == market_filter]
        if not filtered_logs.empty:
            filtered_logs = filtered_logs[filtered_logs["market_code"] == market_filter]
    if selected_models:
        filtered_trades = filtered_trades[filtered_trades["model_id"].isin(selected_models)]
        if not filtered_logs.empty:
            filtered_logs = filtered_logs[filtered_logs["model_id"].isin(selected_models)]

    if not filtered_trades.empty:
        trades = filtered_trades.copy()
        trades["created_at"] = pd.to_datetime(trades["created_at"])
        trades["bucket"] = trades["created_at"].dt.floor("h")
        trades["trade_overhead"] = trades[["commission_amount", "tax_amount", "regulatory_fee_amount"]].fillna(0).sum(axis=1)
        fees = trades.groupby(["bucket", "model_id"], as_index=False)["trade_overhead"].sum()
        fees["metric"] = "Trade overhead"
        fees = fees.rename(columns={"bucket": "created_at", "trade_overhead": "value"})[["created_at", "model_id", "metric", "value"]]
        frames.append(fees)
    if not filtered_logs.empty:
        logs = filtered_logs.copy()
        logs["created_at"] = pd.to_datetime(logs["created_at"])
        logs["bucket"] = logs["created_at"].dt.floor("h")
        logs["estimated_cost_usd"] = pd.to_numeric(logs["estimated_cost_usd"], errors="coerce").fillna(0)
        token_cost = logs.groupby(["bucket", "model_id"], as_index=False)["estimated_cost_usd"].sum()
        token_cost["metric"] = "LLM overhead"
        token_cost = token_cost.rename(columns={"bucket": "created_at", "estimated_cost_usd": "value"})[["created_at", "model_id", "metric", "value"]]
        frames.append(token_cost)
    if not frames:
        return None
    cost_df = pd.concat(frames, ignore_index=True)
    color_scale = _model_color_scale(selected_models or cost_df["model_id"].dropna().tolist())
    selection = legend_selection or _legend_highlight_selection("model_id")
    y_domain = _padded_domain(cost_df["value"])
    chart = (
        alt.Chart(cost_df)
        .mark_line(point=True, strokeWidth=2.2)
        .encode(
            x=alt.X("created_at:T", axis=alt.Axis(title=None, format="%y%m%d %H:%M", labelAngle=-25, labelLimit=120)),
            y=alt.Y("value:Q", title="Overhead", scale=alt.Scale(domain=y_domain, zero=False)),
            color=alt.Color("model_id:N", scale=color_scale, legend=None),
            strokeDash=alt.StrokeDash("metric:N", legend=None, sort=["Trade overhead", "LLM overhead"]),
            opacity=alt.condition(selection, alt.value(1.0), alt.value(0.15)),
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
    return _apply_chart_theme(chart)


def market_pulse_chart(history_df: pd.DataFrame) -> alt.Chart:
    instrument_count = max(len(history_df["display_name"].dropna().unique()), 1)
    color_scale = alt.Scale(domain=list(dict.fromkeys(history_df["display_name"].dropna().tolist())), range=COLOR_RANGE[:instrument_count])
    selection = _legend_highlight_selection("display_name")
    return _apply_chart_theme(
        alt.Chart(history_df)
        .mark_line(point=True, strokeWidth=2.2)
        .encode(
            x=alt.X("as_of:T", axis=alt.Axis(title=None, format="%y%m%d %H:%M", labelAngle=-25, labelLimit=120)),
            y=alt.Y("return_1h_pct:Q", title="Hourly move %"),
            color=alt.Color("display_name:N", scale=color_scale, legend=alt.Legend(orient="bottom", columns=min(4, instrument_count), labelLimit=220)),
            opacity=alt.condition(selection, alt.value(1.0), alt.value(0.15)),
            tooltip=[
                alt.Tooltip("display_name:N", title="Instrument"),
                alt.Tooltip("ticker:N", title="Ticker"),
                alt.Tooltip("as_of:T", title="Time"),
                alt.Tooltip("return_1h_pct:Q", title="1h %", format=".3f"),
                alt.Tooltip("return_1d_pct:Q", title="1d %", format=".3f"),
                alt.Tooltip("current_price:Q", title="Price", format=".4f"),
            ],
        )
        .add_params(selection)
        .properties(height=460)
    )


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
            <div>LLM: ${(row.get('llm_cost_usd') or 0):.4f}</div>
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
if "dashboard_auto_refresh" not in st.session_state:
    st.session_state["dashboard_auto_refresh"] = False

auto_refresh_enabled = bool(st.session_state.get("dashboard_auto_refresh", False))
if auto_refresh_enabled:
    components.html("<script>setTimeout(function(){ window.parent.location.reload(); }, 300000);</script>", height=0, width=0)

api_base_url = str(st.session_state.get("dashboard_api_base_url", ""))
selected_only = bool(st.session_state.get("dashboard_selected_only", True))

payload = load_base_data(api_base_url or None, selected_only)
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
    "news_collection_policy": "development_fallback",
    "news_refresh_interval_minutes": 30,
}
scheduler_payload = payload.get("scheduler") or {"markets": []}
market_windows = settings_payload.get("markets", {})

models_df = pd.DataFrame(payload["models"])
rankings_df = pd.DataFrame(payload["rankings"])
portfolios_df = pd.DataFrame(payload["portfolios"])
positions_df = pd.DataFrame(payload["positions"])
trades_df = pd.DataFrame(payload["trades"])
snapshots_df = pd.DataFrame(payload["snapshots"])
news_batches = payload["news"]
logs_all_df = pd.DataFrame(payload.get("logs", []))
runs_df = pd.DataFrame(payload.get("runs", []))

model_options = models_df["model_id"].tolist() if not models_df.empty else []
default_models = models_df.loc[models_df["is_selected"], "model_id"].tolist() if not models_df.empty else []
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
    if not runs_df.empty and "model_id" in runs_df.columns:
        runs_df = runs_df[runs_df["model_id"].isin(chosen_models)]

render_hero(settings_payload, scheduler_payload, rankings_df, news_batches)

scheduler_df = pd.DataFrame(scheduler_payload.get("markets", []))

ranking_tab, performance_tab, market_tab, news_tab, detail_tab, admin_tab = st.tabs(
    ["Ranking", "Performance", "Market Pulse", "Shared News", "Model Detail", "Admin"]
)

with ranking_tab:
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
            "display_name",
            "search_mode",
            "is_free_like",
            sort_column,
            "kr_return_pct",
            "us_return_pct",
            "composite_score",
            "max_drawdown",
            "win_rate",
            "trade_count",
            "llm_cost_usd",
            "pricing_label",
        ]
        rename_map = {
            "model_id": "Model ID",
            "display_name": "Display name",
            "search_mode": "Search",
            "is_free_like": "Free",
            sort_column: period_label,
            "kr_return_pct": "KR return %",
            "us_return_pct": "US return %",
            "composite_score": "Composite",
            "max_drawdown": "MDD",
            "win_rate": "Win rate",
            "trade_count": "Trades",
            "llm_cost_usd": "LLM cost (USD)",
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

with performance_tab:
    st.markdown('<div class="asa-section-label">Trajectory</div>', unsafe_allow_html=True)
    metric_name = st.selectbox("Chart metric", ["total_return_pct", "total_equity"], index=0)
    performance_market = st.selectbox("Performance market", ["All", "KR", "US"], index=0)
    performance_models = st.multiselect("Legend models", chosen_models or model_options, default=(chosen_models or model_options))
    if snapshots_df.empty:
        st.info("No performance snapshots found.")
    else:
        chart_df = snapshots_df.copy()
        if performance_market != "All":
            chart_df = chart_df[chart_df["market_code"] == performance_market]
        if performance_models:
            chart_df = chart_df[chart_df["model_id"].isin(performance_models)]
        if chart_df.empty:
            st.caption("No performance rows match the current filters.")
        else:
            chart_df["created_at"] = pd.to_datetime(chart_df["created_at"])
            x_zoom = alt.selection_interval(encodings=["x"], bind="scales")
            legend_selection = alt.selection_point(fields=["model_id"], bind="legend")
            charts = [performance_chart(chart_df, metric_name, performance_models, x_zoom=x_zoom, legend_selection=legend_selection)]
            buy_sell = buy_sell_chart(trades_df, performance_market, performance_models, x_zoom=x_zoom, legend_selection=legend_selection)
            if buy_sell is not None:
                st.markdown("**Buy / Sell:** Solid line = Buy, dashed line = Sell.")
                charts.append(buy_sell)
            overhead = overhead_chart(trades_df, logs_all_df, performance_market, performance_models, x_zoom=x_zoom, legend_selection=legend_selection)
            if overhead is not None:
                st.markdown("**Overhead:** Solid line = Trade overhead, dashed line = LLM overhead.")
                charts.append(overhead)
            performance_bundle = _apply_chart_theme(alt.vconcat(*charts, spacing=18).add_params(legend_selection, x_zoom))
            chart_col, _ = st.columns([5, 1])
            chart_col.altair_chart(performance_bundle, use_container_width=True)

with market_tab:
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
            latest_rows[["display_name", "current_price", "return_1h_pct", "return_1d_pct", "intraday_volatility_pct", "latest_volume", "is_active"]].rename(
                columns={
                    "display_name": "Instrument",
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
            instrument_registry[["display_name", "is_active", "first_seen_at", "last_seen_at", "delisted_at"]].rename(
                columns={
                    "display_name": "Instrument",
                    "is_active": "Active",
                    "first_seen_at": "First seen",
                    "last_seen_at": "Last seen",
                    "delisted_at": "Delisted at",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
with news_tab:
    st.markdown('<div class="asa-section-label">Shared News</div>', unsafe_allow_html=True)
    if not settings_payload.get("news_enabled", False):
        st.markdown('<div class="asa-warning">Shared news is disabled. This league is running as a pure model benchmark with no external news context.</div>', unsafe_allow_html=True)
    else:
        st.caption(f"Collection policy: {settings_payload.get('news_collection_policy', 'development_fallback')}")
    if not news_batches:
        st.caption("No shared news batches stored yet.")
    for batch in news_batches:
        with st.expander(f"{batch['market_code']} | {batch['batch_key']} | {batch['created_at']}"):
            if batch.get("summary"):
                st.write(batch["summary"])
            items = pd.DataFrame(batch.get("items", []))
            if items.empty:
                st.caption("No items in this batch.")
            else:
                st.dataframe(items, use_container_width=True, hide_index=True)

with detail_tab:
    st.markdown('<div class="asa-section-label">Model Drilldown</div>', unsafe_allow_html=True)
    if not model_options:
        st.info("No models available.")
    else:
        detail_model = st.selectbox("Model", model_options, index=0)
        detail_market = st.selectbox("Market", ["KR", "US"], index=0)
        model_logs = load_model_logs(api_base_url or None, detail_model, detail_market)
        model_runs = runs_df[(runs_df["model_id"] == detail_model) & (runs_df["market_code"] == detail_market)] if not runs_df.empty and {"model_id", "market_code"}.issubset(runs_df.columns) else pd.DataFrame()
        model_portfolios = portfolios_df[(portfolios_df["model_id"] == detail_model) & (portfolios_df["market_code"] == detail_market)] if {"model_id", "market_code"}.issubset(portfolios_df.columns) else pd.DataFrame()
        model_positions = positions_df[(positions_df["model_id"] == detail_model) & (positions_df["market_code"] == detail_market)] if {"model_id", "market_code"}.issubset(positions_df.columns) else pd.DataFrame()
        model_trades = trades_df[(trades_df["model_id"] == detail_model) & (trades_df["market_code"] == detail_market)] if {"model_id", "market_code"}.issubset(trades_df.columns) else pd.DataFrame()
        if not model_portfolios.empty:
            row = model_portfolios.iloc[0]
            detail_metrics = st.columns(4)
            detail_metrics[0].metric("Total equity", _money(float(row["total_equity"])))
            detail_metrics[1].metric("Available cash", _money(float(row["available_cash"])))
            detail_metrics[2].metric("Return", _pct(float(row["total_return_pct"])))
            detail_metrics[3].metric("Positions", int(row["position_count"]))
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

with admin_tab:
    st.markdown('<div class="asa-section-label">Admin Controls</div>', unsafe_allow_html=True)
    st.caption("All timestamps and windows in this tab are shown in UTC.")
    st.text_input("Admin token", type="password", key="dashboard_admin_token", help="Press Enter to apply.")
    current_admin_token = str(st.session_state.get("dashboard_admin_token", ""))
    admin_mode = _is_admin(current_admin_token)
    if not settings.admin_token:
        st.warning("ADMIN_TOKEN is not configured. Admin actions are disabled.")
    elif not admin_mode:
        st.info("Enter the correct admin token above and press Enter to unlock admin actions.")
    else:
        st.text_input("FastAPI base URL", key="dashboard_api_base_url", placeholder="http://127.0.0.1:8000")
        st.checkbox("Selected models only", key="dashboard_selected_only")
        st.toggle("Auto refresh every 5 minutes", key="dashboard_auto_refresh")
        st.success("Admin mode enabled")
        for message in st.session_state.pop("admin_action_messages", []):
            st.info(message)

        st.markdown("**News and runtime controls**")
        scheduler_admin_df = _utc_frame(
            scheduler_df,
            ["last_started_at", "last_completed_at", "next_run_at", "news_last_started_at", "news_last_completed_at"],
        )
        runtime_cols = st.columns([1.2, 1.2, 1.6])
        runtime_cols[0].metric("Trade cadence", f"{int(settings_payload.get('decision_interval_minutes', 60))} min")
        runtime_cols[1].metric("News refresh cadence", f"{int(settings_payload.get('news_refresh_interval_minutes', 30))} min")
        runtime_cols[2].metric("News policy", str(settings_payload.get("news_collection_policy", "development_fallback")))

        if not scheduler_admin_df.empty:
            news_status_df = scheduler_admin_df[[
                "market_code",
                "window_label_utc",
                "in_active_window",
                "news_in_active_window",
                "news_is_due",
                "news_last_status",
                "news_last_completed_at",
                "news_last_message",
            ]].rename(
                columns={
                    "market_code": "Market",
                    "window_label_utc": "Runtime window (UTC)",
                    "in_active_window": "Trade window active",
                    "news_in_active_window": "News window active",
                    "news_is_due": "News due now",
                    "news_last_status": "Last news status",
                    "news_last_completed_at": "Last news refresh (UTC)",
                    "news_last_message": "Last news message",
                }
            )
            st.dataframe(news_status_df, use_container_width=True, hide_index=True)

        with st.form("runtime_settings_form"):
            cadence = st.slider(
                "Decision interval (minutes)",
                min_value=1,
                max_value=180,
                step=1,
                value=int(settings_payload.get("decision_interval_minutes", 60)),
            )
            news_refresh_interval = st.slider(
                "News refresh interval (minutes)",
                min_value=1,
                max_value=120,
                step=1,
                value=int(settings_payload.get("news_refresh_interval_minutes", 30)),
            )
            weekday_defaults = settings_payload.get("active_weekdays", [0, 1, 2, 3, 4])
            active_weekdays = st.multiselect(
                "Active weekdays",
                options=[value for value, _ in WEEKDAY_OPTIONS],
                default=weekday_defaults,
                format_func=lambda value: dict(WEEKDAY_OPTIONS)[value],
            )
            news_enabled = st.checkbox("Enable shared news", value=bool(settings_payload.get("news_enabled", False)))
            news_collection_policy = st.selectbox(
                "News collection policy",
                ["development_fallback", "live_strict"],
                index=0 if str(settings_payload.get("news_collection_policy", "development_fallback")) == "development_fallback" else 1,
                help="development_fallback keeps wider local testing fallback windows. live_strict uses only the current 15-minute window inside the active runtime window.",
            )
            st.markdown("**Runtime windows (UTC)**")
            kr_window = market_windows.get("KR", {})
            us_window = market_windows.get("US", {})
            kr_start_utc = st.text_input("KR window start (UTC)", value=kr_window.get("window_start_utc", "23:00"))
            kr_end_utc = st.text_input("KR window end (UTC)", value=kr_window.get("window_end_utc", "07:00"))
            us_start_utc = st.text_input("US window start (UTC)", value=us_window.get("window_start_utc", "12:00"))
            us_end_utc = st.text_input("US window end (UTC)", value=us_window.get("window_end_utc", "22:00"))
            if st.form_submit_button("Save runtime settings"):
                payload = {
                    "decision_interval_minutes": cadence,
                    "active_weekdays": sorted(active_weekdays),
                    "news_enabled": news_enabled,
                    "news_collection_policy": news_collection_policy,
                    "news_refresh_interval_minutes": news_refresh_interval,
                    "markets": {
                        "KR": {
                            "enabled": True,
                            "window_start": kr_window.get("window_start", "08:00"),
                            "window_end": kr_window.get("window_end", "16:00"),
                            "window_start_utc": kr_start_utc,
                            "window_end_utc": kr_end_utc,
                        },
                        "US": {
                            "enabled": True,
                            "window_start": us_window.get("window_start", "08:00"),
                            "window_end": us_window.get("window_end", "17:00"),
                            "window_start_utc": us_start_utc,
                            "window_end_utc": us_end_utc,
                        },
                    },
                }
                if api_base_url:
                    with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
                        client.put("/admin/settings", headers={"X-Admin-Token": current_admin_token}, json=payload).raise_for_status()
                else:
                    with SessionLocal() as session:
                        update_runtime_settings(session, payload)
                        session.commit()
                refresh_all()
                st.rerun()

        st.markdown("**Manual actions**")
        action_cols = st.columns(2)
        if action_cols[0].button("Refresh shared news now"):
            if api_base_url:
                with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=120.0) as client:
                    result = client.post("/admin/news/refresh", headers={"X-Admin-Token": current_admin_token}).json()
            else:
                with SessionLocal() as session:
                    result = {"messages": run_manual_news_refreshes(session)}
            st.session_state["admin_action_messages"] = result.get("messages", [])
            refresh_all()
            st.rerun()
        if action_cols[1].button("Run full trade cycle now"):
            if api_base_url:
                with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=600.0) as client:
                    result = client.post("/admin/trades/run", headers={"X-Admin-Token": current_admin_token}).json()
            else:
                with SessionLocal() as session:
                    result = {"messages": run_manual_trade_cycles(session)}
            st.session_state["admin_action_messages"] = result.get("messages", [])
            refresh_all()
            st.rerun()

        st.markdown("**Runtime secrets**")
        show_secrets = st.toggle("Show secrets", key="dashboard_show_admin_secrets")
        admin_secrets = load_admin_secrets(api_base_url or None, current_admin_token)
        with st.form("runtime_secrets_form"):
            openrouter_value = st.text_input(
                "OpenRouter API token",
                value=admin_secrets.get("openrouter_api_key") or "",
                type="default" if show_secrets else "password",
            )
            marketaux_value = st.text_input(
                "Marketaux API token",
                value=admin_secrets.get("marketaux_api_token") or "",
                type="default" if show_secrets else "password",
            )
            st.caption(f"Masked preview: OpenRouter={_mask_secret(admin_secrets.get('openrouter_api_key'))} | Marketaux={_mask_secret(admin_secrets.get('marketaux_api_token'))}")
            if st.form_submit_button("Save secrets"):
                payload = {
                    "openrouter_api_key": openrouter_value,
                    "marketaux_api_token": marketaux_value,
                }
                if api_base_url:
                    with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
                        client.put("/admin/secrets", headers={"X-Admin-Token": current_admin_token}, json=payload).raise_for_status()
                else:
                    with SessionLocal() as session:
                        update_runtime_secrets(session, payload)
                        session.commit()
                refresh_all()
                st.rerun()

        st.markdown("**Visible models**")
        visible_models_df = models_df[["model_id", "display_name"]].copy() if not models_df.empty else pd.DataFrame(columns=["model_id", "display_name"])
        visible_models_df.insert(0, "visible", visible_models_df["model_id"].isin(st.session_state.get("dashboard_models", [])))
        edited_visible_models = st.data_editor(
            visible_models_df.rename(columns={"visible": "Visible", "model_id": "Profile ID", "display_name": "Display name"}),
            use_container_width=True,
            hide_index=True,
            height=840,
            disabled=["Profile ID", "Display name"],
            key="dashboard_visible_models_editor",
            column_config={"Visible": st.column_config.CheckboxColumn("Visible")},
        )
        visible_selection = edited_visible_models.loc[edited_visible_models["Visible"], "Profile ID"].tolist() if not edited_visible_models.empty else []
        utility_cols = st.columns([1, 1.2, 2.2])
        if utility_cols[0].button("Apply visible models"):
            st.session_state["dashboard_models"] = visible_selection or model_options
            refresh_all()
            st.rerun()
        if utility_cols[1].button("Refresh data"):
            refresh_all()
            st.rerun()
        utility_cols[2].caption("Visible models now show about three times more rows than before. Changes apply after you press Apply visible models.")

        st.markdown("**Investment profiles**")
        profile_columns = [
            "model_id",
            "display_name",
            "request_model_id",
            "is_selected",
            "api_enabled",
            "search_mode",
            "uses_custom_prompt",
            "pricing_label",
        ]
        st.dataframe(
            models_df[profile_columns].rename(
                columns={
                    "model_id": "Profile ID",
                    "display_name": "Display name",
                    "request_model_id": "Request model",
                    "is_selected": "In league",
                    "api_enabled": "API enabled",
                    "search_mode": "Search",
                    "uses_custom_prompt": "Custom prompt",
                    "pricing_label": "Pricing",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        profile_ids = models_df["model_id"].tolist()
        runtime_target = st.selectbox("Profile runtime control", profile_ids, index=0 if profile_ids else None)
        runtime_row = models_df.loc[models_df["model_id"] == runtime_target].iloc[0] if runtime_target else None
        runtime_selected = bool(runtime_row["is_selected"]) if runtime_row is not None else False
        runtime_api_enabled = bool(runtime_row["api_enabled"]) if runtime_row is not None else True
        runtime_prompt = (runtime_row.get("custom_prompt") or "") if runtime_row is not None else ""
        keep_selected = st.checkbox("Selected for league", value=runtime_selected)
        api_enabled = st.checkbox("Enable API calls", value=runtime_api_enabled)
        custom_prompt = st.text_area(
            "Custom prompt template",
            value=runtime_prompt,
            height=180,
            help="Optional. This prompt is used as the profile prompt for both markets. You can use {market_code}, {market_name}, {profile_id}, {request_model_id}, and {display_name} placeholders.",
        )
        control_cols = st.columns([1, 1, 1.4])
        if control_cols[0].button("Save profile runtime", disabled=not bool(runtime_target)):
            payload = {
                "is_selected": keep_selected,
                "api_enabled": api_enabled,
                "custom_prompt": custom_prompt,
            }
            if api_base_url:
                with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
                    client.patch(
                        f"/admin/models/{runtime_target}",
                        headers={"X-Admin-Token": current_admin_token},
                        json=payload,
                    ).raise_for_status()
            else:
                with SessionLocal() as session:
                    update_model_runtime(
                        session,
                        runtime_target,
                        is_selected=keep_selected,
                        api_enabled=api_enabled,
                        custom_prompt=custom_prompt,
                    )
                    session.commit()
            refresh_all()
            st.rerun()
        if control_cols[1].button("Delete profile", disabled=not bool(runtime_target)):
            if api_base_url:
                with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
                    client.delete(
                        f"/admin/models/{runtime_target}",
                        headers={"X-Admin-Token": current_admin_token},
                    ).raise_for_status()
            else:
                with SessionLocal() as session:
                    delete_model_profile(session, runtime_target)
                    session.commit()
            refresh_all()
            st.rerun()
        control_cols[2].caption("Turn off API calls to pause token usage without removing the profile from rankings and history.")

        st.markdown("**Create or update investment profile**")
        with st.form("model_add_form"):
            profile_id = st.text_input("Profile ID")
            request_model_id = st.text_input("Request model ID")
            display_name = st.text_input("Display name")
            search_mode = st.selectbox("Search mode", ["off", "on"], index=0)
            prompt_price = st.number_input("Prompt price / 1M", min_value=0.0, value=0.0, step=0.01)
            completion_price = st.number_input("Completion price / 1M", min_value=0.0, value=0.0, step=0.01)
            select_profile = st.checkbox("Select profile immediately", value=True)
            api_enabled_new = st.checkbox("Enable API calls immediately", value=True)
            custom_prompt_new = st.text_area("Custom prompt template (optional)", height=180)
            if st.form_submit_button("Add or update profile"):
                payload = {
                    "profile_id": profile_id,
                    "request_model_id": request_model_id,
                    "display_name": display_name or profile_id,
                    "search_mode": search_mode,
                    "select_profile": select_profile,
                    "api_enabled": api_enabled_new,
                    "custom_prompt": custom_prompt_new,
                    "prompt_price_per_million": prompt_price if prompt_price > 0 else None,
                    "completion_price_per_million": completion_price if completion_price > 0 else None,
                }
                if api_base_url:
                    with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
                        client.post("/admin/models", headers={"X-Admin-Token": current_admin_token}, json=payload).raise_for_status()
                else:
                    with SessionLocal() as session:
                        create_or_update_model_profile(
                            session,
                            profile_id=payload["profile_id"],
                            request_model_id=payload["request_model_id"],
                            display_name=payload["display_name"],
                            search_mode=payload["search_mode"],
                            select_profile=payload["select_profile"],
                            prompt_price_per_million=payload["prompt_price_per_million"],
                            completion_price_per_million=payload["completion_price_per_million"],
                            custom_prompt=payload["custom_prompt"],
                            api_enabled=payload["api_enabled"],
                        )
                        session.commit()
                refresh_all()
                st.rerun()

        if not runs_df.empty:
            st.markdown("**Recent run queue (UTC)**")
            runs_admin_df = _utc_frame(runs_df, ["requested_at", "started_at", "completed_at", "snapshot_as_of"])
            st.dataframe(
                runs_admin_df[[
                    "requested_at",
                    "model_id",
                    "market_code",
                    "status",
                    "trigger_source",
                    "candidate_count",
                    "summary_message",
                    "error_message",
                ]].rename(
                    columns={
                        "requested_at": "Requested at (UTC)",
                        "model_id": "Model",
                        "market_code": "Market",
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

        if not scheduler_admin_df.empty:
            st.markdown("**Scheduler status (UTC)**")
            st.dataframe(
                scheduler_admin_df[["market_code", "market_timezone", "window_label_utc", "in_active_window", "is_due", "last_status", "last_completed_at", "next_run_at", "news_in_active_window", "news_is_due", "news_last_status", "news_last_completed_at", "news_last_message"]].rename(
                    columns={
                        "market_code": "Market",
                        "market_timezone": "Timezone",
                        "window_label_utc": "Window (UTC)",
                        "in_active_window": "Trade window",
                        "is_due": "Trade due now",
                        "last_status": "Trade last status",
                        "last_completed_at": "Trade last completed (UTC)",
                        "next_run_at": "Next trade run (UTC)",
                        "news_in_active_window": "News window",
                        "news_is_due": "News due now",
                        "news_last_status": "News last status",
                        "news_last_completed_at": "News last completed (UTC)",
                        "news_last_message": "News last message",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

        st.caption("Destructive model deletion remains admin-only. Use API disable to stop token usage without deleting history.")

        st.markdown("**Reset simulation**")
        if st.button("Reset all trading data and restart", type="primary"):
            if api_base_url:
                with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
                    client.post("/admin/reset", headers={"X-Admin-Token": current_admin_token}, params={"reset_prompts": "true"}).raise_for_status()
            else:
                with SessionLocal() as session:
                    reset_simulation(session, reset_prompts=True)
                    session.commit()
            refresh_all()
            st.rerun()
