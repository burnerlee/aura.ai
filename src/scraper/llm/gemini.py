# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Gemini embedding + structured-generation client."""

from __future__ import annotations

import logging
import threading
from typing import TypeVar

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


class GeminiClient:
    """Thin wrapper around google-genai with retries and concurrency limits."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to .env to embed / call the LLM."
            )
        from google import genai

        self._client = genai.Client(api_key=self.settings.gemini_api_key)
        self._sem = threading.Semaphore(self.settings.embed_concurrency)

    def _truncate(self, values: list[float]) -> list[float]:
        dim = self.settings.embedding_dim
        if len(values) > dim:
            values = values[:dim]
        return _l2_normalize(values)

    @retry(wait=wait_exponential(multiplier=1, min=1, max=20), stop=stop_after_attempt(4))
    def _embed_raw(self, text: str) -> list[float]:
        with self._sem:
            result = self._client.models.embed_content(
                model=self.settings.gemini_embedding_model,
                contents=text,
            )
        embedding = result.embeddings[0]
        values = list(embedding.values)
        return self._truncate(values)

    def embed_document(self, text: str, title: str | None = None) -> list[float]:
        title_part = title.strip() if title and title.strip() else "none"
        payload = f"title: {title_part} | text: {text}"
        return self._embed_raw(payload)

    def embed_query(self, text: str) -> list[float]:
        payload = f"task: search result | query: {text}"
        return self._embed_raw(payload)

    def embed_image(self, url: str) -> list[float] | None:
        """Optional multimodal image embedding (cover images)."""
        try:
            response = httpx.get(url, timeout=self.settings.http_timeout_seconds)
            response.raise_for_status()
            from google.genai import types

            with self._sem:
                result = self._client.models.embed_content(
                    model=self.settings.gemini_embedding_model,
                    contents=[
                        types.Part.from_bytes(
                            data=response.content,
                            mime_type=response.headers.get("content-type", "image/jpeg"),
                        )
                    ],
                )
            values = list(result.embeddings[0].values)
            return self._truncate(values)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Image embed failed for %s: %s", url, exc)
            return None

    @retry(wait=wait_exponential(multiplier=1, min=1, max=20), stop=stop_after_attempt(3))
    def generate_json(self, prompt: str, schema: type[T]) -> T:
        from google.genai import types

        with self._sem:
            response = self._client.models.generate_content(
                model=self.settings.gemini_llm_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
        text = response.text or "{}"
        return schema.model_validate_json(text)
