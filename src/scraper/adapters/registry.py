# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Registry mapping source names to ContentAdapter implementations."""

from __future__ import annotations

from scraper.adapters.base import ContentAdapter

_REGISTRY: dict[str, type[ContentAdapter]] = {}
_DEFAULT: type[ContentAdapter] | None = None


def register_adapter(cls: type[ContentAdapter]) -> type[ContentAdapter]:
    global _DEFAULT
    if cls.source is None:
        _DEFAULT = cls
        return cls
    key = cls.source.lower()
    if key in _REGISTRY:
        raise ValueError(f"Adapter already registered: {key}")
    _REGISTRY[key] = cls
    return cls


def get_adapter(source: str | None = None) -> ContentAdapter:
    if source:
        key = source.lower()
        if key in _REGISTRY:
            return _REGISTRY[key]()
    if _DEFAULT is None:
        raise RuntimeError("No default ContentAdapter registered")
    return _DEFAULT()


def list_adapters() -> list[dict[str, str]]:
    items = [
        {"source": cls.source or "(default)", "class": cls.__name__}
        for cls in sorted(
            list(_REGISTRY.values()) + ([_DEFAULT] if _DEFAULT else []),
            key=lambda c: c.source or "",
        )
    ]
    return items
