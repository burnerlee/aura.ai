# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Registry mapping connector names to implementations."""

from __future__ import annotations

from scraper.connectors.base import BaseConnector, ConnectorConfig

_REGISTRY: dict[str, type[BaseConnector]] = {}


def register_connector(cls: type[BaseConnector]) -> type[BaseConnector]:
    key = cls.name.lower()
    if key in _REGISTRY:
        raise ValueError(f"Connector already registered: {key}")
    _REGISTRY[key] = cls
    return cls


def get_connector(name: str, config: ConnectorConfig) -> BaseConnector:
    key = name.lower()
    if key not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(f"Unknown connector '{name}'. Available: {available}")
    connector = _REGISTRY[key](config)
    connector.validate_config()
    return connector


def list_connectors() -> list[dict[str, str]]:
    return [
        {"name": cls.name, "description": cls.description}
        for cls in sorted(_REGISTRY.values(), key=lambda c: c.name)
    ]
