from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

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

st.set_page_config(page_title="AI Stock Arena", layout="wide")
st.title("AI Stock Arena")
st.caption("Pure model benchmark dashboard for shared-data virtual trading.")


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


api_base_url = st.sidebar.text_input(
    "FastAPI base URL",
    value=settings.api_base_url or "",
    placeholder="http://127.0.0.1:8000",
)
selected_only = st.sidebar.checkbox("Selected models only", value=True)
admin_token = st.sidebar.text_input("Admin token", value="", type="password")
admin_mode = _is_admin(admin_token)
if st.sidebar.button("Refresh"):
    refresh_all()

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

models_df = pd.DataFrame(payload["models"])
rankings_df = pd.DataFrame(payload["rankings"])
portfolios_df = pd.DataFrame(payload["portfolios"])
positions_df = pd.DataFrame(payload["positions"])
trades_df = pd.DataFrame(payload["trades"])
snapshots_df = pd.DataFrame(payload["snapshots"])
news_batches = payload["news"]

model_options = models_df["model_id"].tolist() if not models_df.empty else []
default_models = models_df.loc[models_df["is_selected"], "model_id"].tolist() if not models_df.empty else []
chosen_models = st.sidebar.multiselect("Models", model_options, default=default_models or model_options)
if chosen_models:
    rankings_df = rankings_df[rankings_df["model_id"].isin(chosen_models)]
    portfolios_df = portfolios_df[portfolios_df["model_id"].isin(chosen_models)]
    positions_df = positions_df[positions_df["model_id"].isin(chosen_models)]
    trades_df = trades_df[trades_df["model_id"].isin(chosen_models)]
    snapshots_df = snapshots_df[snapshots_df["model_id"].isin(chosen_models)]
    models_df = models_df[models_df["model_id"].isin(chosen_models)]

market_windows = settings_payload.get("markets", {})
utc_windows = {
    item.get("market_code"): item.get("window_label_utc", "n/a")
    for item in scheduler_payload.get("markets", [])
}
window_caption = " | ".join(f"{code}: {utc_windows.get(code, 'n/a')}" for code in market_windows)
st.caption(
    f"Cadence: every {settings_payload.get('decision_interval_minutes', 60)} minutes | "
    f"Weekdays: {_weekday_labels(settings_payload.get('active_weekdays', [0, 1, 2, 3, 4]))} | "
    f"Execution window (UTC): {window_caption}"
)

metric_cols = st.columns(4)
metric_cols[0].metric("Selected models", overview["selected_model_count"])
metric_cols[1].metric("Visible portfolios", overview["portfolio_count"])
metric_cols[2].metric("Combined equity", _money(overview["combined_total_equity"]))
metric_cols[3].metric("Combined return", _pct(overview["combined_return_pct"]))

scheduler_df = pd.DataFrame(scheduler_payload.get("markets", []))
if not scheduler_df.empty:
    st.markdown("**Scheduler status**")
    st.dataframe(
        scheduler_df[
            [
                "market_code",
                "market_timezone",
                "window_label_utc",
                "enabled",
                "in_active_window",
                "is_due",
                "last_status",
                "last_message",
                "last_started_at",
                "last_completed_at",
                "next_run_at",
            ]
        ].rename(
            columns={
                "market_code": "Market",
                "market_timezone": "Timezone",
                "window_label_utc": "Window (UTC)",
                "enabled": "Enabled",
                "in_active_window": "In window",
                "is_due": "Due now",
                "last_status": "Last status",
                "last_message": "Last message",
                "last_started_at": "Last started",
                "last_completed_at": "Last completed",
                "next_run_at": "Next run",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

ranking_tab, performance_tab, news_tab, detail_tab, admin_tab = st.tabs(
    ["Ranking", "Performance", "Shared News", "Model Detail", "Admin"]
)

with ranking_tab:
    st.subheader("Model ranking")
    period_map = {
        "Since inception": "current_return_pct",
        "1 day": "return_1d_pct",
        "1 week": "return_1w_pct",
        "1 month": "return_1m_pct",
    }
    period_label = st.selectbox("Ranking period", list(period_map.keys()), index=0)
    sort_column = period_map[period_label]
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
        st.dataframe(
            ranked[ranking_columns].rename(columns=rename_map),
            use_container_width=True,
        )

with performance_tab:
    st.subheader("Performance history")
    metric_name = st.selectbox("Chart metric", ["total_return_pct", "total_equity"], index=0)
    if snapshots_df.empty:
        st.info("No performance snapshots found.")
    else:
        chart_df = snapshots_df.copy()
        chart_df["series"] = chart_df["model_id"] + " | " + chart_df["market_code"]
        pivoted = chart_df.pivot_table(index="created_at", columns="series", values=metric_name, aggfunc="last").sort_index()
        st.line_chart(pivoted)

with news_tab:
    st.subheader("Shared news feed")
    if not settings_payload.get("news_enabled", False):
        st.info("Shared news is currently disabled. All models are running without external news context.")
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
    st.subheader("Model detail")
    if not model_options:
        st.info("No models available.")
    else:
        detail_model = st.selectbox("Model", model_options, index=0)
        detail_market = st.selectbox("Market", ["KR", "US"], index=0)
        model_logs = load_model_logs(api_base_url or None, detail_model, detail_market)
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
    st.subheader("Admin controls")
    if not settings.admin_token:
        st.warning("ADMIN_TOKEN is not configured. Admin actions are disabled.")
    elif not admin_mode:
        st.info("Enter the correct admin token in the sidebar to unlock settings, reset, and model management.")
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
                        client.put("/admin/settings", headers={"X-Admin-Token": admin_token}, json=payload).raise_for_status()
                else:
                    with SessionLocal() as session:
                        update_runtime_settings(session, payload)
                        session.commit()
                refresh_all()
                st.rerun()

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
                        client.post("/admin/models", headers={"X-Admin-Token": admin_token}, json=payload).raise_for_status()
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

        delete_options = models_df["model_id"].tolist() if not models_df.empty else []
        delete_target = st.selectbox("Delete model profile", delete_options, index=0 if delete_options else None)
        if st.button("Delete selected model profile", type="secondary", disabled=not bool(delete_target)):
            if api_base_url:
                with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
                    client.delete(f"/admin/models/{delete_target}", headers={"X-Admin-Token": admin_token}).raise_for_status()
            else:
                with SessionLocal() as session:
                    delete_model_profile(session, delete_target)
                    session.commit()
            refresh_all()
            st.rerun()

        st.markdown("**Reset simulation**")
        if st.button("Reset all trading data and restart", type="primary"):
            if api_base_url:
                with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20.0) as client:
                    client.post("/admin/reset", headers={"X-Admin-Token": admin_token}, params={"reset_prompts": "true"}).raise_for_status()
            else:
                with SessionLocal() as session:
                    reset_simulation(session, reset_prompts=True)
                    session.commit()
            refresh_all()
            st.rerun()
