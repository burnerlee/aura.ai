# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Mongo upsert preserves embedding fields (requires running MongoDB)."""

from __future__ import annotations

import os

import pytest

from scraper.models.document import ContentDocument, EmbeddingStatus
from scraper.storage.mongodb import MongoDocumentStore

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_MONGO_TESTS") == "1",
    reason="SKIP_MONGO_TESTS=1",
)


@pytest.fixture
def store():
    s = MongoDocumentStore()
    if not s.ping():
        pytest.skip("MongoDB not available")
    # Use a unique external_id namespace
    yield s
    s.collection.delete_many({"source": "test_upsert"})
    s.close()


def test_re_scrape_preserves_embedding(store: MongoDocumentStore):
    doc = ContentDocument(
        source="test_upsert",
        external_id="preserve-1",
        title="Hello",
        content_text=" ".join(["word"] * 50),
    )
    store.upsert(doc)
    store.mark_embedded(
        "test_upsert",
        "preserve-1",
        embedding_id="point-1",
        embedding_model="test-model",
        content_hash="hash-a",
        chunk_count=2,
        facets={"topics": ["x"]},
    )
    before = store.get("test_upsert", "preserve-1")
    assert before["embedding_status"] == EmbeddingStatus.READY.value
    assert before["embedding_id"] == "point-1"

    # Re-scrape without content_hash in scraped fields
    doc2 = ContentDocument(
        source="test_upsert",
        external_id="preserve-1",
        title="Hello updated title",
        content_text=" ".join(["word"] * 50),
    )
    store.upsert(doc2)
    after = store.get("test_upsert", "preserve-1")
    assert after["embedding_status"] == EmbeddingStatus.READY.value
    assert after["embedding_id"] == "point-1"
    assert after["title"] == "Hello updated title"
    assert after.get("facets", {}).get("topics") == ["x"]


def test_content_hash_change_flips_pending(store: MongoDocumentStore):
    store.collection.update_one(
        {"source": "test_upsert", "external_id": "hash-1"},
        {
            "$set": {
                "source": "test_upsert",
                "external_id": "hash-1",
                "title": "A",
                "content_text": "body",
                "content_hash": "old",
                "embedding_status": EmbeddingStatus.READY.value,
                "embedding_id": "p",
            }
        },
        upsert=True,
    )
    # scraped_fields excludes embedding-owned content_hash; worker sets it on mark_embedded.
    # Simulate the content-change branch that flips status back to pending.
    existing = store.collection.find_one({"source": "test_upsert", "external_id": "hash-1"})
    assert existing["content_hash"] == "old"
    store.collection.update_one(
        {"source": "test_upsert", "external_id": "hash-1"},
        {
            "$set": {
                "title": "B",
                "content_hash": "new",
                "embedding_status": EmbeddingStatus.PENDING.value,
            },
            "$unset": {"embedding_id": "", "embedding_error": "", "embedded_at": ""},
        },
    )
    after = store.get("test_upsert", "hash-1")
    assert after["embedding_status"] == EmbeddingStatus.PENDING.value
    assert "embedding_id" not in after or after.get("embedding_id") is None
