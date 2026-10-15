# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Offline leave-last-out eval + hold_ms correlation + reweigh."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from scraper.config import Settings, get_settings
from scraper.models.user import EventType, Interaction
from scraper.profile.weights import (
    WEIGHT_FUNCTIONS,
    WEIGHT_VERSION_DEFAULT,
    compute_weight,
    correlation,
)
from scraper.storage.mongodb import MongoDocumentStore

logger = logging.getLogger(__name__)


def leave_last_out_metrics(
    store: MongoDocumentStore,
    *,
    recommend_fn,
    k: int = 10,
    min_positives: int = 2,
) -> dict[str, float]:
    """Recall@k / Precision@k over users with enough positive interactions."""
    by_user: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for doc in store.interactions.find({"weight": {"$gt": 0.2}}).sort("ts", 1):
        by_user[doc["user_id"]].append(doc)

    recalls: list[float] = []
    precisions: list[float] = []
    for user_id, events in by_user.items():
        if len(events) < min_positives:
            continue
        held = events[-1]
        held_post = held.get("post_id")
        if not held_post:
            continue
        # Temporarily treat as unseen by recommending with exclude of prior
        results = recommend_fn(user_id, k=k, exclude_last=held_post)
        ids = [r.post_id for r in results]
        hit = 1.0 if held_post in ids else 0.0
        recalls.append(hit)
        precisions.append(hit / max(k, 1))

    n = len(recalls) or 1
    return {
        "users_evaluated": float(len(recalls)),
        f"recall@{k}": sum(recalls) / n if recalls else 0.0,
        f"precision@{k}": sum(precisions) / n if recalls else 0.0,
    }


def hold_ms_correlation_report(store: MongoDocumentStore) -> dict[str, float | None]:
    """Correlate swipe hold_ms with later strong positive signals on the same post."""
    swipes = list(
        store.interactions.find(
            {
                "event": {"$in": [EventType.LIKE.value, EventType.NOT_INTERESTED.value]},
                "hold_ms": {"$ne": None},
            }
        )
    )
    holds: list[float] = []
    later_pos: list[float] = []
    for swipe in swipes:
        user_id = swipe["user_id"]
        post_id = swipe.get("post_id")
        if not post_id:
            continue
        later = store.interactions.find_one(
            {
                "user_id": user_id,
                "post_id": post_id,
                "event": {
                    "$in": [
                        EventType.SAVE.value,
                        EventType.CLICK_THROUGH.value,
                        EventType.DWELL.value,
                    ]
                },
                "ts": {"$gt": swipe["ts"]},
            }
        )
        holds.append(float(swipe.get("hold_ms") or 0))
        if later is None:
            later_pos.append(0.0)
        elif later.get("event") == EventType.DWELL.value:
            later_pos.append(float(later.get("read_ratio") or 0.0))
        else:
            later_pos.append(1.0)
    return {
        "n": float(len(holds)),
        "corr_hold_vs_later_positive": correlation(holds, later_pos),
    }


def reweigh_interactions(
    store: MongoDocumentStore,
    *,
    version: str = WEIGHT_VERSION_DEFAULT,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    if version not in WEIGHT_FUNCTIONS and version not in (
        "default",
        "hold_linear",
        "hold_log",
    ):
        raise ValueError(f"Unknown weight version: {version}")
    updated = 0
    users: set[str] = set()
    for doc in store.interactions.find({}):
        interaction = Interaction.model_validate(
            {k: v for k, v in doc.items() if k != "_id"}
        )
        word_count = None
        if interaction.post_id:
            post = store.get_by_id(interaction.post_id)
            if post:
                word_count = post.get("word_count")
        new_weight = compute_weight(
            interaction, version=version, word_count=word_count
        )
        if interaction.event == EventType.PAIRWISE and interaction.text == "loser":
            new_weight = -0.3
        store.interactions.update_one(
            {"_id": doc["_id"]},
            {"$set": {"weight": new_weight, "weight_version": version}},
        )
        updated += 1
        users.add(interaction.user_id)
    return {"updated": updated, "users": len(users), "version": version}


def synthetic_user_signals(
    store: MongoDocumentStore,
    *,
    category: str,
    user_id: str = "synthetic",
    n_likes: int = 5,
) -> int:
    """Seed interactions for a synthetic user from a category (for offline iteration)."""
    posts = list(
        store.collection.find({"categories": category}).limit(n_likes)
    )
    count = 0
    for post in posts:
        interaction = Interaction(
            user_id=user_id,
            post_id=str(post["_id"]),
            event=EventType.LIKE,
            strength=1,
            weight=0.7,
            weight_version=WEIGHT_VERSION_DEFAULT,
        )
        store.interactions.insert_one(interaction.to_mongo())
        count += 1
    return count
