from __future__ import annotations

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.api.query_service import (
    get_overview,
    list_models,
    list_portfolios,
    list_positions,
    list_snapshots,
    list_trades,
)
from app.api.schemas import (
    HealthResponse,
    ModelSummary,
    OverviewResponse,
    PortfolioSummary,
    PositionSummary,
    SnapshotSummary,
    TradeSummary,
)
from app.config.loader import load_runtime_config
from app.db.session import get_session

runtime_config = load_runtime_config()

app = FastAPI(
    title="AI Stock Arena API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", app_name=runtime_config.app.name)


@app.get("/overview", response_model=OverviewResponse)
def overview(
    market_code: str | None = Query(default=None),
    selected_only: bool = Query(default=True),
    session: Session = Depends(get_session),
) -> OverviewResponse:
    return get_overview(session=session, market_code=market_code, selected_only=selected_only)


@app.get("/models", response_model=list[ModelSummary])
def models(
    selected_only: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> list[ModelSummary]:
    return list_models(session=session, selected_only=selected_only)


@app.get("/portfolios", response_model=list[PortfolioSummary])
def portfolios(
    market_code: str | None = Query(default=None),
    selected_only: bool = Query(default=True),
    session: Session = Depends(get_session),
) -> list[PortfolioSummary]:
    return list_portfolios(session=session, market_code=market_code, selected_only=selected_only)


@app.get("/positions", response_model=list[PositionSummary])
def positions(
    market_code: str | None = Query(default=None),
    model_id: str | None = Query(default=None),
    selected_only: bool = Query(default=True),
    session: Session = Depends(get_session),
) -> list[PositionSummary]:
    return list_positions(
        session=session,
        market_code=market_code,
        model_id=model_id,
        selected_only=selected_only,
    )


@app.get("/trades", response_model=list[TradeSummary])
def trades(
    market_code: str | None = Query(default=None),
    model_id: str | None = Query(default=None),
    selected_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[TradeSummary]:
    return list_trades(
        session=session,
        market_code=market_code,
        model_id=model_id,
        selected_only=selected_only,
        limit=limit,
    )


@app.get("/snapshots", response_model=list[SnapshotSummary])
def snapshots(
    market_code: str | None = Query(default=None),
    model_id: str | None = Query(default=None),
    selected_only: bool = Query(default=True),
    limit: int = Query(default=300, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> list[SnapshotSummary]:
    return list_snapshots(
        session=session,
        market_code=market_code,
        model_id=model_id,
        selected_only=selected_only,
        limit=limit,
    )
