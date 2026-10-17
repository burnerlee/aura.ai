# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Reddit-specific content adapter: drops moderator stickies and recurring threads."""

from __future__ import annotations

import re
from typing import Any

from scraper.adapters.default import DefaultContentAdapter
from scraper.adapters.registry import register_adapter
from scraper.models.embeddable import EmbeddableContent, SkipReason

_AMA = re.compile(r"\bAMA\b")
_BOT_AUTHOR = re.compile(r"(?i)(automoderator|moderator$|_mod$|^bernardjortcutt$)")
_HOUSEKEEPING_TITLE = re.compile(
    r"(?i)("
    r"megathread|\[meta\]|^meta\b|welcome to /?r/|rules?\b.*\b(guidelines|read before|policy)"
    r"|subreddit rules|announcement|self-promotion|who'?s hiring"
    r"|\b(daily|weekly|monthly|quarterly)\b.*\b(thread|post|roundup|questions?)\b"
    r"|\b(discussion|questions?|support|rec|win|venting|surveys?) thread\b"
    r"|\|\s*\w+ \d{1,2}, \d{4}$|— \d{1,2}/\d{1,2}/\d{2}$"
    r")"
)


def is_housekeeping(raw: dict[str, Any]) -> bool:
    """Moderator / bot posts and scheduled threads: not content anyone wants recommended."""
    title = str(raw.get("title") or "")
    if _AMA.search(title):
        return False
    author = str((raw.get("author") or {}).get("name") or "").removeprefix("/u/")
    if _BOT_AUTHOR.search(author):
        return True
    return bool(_HOUSEKEEPING_TITLE.search(title))


@register_adapter
class RedditContentAdapter(DefaultContentAdapter):
    source = "reddit"

    def adapt(self, raw: dict[str, Any]) -> EmbeddableContent | SkipReason:
        if is_housekeeping(raw):
            return SkipReason.NOT_A_POST
        return super().adapt(raw)
