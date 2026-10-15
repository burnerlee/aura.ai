# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Create and fetch posts for the recommendation / Aura UI API."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, field_validator

from scraper.api.cards import (
    UGC_SOURCE,
    FeedCard,
    PostKind,
    hydrate_scored,
    mongo_to_card,
)
from scraper.embedding.worker import embed_by_ids
from scraper.models.document import Author, ContentDocument
from scraper.query.types import ScoredPost
from scraper.storage.mongodb import MongoDocumentStore

logger = logging.getLogger(__name__)


class CreatePostRequest(BaseModel):
    kind: PostKind = PostKind.SHORT
    title: str | None = None
    body: str = ""
    category: str = "General"
    embed_url: str | None = None
    platform: str | None = None
    image_url: str | None = None
    user_id: str | None = None
    author_name: str | None = None
    # When true, embed synchronously before responding (tests / small posts).
    wait_for_embed: bool = False

    @field_validator("category")
    @classmethod
    def _category_ok(cls, value: str) -> str:
        label = value.strip()
        if not label:
            return "General"
        # Allow free-form themes (facet topics) plus legacy seed ids.
        if len(label) > 64:
            raise ValueError("category must be 64 characters or fewer")
        return label

    @field_validator("body")
    @classmethod
    def _strip_body(cls, value: str) -> str:
        return value.strip()


class CreatePostResponse(BaseModel):
    post: FeedCard
    embedding_summary: dict[str, Any] | None = None


def create_user_post(
    body: CreatePostRequest,
    *,
    store: MongoDocumentStore,
) -> tuple[dict[str, Any], FeedCard]:
    """Persist a UGC post as ``source=aura`` with ``embedding_status=pending``."""
    if body.kind == PostKind.EMBED and not body.embed_url:
        raise ValueError("embed_url is required for kind=embed")
    if body.kind != PostKind.EMBED and not body.body:
        raise ValueError("body is required")
    if body.kind == PostKind.ARTICLE and not (body.title and body.title.strip()):
        raise ValueError("title is required for kind=article")

    external_id = uuid.uuid4().hex
    author_name = body.author_name or ("Aura member" if not body.user_id else "You")
    content_text = body.body
    if body.kind == PostKind.EMBED and not content_text:
        content_text = body.title or body.embed_url or "Shared link"

    doc = ContentDocument(
        source=UGC_SOURCE,
        external_id=external_id,
        url=body.embed_url,
        embed_url=body.embed_url,
        canonical_url=body.embed_url,
        title=body.title.strip() if body.title else None,
        content_text=content_text,
        summary=content_text[:280] if content_text else None,
        author=Author(
            name=author_name,
            external_id=body.user_id,
        ),
        cover_image_url=body.image_url,
        categories=[body.category],
        tags=[body.category],
        published_at=datetime.now(UTC),
        word_count=len(content_text.split()) if content_text else 0,
        metadata={
            "kind": body.kind.value,
            "category": body.category,
            "platform": body.platform,
            "created_by_user_id": body.user_id,
            "ugc": True,
        },
    )
    store.ensure_indexes()
    raw = store.upsert(doc)
    card = mongo_to_card(raw)
    return raw, card


def get_card(store: MongoDocumentStore, post_id: str) -> FeedCard | None:
    raw = store.get_by_id(post_id)
    if raw is None:
        return None
    return mongo_to_card(raw)


def get_cards(store: MongoDocumentStore, post_ids: list[str]) -> list[FeedCard]:
    docs = store.get_many_by_ids(post_ids)
    # Preserve request order
    return [mongo_to_card(docs[pid]) for pid in post_ids if pid in docs]


def hydrate_results(
    store: MongoDocumentStore,
    results: list[ScoredPost],
) -> list[FeedCard]:
    ids = [r.post_id for r in results]
    docs = store.get_many_by_ids(ids)
    return hydrate_scored(results, docs)


def maybe_embed_post(
    post_id: str,
    *,
    wait: bool,
    store: MongoDocumentStore | None = None,
) -> dict[str, Any] | None:
    if not wait:
        return None
    return embed_by_ids([post_id], store=store)
