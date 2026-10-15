# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""MongoDB persistence — posts, users, and interactions."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure

from scraper.config import Settings, get_settings
from scraper.models.document import ContentDocument, EmbeddingStatus

logger = logging.getLogger(__name__)


def _to_object_id(post_id: str) -> ObjectId | str:
    try:
        return ObjectId(post_id)
    except InvalidId:
        return post_id


class MongoDocumentStore:
    """Upsert posts keyed by (source, external_id)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: MongoClient | None = None

    @property
    def client(self) -> MongoClient:
        if self._client is None:
            uri = self.settings.build_mongo_uri()
            self._client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        return self._client

    @property
    def collection(self) -> Collection:
        return self.client[self.settings.mongo_db][self.settings.mongo_collection]

    @property
    def users(self) -> Collection:
        return self.client[self.settings.mongo_db][self.settings.mongo_users_collection]

    @property
    def interactions(self) -> Collection:
        return self.client[self.settings.mongo_db][
            self.settings.mongo_interactions_collection
        ]

    def ping(self) -> bool:
        try:
            self.client.admin.command("ping")
            return True
        except ConnectionFailure as exc:
            logger.error("MongoDB ping failed: %s", exc)
            return False

    def ensure_indexes(self) -> None:
        coll = self.collection
        coll.create_index(
            [("source", ASCENDING), ("external_id", ASCENDING)],
            unique=True,
            name="uniq_source_external_id",
        )
        coll.create_index(
            [("source", ASCENDING), ("scraped_at", DESCENDING)],
            name="source_scraped_at",
        )
        coll.create_index([("categories", ASCENDING)], name="categories")
        coll.create_index([("author.name", ASCENDING)], name="author_name")
        coll.create_index([("published_at", DESCENDING)], name="published_at")
        coll.create_index([("tags", ASCENDING)], name="tags")
        coll.create_index([("embedding_status", ASCENDING)], name="embedding_status")
        coll.create_index([("metadata.subdomain", ASCENDING)], name="subdomain")
        coll.create_index([("metadata.type", ASCENDING)], name="metadata_type")
        coll.create_index([("content_hash", ASCENDING)], name="content_hash")

        self.users.create_index([("user_id", ASCENDING)], unique=True, name="uniq_user_id")
        self.interactions.create_index(
            [("user_id", ASCENDING), ("ts", DESCENDING)],
            name="user_ts",
        )
        self.interactions.create_index(
            [("user_id", ASCENDING), ("post_id", ASCENDING)],
            name="user_post",
        )
        logger.info("Ensured MongoDB indexes on %s", self.settings.mongo_db)

    def drop_all(self) -> int:
        """Delete every document in the posts collection. Dev-friendly reset."""
        result = self.collection.delete_many({})
        logger.info("Dropped %s posts", result.deleted_count)
        return result.deleted_count

    def upsert(self, document: ContentDocument) -> dict[str, Any]:
        self._upsert_one(document)
        return self.collection.find_one(document.mongo_key()) or document.scraped_fields()

    def _upsert_one(self, document: ContentDocument) -> None:
        scraped = document.scraped_fields()
        existing = self.collection.find_one(
            document.mongo_key(),
            {"content_hash": 1, "embedding_status": 1},
        )
        update: dict[str, Any] = {"$set": scraped}
        set_on_insert: dict[str, Any] = {
            "embedding_status": EmbeddingStatus.PENDING.value,
        }
        # Re-queue for embedding when content hash changes (caller may set content_hash later)
        if existing and existing.get("content_hash") and scraped.get("content_hash"):
            if existing["content_hash"] != scraped["content_hash"]:
                update["$set"]["embedding_status"] = EmbeddingStatus.PENDING.value
                update["$unset"] = {
                    "embedding_id": "",
                    "embedding_error": "",
                    "embedded_at": "",
                }
        update["$setOnInsert"] = set_on_insert
        self.collection.update_one(document.mongo_key(), update, upsert=True)

    def upsert_many(self, documents: list[ContentDocument]) -> dict[str, int]:
        if not documents:
            return {"upserted": 0, "modified": 0, "matched": 0}

        keys = [doc.mongo_key() for doc in documents]
        existing_map: dict[tuple[str, str], dict[str, Any]] = {}
        for doc in self.collection.find(
            {"$or": keys},
            {"source": 1, "external_id": 1, "content_hash": 1},
        ):
            existing_map[(doc["source"], doc["external_id"])] = doc

        ops: list[UpdateOne] = []
        for document in documents:
            scraped = document.scraped_fields()
            existing = existing_map.get((document.source, document.external_id))
            update: dict[str, Any] = {
                "$set": scraped,
                "$setOnInsert": {"embedding_status": EmbeddingStatus.PENDING.value},
            }
            if (
                existing
                and existing.get("content_hash")
                and scraped.get("content_hash")
                and existing["content_hash"] != scraped["content_hash"]
            ):
                update["$set"]["embedding_status"] = EmbeddingStatus.PENDING.value
                update["$unset"] = {
                    "embedding_id": "",
                    "embedding_error": "",
                    "embedded_at": "",
                }
            ops.append(UpdateOne(document.mongo_key(), update, upsert=True))

        result = self.collection.bulk_write(ops, ordered=False)
        summary = {
            "upserted": result.upserted_count,
            "modified": result.modified_count,
            "matched": result.matched_count,
        }
        logger.info("Bulk upsert complete: %s", summary)
        return summary

    def get(self, source: str, external_id: str) -> dict[str, Any] | None:
        return self.collection.find_one({"source": source, "external_id": external_id})

    def get_by_id(self, post_id: str) -> dict[str, Any] | None:
        return self.collection.find_one({"_id": _to_object_id(post_id)})

    def get_many_by_ids(self, post_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Return ``{post_id_str: doc}`` for ids that exist."""
        if not post_ids:
            return {}
        object_ids: list[ObjectId | str] = []
        for pid in post_ids:
            object_ids.append(_to_object_id(pid))
        found: dict[str, dict[str, Any]] = {}
        for doc in self.collection.find({"_id": {"$in": object_ids}}):
            found[str(doc["_id"])] = doc
        return found

    def list_by_source(
        self,
        source: str,
        *,
        limit: int = 100,
        skip: int = 0,
    ) -> Iterator[dict[str, Any]]:
        cursor = (
            self.collection.find({"source": source})
            .sort([("scraped_at", DESCENDING), ("published_at", DESCENDING)])
            .skip(skip)
            .limit(limit)
        )
        yield from cursor

    def list_discover(
        self,
        *,
        limit: int = 40,
        source: str | None = None,
        ready_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Popular / recent posts for the Discover tab."""
        filt: dict[str, Any] = {}
        if source:
            filt["source"] = source
        if ready_only:
            filt["embedding_status"] = EmbeddingStatus.READY.value
        cursor = (
            self.collection.find(filt)
            .sort(
                [
                    ("reaction_count", DESCENDING),
                    ("published_at", DESCENDING),
                    ("scraped_at", DESCENDING),
                ]
            )
            .limit(limit)
        )
        return list(cursor)

    def count(self, source: str | None = None) -> int:
        filt: dict[str, Any] = {}
        if source:
            filt["source"] = source
        return self.collection.count_documents(filt)

    def iter_for_embedding(
        self,
        *,
        source: str | None = None,
        limit: int | None = None,
        retry_failed: bool = False,
        force: bool = False,
    ) -> Iterator[dict[str, Any]]:
        filt: dict[str, Any] = {}
        if source:
            filt["source"] = source
        if force:
            pass
        elif retry_failed:
            filt["embedding_status"] = {
                "$in": [EmbeddingStatus.PENDING.value, EmbeddingStatus.FAILED.value]
            }
        else:
            filt["embedding_status"] = EmbeddingStatus.PENDING.value

        cursor = self.collection.find(filt).sort([("scraped_at", DESCENDING)])
        if limit is not None:
            cursor = cursor.limit(limit)
        yield from cursor

    def mark_embedded(
        self,
        source: str,
        external_id: str,
        *,
        embedding_id: str,
        embedding_model: str,
        content_hash: str,
        chunk_count: int,
        facets: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "embedding_status": EmbeddingStatus.READY.value,
            "embedding_id": embedding_id,
            "embedding_model": embedding_model,
            "embedded_at": datetime.now(UTC),
            "content_hash": content_hash,
            "chunk_count": chunk_count,
        }
        if facets is not None:
            payload["facets"] = facets
        self.collection.update_one(
            {"source": source, "external_id": external_id},
            {"$set": payload, "$unset": {"embedding_error": ""}},
        )

    def mark_embedding_skipped(
        self,
        source: str,
        external_id: str,
        reason: str,
    ) -> None:
        self.collection.update_one(
            {"source": source, "external_id": external_id},
            {
                "$set": {
                    "embedding_status": EmbeddingStatus.SKIPPED.value,
                    "embedding_error": reason,
                }
            },
        )

    def mark_embedding_failed(
        self,
        source: str,
        external_id: str,
        error: str,
    ) -> None:
        self.collection.update_one(
            {"source": source, "external_id": external_id},
            {
                "$set": {
                    "embedding_status": EmbeddingStatus.FAILED.value,
                    "embedding_error": error[:500],
                }
            },
        )

    def embedding_stats(self, source: str | None = None) -> dict[str, int]:
        match: dict[str, Any] = {}
        if source:
            match["source"] = source
        pipeline: list[dict[str, Any]] = []
        if match:
            pipeline.append({"$match": match})
        pipeline.append({"$group": {"_id": "$embedding_status", "n": {"$sum": 1}}})
        counts = {row["_id"] or "missing": row["n"] for row in self.collection.aggregate(pipeline)}
        counts["total"] = sum(v for k, v in counts.items() if k != "total")
        return counts

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> MongoDocumentStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
