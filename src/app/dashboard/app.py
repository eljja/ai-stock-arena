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

from app.api.query_service import get_overview, list_models, list_portfolios, list_positions, list_snapshots, list_trades
from app.config.loader import load_settings
from app.db.session import SessionLocal

settings = load_settings()

st.set_page_config(page_title="AI Stock Arena", layout="wide")
st.title("AI Stock Arena")
st.caption("Selected models, pricing, and virtual portfolio state.")


@st.cache_data(ttl=30, show_spinner=False)
def load_dashboard_data(
    api_base_url: str | None,
    market_code: str | None,
    selected_only: bool,
) -> dict[str, object]:
    if api_base_url:
        return _load_from_api(api_base_url=api_base_url, market_code=market_code, selected_only=selected_only)
    return _load_from_db(market_code=market_code, selected_only=selected_only)


def _load_from_api(api_base_url: str, market_code: str | None, selected_only: bool) -> dict[str, object]:
    params = {"selected_only": str(selected_only).lower()}
    if market_code:
        params["market_code"] = market_code

    with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=15.0) as client:
        overview = client.get("/overview", params=params).json()
        models = client.get("/models", params={"selected_only": "false"}).json()
        portfolios = client.get("/portfolios", params=params).json()
        positions = client.get("/positions", params=params).json()
        trades = client.get("/trades", params={**params, "limit": 100}).json()
        snapshots = client.get("/snapshots", params={**params, "limit": 300}).json()

    return {
        "overview": overview,
        "models": models,
        "portfolios": portfolios,
        "positions": positions,
        "trades": trades,
        "snapshots": snapshots,
    }


def _load_from_db(market_code: str | None, selected_only: bool) -> dict[str, object]:
    with SessionLocal() as session:
        return {
            "overview": get_overview(session=session, market_code=market_code, selected_only=selected_only).model_dump(mode="json"),
            "models": [item.model_dump(mode="json") for item in list_models(session=session, selected_only=False)],
            "portfolios": [
                item.model_dump(mode="json")
                for item in list_portfolios(session=session, market_code=market_code, selected_only=selected_only)
            ],
            "positions": [
                item.model_dump(mode="json")
                for item in list_positions(session=session, market_code=market_code, selected_only=selected_only)
            ],
            "trades": [
                item.model_dump(mode="json")
                for item in list_trades(session=session, market_code=market_code, selected_only=selected_only, limit=100)
            ],
            "snapshots": [
                item.model_dump(mode="json")
                for item in list_snapshots(session=session, market_code=market_code, selected_only=selected_only, limit=300)
            ],
        }


def _money(value: float) -> str:
    return f"{value:,.2f}"


api_base_url = st.sidebar.text_input(
    "FastAPI base URL",
    value=settings.api_base_url or "",
    placeholder="http://127.0.0.1:8000",
)
selected_only = st.sidebar.checkbox("Selected models only", value=True)
market_label = st.sidebar.selectbox("Market", ["All", "KOSPI", "KOSDAQ", "US"], index=0)
market_code = None if market_label == "All" else market_label

if st.sidebar.button("Refresh"):
    load_dashboard_data.clear()

payload = load_dashboard_data(
    api_base_url=api_base_url or None,
    market_code=market_code,
    selected_only=selected_only,
)

models_df = pd.DataFrame(payload["models"])
portfolios_df = pd.DataFrame(payload["portfolios"])
positions_df = pd.DataFrame(payload["positions"])
trades_df = pd.DataFrame(payload["trades"])
snapshots_df = pd.DataFrame(payload["snapshots"])
overview = payload["overview"]

model_options = models_df["model_id"].tolist() if not models_df.empty else []
default_models = models_df.loc[models_df["is_selected"], "model_id"].tolist() if not models_df.empty else []
chosen_models = st.sidebar.multiselect("Models", model_options, default=default_models or model_options)

if chosen_models:
    models_df = models_df[models_df["model_id"].isin(chosen_models)]
    portfolios_df = portfolios_df[portfolios_df["model_id"].isin(chosen_models)]
    positions_df = positions_df[positions_df["model_id"].isin(chosen_models)]
    trades_df = trades_df[trades_df["model_id"].isin(chosen_models)]
    snapshots_df = snapshots_df[snapshots_df["model_id"].isin(chosen_models)]

combined_initial_cash = float(portfolios_df["initial_cash"].sum()) if not portfolios_df.empty else 0.0
combined_total_equity = float(portfolios_df["total_equity"].sum()) if not portfolios_df.empty else 0.0
filtered_return_pct = (
    ((combined_total_equity - combined_initial_cash) / combined_initial_cash) * 100
    if combined_initial_cash
    else 0.0
)

