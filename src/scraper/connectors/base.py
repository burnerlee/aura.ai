# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Connector interface for pluggable content sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, Field

from scraper.models.document import ContentDocument


class ConnectorConfig(BaseModel):
    """Generic connector run configuration."""

    source_id: str
    limit: int | None = None
    offset: int = 0
    fetch_full_content: bool = True
    extras: dict[str, Any] = Field(default_factory=dict)


class BaseConnector(ABC):
    """All scrapers implement this contract and yield ``ContentDocument``s."""

    name: str
    description: str = ""

    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config

    @abstractmethod
    def scrape(self) -> Iterator[ContentDocument]:
        """Yield normalized documents from the source."""

    def validate_config(self) -> None:
        """Optional hook for connector-specific config validation."""
        if not self.config.source_id:
            raise ValueError("source_id is required")
