# Copyright (c) 2026 DevRev Inc. All rights reserved.

import pytest

from scraper.connectors.substack import html_to_text, resolve_publication_base
from scraper.models.document import ContentDocument, EmbeddingStatus


def test_resolve_handle():
    assert resolve_publication_base("platformer") == "https://platformer.substack.com"


def test_resolve_url():
    assert (
        resolve_publication_base("https://www.lennysnewsletter.com/archive")
        == "https://www.lennysnewsletter.com"
    )


def test_resolve_invalid():
    with pytest.raises(ValueError):
        resolve_publication_base("not a handle!!!")


def test_html_to_text():
    assert "Hello" in (html_to_text("<p>Hello <b>world</b></p>") or "")


def test_content_document_mongo_key():
    doc = ContentDocument(
        source="substack",
        external_id="123",
        title="t",
        embedding_status=EmbeddingStatus.PENDING,
        raw={"huge": "blob"},
    )
    assert doc.mongo_key() == {"source": "substack", "external_id": "123"}
    payload = doc.to_mongo()
    assert payload["title"] == "t"
    assert "embed_url" not in payload
    assert "raw" not in payload
    assert "content" not in payload
    assert payload["embedding_status"] == "pending"


def test_to_mongo_prunes_empty_author_fields():
    doc = ContentDocument(
        source="substack",
        external_id="1",
        title="Hello",
        author={"name": "Ada", "bio": "  ", "url": None},  # type: ignore[arg-type]
        tags=[],
        media_urls=[],
    )
    payload = doc.to_mongo()
    assert payload["author"] == {"name": "Ada"}
    assert "tags" not in payload
    assert "media_urls" not in payload
