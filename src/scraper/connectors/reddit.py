# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Reddit connector using Reddit's public Atom feed (no auth).

Endpoints used:
  GET https://www.reddit.com/r/{subreddit}/.rss

Why RSS?
- Reddit's JSON endpoints are frequently blocked (403) without OAuth/cookies in
  many environments. The subreddit RSS feed is still broadly accessible.

Notes:
- This connector is intentionally "best effort" without OAuth.
- RSS has limited metadata compared to the JSON API (e.g. no score / comment
  counts). If you need that, add an OAuth-backed connector that targets
  ``https://oauth.reddit.com``.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from scraper.config import get_settings
from scraper.connectors.base import BaseConnector, ConnectorConfig
from scraper.connectors.registry import register_connector
from scraper.models.document import Author, ContentDocument

logger = logging.getLogger(__name__)

REDDIT_BASE = "https://www.reddit.com"
_SUBREDDIT_RE = re.compile(r"^[A-Za-z0-9_]{2,21}$")
_POST_ID_RE = re.compile(r"/comments/(?P<id>[a-z0-9]+)/", re.IGNORECASE)


def resolve_subreddit(source_id: str) -> str:
    """Normalize a subreddit source_id into a subreddit name (no leading r/).

    Accepts:
    - "worldbuilding"
    - "r/worldbuilding"
    - "https://www.reddit.com/r/worldbuilding/"
    - "https://old.reddit.com/r/worldbuilding/new/"
    """

    value = source_id.strip()
    if not value:
        raise ValueError("Invalid subreddit: empty source_id")

    # URL form
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        parts = [p for p in parsed.path.split("/") if p]
        # expect /r/<name>/...
        if len(parts) >= 2 and parts[0].lower() == "r":
            name = parts[1]
        else:
            raise ValueError(f"Invalid subreddit URL: {source_id}")
    else:
        # "r/foo" form
        if value.lower().startswith("r/"):
            name = value.split("/", 1)[1]
        else:
            name = value

    name = name.strip()
    if not _SUBREDDIT_RE.fullmatch(name):
        raise ValueError(
            f"Invalid subreddit '{source_id}'. Expected something like 'r/worldbuilding'."
        )
    return name


def _parse_utc_ts(value: Any) -> datetime | None:
    try:
        if value is None:
            return None
        return datetime.fromtimestamp(float(value), tz=UTC)
    except Exception:  # noqa: BLE001
        return None


def _parse_iso_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def html_to_text(html: str | None) -> str | None:
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    return text or None


