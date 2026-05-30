from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.query_service import (
    get_overview,
    get_rankings_with_meta,
    get_runtime_settings_response,
    get_scheduler_status_response,
    list_llm_logs,
    list_models,
    list_news_batches,
    list_news_items,
    list_portfolios,
    list_positions,
    list_snapshots,
    list_trades,
)
from app.db.models import AdminSetting


DASHBOARD_SNAPSHOT_REFRESH_MINUTES = 30
DASHBOARD_SNAPSHOT_VERSION = 1
DASHBOARD_SNAPSHOT_KEY_PREFIX = "dashboard_snapshot_v1"


def dashboard_snapshot_key(
    section: str,
    *,
    selected_only: bool | None = None,
    market_code: str | None = None,
) -> str:
    parts = [DASHBOARD_SNAPSHOT_KEY_PREFIX, section]
    if selected_only is not None:
        parts.append("selected" if selected_only else "all")
    if market_code:
        parts.append(market_code.upper())
    return ":".join(parts)


def _scope_label(selected_only: bool) -> str:
    return "selected" if selected_only else "all"


def load_dashboard_snapshot_section(
    session: Session,
    section: str,
    *,
    selected_only: bool | None = None,
    market_code: str | None = None,
) -> dict[str, object] | None:
    setting = session.scalar(
        select(AdminSetting).where(
            AdminSetting.key == dashboard_snapshot_key(
                section,
                selected_only=selected_only,
                market_code=market_code,
            )
        )
    )
    if setting is None or not isinstance(setting.value_json, dict):
        return None
    payload = setting.value_json
    if payload.get("version") != DASHBOARD_SNAPSHOT_VERSION:
        return None
    if selected_only is not None and bool(payload.get("selected_only")) != bool(selected_only):
        return None
    if market_code and str(payload.get("market_code") or "").upper() != market_code.upper():
        return None
    return payload


def load_dashboard_snapshot(session: Session, *, selected_only: bool) -> dict[str, object] | None:
    base = load_dashboard_snapshot_section(session, "base", selected_only=selected_only)
    if base is None:
        return None
    allocation = load_dashboard_snapshot_section(session, "allocation", selected_only=selected_only)
    performance = load_dashboard_snapshot_section(session, "performance", selected_only=selected_only)
    news = load_dashboard_snapshot_section(session, "news")
    return {
        "version": DASHBOARD_SNAPSHOT_VERSION,
        "selected_only": selected_only,
        "generated_at": base.get("generated_at"),
        "base": base.get("data", {}),
        "allocation": allocation.get("data", {}) if allocation else {},
        "performance": performance.get("data", {}) if performance else {},
        "market_pulse": {},
        "news_preview_items": (news.get("data", {}) if news else {}).get("news_preview_items", []),
        "news_batches": (news.get("data", {}) if news else {}).get("news_batches", []),
    }


def _section_payload(
    section: str,
    data: dict[str, object],
    *,
    generated_at: str,
    selected_only: bool | None = None,
    market_code: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "version": DASHBOARD_SNAPSHOT_VERSION,
        "section": section,
        "generated_at": generated_at,
        "data": data,
    }
    if selected_only is not None:
        payload["selected_only"] = selected_only
        payload["scope"] = _scope_label(selected_only)
    if market_code:
        payload["market_code"] = market_code.upper()
    return payload


def refresh_dashboard_snapshots(session: Session) -> list[str]:
    payloads: list[tuple[str, dict[str, object]]] = []
    for selected_only in (True, False):
        payloads.extend(
            build_dashboard_snapshot_sections(session=session, selected_only=selected_only)
        )
    payloads.append(build_news_snapshot_section(session=session))
    for key, payload in payloads:
        setting = session.scalar(select(AdminSetting).where(AdminSetting.key == key))
        if setting is None:
            session.add(AdminSetting(key=key, value_json=payload))
        else:
            setting.value_json = payload
    session.flush()
    return [f"Refreshed {len(payloads)} dashboard snapshot sections."]


def build_dashboard_snapshot_sections(
    session: Session,
    *,
    selected_only: bool,
) -> list[tuple[str, dict[str, object]]]:
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    rankings_payload, rankings_meta = get_rankings_with_meta(
        session=session,
        selected_only=selected_only,
    )
    rankings_stale_at = None
    warnings: list[str] = []
    if rankings_meta.get("cache_status") == "stale":
        rankings_stale_at = rankings_meta.get("cache_updated_at")
        warnings.append("rankings: stale cache")

    base = {
        "overview": get_overview(
            session=session,
            selected_only=selected_only,
        ).model_dump(mode="json"),
        "settings": get_runtime_settings_response(session=session).model_dump(mode="json"),
        "scheduler": get_scheduler_status_response(session=session).model_dump(mode="json"),
        "models": [
            item.model_dump(mode="json")
            for item in list_models(session=session, selected_only=False)
        ],
        "rankings": [item.model_dump(mode="json") for item in rankings_payload],
        "__warnings__": warnings,
        "__rankings_stale_at": rankings_stale_at,
        "__snapshot_generated_at": generated_at,
    }
    allocation = {
        "portfolios": [
            item.model_dump(mode="json")
            for item in list_portfolios(session=session, selected_only=selected_only)
        ],
        "positions": [
            item.model_dump(mode="json")
            for item in list_positions(session=session, selected_only=selected_only)
        ],
        "__snapshot_generated_at": generated_at,
    }
    performance = {
        "portfolios": allocation["portfolios"],
        "positions": allocation["positions"],
        "trades": [
            item.model_dump(mode="json")
            for item in list_trades(session=session, selected_only=selected_only, limit=200)
        ],
        "snapshots": [
            item.model_dump(mode="json")
            for item in list_snapshots(session=session, selected_only=selected_only, limit=2000)
        ],
        "logs": [
            item.model_dump(mode="json")
            for item in list_llm_logs(session=session, limit=200)
        ],
        "__warnings__": [],
        "__snapshot_generated_at": generated_at,
    }
    sections: list[tuple[str, dict[str, object]]] = [
        (
            dashboard_snapshot_key("base", selected_only=selected_only),
            _section_payload("base", base, generated_at=generated_at, selected_only=selected_only),
        ),
        (
            dashboard_snapshot_key("allocation", selected_only=selected_only),
            _section_payload(
                "allocation",
                allocation,
                generated_at=generated_at,
                selected_only=selected_only,
            ),
        ),
        (
            dashboard_snapshot_key("performance", selected_only=selected_only),
            _section_payload(
                "performance",
                performance,
                generated_at=generated_at,
                selected_only=selected_only,
            ),
        ),
    ]
    return sections


def build_news_snapshot_section(session: Session) -> tuple[str, dict[str, object]]:
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    data = {
        "news_preview_items": [
            item.model_dump(mode="json")
            for item in list_news_items(session=session, limit=40)
        ],
        "news_batches": [
            item.model_dump(mode="json")
            for item in list_news_batches(session=session, limit=10)
        ],
    }
    return (
        dashboard_snapshot_key("news"),
        _section_payload("news", data, generated_at=generated_at),
    )
