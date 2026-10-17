# Copyright (c) 2026 DevRev Inc. All rights reserved.

import pytest

from scraper.connectors import get_connector, list_connectors
from scraper.connectors.base import ConnectorConfig
from scraper.connectors.reddit import RedditConnector, resolve_subreddit


def test_resolve_subreddit_bare():
    assert resolve_subreddit("worldbuilding") == "worldbuilding"


def test_resolve_subreddit_r_prefix():
    assert resolve_subreddit("r/worldbuilding") == "worldbuilding"


def test_resolve_subreddit_url():
    assert (
        resolve_subreddit("https://www.reddit.com/r/worldbuilding/new/")
        == "worldbuilding"
    )


def test_resolve_subreddit_invalid():
    with pytest.raises(ValueError):
        resolve_subreddit("r/not a subreddit")


def test_reddit_registered():
    names = {c["name"] for c in list_connectors()}
    assert "reddit" in names


def test_get_reddit_connector():
    connector = get_connector("reddit", ConnectorConfig(source_id="worldbuilding", limit=1))
    assert isinstance(connector, RedditConnector)
    assert connector.subreddit == "worldbuilding"

