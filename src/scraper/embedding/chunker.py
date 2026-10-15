# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Chunk EmbeddableContent into head + body windows for multi-vector embedding."""

from __future__ import annotations

from dataclasses import dataclass

from scraper.config import Settings, get_settings
from scraper.models.embeddable import EmbeddableContent


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    kind: str  # "head" | "body"


def chunk_content(
    content: EmbeddableContent,
    settings: Settings | None = None,
) -> list[Chunk]:
    """Split content into a head chunk plus overlapping body word windows."""
    settings = settings or get_settings()
    chunks: list[Chunk] = []

    head = content.head_text()
    if head:
        chunks.append(Chunk(index=0, text=head, kind="head"))

    words = content.body_text.split()
    if not words:
        return chunks[: settings.max_chunks_per_post]

    window = settings.chunk_words
    overlap = settings.chunk_overlap_words
    step = max(1, window - overlap)

    start = 0
    body_index = 0
    while start < len(words):
        if len(chunks) >= settings.max_chunks_per_post:
            break
        end = min(len(words), start + window)
        text = " ".join(words[start:end]).strip()
        if text:
            # Avoid duplicating the entire body when head already covers it
            if not (body_index == 0 and head and text == head):
                chunks.append(
                    Chunk(index=len(chunks), text=text, kind="body")
                )
                body_index += 1
        if end >= len(words):
            break
        start += step

    return chunks[: settings.max_chunks_per_post]
