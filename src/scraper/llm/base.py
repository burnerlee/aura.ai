# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Shared LLM / embedding client protocol."""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    """Embedding + structured generation interface used across the stack."""

    def embed_document(self, text: str, title: str | None = None) -> list[float]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def embed_image(self, url: str) -> list[float] | None: ...

    def generate_json(self, prompt: str, schema: type[T]) -> T: ...
