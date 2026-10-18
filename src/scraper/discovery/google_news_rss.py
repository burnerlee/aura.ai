# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Google News RSS discovery.

Used for "latest news" style realtime discovery when content is not in our DB yet.
We fetch an RSS feed for a query, resolve Google redirect links to publisher URLs,
and return a compact list of items we can import + embed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

import httpx

from scraper.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GoogleNewsItem:
    title: str | None
    google_link: str
    publisher_link: str | None
    source: str | None
    published_at: datetime | None


def build_google_news_rss_url(
    query: str,
    *,
    hl: str = "en-US",
    gl: str = "US",
    ceid: str = "US:en",
    max_age_hours: int | None = 24,
) -> str:
    q = (query or "").strip()
    if not q:
        raise ValueError("query is required")
    if max_age_hours is not None and max_age_hours > 0:
        # Google News RSS supports Google search operators in the q= string.
        q = f"{q} when:{int(max_age_hours)}h"
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(q)}&hl={quote_plus(hl)}&gl={quote_plus(gl)}&ceid={quote_plus(ceid)}"
    )


def _text(node: ET.Element | None, tag: str) -> str | None:
    if node is None:
        return None
    found = node.find(tag)
    if found is None or found.text is None:
        return None
    value = found.text.strip()
    return value or None


def _parse_pubdate(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:  # noqa: BLE001
        return None


def fetch_google_news_items(
    query: str,
    *,
    max_items: int = 20,
    max_age_hours: int | None = 24,
    settings: Settings | None = None,
) -> tuple[str, list[GoogleNewsItem]]:
    """Fetch Google News RSS items for a query.

    Returns: (rss_url, items)
    """
    settings = settings or get_settings()
    rss_url = build_google_news_rss_url(query, max_age_hours=max_age_hours)
    headers = {
        "User-Agent": settings.http_user_agent,
        "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    with httpx.Client(
        headers=headers,
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
    ) as client:
        resp = client.get(rss_url)
        resp.raise_for_status()
        xml_text = resp.text

    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    items: list[GoogleNewsItem] = []
    for it in (channel.findall("item") if channel is not None else []):
        if len(items) >= max_items:
            break
        link = _text(it, "link")
        if not link:
            continue
        items.append(
            GoogleNewsItem(
                title=_text(it, "title"),
                google_link=link,
                publisher_link=None,
                source=_text(it, "source"),
                published_at=_parse_pubdate(_text(it, "pubDate")),
            )
        )
    return rss_url, items


def resolve_google_news_publisher_url(
    google_link: str,
    *,
    settings: Settings | None = None,
) -> str | None:
    """Resolve a Google News RSS <link> to the final publisher URL.

    Google commonly returns links like:
      https://news.google.com/rss/articles/<id>?oc=5
    which redirect to the publisher. We follow redirects and use the final URL.
    """
    settings = settings or get_settings()
    url = (google_link or "").strip()
    if not url:
        return None
    headers = {"User-Agent": settings.http_user_agent, "Accept": "text/html,*/*;q=0.8"}
    try:
        with httpx.Client(
            headers=headers,
            timeout=min(10.0, settings.http_timeout_seconds),
            follow_redirects=True,
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            # httpx keeps the final URL after redirects here.
            final = str(resp.url)
            return final.strip() or None
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to resolve Google News link %s: %s", url, exc)
        return None


def with_resolved_publishers(
    items: list[GoogleNewsItem],
    *,
    settings: Settings | None = None,
) -> list[GoogleNewsItem]:
    settings = settings or get_settings()
    out: list[GoogleNewsItem] = []
    for item in items:
        resolved = resolve_google_news_publisher_url(item.google_link, settings=settings)
        out.append(
            GoogleNewsItem(
                title=item.title,
                google_link=item.google_link,
                publisher_link=resolved,
                source=item.source,
                published_at=item.published_at,
            )
        )
    return out


def item_metadata(item: GoogleNewsItem, *, rss_url: str, query: str) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "google_news": {
            "rss_url": rss_url,
            "query": query,
            "google_link": item.google_link,
            "source": item.source,
        }
    }
    if item.publisher_link:
        meta["google_news"]["publisher_link"] = item.publisher_link
    if item.published_at is not None:
        meta["google_news"]["published_at"] = item.published_at.isoformat()
    return meta

