from __future__ import annotations

import html
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_IGNORED_QUERY_PARAMS = {
    "ref",
    "cooper",
    "plink",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "mediacodeno",
    "sid",
    "cid",
    "_ref",
}


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return url.strip().lower().rstrip("/")
        query_pairs = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=False)
            if k.lower() not in _IGNORED_QUERY_PARAMS
        ]
        query_pairs.sort(key=lambda pair: pair[0].lower())
        new_query = urlencode(query_pairs)
        clean = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            parsed.params,
            new_query,
            "",
        ))
        return clean
    except Exception:
        return url.strip().lower().rstrip("/")


def normalize_title_fingerprint(title: str | None) -> str:
    if not title:
        return ""
    t = html.unescape(str(title))
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"^[\[\(][^\]\)]+[\]\)]\s*", "", t)
    t = re.sub(r"[\s\.,·…'\"`\(\)\[\]\{\}<>·_~!@#$%^&*+=|\\/:;?\-]+", "", t.lower())
    return t


def news_item_keys(url: str | None, title: str | None) -> list[str]:
    keys: list[str] = []
    clean_url = normalize_url(url)
    if clean_url:
        keys.append(f"url::{clean_url}")
    fp = normalize_title_fingerprint(title)
    if fp:
        keys.append(f"title::{fp}")
    return keys


def is_duplicate_article(url: str | None, title: str | None, seen_keys: set[str]) -> bool:
    for key in news_item_keys(url, title):
        if key in seen_keys:
            return True
    return False


def register_article_keys(url: str | None, title: str | None, seen_keys: set[str]) -> list[str]:
    keys = news_item_keys(url, title)
    for key in keys:
        seen_keys.add(key)
    return keys
