# Copyright (c) 2026 DevRev Inc. All rights reserved.

from scraper.connectors.base import BaseConnector, ConnectorConfig
from scraper.connectors.registry import get_connector, list_connectors, register_connector

# Import concrete connectors so they self-register.
from scraper.connectors import substack as _substack  # noqa: F401

__all__ = [
    "BaseConnector",
    "ConnectorConfig",
    "get_connector",
    "list_connectors",
    "register_connector",
]
