# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Canonical tag vocabulary derived from post facets."""

from scraper.tags.vocabulary import (
    GENERIC_LABELS,
    TagResolver,
    build_tags,
    collapse_labels,
    is_usable_label,
    make_tag_id,
    normalize_label,
    slugify,
    tag_refs_for_facets,
)

__all__ = [
    "GENERIC_LABELS",
    "TagResolver",
    "build_tags",
    "collapse_labels",
    "is_usable_label",
    "make_tag_id",
    "normalize_label",
    "slugify",
    "tag_refs_for_facets",
]
