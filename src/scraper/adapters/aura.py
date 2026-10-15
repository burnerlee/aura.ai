# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Adapter for user-generated Aura posts (short thoughts allowed)."""

from __future__ import annotations

from typing import Any

from scraper.adapters.base import ContentAdapter
from scraper.adapters.default import DefaultContentAdapter
from scraper.adapters.registry import register_adapter
from scraper.models.embeddable import EmbeddableContent, SkipReason

# Thoughts / link cards can be short; still require a non-empty body.
_AURA_MIN_WORDS = 3


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    return []


def _post_id(raw: dict[str, Any]) -> str:
    oid = raw.get("_id")
    if oid is not None:
        return str(oid)
    return f"aura:{raw.get('external_id', 'unknown')}"


@register_adapter
class AuraContentAdapter(ContentAdapter):
    source = "aura"

    def __init__(self) -> None:
        self._default = DefaultContentAdapter()

    def adapt(self, raw: dict[str, Any]) -> EmbeddableContent | SkipReason:
        external_id = raw.get("external_id")
        if not external_id:
            return SkipReason.NOT_A_POST

        body = self._default.body_spec.resolve(raw)
        title = self._default.title_spec.resolve(raw) or ""
        summary = self._default.summary_spec.resolve(raw) or ""
        embed_url = raw.get("embed_url") or raw.get("url")

        # Embed-only posts: synthesize a short body from title + URL.
        if (not body or not str(body).strip()) and embed_url:
            body = f"{title} {embed_url}".strip()

        if not body or not str(body).strip():
            return SkipReason.NO_BODY

        body_text = str(body).strip()
        combined = f"{title} {summary} {body_text}".split()
        if len(combined) < _AURA_MIN_WORDS:
            return SkipReason.TOO_SHORT

        categories = _as_str_list(raw.get("categories"))
        tags = _as_str_list(raw.get("tags"))
        image_urls: list[str] = []
        cover = raw.get("cover_image_url")
        if cover:
            image_urls.append(str(cover))

        return EmbeddableContent(
            post_id=_post_id(raw),
            source="aura",
            external_id=str(external_id),
            title=title or None,
            subtitle=self._default.subtitle_spec.resolve(raw),
            summary=summary or None,
            body_text=body_text,
            author_name=self._default.author_spec.resolve(raw),
            url=self._default.url_spec.resolve(raw),
            published_at=self._default.published_spec.resolve(raw),
            categories=categories,
            tags=tags,
            language="en",
            word_count=len(body_text.split()),
            image_urls=image_urls,
            hints={"kind": (raw.get("metadata") or {}).get("kind")},
        )