@register_connector
class RedditConnector(BaseConnector):
    name = "reddit"
    description = "Scrape posts from a subreddit via the public RSS feed"

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self.settings = get_settings()
        self.subreddit = resolve_subreddit(config.source_id)

        extras = config.extras or {}
        self.sort = str(extras.get("sort") or "new").lower()
        # When sort=top/controversial, Reddit accepts t=hour|day|week|month|year|all
        self.timeframe = str(extras.get("timeframe") or extras.get("t") or "day").lower()
        self.include_comments = bool(extras.get("include_comments") or False)
        self.comment_limit = int(extras.get("comment_limit") or 10)

    def validate_config(self) -> None:
        super().validate_config()
        _ = self.subreddit
        allowed = {"hot", "new", "top", "rising", "controversial"}
        if self.sort not in allowed:
            options = ", ".join(sorted(allowed))
            raise ValueError(f"Invalid sort '{self.sort}'. Use one of: {options}")
        if self.comment_limit < 0:
            raise ValueError("comment_limit must be >= 0")

    def scrape(self) -> Iterator[ContentDocument]:
        """Fetch the subreddit feed once and yield up to (offset + limit) entries."""
        offset = max(0, int(self.config.offset or 0))
        limit = self.config.limit

        with self._http_client() as client:
            entries = self._fetch_feed_entries(client)

        if offset:
            entries = entries[offset:]
        if limit is not None:
            entries = entries[: max(0, limit)]

        for entry in entries:
            doc = self._entry_to_document(entry)
            yield doc

    def _http_client(self) -> httpx.Client:
        return httpx.Client(
            headers={
                "User-Agent": self.settings.http_user_agent,
                "Accept": "application/atom+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            timeout=self.settings.http_timeout_seconds,
            follow_redirects=True,
        )

    def _throttle(self) -> None:
        delay = self.settings.request_delay_seconds
        if delay > 0:
            time.sleep(delay)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _fetch_feed_entries(self, client: httpx.Client) -> list[dict[str, Any]]:
        """Return a list of parsed Atom entries with normalized fields."""
        xml_text = self._fetch_rss(client)
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        out: list[dict[str, Any]] = []
        for entry in root.findall("atom:entry", ns):
            title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
            entry_id = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
            updated = (entry.findtext("atom:updated", default="", namespaces=ns) or "").strip()
            published = (entry.findtext("atom:published", default="", namespaces=ns) or "").strip()
            author = (
                entry.findtext("atom:author/atom:name", default="", namespaces=ns) or ""
            ).strip()

            link_url = ""
            for link in entry.findall("atom:link", ns):
                if link.get("rel") in (None, "", "alternate"):
                    link_url = (link.get("href") or "").strip()
                    if link_url:
                        break

            content_html = (entry.findtext("atom:content", default="", namespaces=ns) or "").strip()

            out.append(
                {
                    "title": title or None,
                    "entry_id": entry_id or None,
                    "updated": updated or None,
                    "published": published or None,
                    "author": author or None,
                    "url": link_url or None,
                    "content_html": content_html or None,
                }
            )
        return out

    def _fetch_rss(self, client: httpx.Client) -> str:
        url = f"{REDDIT_BASE}/r/{self.subreddit}/.rss"
        # Reddit will rate-limit RSS scraping with HTTP 429. Tenacity retries can
        # unintentionally amplify the problem unless we back off hard here.
        max_attempts = 8
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            self._throttle()
            try:
                logger.debug("GET %s", url)
                resp = client.get(url, params={"raw_json": 1})
                if resp.status_code == 429:
                    retry_after = (resp.headers.get("Retry-After") or "").strip()
                    try:
                        delay = float(retry_after) if retry_after else None
                    except ValueError:
                        delay = None
                    backoff = min(60.0, 2.0**attempt)
                    sleep_s = max(5.0, delay or backoff)
                    logger.warning(
                        "Reddit RSS rate-limited (429) for r/%s; sleeping %.1fs (attempt %s/%s)",
                        self.subreddit,
                        sleep_s,
                        attempt,
                        max_attempts,
                    )
                    time.sleep(sleep_s)
                    continue

                resp.raise_for_status()
                return resp.text
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                code = exc.response.status_code if exc.response is not None else None
                if code in {500, 502, 503, 504}:
                    sleep_s = min(30.0, 2.0**attempt)
                    logger.warning(
                        "Reddit RSS transient HTTP %s for r/%s; sleeping %.1fs (attempt %s/%s)",
                        code,
                        self.subreddit,
                        sleep_s,
                        attempt,
                        max_attempts,
                    )
                    time.sleep(sleep_s)
                    continue
                raise
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                sleep_s = min(30.0, 2.0**attempt)
                logger.warning(
                    "Reddit RSS network error for r/%s (%s); sleeping %.1fs (attempt %s/%s)",
                    self.subreddit,
                    type(exc).__name__,
                    sleep_s,
                    attempt,
                    max_attempts,
                )
                time.sleep(sleep_s)
                continue

        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"Failed to fetch reddit RSS after {max_attempts} attempts: {url}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _fetch_comments(
        self, client: httpx.Client, *, permalink: str, limit: int
    ) -> list[Any]:
        # Reddit returns a two-element list: [post_listing, comment_listing]
        url = f"{REDDIT_BASE}{permalink}.json"
        params = {"limit": limit, "raw_json": 1}
        logger.debug("GET %s params=%s", url, params)
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise ValueError(f"Unexpected reddit comments response type: {type(data)}")
        return data

    def _entry_to_document(self, entry: dict[str, Any]) -> ContentDocument:
        url = entry.get("url") if isinstance(entry.get("url"), str) else None
        entry_id = entry.get("entry_id") if isinstance(entry.get("entry_id"), str) else None

        external_id = entry_id or (url or "")
        if url:
            match = _POST_ID_RE.search(url)
            if match:
                external_id = match.group("id")

        title = entry.get("title") if isinstance(entry.get("title"), str) else None
        content_html = (
            entry.get("content_html") if isinstance(entry.get("content_html"), str) else None
        )
        content_text = html_to_text(content_html)

        author_name = entry.get("author") if isinstance(entry.get("author"), str) else None
        author = Author(name=author_name) if author_name else None

        published_at = _parse_iso_dt(entry.get("published"))
        updated_at = _parse_iso_dt(entry.get("updated"))

        tags: list[str] = [f"r/{self.subreddit}"]
        metadata: dict[str, Any] = {
            "subreddit": self.subreddit,
            "feed_entry_id": entry_id,
            "feed_url": f"{REDDIT_BASE}/r/{self.subreddit}/.rss",
            "sort_requested": self.sort,
            "timeframe_requested": self.timeframe,
        }

        return ContentDocument(
            source=self.name,
            external_id=str(external_id),
            url=url,
            embed_url=url,
            canonical_url=url,
            title=title,
            content_html=content_html,
            content_text=content_text,
            content=content_text,
            summary=(content_text[:240] if content_text else None),
            author=author,
            tags=tags,
            categories=[self.subreddit],
            published_at=published_at,
            updated_at=updated_at,
            metadata=metadata,
            raw=entry,
        )

    def _attach_comments(
        self, client: httpx.Client, doc: ContentDocument, raw: dict[str, Any]
    ) -> ContentDocument:
        # Not supported for RSS-only mode; retained for a future OAuth/JSON connector.
        if self.comment_limit <= 0:
            return doc
        permalink = raw.get("permalink")
        if not isinstance(permalink, str) or not permalink:
            return doc

        try:
            data = self._fetch_comments(
                client,
                permalink=permalink.rstrip("/"),
                limit=self.comment_limit,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to fetch comments for %s: %s", permalink, exc)
            return doc

        # Second element is comment listing
        if len(data) < 2 or not isinstance(data[1], dict):
            return doc
        listing = data[1]
        children = (listing.get("data") or {}).get("children")
        if not isinstance(children, list):
            return doc

        comments: list[str] = []
        for child in children:
            c = child.get("data") if isinstance(child, dict) else None
            if not isinstance(c, dict):
                continue
            body = c.get("body")
            if isinstance(body, str) and body.strip():
                comments.append(body.strip())
            if len(comments) >= self.comment_limit:
                break

        if not comments:
            return doc

        # Append a compact comments block to content_text; keep original in metadata too.
        base = doc.content_text or ""
        appended = "\n\n---\nTop comments (sample)\n" + "\n\n".join(
            f"- {c}" for c in comments[: self.comment_limit]
        )
        doc.content_text = (base + appended).strip()
        doc.content = doc.content_text
        doc.metadata = {**(doc.metadata or {}), "top_comments": comments[: self.comment_limit]}
        return doc

