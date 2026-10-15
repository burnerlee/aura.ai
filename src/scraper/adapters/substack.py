# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Substack-specific content adapter."""

from __future__ import annotations

import re
from typing import Any

from scraper.adapters.default import DefaultContentAdapter
from scraper.adapters.registry import register_adapter
from scraper.models.embeddable import EmbeddableContent, SkipReason

_BOILERPLATE_PATTERNS = [
    re.compile(r"(?i)^\s*thanks for reading.*$", re.M),
    re.compile(r"(?i)^\s*subscribe\s*(now)?\s*$", re.M),
    re.compile(r"(?i)^\s*share this post\s*$", re.M),
    re.compile(r"(?i)^\s*liked by\s+\d+.*$", re.M),
    re.compile(r"(?i)^\s*©\s*\d{4}.*substack.*$", re.M),
]


def _strip_substack_boilerplate(text: str) -> str:
    cleaned = text
    for pattern in _BOILERPLATE_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


@register_adapter
class SubstackContentAdapter(DefaultContentAdapter):
    source = "substack"

    def adapt(self, raw: dict[str, Any]) -> EmbeddableContent | SkipReason:
        metadata = raw.get("metadata") or {}
        meta_type = metadata.get("type")
        if meta_type and meta_type != "post":
            return SkipReason.NOT_A_POST

        result = super().adapt(raw)
        if isinstance(result, SkipReason):
            return result

        body = _strip_substack_boilerplate(result.body_text)
        if not body:
            return SkipReason.NO_BODY

        categories = list(result.categories)
        section = metadata.get("section_name")
        if section and str(section) not in categories:
            categories.append(str(section))

        hints: dict[str, Any] = {}
        if "is_paid" in metadata:
            hints["is_paid"] = metadata["is_paid"]
        if metadata.get("post_type"):
            hints["post_type"] = metadata["post_type"]
        if section:
            hints["section_name"] = section
        if metadata.get("slug"):
            hints["slug"] = metadata["slug"]

        return result.model_copy(
            update={
                "body_text": body,
                "categories": categories,
                "hints": hints,
                "word_count": len(body.split()),
            }
        )
