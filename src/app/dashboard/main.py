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

from app.api.query_service import (
    get_overview,
    get_runtime_settings_response,
    get_scheduler_status_response,
    list_llm_logs,
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
    set_model_selection,
    update_runtime_settings,
)

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


def _is_admin(token: str) -> bool:
    return bool(settings.admin_token and token and token == settings.admin_token)


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
        .asa-strip {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-top: 20px;
        }
        .asa-stat {
            padding: 14px 16px;
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid rgba(148, 163, 184, 0.16);
            border-radius: 18px;
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


def render_hero(settings_payload: dict, scheduler_payload: dict, rankings_df: pd.DataFrame) -> None:
    market_windows = settings_payload.get("markets", {})
    utc_windows = {
        item.get("market_code"): item.get("window_label_utc", "n/a")
        for item in scheduler_payload.get("markets", [])
    }
    windows_line = " | ".join(f"{code}: {utc_windows.get(code, 'n/a')}" for code in market_windows)
    leader_name = "No active model"
    leader_return = "n/a"
    if not rankings_df.empty:
        leader = rankings_df.sort_values(by=["current_return_pct"], ascending=False, na_position="last").iloc[0]
        leader_name = html.escape(str(leader.get("display_name") or leader.get("model_id")))
        leader_return = _pct(leader.get("current_return_pct"))
    news_mode = "OFF" if not settings_payload.get("news_enabled", False) else str(settings_payload.get("news_mode", "shared_on")).upper()
    st.markdown(
        f"""
        <section class="asa-hero">
            <div class="asa-eyebrow">Pure Model Benchmark</div>
            <div style="display:flex; align-items:flex-end; gap:14px; flex-wrap:wrap;">
                <h1 class="asa-headline">AI Stock Arena</h1>
                <div class="asa-signature">eljja1@gmail.com</div>
            </div>
            <div class="asa-subhead">Rank LLMs by fee-adjusted return, drawdown, and execution cost. Same markets, same cadence, same rules.</div>
            <div class="asa-strip">
                <div class="asa-stat"><div class="asa-stat-label">Cadence</div><div class="asa-stat-value">Every {settings_payload.get('decision_interval_minutes', 60)} min</div></div>
                <div class="asa-stat"><div class="asa-stat-label">Windows (UTC)</div><div class="asa-stat-value">{html.escape(windows_line)}</div></div>
                <div class="asa-stat"><div class="asa-stat-label">Current Leader</div><div class="asa-stat-value">{leader_name} | {leader_return}</div></div>
                <div class="asa-stat"><div class="asa-stat-label">Shared News</div><div class="asa-stat-value">{html.escape(news_mode)}</div></div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Active weekdays: {_weekday_labels(settings_payload.get('active_weekdays', [0, 1, 2, 3, 4]))}")


def model_allocation_frame(model_id: str, positions_df: pd.DataFrame, portfolios_df: pd.DataFrame, top_n: int = 6) -> pd.DataFrame:
    if positions_df.empty or portfolios_df.empty:
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


COLOR_RANGE = ["#60a5fa", "#34d399", "#f472b6", "#f59e0b", "#a78bfa", "#f87171", "#22d3ee", "#fb7185"]


def allocation_chart(allocation_df: pd.DataFrame) -> alt.Chart:
    if allocation_df.empty:
        return alt.Chart(pd.DataFrame({"label": [], "weight_pct": []})).mark_bar()
    return (
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


def performance_chart(chart_df: pd.DataFrame, metric_name: str) -> alt.Chart:
    series_count = max(len(chart_df["series"].unique()), 1)
    base = alt.Chart(chart_df).encode(
        x=alt.X("created_at:T", axis=alt.Axis(title=None, format="%y%m%d %H:%M", labelAngle=-25, labelLimit=120)),
        y=alt.Y(f"{metric_name}:Q", title=metric_name.replace("_", " ").title()),
        color=alt.Color(
            "series:N",
            legend=alt.Legend(orient="bottom", columns=min(4, series_count), labelLimit=240, symbolLimit=series_count),
            scale=alt.Scale(range=COLOR_RANGE * 4),
        ),
        tooltip=[alt.Tooltip("series:N", title="Series"), alt.Tooltip("created_at:T", title="Time"), alt.Tooltip(f"{metric_name}:Q", title="Value", format=".4f")],
    )
    line = base.mark_line(strokeWidth=2.4)
    points = base.mark_point(size=56, filled=True)
    return (line + points).properties(height=520)


def overhead_chart(trades_df: pd.DataFrame, logs_df: pd.DataFrame, market_filter: str, selected_models: list[str]) -> alt.Chart | None:
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
        buy_sell = trades.groupby(["bucket", "side"], as_index=False)["gross_amount"].sum()
        buy_sell["metric"] = buy_sell["side"].map({"BUY": "Buy notional", "SELL": "Sell notional"}).fillna(buy_sell["side"])
        buy_sell = buy_sell.rename(columns={"bucket": "created_at", "gross_amount": "value"})[["created_at", "metric", "value"]]
        frames.append(buy_sell)
        fees = trades.groupby("bucket", as_index=False)["trade_overhead"].sum()
        fees["metric"] = "Trade overhead"
        fees = fees.rename(columns={"bucket": "created_at", "trade_overhead": "value"})[["created_at", "metric", "value"]]
        frames.append(fees)
    if not filtered_logs.empty:
        logs = filtered_logs.copy()
        logs["created_at"] = pd.to_datetime(logs["created_at"])
        logs["bucket"] = logs["created_at"].dt.floor("h")
        logs["estimated_cost_usd"] = pd.to_numeric(logs["estimated_cost_usd"], errors="coerce").fillna(0)
        token_cost = logs.groupby("bucket", as_index=False)["estimated_cost_usd"].sum()
        token_cost["metric"] = "LLM overhead"
        token_cost = token_cost.rename(columns={"bucket": "created_at", "estimated_cost_usd": "value"})[["created_at", "metric", "value"]]
        frames.append(token_cost)
    if not frames:
        return None
    cost_df = pd.concat(frames, ignore_index=True)
    return (
        alt.Chart(cost_df)
        .mark_line(point=True, strokeWidth=2.2)
        .encode(
            x=alt.X("created_at:T", axis=alt.Axis(title=None, format="%y%m%d %H:%M", labelAngle=-25, labelLimit=120)),
            y=alt.Y("value:Q", title="Flow / overhead"),
            color=alt.Color("metric:N", scale=alt.Scale(range=COLOR_RANGE), legend=alt.Legend(orient="bottom", columns=2)),
            tooltip=[alt.Tooltip("metric:N", title="Metric"), alt.Tooltip("created_at:T", title="Time"), alt.Tooltip("value:Q", title="Value", format=".4f")],
        )
        .properties(height=320)
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
    rankings_df = rankings_df[rankings_df["model_id"].isin(chosen_models)]
    portfolios_df = portfolios_df[portfolios_df["model_id"].isin(chosen_models)]
    positions_df = positions_df[positions_df["model_id"].isin(chosen_models)]
    trades_df = trades_df[trades_df["model_id"].isin(chosen_models)]
    snapshots_df = snapshots_df[snapshots_df["model_id"].isin(chosen_models)]
    models_df = models_df[models_df["model_id"].isin(chosen_models)]
    if not logs_all_df.empty:
        logs_all_df = logs_all_df[logs_all_df["model_id"].isin(chosen_models)]
    if not runs_df.empty:
        runs_df = runs_df[runs_df["model_id"].isin(chosen_models)]

render_hero(settings_payload, scheduler_payload, rankings_df)

scheduler_df = pd.DataFrame(scheduler_payload.get("markets", []))

ranking_tab, performance_tab, news_tab, detail_tab, admin_tab = st.tabs(
    ["Ranking", "Performance", "Shared News", "Model Detail", "Admin"]
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
    performance_models = st.multiselect("Legend models", chosen_models or model_options, default=(chosen_models or model_options)[:8])
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
            chart_df["series"] = chart_df["model_id"] + " | " + chart_df["market_code"]
            st.altair_chart(performance_chart(chart_df, metric_name), use_container_width=True)
            overhead = overhead_chart(trades_df, logs_all_df, performance_market, performance_models)
            if overhead is not None:
                st.markdown("**Buy / Sell / Overhead**")
                st.altair_chart(overhead, use_container_width=True)

with news_tab:
    st.markdown('<div class="asa-section-label">Shared News</div>', unsafe_allow_html=True)
    if not settings_payload.get("news_enabled", False):
        st.markdown('<div class="asa-warning">Shared news is disabled. This league is running as a pure model benchmark with no external news context.</div>', unsafe_allow_html=True)
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
        model_runs = runs_df[(runs_df["model_id"] == detail_model) & (runs_df["market_code"] == detail_market)] if not runs_df.empty else pd.DataFrame()
        model_portfolios = portfolios_df[(portfolios_df["model_id"] == detail_model) & (portfolios_df["market_code"] == detail_market)]
        model_positions = positions_df[(positions_df["model_id"] == detail_model) & (positions_df["market_code"] == detail_market)]
        model_trades = trades_df[(trades_df["model_id"] == detail_model) & (trades_df["market_code"] == detail_market)]
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
    st.text_input("Admin token", type="password", key="dashboard_admin_token", help="Press Enter to apply.")
    st.text_input("FastAPI base URL", key="dashboard_api_base_url", placeholder="http://127.0.0.1:8000")
    st.checkbox("Selected models only", key="dashboard_selected_only")
    st.multiselect("Visible models", model_options, key="dashboard_models")
    if st.button("Refresh data"):
        refresh_all()
        st.rerun()
    current_admin_token = str(st.session_state.get("dashboard_admin_token", ""))
    admin_mode = _is_admin(current_admin_token)
    if not settings.admin_token:
        st.warning("ADMIN_TOKEN is not configured. Admin actions are disabled.")
    elif not admin_mode:
        st.info("Enter the correct admin token above and press Enter to unlock admin actions.")
    else:
        st.success("Admin mode enabled")
        with st.form("runtime_settings_form"):
            cadence = st.slider(
                "Decision interval (minutes)",
                min_value=15,
                max_value=180,
                step=15,
                value=int(settings_payload.get("decision_interval_minutes", 60)),
            )
            weekday_defaults = settings_payload.get("active_weekdays", [0, 1, 2, 3, 4])
            active_weekdays = st.multiselect(
                "Active weekdays",
                options=[value for value, _ in WEEKDAY_OPTIONS],
                default=weekday_defaults,
                format_func=lambda value: dict(WEEKDAY_OPTIONS)[value],
            )
            kr_start = st.text_input("KR window start (market local)", value=market_windows.get("KR", {}).get("window_start", "08:00"))
            kr_end = st.text_input("KR window end (market local)", value=market_windows.get("KR", {}).get("window_end", "16:00"))
            us_start = st.text_input("US window start (market local)", value=market_windows.get("US", {}).get("window_start", "08:00"))
            us_end = st.text_input("US window end (market local)", value=market_windows.get("US", {}).get("window_end", "17:00"))
            news_enabled = st.checkbox("Enable shared news", value=bool(settings_payload.get("news_enabled", False)))
            if st.form_submit_button("Save runtime settings"):
                payload = {
                    "decision_interval_minutes": cadence,
                    "active_weekdays": sorted(active_weekdays),
                    "news_enabled": news_enabled,
                    "markets": {
                        "KR": {"enabled": True, "window_start": kr_start, "window_end": kr_end},
                        "US": {"enabled": True, "window_start": us_start, "window_end": us_end},
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

        st.markdown("**Visibility and participation**")
        visibility_target = st.selectbox("Toggle model participation", models_df["model_id"].tolist(), index=0 if not models_df.empty else None)
        visibility_default = bool(models_df.loc[models_df["model_id"] == visibility_target, "is_selected"].iloc[0]) if visibility_target else False
        keep_selected = st.checkbox("Selected for league", value=visibility_default)
        if st.button("Save participation state", disabled=not bool(visibility_target)):
            if api_base_url:
                with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
                    client.patch(
                        f"/admin/models/{visibility_target}/selection",
                        headers={"X-Admin-Token": current_admin_token},
                        json={"is_selected": keep_selected},
                    ).raise_for_status()
            else:
                with SessionLocal() as session:
                    set_model_selection(session, visibility_target, keep_selected)
                    session.commit()
            refresh_all()
            st.rerun()
        st.caption("Use participation toggle to keep data but remove a model from the active league.")

        st.markdown("**Model management**")
        with st.form("model_add_form"):
            profile_id = st.text_input("Profile ID")
            request_model_id = st.text_input("Request model ID")
            display_name = st.text_input("Display name")
            search_mode = st.selectbox("Search mode", ["off", "on"], index=0)
            prompt_price = st.number_input("Prompt price / 1M", min_value=0.0, value=0.0, step=0.01)
            completion_price = st.number_input("Completion price / 1M", min_value=0.0, value=0.0, step=0.01)
            select_profile = st.checkbox("Select profile immediately", value=True)
            if st.form_submit_button("Add or update model"):
                payload = {
                    "profile_id": profile_id,
                    "request_model_id": request_model_id,
                    "display_name": display_name or profile_id,
                    "search_mode": search_mode,
                    "select_profile": select_profile,
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
                        )
                        session.commit()
                refresh_all()
                st.rerun()

        if not runs_df.empty:
            st.markdown("**Recent run queue**")
            st.dataframe(
                runs_df[[
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
                        "requested_at": "Requested at",
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

        if not scheduler_df.empty:
            st.markdown("**Scheduler status**")
            st.dataframe(
                scheduler_df[["market_code", "market_timezone", "window_label_utc", "in_active_window", "is_due", "last_status", "last_completed_at", "next_run_at"]].rename(
                    columns={
                        "market_code": "Market",
                        "market_timezone": "Timezone",
                        "window_label_utc": "Window (UTC)",
                        "in_active_window": "In window",
                        "is_due": "Due now",
                        "last_status": "Last status",
                        "last_completed_at": "Last completed",
                        "next_run_at": "Next run",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

        st.caption("Destructive model deletion is no longer available in the dashboard. Use the admin API only if you need a permanent purge.")

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


