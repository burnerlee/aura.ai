# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""On-demand imports (real-time fetch into Mongo + embedding queue)."""

from scraper.imports.url_import import ImportKind, import_document_from_url, normalize_url

__all__ = [
    "ImportKind",
    "import_document_from_url",
    "normalize_url",
]