metric_columns = st.columns(4)
metric_columns[0].metric("Visible models", len(models_df.index), overview["selected_model_count"])
metric_columns[1].metric("Visible portfolios", len(portfolios_df.index), overview["portfolio_count"])
metric_columns[2].metric("Combined equity", _money(combined_total_equity))
metric_columns[3].metric("Combined return", f"{filtered_return_pct:.2f}%")

st.subheader("Model catalog")
if models_df.empty:
    st.info("No models found for the current filter.")
else:
    catalog_df = models_df[
        [
            "model_id",
            "display_name",
            "is_selected",
            "is_available",
            "is_free_like",
            "pricing_label",
            "context_length",
            "probe_detail",
            "updated_at",
        ]
    ].rename(
        columns={
            "model_id": "Model ID",
            "display_name": "Display name",
            "is_selected": "Selected",
            "is_available": "Available",
            "is_free_like": "Free",
            "pricing_label": "Pricing",
            "context_length": "Context",
            "probe_detail": "Probe detail",
            "updated_at": "Updated at",
        }
    )
    st.dataframe(catalog_df, use_container_width=True, hide_index=True)

st.subheader("Portfolio state")
if portfolios_df.empty:
    st.info("No portfolio rows found for the current filter.")
else:
    portfolio_view = portfolios_df[
        [
            "model_id",
            "market_code",
            "currency",
            "initial_cash",
            "available_cash",
            "invested_value",
            "total_equity",
            "total_realized_pnl",
            "total_unrealized_pnl",
            "total_return_pct",
            "position_count",
            "updated_at",
        ]
    ].rename(
        columns={
            "model_id": "Model ID",
            "market_code": "Market",
            "currency": "Currency",
            "initial_cash": "Initial cash",
            "available_cash": "Available cash",
            "invested_value": "Invested value",
            "total_equity": "Total equity",
            "total_realized_pnl": "Realized PnL",
            "total_unrealized_pnl": "Unrealized PnL",
            "total_return_pct": "Return %",
            "position_count": "Positions",
            "updated_at": "Updated at",
        }
    )
    st.dataframe(portfolio_view, use_container_width=True, hide_index=True)

st.subheader("Open positions")
if positions_df.empty:
    st.info("No open positions.")
else:
    positions_view = positions_df[
        [
            "model_id",
            "market_code",
            "ticker",
            "instrument_name",
            "quantity",
            "avg_entry_price",
            "current_price",
            "market_value",
            "unrealized_pnl",
            "unrealized_pnl_pct",
            "updated_at",
        ]
    ].rename(
        columns={
            "model_id": "Model ID",
            "market_code": "Market",
            "ticker": "Ticker",
            "instrument_name": "Instrument",
            "quantity": "Quantity",
            "avg_entry_price": "Avg entry",
            "current_price": "Current price",
            "market_value": "Market value",
            "unrealized_pnl": "Unrealized PnL",
            "unrealized_pnl_pct": "PnL %",
            "updated_at": "Updated at",
        }
    )
    st.dataframe(positions_view, use_container_width=True, hide_index=True)

st.subheader("Recent trades")
if trades_df.empty:
    st.info("No trades found.")
else:
    trades_view = trades_df[
        [
            "created_at",
            "model_id",
            "market_code",
            "ticker",
            "side",
            "quantity",
            "price",
            "gross_amount",
            "commission_amount",
            "tax_amount",
            "realized_pnl",
            "reason",
        ]
    ].rename(
        columns={
            "created_at": "Created at",
            "model_id": "Model ID",
            "market_code": "Market",
            "ticker": "Ticker",
            "side": "Side",
            "quantity": "Quantity",
            "price": "Price",
            "gross_amount": "Gross amount",
            "commission_amount": "Commission",
            "tax_amount": "Tax",
            "realized_pnl": "Realized PnL",
            "reason": "Reason",
        }
    )
    st.dataframe(trades_view, use_container_width=True, hide_index=True)

st.subheader("Return history")
if snapshots_df.empty:
    st.info("No performance snapshots found.")
else:
    chart_df = snapshots_df.copy()
    chart_df["series"] = chart_df["model_id"] + " | " + chart_df["market_code"]
    pivoted = chart_df.pivot_table(
        index="created_at",
        columns="series",
        values="total_return_pct",
        aggfunc="last",
    ).sort_index()
    st.line_chart(pivoted)

st.caption(
    f"Latest trade: {overview['latest_trade_at'] or 'n/a'} | "
    f"Latest snapshot: {overview['latest_snapshot_at'] or 'n/a'}"
)
