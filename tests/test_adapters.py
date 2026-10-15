# Copyright (c) 2026 DevRev Inc. All rights reserved.

from datetime import UTC, datetime

from scraper.adapters import get_adapter
from scraper.adapters.base import FieldSpec, strip_html
from scraper.models.embeddable import SkipReason


def test_default_adapter_html_only_body():
    raw = {
        "_id": "abc123",
        "source": "rss",
        "external_id": "1",
        "title": "Hello",
        "content_html": "<p>" + "word " * 50 + "</p>",
        "published_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    result = get_adapter("rss").adapt(raw)
    assert not isinstance(result, SkipReason)
    assert "word" in result.body_text
    assert result.title == "Hello"
    assert result.content_hash


def test_missing_author_and_published():
    raw = {
        "_id": "x",
        "source": "rss",
        "external_id": "2",
        "title": "T",
        "content_text": " ".join(["alpha"] * 60),
        "scraped_at": datetime(2026, 2, 1, tzinfo=UTC),
    }
    result = get_adapter("unknown").adapt(raw)
    assert not isinstance(result, SkipReason)
    assert result.author_name is None
    assert result.published_at is not None


def test_too_short_skipped():
    raw = {
        "_id": "y",
        "source": "rss",
        "external_id": "3",
        "title": "Short",
        "content_text": "tiny",
    }
    result = get_adapter().adapt(raw)
    assert result == SkipReason.TOO_SHORT


def test_substack_skips_non_post():
    raw = {
        "_id": "z",
        "source": "substack",
        "external_id": "4",
        "title": "Blog card",
        "content_text": " ".join(["word"] * 80),
        "metadata": {"type": "publication"},
    }
    result = get_adapter("substack").adapt(raw)
    assert result == SkipReason.NOT_A_POST


def test_substack_folds_section_and_hints():
    raw = {
        "_id": "s1",
        "source": "substack",
        "external_id": "5",
        "title": "Post",
        "content_text": " ".join(["word"] * 80),
        "categories": ["newsletter"],
        "metadata": {
            "type": "post",
            "section_name": "Deep Dives",
            "is_paid": "False",
            "post_type": "newsletter",
            "slug": "post",
        },
        "author": {"name": "Ada"},
    }
    result = get_adapter("substack").adapt(raw)
    assert not isinstance(result, SkipReason)
    assert "Deep Dives" in result.categories
    assert result.hints.get("section_name") == "Deep Dives"
    assert result.author_name == "Ada"


def test_field_spec_dotted_path():
    raw = {"author": {"name": "Bob"}, "metadata": {"byline": "X"}}
    spec = FieldSpec("author.name", "metadata.byline")
    assert spec.resolve(raw) == "Bob"
    assert FieldSpec("missing", "metadata.byline").resolve(raw) == "X"


def test_strip_html():
    assert strip_html("<p>Hi <b>there</b></p>") == "Hi there"
