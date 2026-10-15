# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""ContentAdapter ABC and FieldSpec for declarative field resolution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup

from scraper.models.embeddable import EmbeddableContent, SkipReason

Transform = Callable[[Any], Any]


def strip_html(value: Any) -> str | None:
    if value is None:
        return None
    text = BeautifulSoup(str(value), "lxml").get_text(" ", strip=True)
    return text or None


def to_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            return None
    return None


def _resolve_path(raw: dict[str, Any], path: str) -> Any:
    current: Any = raw
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict, tuple, set)) and len(value) == 0:
        return True
    return False


class FieldSpec:
    """Ordered fallback paths with optional transforms and coercions."""

    def __init__(
        self,
        *paths: str | tuple[str, Transform],
        coerce: Transform | None = None,
        min_words: int | None = None,
        default: Any = None,
    ) -> None:
        self.paths = paths
        self.coerce = coerce
        self.min_words = min_words
        self.default = default

    def resolve(self, raw: dict[str, Any]) -> Any:
        for entry in self.paths:
            if isinstance(entry, tuple):
                path, transform = entry
            else:
                path, transform = entry, None
            value = _resolve_path(raw, path)
            if transform is not None and not _is_blank(value):
                value = transform(value)
            if _is_blank(value):
                continue
            if self.coerce is not None:
                value = self.coerce(value)
            if _is_blank(value):
                continue
            if self.min_words is not None and isinstance(value, str):
                if len(value.split()) < self.min_words:
                    continue
            return value
        return self.default


class ContentAdapter(ABC):
    """Map a raw Mongo post document to EmbeddableContent or SkipReason."""

    source: str | None = None

    @abstractmethod
    def adapt(self, raw: dict[str, Any]) -> EmbeddableContent | SkipReason:
        raise NotImplementedError
