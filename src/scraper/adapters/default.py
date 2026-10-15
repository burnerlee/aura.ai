# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Default adapter for the generic ContentDocument Mongo shape."""

from __future__ import annotations

from typing import Any

from scraper.adapters.base import ContentAdapter, FieldSpec, strip_html, to_utc
from scraper.adapters.registry import register_adapter
from scraper.config import get_settings
from scraper.models.embeddable import EmbeddableContent, SkipReason


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
    return f"{raw.get('source', 'unknown')}:{raw.get('external_id', 'unknown')}"


@register_adapter
class DefaultContentAdapter(ContentAdapter):
    source = None

    body_spec = FieldSpec(
        "content_text",
        "content",
        ("content_html", strip_html),
        "summary",
    )
    author_spec = FieldSpec("author.name", "metadata.author", "metadata.byline")
    published_spec = FieldSpec(
        "published_at",
        "updated_at",
        "scraped_at",
        coerce=to_utc,
    )
    title_spec = FieldSpec("title")
    subtitle_spec = FieldSpec("subtitle")
    summary_spec = FieldSpec("summary")
    url_spec = FieldSpec("url", "canonical_url", "embed_url")
    language_spec = FieldSpec("language", default="en")

    def adapt(self, raw: dict[str, Any]) -> EmbeddableContent | SkipReason:
        settings = get_settings()
        source = str(raw.get("source") or "unknown")
        external_id = raw.get("external_id")
        if not external_id:
            return SkipReason.NOT_A_POST

        body = self.body_spec.resolve(raw)
        if not body or not str(body).strip():
            return SkipReason.NO_BODY
        body_text = str(body).strip()
        words = body_text.split()
        if len(words) < settings.min_body_words:
            # Allow title+summary head-only posts that are still short
            title = self.title_spec.resolve(raw) or ""
            summary = self.summary_spec.resolve(raw) or ""
            combined = f"{title} {summary} {body_text}".split()
            if len(combined) < settings.min_body_words:
                return SkipReason.TOO_SHORT

        language = self.language_spec.resolve(raw) or "en"
        if isinstance(language, str) and language.lower() not in {
            "en",
            "en-us",
            "en-gb",
            "english",
        }:
            # Soft gate: still allow unknown / missing; skip only clearly unsupported
            if len(language) == 2 and language.lower() != "en":
                return SkipReason.UNSUPPORTED_LANGUAGE

        categories = _as_str_list(raw.get("categories"))
        tags = _as_str_list(raw.get("tags"))
        image_urls: list[str] = []
        cover = raw.get("cover_image_url")
        if cover:
            image_urls.append(str(cover))
        media = raw.get("media_urls") or []
        if isinstance(media, list):
            for url in media:
                if url and str(url) not in image_urls:
                    image_urls.append(str(url))

        word_count = raw.get("word_count")
        if not isinstance(word_count, int):
            word_count = len(words)

        return EmbeddableContent(
            post_id=_post_id(raw),
            source=source,
            external_id=str(external_id),
            title=self.title_spec.resolve(raw),
            subtitle=self.subtitle_spec.resolve(raw),
            summary=self.summary_spec.resolve(raw),
            body_text=body_text,
            author_name=self.author_spec.resolve(raw),
            url=self.url_spec.resolve(raw),
            published_at=self.published_spec.resolve(raw),
            categories=categories,
            tags=tags,
            language=str(language).lower() if language else "en",
            word_count=word_count,
            image_urls=image_urls,
            hints={},
        )
