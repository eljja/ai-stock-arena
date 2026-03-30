from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.loader import load_settings
from app.db.models import AdminSetting
from app.db.session import SessionLocal

RUNTIME_SECRETS_KEY = "runtime_secrets"
SECRET_FIELDS = {
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "marketaux_api_token": "MARKETAUX_API_TOKEN",
    "naver_client_id": "NAVER_CLIENT_ID",
    "naver_client_secret": "NAVER_CLIENT_SECRET",
    "alpha_vantage_api_key": "ALPHA_VANTAGE_API_KEY",
}


def get_runtime_secrets(session: Session) -> dict[str, str | None]:
    settings = load_settings()
    setting = session.scalar(select(AdminSetting).where(AdminSetting.key == RUNTIME_SECRETS_KEY))
    stored = setting.value_json if setting is not None else {}
    return {
        "openrouter_api_key": stored.get("openrouter_api_key") or settings.openrouter_api_key,
        "marketaux_api_token": stored.get("marketaux_api_token") or settings.marketaux_api_token,
        "naver_client_id": stored.get("naver_client_id") or settings.naver_client_id,
        "naver_client_secret": stored.get("naver_client_secret") or settings.naver_client_secret,
        "alpha_vantage_api_key": stored.get("alpha_vantage_api_key") or settings.alpha_vantage_api_key,
    }


def update_runtime_secrets(session: Session, payload: dict[str, str | None]) -> dict[str, str | None]:
    current = get_runtime_secrets(session)
    merged = {**current}
    for key in SECRET_FIELDS:
        if key not in payload:
            continue
        value = (payload.get(key) or "").strip()
        merged[key] = value or None

    setting = session.scalar(select(AdminSetting).where(AdminSetting.key == RUNTIME_SECRETS_KEY))
    if setting is None:
        setting = AdminSetting(key=RUNTIME_SECRETS_KEY, value_json=merged)
        session.add(setting)
    else:
        setting.value_json = merged
        setting.updated_at = datetime.now(UTC)
    session.flush()
    return merged


def get_runtime_secret(secret_name: str) -> str | None:
    if secret_name not in SECRET_FIELDS:
        raise KeyError(f"Unsupported runtime secret: {secret_name}")
    with SessionLocal() as session:
        return get_runtime_secrets(session).get(secret_name)
