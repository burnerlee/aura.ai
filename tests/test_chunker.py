# Copyright (c) 2026 DevRev Inc. All rights reserved.

from scraper.config import Settings
from scraper.embedding.chunker import chunk_content
from scraper.models.embeddable import EmbeddableContent


def _content(body_words: int = 500) -> EmbeddableContent:
    return EmbeddableContent(
        post_id="p1",
        source="test",
        external_id="1",
        title="Title here",
        subtitle="Sub",
        summary="Summary line",
        body_text=" ".join([f"w{i}" for i in range(body_words)]),
    )


def test_head_chunk_first():
    chunks = chunk_content(_content(100), Settings(chunk_words=50, chunk_overlap_words=10))
    assert chunks[0].kind == "head"
    assert "Title here" in chunks[0].text


def test_overlap_and_cap():
    settings = Settings(chunk_words=50, chunk_overlap_words=10, max_chunks_per_post=5)
    chunks = chunk_content(_content(1000), settings)
    assert len(chunks) <= 5
    assert any(c.kind == "body" for c in chunks)


def test_content_hash_stable():
    a = _content(80)
    b = _content(80)
    assert a.content_hash == b.content_hash
    c = a.model_copy(update={"title": "Other"})
    assert c.content_hash != a.content_hash
