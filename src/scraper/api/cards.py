# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""UI-facing FeedCard DTO and Mongo → card mapping.

Contract (Phase 0):
- ``id`` is always the Mongo ``_id`` string (not ``source:external_id``).
- UGC uses ``source=aura``; scraped posts keep their connector source.
- Persona for live UI is the backend ``Persona`` model; card ``category`` comes
  from facet topics (dynamic themes), not a fixed 4-bucket taxonomy.
- Anonymous ``user_id`` is client-owned (localStorage); passed on create/events.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from scraper.models.document import EmbeddingStatus
from scraper.query.types import ScoredPost

# Seed labels kept for UGC composer defaults; live cards use facet topics.
CATEGORY_IDS = ("cyberpunk", "ai", "space", "culture")
UGC_SOURCE = "aura"
_GENERIC_TOPICS = frozenset(
    {
        "newsletter",
        "podcast",
        "blog",
        "article",
        "post",
        "general",
        "misc",
        "other",
    }
)


class PostKind(StrEnum):
    IMAGE = "image"
    ARTICLE = "article"
    SHORT = "short"
    EMBED = "embed"


class CardAuthor(BaseModel):
    name: str
    handle: str
    initials: str
    avatar_color: str = "#626b7a"
    verified: bool = False


class FeedCard(BaseModel):
    """Shape close to aura-web ``FeedPost`` (snake_case for JSON API)."""

    id: str
    kind: PostKind = PostKind.ARTICLE
    category: str = "General"
    author: CardAuthor
    published_at: str
    title: str | None = None
    body: str
    image_url: str | None = None
    image_alt: str | None = None
    platform: str | None = None
    embed_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    likes: int = 0
    comments: int = 0
    source: str
    external_id: str
    url: str | None = None
    embedding_status: str = EmbeddingStatus.PENDING.value
    embedding_error: str | None = None
    score: float | None = None
    why: str | None = None
    per_query_scores: dict[str, float] = Field(default_factory=dict)


def _initials(name: str) -> str:
    parts = [p for p in name.replace("@", "").split() if p]
    if not parts:
        return "??"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _as_iso(value: Any) -> str:
    if value is None:
        return datetime.now(UTC).isoformat()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC).isoformat()
    text = str(value).strip()
    return text or datetime.now(UTC).isoformat()


def _pick_topic_label(candidates: list[str]) -> str | None:
    for item in candidates:
        label = str(item).strip()
        if not label:
            continue
        if label.lower() in _GENERIC_TOPICS:
            continue
        # Cap length for chip UI; keep original casing for display.
        return label[:48]
    return None


def _normalize_category(raw: dict[str, Any]) -> str:
    """Prefer facet topics over the old 4-bucket Interest DNA labels."""
    meta = raw.get("metadata") or {}
    if isinstance(meta, dict):
        cat = meta.get("category")
        if isinstance(cat, str) and cat.strip():
            # UGC still stores seed ids; pass them through.
            return cat.strip()

    facets = raw.get("facets") or {}
    if isinstance(facets, dict):
        topics = facets.get("topics") or []
        if isinstance(topics, list):
            picked = _pick_topic_label([str(t) for t in topics if t])
            if picked:
                return picked

    categories = raw.get("categories") or []
    if isinstance(categories, list):
        picked = _pick_topic_label([str(c) for c in categories if c])
        if picked:
            return picked

    tags = raw.get("tags") or []
    if isinstance(tags, list):
        picked = _pick_topic_label([str(t) for t in tags if t])
        if picked:
            return picked

    return "General"


def _normalize_kind(raw: dict[str, Any]) -> PostKind:
    meta = raw.get("metadata") or {}
    if isinstance(meta, dict):
        kind = meta.get("kind")
        if isinstance(kind, str):
            try:
                return PostKind(kind.lower())
            except ValueError:
                pass
    if raw.get("embed_url") and not (raw.get("content_text") or raw.get("content")):
        return PostKind.EMBED
    title = (raw.get("title") or "").strip()
    body = (
        (raw.get("summary") or "")
        or (raw.get("content_text") or "")
        or (raw.get("content") or "")
    ).strip()
    if title and len(body.split()) >= 40:
        return PostKind.ARTICLE
    return PostKind.SHORT


