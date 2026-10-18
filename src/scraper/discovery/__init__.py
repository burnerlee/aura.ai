# Copyright (c) 2026 DevRev Inc. All rights reserved.

from scraper.discovery.substack import BlogTarget, SubstackDiscovery, discover_substack
from scraper.discovery.google_news_rss import (
    GoogleNewsItem,
    fetch_google_news_items,
    with_resolved_publishers,
)

__all__ = [
    "BlogTarget",
    "SubstackDiscovery",
    "discover_substack",
    "GoogleNewsItem",
    "fetch_google_news_items",
    "with_resolved_publishers",
]
