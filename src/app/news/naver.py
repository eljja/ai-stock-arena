from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import email.utils
import re

import httpx

from app.services.runtime_secrets import get_runtime_secret

BASE_URL = "https://openapi.naver.com/v1/search/news.json"
SUMMARY_LIMIT = 220
DEFAULT_QUERY = "\uc99d\uc2dc"


@dataclass(slots=True)
class NaverNewsItem:
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


class NaverNewsClient:
    def __init__(self) -> None:
        self.client_id = get_runtime_secret("naver_client_id")
        self.client_secret = get_runtime_secret("naver_client_secret")
        if not self.client_id or not self.client_secret:
            raise ValueError("NAVER_CLIENT_ID or NAVER_CLIENT_SECRET is not configured.")

    def fetch_recent_news(
        self,
        *,
        published_after: datetime,
        published_before: datetime,
        target_count: int = 5,
        existing_keys: set[str] | None = None,
    ) -> list[NaverNewsItem]:
        existing_keys = existing_keys or set()
        items: list[NaverNewsItem] = []
        seen_keys = set(existing_keys)
        for start in (1, 11, 21):
            payload = self._request_page(start=start, display=10)
            raw_items = payload.get("items") or []
            if not raw_items:
                break
            for raw_item in raw_items:
                item = self._parse_item(raw_item)
                if item is None:
                    continue
                if item.published_at is not None:
                    published_utc = item.published_at.astimezone(UTC)
                    if published_utc < published_after.astimezone(UTC) or published_utc > published_before.astimezone(UTC):
                        continue
                if item.dedupe_key in seen_keys:
                    continue
                seen_keys.add(item.dedupe_key)
                items.append(item)
                if len(items) >= target_count:
                    return items
        return items

    def _request_page(self, *, start: int, display: int) -> dict:
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }
        params = {
            "query": DEFAULT_QUERY,
            "display": str(display),
            "start": str(start),
            "sort": "date",
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.get(BASE_URL, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected Naver news response.")
        return payload

    def _parse_item(self, raw_item: dict) -> NaverNewsItem | None:
        title = _strip_html(str(raw_item.get("title") or "").strip())
        if not title:
            return None
        summary = _summarize_text(_strip_html(str(raw_item.get("description") or "").strip()) or title)
        link = str(raw_item.get("originallink") or raw_item.get("link") or "").strip() or None
        published_at = _parse_pubdate(raw_item.get("pubDate"))
        return NaverNewsItem(
            title=title,
            summary=summary,
            source="Naver News",
            url=link,
            published_at=published_at,
            tickers=[],
            significance_score=0.0,
        )


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _summarize_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= SUMMARY_LIMIT:
        return normalized
    return normalized[: SUMMARY_LIMIT - 3].rstrip() + "..."


def _parse_pubdate(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(str(value))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)

