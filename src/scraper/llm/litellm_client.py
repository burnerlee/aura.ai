# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""LiteLLM client for indexing embeds + facet extraction (paid / proxy key)."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, TypeVar

import httpx
import numpy as np
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from scraper.config import Settings, get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _l2_normalize(vector: list[float]) -> list[float]:
    arr = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm < 1e-12:
        return arr.tolist()
    return (arr / norm).tolist()


class LiteLLMClient:
    """Embeddings + JSON generation via LiteLLM (Gemini or any supported model)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.litellm_api_key:
            raise RuntimeError(
                "LITELLM_API_KEY is not set. Add it to .env for indexing embeds / facets."
            )
        self._sem = threading.Semaphore(self.settings.embed_concurrency)

    def _completion_kwargs(self) -> dict[str, Any]:
        """Auth for chat/completions via DevRev AI gateway (or any LiteLLM proxy)."""
        kwargs: dict[str, Any] = {"api_key": self.settings.litellm_api_key}
        if self.settings.litellm_api_base:
            kwargs["api_base"] = self.settings.litellm_api_base
        return kwargs

    def _embed_kwargs(self) -> dict[str, Any]:
        """Auth for embeddings.

        Gateway virtual keys (arcus) typically expose chat models on ``/v1`` but not
        Gemini embeddings. When the configured embed model is ``gemini/...``, call
        Google directly with ``GEMINI_API_KEY`` and skip the proxy base URL.
        """
        model = self.settings.litellm_embedding_model
        if model.startswith("gemini/") and self.settings.gemini_api_key:
            return {"api_key": self.settings.gemini_api_key}
        kwargs: dict[str, Any] = {"api_key": self.settings.litellm_api_key}
        if self.settings.litellm_api_base:
            # OpenAI-compat embeddings live under /openai/v1 on the DevRev gateway.
            base = self.settings.litellm_api_base.rstrip("/")
            if base.endswith("/v1"):
                root = base[: -len("/v1")]
                kwargs["api_base"] = f"{root}/openai/v1"
            else:
                kwargs["api_base"] = base
        return kwargs

    def _truncate(self, values: list[float]) -> list[float]:
        dim = self.settings.embedding_dim
        if len(values) > dim:
            values = values[:dim]
        return _l2_normalize(values)

    @retry(wait=wait_exponential(multiplier=1, min=1, max=20), stop=stop_after_attempt(4))
    def _embed_raw(self, text: str) -> list[float]:
        from litellm import embedding

        with self._sem:
            result = embedding(
                model=self.settings.litellm_embedding_model,
                input=[text],
                **self._embed_kwargs(),
            )
        data = result.data[0]
        values = list(data["embedding"] if isinstance(data, dict) else data.embedding)
        return self._truncate(values)

    def embed_document(self, text: str, title: str | None = None) -> list[float]:
        title_part = title.strip() if title and title.strip() else "none"
        payload = f"title: {title_part} | text: {text}"
        return self._embed_raw(payload)

    def embed_query(self, text: str) -> list[float]:
        payload = f"task: search result | query: {text}"
        return self._embed_raw(payload)

    def embed_image(self, url: str) -> list[float] | None:
        """Best-effort image embed; many LiteLLM routes are text-only."""
        try:
            response = httpx.get(url, timeout=self.settings.http_timeout_seconds)
            response.raise_for_status()
            # Fall back to captioning the URL as text if multimodal isn't available.
            return self._embed_raw(f"image: {url}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("LiteLLM image embed failed for %s: %s", url, exc)
            return None

    @retry(wait=wait_exponential(multiplier=1, min=1, max=20), stop=stop_after_attempt(3))
    def generate_json(self, prompt: str, schema: type[T]) -> T:
        from litellm import completion

        schema_hint = json.dumps(schema.model_json_schema(), indent=2)
        messages = [
            {
                "role": "system",
                "content": (
                    "Return only valid JSON matching this schema. "
                    f"No markdown fences.\n{schema_hint}"
                ),
            },
            {"role": "user", "content": prompt},
        ]
        with self._sem:
            response = completion(
                model=self.settings.litellm_llm_model,
                messages=messages,
                response_format={"type": "json_object"},
                # Reasoning models (e.g. gemini-3.8-flash) spend tokens on thoughts.
                max_tokens=4096,
                **self._completion_kwargs(),
            )
        text = response.choices[0].message.content or "{}"
        return schema.model_validate_json(text)
