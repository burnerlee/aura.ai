# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""LLM persona synthesis and cold-start onboarding."""

from __future__ import annotations

import logging

from scraper.llm.base import LLMClient
from scraper.models.user import Persona, UserProfile

logger = logging.getLogger(__name__)

_SYNTH_PROMPT = """Synthesize a reading persona for a recommendation system.

Return JSON matching the Persona schema.
Use liked/disliked article signals, reason chips, and any tune instructions.

Liked articles:
{liked}

Disliked articles:
{disliked}

Reason chips / notes:
{notes}

Tune instructions:
{tunes}

Existing persona (revise, do not ignore muted lists):
{existing}
"""


def _fallback_persona(
    *,
    summary: str,
    embed_client: LLMClient,
    existing: Persona | None = None,
) -> tuple[Persona, list[float]]:
    """Build a usable persona without an LLM when free-tier quota is exhausted."""
    text = (summary or "").strip() or "general curious reader"
    persona = Persona(
        summary=text,
        topics=list((existing.topics if existing else [])[:8]),
        anti_topics=list((existing.anti_topics if existing else [])[:8]),
        preferred_styles=list((existing.preferred_styles if existing else [])[:4]),
        muted_authors=list(existing.muted_authors if existing else []),
        muted_sources=list(existing.muted_sources if existing else []),
    )
    try:
        vector = embed_client.embed_query(persona.summary)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fallback persona embed failed (%s); empty vector", exc)
        vector = []
    return persona, vector


def synthesize_persona(
    profile: UserProfile,
    *,
    liked_summaries: list[str],
    disliked_summaries: list[str],
    notes: list[str],
    tunes: list[str],
    llm: LLMClient,
    embed_client: LLMClient,
) -> tuple[Persona, list[float]]:
    prompt = _SYNTH_PROMPT.format(
        liked="\n".join(f"- {s}" for s in liked_summaries) or "(none)",
        disliked="\n".join(f"- {s}" for s in disliked_summaries) or "(none)",
        notes="\n".join(f"- {n}" for n in notes) or "(none)",
        tunes="\n".join(f"- {t}" for t in tunes) or "(none)",
        existing=profile.persona.model_dump_json(),
    )
    try:
        persona = llm.generate_json(prompt, Persona)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Persona synthesis LLM failed (%s); using fallback", exc)
        seed = (
            "; ".join(liked_summaries[:5])
            or profile.persona.summary
            or "general curious reader"
        )
        return _fallback_persona(
            summary=seed, embed_client=embed_client, existing=profile.persona
        )

    persona.muted_authors = list(
        dict.fromkeys(profile.persona.muted_authors + persona.muted_authors)
    )
    persona.muted_sources = list(
        dict.fromkeys(profile.persona.muted_sources + persona.muted_sources)
    )
    vector = embed_client.embed_query(persona.summary or "general reader")
    return persona, vector


def onboard_persona(
    *,
    free_text: str | None,
    seed_titles: list[str],
    llm: LLMClient,
    embed_client: LLMClient,
) -> tuple[Persona, list[float]]:
    prompt = (
        "Create a reading persona from onboarding signals.\n"
        f"Free text: {free_text or '(none)'}\n"
        "Seed articles:\n"
        + ("\n".join(f"- {t}" for t in seed_titles) or "(none)")
        + "\nReturn JSON matching the Persona schema."
    )
    try:
        persona = llm.generate_json(prompt, Persona)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Onboard LLM failed (%s); embedding free-text fallback", exc)
        return _fallback_persona(
            summary=free_text or "; ".join(seed_titles[:5]) or "general curious reader",
            embed_client=embed_client,
        )
    try:
        vector = embed_client.embed_query(
            persona.summary or free_text or "general reader"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Onboard embed failed (%s); empty vector", exc)
        vector = []
    return persona, vector
