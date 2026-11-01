from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re

from curl_cffi import requests

from app.news.dedup import is_duplicate_article, news_item_keys, register_article_keys

BASE_URL = "https://www.saveticker.com/api/news/list"
SUMMARY_LIMIT = 220


@dataclass(slots=True)
class SaveTickerNewsItem:
    title: str
    summary: str
    source: str | None
    url: str | None
    published_at: datetime | None
    tickers: list[str]
    significance_score: float

    @property
    def dedupe_keys(self) -> list[str]:
        return news_item_keys(self.url, self.title)

    @property
    def dedupe_key(self) -> str:
        keys = self.dedupe_keys
        return keys[0] if keys else f"title::{self.title}"


class SaveTickerNewsClient:
    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_recent_news(
        self,
        *,
        published_after: datetime,
        published_before: datetime,
        target_count: int = 5,
        existing_keys: set[str] | None = None,
    ) -> list[SaveTickerNewsItem]:
        existing_keys = existing_keys or set()
        items: list[SaveTickerNewsItem] = []
        seen_keys = set(existing_keys)

        for page in (1, 2):
            raw_items = self._request_page(page=page, page_size=20)
            if not raw_items:
                break
            for raw_item in raw_items:
                item = self._parse_item(raw_item)
                if item is None or is_duplicate_article(item.url, item.title, seen_keys):
                    continue
                if item.published_at and item.published_at < published_after:
                    continue
                if item.published_at and item.published_at > published_before:
                    continue

                register_article_keys(item.url, item.title, seen_keys)
                items.append(item)
                if len(items) >= target_count:
                    return items
        return items

    def _request_page(self, page: int = 1, page_size: int = 20) -> list[dict]:
        params = {
            "page": page,
            "page_size": page_size,
            "sort": "created_at_desc",
        }
        headers = {
            "Content-Type": "application/json",
            "Referer": "https://www.saveticker.com/news",
        }
        try:
            response = requests.get(
                BASE_URL,
                params=params,
                headers=headers,
                impersonate="chrome120",
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            return payload.get("news_list") or []
        except Exception:
            return []

    def _parse_item(self, raw_item: dict) -> SaveTickerNewsItem | None:
        title = str(raw_item.get("title") or "").strip()
        if not title:
            return None

        content = str(raw_item.get("content") or raw_item.get("group_summary") or title).strip()
        summary = _summarize_text(content)

        raw_source = str(raw_item.get("source") or "").strip()
        source = f"SaveTicker ({raw_source})" if raw_source else "SaveTicker"

        item_id = raw_item.get("id")
        url = f"https://www.saveticker.com/news/{item_id}" if item_id else None

        published_at = _parse_timestamp(raw_item.get("created_at"))

        # Extract ticker symbols (e.g., [{'id': 240, 'symbol': 'SNDK', 'name': '샌디스크'}])
        tickers: list[str] = []
        raw_tickers = raw_item.get("tickers") or []
        for t in raw_tickers:
            if isinstance(t, dict) and "symbol" in t:
                symbol = str(t["symbol"]).strip().upper()
                if symbol:
                    tickers.append(symbol)
            elif isinstance(t, str):
                tickers.append(t.strip().upper())

        return SaveTickerNewsItem(
            title=title,
            summary=summary,
            source=source,
            url=url,
            published_at=published_at,
            tickers=list(dict.fromkeys(tickers)),
            significance_score=0.0,
        )


def _parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    # Format example: "2026-11-01T00:07:13.158925Z" or "2026-11-01T00:07:13Z"
    try:
        # replace Z with +00:00 for fromisoformat
        clean = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(clean)
        return parsed.astimezone(UTC)
    except Exception:
        return None


def _summarize_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= SUMMARY_LIMIT:
        return normalized
    return normalized[: SUMMARY_LIMIT - 3].rstrip() + "..."
