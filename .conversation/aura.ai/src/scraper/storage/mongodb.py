# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""MongoDB persistence — single posts collection for all connectors."""

from __future__ import annotations

import logging
from typing import Any, Iterator

from pymongo import ASCENDING, DESCENDING, MongoClient, ReplaceOne
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure

from scraper.config import Settings, get_settings
from scraper.models.document import ContentDocument

logger = logging.getLogger(__name__)


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
        logger.info("Ensured MongoDB indexes on %s.%s", self.settings.mongo_db, coll.name)

    def drop_all(self) -> int:
        """Delete every document in the posts collection. Dev-friendly reset."""
        result = self.collection.delete_many({})
        logger.info("Dropped %s posts", result.deleted_count)
        return result.deleted_count

    def upsert(self, document: ContentDocument) -> dict[str, Any]:
        payload = document.to_mongo()
        self.collection.replace_one(document.mongo_key(), payload, upsert=True)
        return self.collection.find_one(document.mongo_key()) or payload

    def upsert_many(self, documents: list[ContentDocument]) -> dict[str, int]:
        if not documents:
            return {"upserted": 0, "modified": 0, "matched": 0}

        ops = [
            ReplaceOne(doc.mongo_key(), doc.to_mongo(), upsert=True) for doc in documents
        ]
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

    def count(self, source: str | None = None) -> int:
        filt: dict[str, Any] = {}
        if source:
            filt["source"] = source
        return self.collection.count_documents(filt)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> MongoDocumentStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
