# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""LLM persona synthesis and cold-start onboarding."""

from __future__ import annotations

import logging

from scraper.llm.gemini import GeminiClient
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


def synthesize_persona(
    profile: UserProfile,
    *,
    liked_summaries: list[str],
    disliked_summaries: list[str],
    notes: list[str],
    tunes: list[str],
    client: GeminiClient,
) -> tuple[Persona, list[float]]:
    prompt = _SYNTH_PROMPT.format(
        liked="\n".join(f"- {s}" for s in liked_summaries) or "(none)",
        disliked="\n".join(f"- {s}" for s in disliked_summaries) or "(none)",
        notes="\n".join(f"- {n}" for n in notes) or "(none)",
        tunes="\n".join(f"- {t}" for t in tunes) or "(none)",
        existing=profile.persona.model_dump_json(),
    )
    persona = client.generate_json(prompt, Persona)
    # Preserve mutes unless the model returned them
    persona.muted_authors = list(
        dict.fromkeys(profile.persona.muted_authors + persona.muted_authors)
    )
    persona.muted_sources = list(
        dict.fromkeys(profile.persona.muted_sources + persona.muted_sources)
    )
    vector = client.embed_query(persona.summary or "general reader")
    return persona, vector


def onboard_persona(
    *,
    free_text: str | None,
    seed_titles: list[str],
    client: GeminiClient,
) -> tuple[Persona, list[float]]:
    prompt = (
        "Create a reading persona from onboarding signals.\n"
        f"Free text: {free_text or '(none)'}\n"
        "Seed articles:\n"
        + ("\n".join(f"- {t}" for t in seed_titles) or "(none)")
        + "\nReturn JSON matching the Persona schema."
    )
    persona = client.generate_json(prompt, Persona)
    vector = client.embed_query(persona.summary or free_text or "general reader")
    return persona, vector
