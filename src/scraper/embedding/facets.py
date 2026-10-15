# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""LLM facet extraction for EmbeddableContent."""

from __future__ import annotations

import logging

from scraper.llm.base import LLMClient
from scraper.models.embeddable import EmbeddableContent
from scraper.models.facets import PostFacets

logger = logging.getLogger(__name__)

_STYLE_HINTS = (
    "analytical, narrative, listicle, tutorial, opinion, humorous, "
    "investigative, personal, technical, news"
)

_PROMPT = """Extract recommendation facets for this article.

Return JSON matching the schema.
Styles should be chosen from: {styles}.
Emotion scores must be between 0 and 1 and roughly sum-normalized by importance.
Personality appeal is Big Five scores in [0, 1] describing who this article appeals to.

Title: {title}
Subtitle: {subtitle}
Summary: {summary}
Hints: {hints}

Body (truncated):
{body}
"""


def facets_to_text(facets: PostFacets) -> str:
    return facets.to_embed_text()


def extract_facets(
    content: EmbeddableContent,
    client: LLMClient,
    *,
    max_body_words: int = 2000,
) -> PostFacets:
    body_words = content.body_text.split()[:max_body_words]
    body = " ".join(body_words)
    prompt = _PROMPT.format(
        styles=_STYLE_HINTS,
        title=content.title or "",
        subtitle=content.subtitle or "",
        summary=content.summary or "",
        hints=content.hints or {},
        body=body,
    )
    try:
        return client.generate_json(prompt, PostFacets)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Facet extraction failed for %s: %s", content.external_id, exc)
        return PostFacets(
            topics=list(content.categories[:5]),
            one_line_appeal=content.summary or content.title,
        )
