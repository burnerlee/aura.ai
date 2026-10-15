# Copyright (c) 2026 DevRev Inc. All rights reserved.

from scraper.adapters import get_adapter
from scraper.models.embeddable import SkipReason


def test_aura_adapter_accepts_short_thought():
    raw = {
        "_id": "oid1",
        "source": "aura",
        "external_id": "u1",
        "content_text": "neon rain on chrome streets",
        "metadata": {"kind": "short", "category": "cyberpunk"},
        "author": {"name": "You"},
    }
    result = get_adapter("aura").adapt(raw)
    assert not isinstance(result, SkipReason)
    assert result.source == "aura"
    assert "neon" in result.body_text


def test_aura_adapter_embed_only_synthesizes_body():
    raw = {
        "_id": "oid2",
        "source": "aura",
        "external_id": "u2",
        "title": "Cool thread",
        "embed_url": "https://example.com/x/status/1",
        "metadata": {"kind": "embed"},
    }
    result = get_adapter("aura").adapt(raw)
    assert not isinstance(result, SkipReason)
    assert "example.com" in result.body_text


def test_default_still_skips_tiny_body():
    raw = {
        "_id": "oid3",
        "source": "rss",
        "external_id": "r1",
        "content_text": "too short",
    }
    assert get_adapter("rss").adapt(raw) == SkipReason.TOO_SHORT
