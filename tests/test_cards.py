# Copyright (c) 2026 DevRev Inc. All rights reserved.

from scraper.api.cards import UGC_SOURCE, hydrate_scored, mongo_to_card
from scraper.models.document import EmbeddingStatus
from scraper.query.types import ScoredPost


def test_mongo_to_card_uses_mongo_id():
    raw = {
        "_id": "507f1f77bcf86cd799439011",
        "source": "substack",
        "external_id": "post-9",
        "title": "Hello",
        "content_text": "A longer body about climate and policy " + ("word " * 40),
        "author": {"name": "Casey"},
        "categories": ["ai"],
        "tags": ["ml"],
        "reaction_count": 3,
        "embedding_status": EmbeddingStatus.READY.value,
        "published_at": "2026-01-02T00:00:00+00:00",
    }
    card = mongo_to_card(raw, score=0.9, why="matched query")
    assert card.id == "507f1f77bcf86cd799439011"
    assert card.source == "substack"
    assert card.external_id == "post-9"
    assert card.category == "ai"
    assert card.author.name == "Casey"
    assert card.score == 0.9
    assert card.why == "matched query"
    assert card.platform == "Substack"


def test_aura_ugc_category_from_metadata():
    raw = {
        "_id": "abc",
        "source": UGC_SOURCE,
        "external_id": "u1",
        "title": None,
        "content_text": "short thought about neon cities tonight",
        "metadata": {"kind": "short", "category": "cyberpunk"},
        "author": {"name": "You", "external_id": "user-1"},
        "embedding_status": EmbeddingStatus.PENDING.value,
    }
    card = mongo_to_card(raw)
    assert card.kind.value == "short"
    assert card.category == "cyberpunk"
    assert card.embedding_status == "pending"


def test_hydrate_scored_falls_back_to_payload():
    results = [
        ScoredPost(
            post_id="missing",
            score=0.5,
            payload={
                "source": "substack",
                "external_id": "x",
                "title": "From payload",
                "author_name": "Pat",
            },
            reason="fallback",
        )
    ]
    cards = hydrate_scored(results, {})
    assert len(cards) == 1
    assert cards[0].title == "From payload"
    assert cards[0].why == "fallback"
