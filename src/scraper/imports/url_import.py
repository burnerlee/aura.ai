# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Import a single URL into Mongo as a ContentDocument (best-effort).

This is the missing piece for "recommend something we haven't pre-scraped":

- User pastes a URL (Substack, Reddit, or generic web page)
- Backend fetches minimal content now
- Saves it into Mongo with ``embedding_status=pending``
- Queues embedding (or embeds synchronously if requested)

Once embedded, the post is eligible for ANN retrieval and similarity queries.
"""

from __future__ import annotations

import hashlib
import logging
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse, urlunparse
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from scraper.config import Settings, get_settings
from scraper.connectors.base import ConnectorConfig
from scraper.connectors.reddit import REDDIT_BASE, _POST_ID_RE, html_to_text as reddit_html_to_text
from scraper.connectors.reddit import _parse_iso_dt as reddit_parse_iso_dt
from scraper.connectors.substack import SubstackConnector
from scraper.models.document import Author, ContentDocument

_MAX_IMPORTED_CHARS = 40_000

logger = logging.getLogger(__name__)


class ImportKind(StrEnum):
    SUBSTACK = "substack"
    REDDIT = "reddit"
    LINK = "link"


def normalize_url(value: str) -> str:
    """Normalize a user-provided URL to a stable string for dedupe.

    - drop fragments
    - strip trailing slash (except for root)
    - keep querystring (some pages are meaningful with it)
    """

    raw = (value or "").strip()
    if not raw:
        raise ValueError("url is required")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url must be an http(s) URL")
    cleaned = parsed._replace(fragment="")
    url = urlunparse(cleaned)
    if url.endswith("/") and cleaned.path not in ("", "/"):
        url = url.rstrip("/")
    return url


def _stable_external_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _guess_kind(url: str) -> ImportKind:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().removeprefix("www.")
    if hostname.endswith("substack.com"):
        return ImportKind.SUBSTACK
    if hostname.endswith("reddit.com") or hostname.endswith(".reddit.com"):
        return ImportKind.REDDIT
    return ImportKind.LINK


def _import_substack(url: str, *, settings: Settings) -> ContentDocument:
    parsed = urlparse(url)
    if not parsed.netloc:
        raise ValueError("Invalid Substack URL")
    base = f"{parsed.scheme}://{parsed.netloc}"
    parts = [p for p in parsed.path.split("/") if p]
    # Canonical post URLs are typically /p/<slug>
    if len(parts) < 2 or parts[0].lower() != "p":
        raise ValueError("Substack URL must look like /p/<slug>")
    slug = parts[1]

    connector = SubstackConnector(
        ConnectorConfig(source_id=base, limit=1, offset=0, fetch_full_content=True)
    )
    with connector._http_client() as client:  # intentionally reuse headers/timeouts
        detail = connector._fetch_post(client, slug)
    if not detail:
        raise ValueError("Substack post not found")
    # Ensure canonical URL set to the imported URL when API omits it.
    if "canonical_url" not in detail and "url" not in detail:
        detail = {**detail, "canonical_url": url}
    return connector._to_document(detail)


def _reddit_post_rss_url(post_id: str) -> str:
    # Post-level RSS feed (single entry) is public and tends to be more reliable than JSON.
    return f"{REDDIT_BASE}/comments/{post_id}/.rss"


def _import_reddit(url: str, *, settings: Settings) -> ContentDocument:
    match = _POST_ID_RE.search(url)
    if not match:
        raise ValueError("Reddit URL must include /comments/<id>/")
    post_id = match.group("id")

    headers = {
        "User-Agent": settings.http_user_agent,
        "Accept": "application/atom+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    rss_url = _reddit_post_rss_url(post_id)
    with httpx.Client(
        headers=headers,
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
    ) as client:
        resp = client.get(rss_url, params={"raw_json": 1})
        resp.raise_for_status()
        xml_text = resp.text

    root = ET.fromstring(xml_text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)
    if entry is None:
        raise ValueError("Reddit RSS did not include an entry")

    title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip() or None
    updated = (entry.findtext("atom:updated", default="", namespaces=ns) or "").strip() or None
    published = (entry.findtext("atom:published", default="", namespaces=ns) or "").strip() or None
    author = (
        entry.findtext("atom:author/atom:name", default="", namespaces=ns) or ""
    ).strip() or None
    content_html = (entry.findtext("atom:content", default="", namespaces=ns) or "").strip() or None
    content_text = reddit_html_to_text(content_html)

    # Prefer the entry link if present.
    link_url: str | None = None
    for link in entry.findall("atom:link", ns):
        if link.get("rel") in (None, "", "alternate"):
            link_url = (link.get("href") or "").strip() or None
            if link_url:
                break

    metadata: dict[str, Any] = {
        "import_url": url,
        "rss_url": rss_url,
    }
    if author:
        metadata["author_name"] = author

    # Keep Reddit docs shaped similarly to connector output.
    return ContentDocument(
        source="reddit",
        external_id=str(post_id),
        url=link_url or url,
        embed_url=link_url or url,
        canonical_url=link_url or url,
        title=title,
        content_html=content_html,
        content_text=content_text,
        content=content_text,
        summary=(content_text[:240] if content_text else None),
        author=Author(name=author) if author else None,
        tags=[],
        categories=[],
        published_at=reddit_parse_iso_dt(published),
        updated_at=reddit_parse_iso_dt(updated),
        metadata=metadata,
    )


def _extract_html_text(html: str) -> tuple[str | None, str | None]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = (soup.title.get_text(" ", strip=True) if soup.title else None) or None
    # Best-effort "main content": <article> if present, else whole body.
    node = soup.find("article") or soup.body or soup
    text = node.get_text("\n", strip=True) if node else ""
    cleaned = "\n".join(line for line in (text or "").splitlines() if line.strip())
    return title, cleaned or None


def _import_link(url: str, *, settings: Settings) -> ContentDocument:
    headers = {"User-Agent": settings.http_user_agent, "Accept": "text/html,*/*;q=0.8"}
    with httpx.Client(
        headers=headers,
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        title, text = _extract_html_text(resp.text)

    # Avoid embedding megabytes of nav / footer; keep the "top" of the page.
    if text:
        text = text[:_MAX_IMPORTED_CHARS]

    hostname = (urlparse(url).hostname or "").lower().removeprefix("www.")
    meta: dict[str, Any] = {"hostname": hostname, "import_url": url}
    return ContentDocument(
        source="link",
        external_id=_stable_external_id(url),
        url=url,
        embed_url=url,
        canonical_url=url,
        title=title,
        content_text=text or (title or url),
        content=text or (title or url),
        summary=(text[:280] if text else (title or url)[:280]),
        metadata=meta,
    )


def import_document_from_url(url: str, *, settings: Settings | None = None) -> ContentDocument:
    """Fetch and map a URL into a ContentDocument."""
    settings = settings or get_settings()
    norm = normalize_url(url)
    kind = _guess_kind(norm)
    logger.info("Importing url kind=%s url=%s", kind.value, norm)
    if kind == ImportKind.SUBSTACK:
        return _import_substack(norm, settings=settings)
    if kind == ImportKind.REDDIT:
        return _import_reddit(norm, settings=settings)
    return _import_link(norm, settings=settings)

