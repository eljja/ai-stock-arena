from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re

import httpx

from app.services.runtime_secrets import get_runtime_secret

BASE_URL = "https://www.alphavantage.co/query"
SUMMARY_LIMIT = 220
DEFAULT_TOPICS = "financial_markets,economy_macro,economy_monetary"


@dataclass(slots=True)
class AlphaVantageNewsItem:
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


class AlphaVantageNewsClient:
    def __init__(self) -> None:
        self.api_key = get_runtime_secret("alpha_vantage_api_key")
        if not self.api_key:
            raise ValueError("ALPHA_VANTAGE_API_KEY is not configured.")

    def fetch_recent_news(
        self,
        *,
        published_after: datetime,
        published_before: datetime,
        target_count: int = 5,
        existing_keys: set[str] | None = None,
    ) -> list[AlphaVantageNewsItem]:
        payload = self._request_feed(published_after=published_after, published_before=published_before, limit=max(target_count, 10))
        feed = payload.get("feed") or []
        existing_keys = existing_keys or set()
        items: list[AlphaVantageNewsItem] = []
        seen_keys = set(existing_keys)
        for raw_item in feed:
            item = self._parse_item(raw_item)
            if item is None or item.dedupe_key in seen_keys:
                continue
            seen_keys.add(item.dedupe_key)
            items.append(item)
            if len(items) >= target_count:
                return items
        return items

    def _request_feed(self, *, published_after: datetime, published_before: datetime, limit: int) -> dict:
        params = {
            "function": "NEWS_SENTIMENT",
            "topics": DEFAULT_TOPICS,
            "sort": "LATEST",
            "limit": str(limit),
            "time_from": published_after.astimezone(UTC).strftime("%Y%m%dT%H%M"),
            "time_to": published_before.astimezone(UTC).strftime("%Y%m%dT%H%M"),
            "apikey": self.api_key,
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.get(BASE_URL, params=params)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected Alpha Vantage response.")
        if "Error Message" in payload or "Information" in payload or "Note" in payload:
            message = payload.get("Error Message") or payload.get("Information") or payload.get("Note")
            raise ValueError(str(message))
        return payload

    def _parse_item(self, raw_item: dict) -> AlphaVantageNewsItem | None:
        title = str(raw_item.get("title") or "").strip()
        if not title:
            return None
        summary = _summarize_text(str(raw_item.get("summary") or title).strip())
        source = str(raw_item.get("source") or "").strip() or "Alpha Vantage"
        url = str(raw_item.get("url") or "").strip() or None
        published_at = _parse_timestamp(raw_item.get("time_published"))
        tickers = []
        significance_score = 0.0
        for row in raw_item.get("ticker_sentiment") or []:
            ticker = str(row.get("ticker") or "").strip()
            if ticker:
                tickers.append(ticker)
            relevance = float(row.get("relevance_score") or 0.0)
            sentiment = abs(float(row.get("ticker_sentiment_score") or 0.0))
            significance_score = max(significance_score, relevance + sentiment)
        return AlphaVantageNewsItem(
            title=title,
            summary=summary,
            source=source,
            url=url,
            published_at=published_at,
            tickers=list(dict.fromkeys(tickers)),
            significance_score=significance_score,
        )


def _parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.strptime(text, "%Y%m%dT%H%M%S")
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y%m%dT%H%M")
        except ValueError:
            return None
    return parsed.replace(tzinfo=UTC)


def _summarize_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= SUMMARY_LIMIT:
        return normalized
    return normalized[: SUMMARY_LIMIT - 3].rstrip() + "..."
