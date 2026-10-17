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
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from litellm import completion, embedding

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

    def _embed_kwargs(self, model: str) -> dict[str, Any]:
        """Auth for embeddings.

        Gateway virtual keys (arcus) typically expose chat models on ``/v1`` but not
        Gemini embeddings. When the configured embed model is ``gemini/...``, call
        Google directly with ``GEMINI_API_KEY`` and skip the proxy base URL.
        """
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

    @staticmethod
    def _is_retryable(exc: BaseException) -> bool:
        """Best-effort classification for transient failures worth retrying."""
        name = exc.__class__.__name__.lower()
        msg = str(exc).lower()
        if "ratelimit" in name or "rate limit" in msg:
            return True
        if "too many requests" in msg or " 429" in msg or "status code 429" in msg:
            return True
        if "timeout" in name or "timed out" in msg:
            return True
        if "serviceunavailable" in name or "503" in msg:
            return True
        if "connection" in name or "connect" in msg or "dns" in msg:
            return True
        return False

    @retry(
        retry=retry_if_exception(_is_retryable.__func__),
        wait=wait_exponential(multiplier=2, min=2, max=120),
        stop=stop_after_attempt(8),
        reraise=True,
    )
    def _embed_raw(self, text: str) -> list[float]:
        """Embed with Gemini first (when configured), fallback to LiteLLM proxy on quota."""
        primary_model = self.settings.litellm_embedding_model
        fallback_model = self.settings.litellm_embedding_fallback_model
        self.last_embed_model = primary_model

        with self._sem:
            try:
                result = embedding(
                    model=primary_model,
                    input=[text],
                    **self._embed_kwargs(primary_model),
                )
            except Exception as exc:  # noqa: BLE001
                # If Gemini quota is exhausted, optionally fall back to the proxy.
                if (
                    fallback_model
                    and primary_model.startswith("gemini/")
                    and self._is_retryable(exc)
                ):
                    logger.warning(
                        "Embedding rate-limited on %s; falling back to %s",
                        primary_model,
                        fallback_model,
                    )
                    self.last_embed_model = fallback_model
                    result = embedding(
                        model=fallback_model,
                        input=[text],
                        **self._embed_kwargs(fallback_model),
                    )
                else:
                    raise
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

    @retry(
        retry=retry_if_exception(_is_retryable.__func__),
        wait=wait_exponential(multiplier=2, min=2, max=120),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    def generate_json(self, prompt: str, schema: type[T]) -> T:
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
                max_tokens=self.settings.llm_max_output_tokens,
                **self._completion_kwargs(),
            )
        text = response.choices[0].message.content or "{}"
        return schema.model_validate_json(text)