def _platform(raw: dict[str, Any]) -> str | None:
    meta = raw.get("metadata") or {}
    if isinstance(meta, dict) and meta.get("platform"):
        return str(meta["platform"])
    source = str(raw.get("source") or "").lower()
    if source == "substack":
        return "Substack"
    return None


def mongo_to_card(
    raw: dict[str, Any],
    *,
    score: float | None = None,
    why: str | None = None,
    per_query_scores: dict[str, float] | None = None,
) -> FeedCard:
    """Map a Mongo posts document to a UI card."""
    post_id = str(raw.get("_id") or raw.get("post_id") or "")
    source = str(raw.get("source") or "unknown")
    external_id = str(raw.get("external_id") or "")
    author_raw = raw.get("author") if isinstance(raw.get("author"), dict) else {}
    author_name = (
        (author_raw or {}).get("name")
        or (raw.get("metadata") or {}).get("author_name")
        or ("Aura member" if source == UGC_SOURCE else source.title())
    )
    handle = f"@{source}"
    if (author_raw or {}).get("external_id"):
        handle = f"@{(author_raw or {})['external_id']}"

    title = (raw.get("title") or "").strip() or None
    body = (
        (raw.get("summary") or "").strip()
        or (raw.get("content_text") or "").strip()
        or (raw.get("content") or "").strip()
        or "Open the source to read the full post."
    )
    tags: list[str] = []
    for key in ("categories", "tags"):
        values = raw.get(key) or []
        if isinstance(values, list):
            for item in values:
                if item and str(item) not in tags:
                    tags.append(str(item))

    image_url = raw.get("cover_image_url")
    if not image_url:
        media = raw.get("media_urls") or []
        if isinstance(media, list) and media:
            image_url = media[0]

    status = raw.get("embedding_status") or EmbeddingStatus.PENDING.value
    return FeedCard(
        id=post_id,
        kind=_normalize_kind(raw),
        category=_normalize_category(raw),
        author=CardAuthor(
            name=str(author_name),
            handle=handle,
            initials=_initials(str(author_name)),
        ),
        published_at=_as_iso(raw.get("published_at") or raw.get("scraped_at")),
        title=title,
        body=body,
        image_url=str(image_url) if image_url else None,
        image_alt=title,
        platform=_platform(raw),
        embed_url=raw.get("embed_url") or raw.get("canonical_url") or raw.get("url"),
        tags=tags[:8],
        likes=int(raw.get("reaction_count") or 0),
        comments=int(raw.get("comment_count") or 0),
        source=source,
        external_id=external_id,
        url=raw.get("url") or raw.get("canonical_url"),
        embedding_status=str(status),
        embedding_error=raw.get("embedding_error"),
        score=score,
        why=why,
        per_query_scores=per_query_scores or {},
    )


def hydrate_scored(
    results: list[ScoredPost],
    docs_by_id: dict[str, dict[str, Any]],
) -> list[FeedCard]:
    """Attach Mongo documents to scored retrieval hits."""
    cards: list[FeedCard] = []
    for result in results:
        raw = docs_by_id.get(result.post_id)
        if raw is None and result.payload:
            # Fallback: sparse Qdrant payload only
            sparse = {
                "_id": result.post_id,
                "post_id": result.post_id,
                **result.payload,
                "content_text": result.payload.get("title") or "",
                "author": {"name": result.payload.get("author_name")},
            }
            cards.append(
                mongo_to_card(
                    sparse,
                    score=result.score,
                    why=result.reason,
                    per_query_scores=result.per_query_scores,
                )
            )
            continue
        if raw is None:
            continue
        cards.append(
            mongo_to_card(
                raw,
                score=result.score,
                why=result.reason,
                per_query_scores=result.per_query_scores,
            )
        )
    return cards
