# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Orchestrate scrape → normalize → MongoDB upsert."""

from __future__ import annotations

import logging
from typing import Any

from scraper.connectors import get_connector
from scraper.connectors.base import ConnectorConfig
from scraper.storage.mongodb import MongoDocumentStore

logger = logging.getLogger(__name__)


def run_scrape(
    connector_name: str,
    source_id: str,
    *,
    limit: int | None = None,
    offset: int = 0,
    fetch_full_content: bool = True,
    batch_size: int = 25,
    extras: dict[str, Any] | None = None,
    store: MongoDocumentStore | None = None,
) -> dict[str, Any]:
    """Run a connector and persist documents to MongoDB."""
    config = ConnectorConfig(
        source_id=source_id,
        limit=limit,
        offset=offset,
        fetch_full_content=fetch_full_content,
        extras=extras or {},
    )
    connector = get_connector(connector_name, config)
    owns_store = store is None
    store = store or MongoDocumentStore()

    scraped = 0
    batch: list = []
    totals = {"upserted": 0, "modified": 0, "matched": 0}

    try:
        if not store.ping():
            raise RuntimeError(
                "Cannot reach MongoDB. Run `make mongo-up` and check MONGO_* settings."
            )
        store.ensure_indexes()

        for doc in connector.scrape():
            batch.append(doc)
            scraped += 1
            if len(batch) >= batch_size:
                result = store.upsert_many(batch)
                for key in totals:
                    totals[key] += result[key]
                batch.clear()

        if batch:
            result = store.upsert_many(batch)
            for key in totals:
                totals[key] += result[key]

        summary = {
            "connector": connector_name,
            "source_id": source_id,
            "scraped": scraped,
            **totals,
            "collection_total": store.count(connector_name),
        }
        logger.info("Scrape finished: %s", summary)
        return summary
    finally:
        if owns_store:
            store.close()
