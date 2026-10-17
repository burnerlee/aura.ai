# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Per-source content adapters: raw Mongo dict -> EmbeddableContent."""

# Side-effect registration
from scraper.adapters import aura as _aura  # noqa: F401
from scraper.adapters import default as _default  # noqa: F401
from scraper.adapters import reddit as _reddit  # noqa: F401
from scraper.adapters import substack as _substack  # noqa: F401
from scraper.adapters.registry import get_adapter, list_adapters, register_adapter

__all__ = ["get_adapter", "list_adapters", "register_adapter"]
