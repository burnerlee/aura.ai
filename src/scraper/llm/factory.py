# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Resolve indexing vs user-inference LLM clients."""

from __future__ import annotations

import logging

from scraper.config import Settings, get_settings
from scraper.llm.base import LLMClient
from scraper.llm.gemini import GeminiClient
from scraper.llm.litellm_client import LiteLLMClient

logger = logging.getLogger(__name__)


def get_indexing_client(settings: Settings | None = None) -> LLMClient:
    """Client for batch embed / facet extraction.

    Prefers LiteLLM (paid / proxy key). Falls back to free-tier Gemini.
    """
    settings = settings or get_settings()
    if settings.litellm_api_key:
        logger.debug("Indexing client: LiteLLM (%s)", settings.litellm_embedding_model)
        return LiteLLMClient(settings)
    if settings.gemini_api_key:
        logger.warning(
            "LITELLM_API_KEY unset — indexing via free-tier Gemini (rate limits likely)"
        )
        return GeminiClient(settings)
    raise RuntimeError(
        "Set LITELLM_API_KEY (preferred for indexing) or GEMINI_API_KEY."
    )


def get_inference_client(settings: Settings | None = None) -> LLMClient:
    """Client for onboard / persona / rerank.

    Prefers free-tier Gemini. Falls back to LiteLLM when Gemini is unset.
    """
    settings = settings or get_settings()
    if settings.gemini_api_key:
        logger.debug("Inference client: Gemini (%s)", settings.gemini_llm_model)
        return GeminiClient(settings)
    if settings.litellm_api_key:
        logger.warning(
            "GEMINI_API_KEY unset — user inference via LiteLLM"
        )
        return LiteLLMClient(settings)
    raise RuntimeError(
        "Set GEMINI_API_KEY (preferred for user inference) or LITELLM_API_KEY."
    )


def get_chat_client(settings: Settings | None = None) -> LLMClient:
    """Client for Aura conversational chat.

    Prefers LiteLLM (paid gateway). Falls back to free-tier Gemini.
    """
    settings = settings or get_settings()
    if settings.litellm_api_key:
        logger.debug("Chat client: LiteLLM (%s)", settings.litellm_llm_model)
        return LiteLLMClient(settings)
    if settings.gemini_api_key:
        logger.warning(
            "LITELLM_API_KEY unset — Aura chat via free-tier Gemini (rate limits likely)"
        )
        return GeminiClient(settings)
    raise RuntimeError(
        "Set LITELLM_API_KEY (preferred for Aura chat) or GEMINI_API_KEY."
    )
