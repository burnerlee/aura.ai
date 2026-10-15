# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Substack connector using the public publication JSON API.

Endpoints used (no auth required for public posts):
  GET {base}/api/v1/archive?sort=new&limit=&offset=
  GET {base}/api/v1/posts/{slug}
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from scraper.config import get_settings
from scraper.connectors.base import BaseConnector, ConnectorConfig
from scraper.connectors.registry import register_connector
from scraper.models.document import Author, ContentDocument

logger = logging.getLogger(__name__)

_SUBSTACK_HOST_RE = re.compile(r"^(?P<sub>[^.]+)\.substack\.com$", re.IGNORECASE)
_PAGE_SIZE = 50


def resolve_publication_base(source_id: str) -> str:
    """Normalize publication handle / URL to an origin base URL."""
    value = source_id.strip().rstrip("/")
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        if not parsed.netloc:
            raise ValueError(f"Invalid Substack URL: {source_id}")
        return f"{parsed.scheme}://{parsed.netloc}"

    # Bare subdomain handle, e.g. "platformer"
    handle = value.removesuffix(".substack.com")
    if not re.fullmatch(r"[a-zA-Z0-9-]+", handle):
        raise ValueError(
            f"Invalid Substack source_id '{source_id}'. "
            "Use a handle (e.g. platformer) or full URL."
        )
    return f"https://{handle}.substack.com"


def html_to_text(html: str | None) -> str | None:
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    return text or None


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    # Substack uses ISO-8601 with Z
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        logger.warning("Could not parse datetime: %s", value)
        return None


@register_connector
class SubstackConnector(BaseConnector):
    name = "substack"
    description = "Scrape public posts from a Substack publication"

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self.settings = get_settings()
        self.base_url = resolve_publication_base(config.source_id)
        self._client: httpx.Client | None = None

    def validate_config(self) -> None:
        super().validate_config()
        # Force early URL validation
        _ = self.base_url

    def scrape(self) -> Iterator[ContentDocument]:
        yielded = 0
        offset = self.config.offset
        limit = self.config.limit

        with self._http_client() as client:
            while True:
                page_limit = _PAGE_SIZE
                if limit is not None:
                    remaining = limit - yielded
                    if remaining <= 0:
                        break
                    page_limit = min(_PAGE_SIZE, remaining)

                archive = self._fetch_archive(client, offset=offset, limit=page_limit)
                if not archive:
                    break

                for entry in archive:
                    slug = entry.get("slug")
                    if not slug:
                        logger.warning("Skipping archive entry without slug: %s", entry.get("id"))
                        continue

                    raw: dict[str, Any] = entry
                    if self.config.fetch_full_content:
                        detail = self._fetch_post(client, slug)
                        if detail:
                            # Detail is authoritative for body / author
                            raw = {**entry, **detail}

                    doc = self._to_document(raw)
                    yield doc
                    yielded += 1

                    if limit is not None and yielded >= limit:
                        return

                    self._throttle()

                if len(archive) < page_limit:
                    break
                offset += len(archive)

    def _http_client(self) -> httpx.Client:
        return httpx.Client(
            headers={"User-Agent": self.settings.http_user_agent, "Accept": "application/json"},
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
    def _fetch_archive(
        self, client: httpx.Client, *, offset: int, limit: int
    ) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/v1/archive"
        params = {"sort": "new", "offset": offset, "limit": limit}
        logger.debug("GET %s params=%s", url, params)
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise ValueError(f"Unexpected archive response type: {type(data)}")
        return data

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _fetch_post(self, client: httpx.Client, slug: str) -> dict[str, Any] | None:
        url = f"{self.base_url}/api/v1/posts/{slug}"
        logger.debug("GET %s", url)
        resp = client.get(url)
        if resp.status_code == 404:
            logger.warning("Post not found: %s", slug)
            return None
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError(f"Unexpected post response type: {type(data)}")
        return data

    def _to_document(self, raw: dict[str, Any]) -> ContentDocument:
        post_id = raw.get("id")
        slug = raw.get("slug") or ""
        canonical = raw.get("canonical_url") or raw.get("url")
        publication_url = self.base_url

        # Embeddable iframe-friendly URL used by Substack embeds
        embed_url = f"{publication_url}/embed/p/{slug}" if slug else None

        body_html = raw.get("body_html")
        content_text = html_to_text(body_html) or raw.get("truncated_body_text")

        published = parse_datetime(raw.get("post_date"))
        updated = parse_datetime(raw.get("updated_at") or raw.get("edited_at"))

        author = self._extract_author(raw)
        reactions = raw.get("reactions") or {}
        reaction_count = raw.get("reaction_count")
        if reaction_count is None and isinstance(reactions, dict):
            reaction_count = sum(int(v) for v in reactions.values() if isinstance(v, (int, float)))

        media_urls: list[str] = []
        cover = raw.get("cover_image") or raw.get("cover_image_url")
        if cover:
            media_urls.append(cover)

        tags: list[str] = []
        for key in ("postTags", "tags"):
            value = raw.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        tags.append(item)
                    elif isinstance(item, dict) and item.get("name"):
                        tags.append(str(item["name"]))

        publication_name = None
        if isinstance(raw.get("publication"), dict):
            publication_name = raw["publication"].get("name")

        metadata: dict[str, Any] = {
            "publication_base_url": publication_url,
            "publication_name": publication_name,
            "slug": slug,
            "post_type": raw.get("type"),
            "is_paid": bool(raw.get("is_paid") or raw.get("audience") == "only_paid"),
        }
        if raw.get("section_name"):
            metadata["section_name"] = raw.get("section_name")
        if reactions:
            metadata["reactions"] = reactions
        if raw.get("restacks") is not None:
            metadata["restacks"] = raw.get("restacks")

        return ContentDocument(
            source=self.name,
            external_id=str(post_id) if post_id is not None else slug,
            url=canonical or (f"{publication_url}/p/{slug}" if slug else None),
            embed_url=embed_url,
            canonical_url=canonical,
            title=raw.get("title"),
            subtitle=raw.get("subtitle"),
            content=content_text,
            content_html=body_html,
            content_text=content_text,
            summary=raw.get("description") or raw.get("truncated_body_text"),
            language=raw.get("language") or raw.get("locale"),
            author=author,
            cover_image_url=cover,
            media_urls=media_urls,
            tags=tags,
            categories=[raw.get("type")] if raw.get("type") else [],
            audience=raw.get("audience"),
            published_at=published,
            updated_at=updated,
            word_count=raw.get("wordcount") or raw.get("word_count"),
            reaction_count=reaction_count,
            comment_count=raw.get("comment_count"),
            metadata=metadata,
            raw=raw,
        )

    def _extract_author(self, raw: dict[str, Any]) -> Author | None:
        bylines = raw.get("publishedBylines") or raw.get("published_bylines") or []
        if isinstance(bylines, list) and bylines:
            primary = bylines[0]
            if isinstance(primary, dict):
                return Author(
                    name=primary.get("name"),
                    external_id=str(primary["id"]) if primary.get("id") is not None else None,
                    url=primary.get("profile_url") or primary.get("canonical_url"),
                    bio=primary.get("bio"),
                    avatar_url=primary.get("photo_url") or primary.get("image_url"),
                    metadata={
                        "handle": primary.get("handle") or primary.get("slug"),
                        "is_guest": primary.get("is_guest"),
                    },
                )

        name = raw.get("author_name") or raw.get("writer_slug")
        if name:
            return Author(name=str(name))
        return None
