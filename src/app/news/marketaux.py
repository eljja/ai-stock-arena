from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re

import httpx

from app.services.runtime_secrets import get_runtime_secret

BASE_URL = "https://api.marketaux.com/v1/news/all"
SUMMARY_LIMIT = 220


@dataclass(slots=True)
class MarketauxNewsItem:
    uuid: str
    title: str
    summary: str
    source: str | None
    url: str | None
    published_at: datetime | None
    tickers: list[str]
    significance_score: float

    @property
    def dedupe_key(self) -> str:
        if self.url:
            return f"url::{self.url.strip().lower()}"
        normalized_title = re.sub(r"\s+", " ", self.title.strip().lower())
        return f"title::{normalized_title}"


class MarketauxNewsClient:
    def __init__(self) -> None:
        self.api_token = get_runtime_secret("marketaux_api_token")
        if not self.api_token:
            raise ValueError("MARKETAUX_API_TOKEN is not configured.")

    def fetch_recent_news(
        self,
        market_code: str,
        *,
        published_after: datetime,
        published_before: datetime,
        target_count: int = 3,
        max_pages: int = 4,
        existing_keys: set[str] | None = None,
        collection_policy: str = "development_fallback",
    ) -> list[MarketauxNewsItem]:
        existing_keys = existing_keys or set()
        items: list[MarketauxNewsItem] = []
        seen_keys = set(existing_keys)
        variants = self._request_variants(market_code, collection_policy)

        for request_variant in variants:
            for page in range(1, max_pages + 1):
                payload = self._request_page(
                    market_code=market_code,
                    page=page,
                    published_after=published_after,
                    published_before=published_before,
                    params=request_variant,
                )
                raw_items = payload.get("data") or []
                if not raw_items:
                    break
                for raw_item in raw_items:
                    item = self._parse_item(raw_item, market_code)
                    if item is None or item.dedupe_key in seen_keys:
                        continue
                    seen_keys.add(item.dedupe_key)
                    items.append(item)
                    if len(items) >= target_count:
                        return items
                meta = payload.get("meta") or {}
                returned = int(meta.get("returned") or len(raw_items) or 0)
                limit = int(meta.get("limit") or target_count or 0)
                if returned < limit:
                    break
            if items:
                return items
        return items

    def _request_page(
        self,
        *,
        market_code: str,
        page: int,
        published_after: datetime,
        published_before: datetime,
        params: dict[str, str],
    ) -> dict:
        request_params = {
            "api_token": self.api_token,
            "group_similar": "true",
            "limit": "3",
            "page": str(page),
            "published_after": published_after.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            "published_before": published_before.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            **params,
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.get(BASE_URL, params=request_params)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected Marketaux response for {market_code}.")
        return payload

    def _request_variants(self, market_code: str, collection_policy: str) -> list[dict[str, str]]:
        # Keep collection broad, but restrict Marketaux items to English so the shared feed stays consistent.
        return [{"sort": "published_at", "sort_order": "desc", "language": "en"}]

    def _parse_item(self, raw_item: dict, market_code: str) -> MarketauxNewsItem | None:
        title = str(raw_item.get("title") or "").strip()
        if not title:
            return None
        description = str(raw_item.get("description") or "").strip()
        snippet = str(raw_item.get("snippet") or "").strip()
        summary = _summarize_text(description or snippet or title)
        published_at = _parse_datetime(raw_item.get("published_at"))
        entities = raw_item.get("entities") or []
        tickers: list[str] = []
        significance_score = 0.0
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            symbol = str(entity.get("symbol") or "").strip()
            if symbol:
                tickers.append(symbol)
            match_score = float(entity.get("match_score") or 0.0)
            sentiment_score = abs(float(entity.get("sentiment_score") or 0.0))
            significance_score = max(significance_score, match_score + (sentiment_score * 10.0))
        deduped_tickers = list(dict.fromkeys(tickers))
        return MarketauxNewsItem(
            uuid=str(raw_item.get("uuid") or ""),
            title=title,
            summary=summary,
            source=str(raw_item.get("source") or "").strip() or None,
            url=str(raw_item.get("url") or "").strip() or None,
            published_at=published_at,
            tickers=deduped_tickers,
            significance_score=significance_score,
        )


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _summarize_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= SUMMARY_LIMIT:
        return normalized
    return normalized[: SUMMARY_LIMIT - 3].rstrip() + "..."
