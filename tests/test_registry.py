# Copyright (c) 2026 DevRev Inc. All rights reserved.

from scraper.connectors import get_connector, list_connectors
from scraper.connectors.base import ConnectorConfig


def test_substack_registered():
    names = {c["name"] for c in list_connectors()}
    assert "substack" in names


def test_get_substack():
    connector = get_connector("substack", ConnectorConfig(source_id="platformer", limit=1))
    assert connector.name == "substack"
