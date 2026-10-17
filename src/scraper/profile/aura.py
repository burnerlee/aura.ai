# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Aura — conversational personalization agent."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from scraper.llm.base import LLMClient
from scraper.models.user import Persona

logger = logging.getLogger(__name__)

AURA_SYSTEM_PROMPT = """You are Aura, a warm, curious personalization guide for a content feed.

Your job is to talk with the user — never ask them to write a long free-form interest prompt.
Understand what content they enjoy by chatting: ask short questions, offer multiple-choice
options they can tap, and suggest fresh themes they might like.

Conversation style:
- Friendly, concise, and specific. One clear question per turn.
- Always include 3–6 tap-friendly options when asking a question.
- Suggest 2–4 new theme ideas as the conversation progresses (short labels, e.g. "indie games",
  "deep space", "practical AI", "synthwave").
- Reflect back what you heard so the user feels understood.
- After enough signal (usually 2–3 exchanges), or when the user says they're ready / done /
  "build my profile", set ready=true and fill the profile object.
- Every ready profile is applied to the feed immediately. When the user already has a
  current profile and asks for a change ("more X", "less Y", "drop Z", a new interest),
  set ready=true in that same turn with the full updated profile: keep what still holds,
  apply the change, and say in one line what you changed. Don't ask a follow-up first.

Profile rules (when ready=true):
- prompt: a natural first-person interest summary (1–3 sentences) Aura will use as the signal.
- topics: themes / subjects to lean into.
- anti_topics: things to dial down or avoid.
- themes: short theme ids/labels for the feed DNA (lowercase, hyphen or space ok).
- theme_weights: map theme -> weight 5–95 (relative interest). Include all themes listed.
- preferred_styles / preferred_emotions: optional reading vibes (e.g. "practical", "curious").

If known corpus themes are provided, prefer those labels when they fit, but you may invent
new themes the corpus does not yet have.

When prior conversation context is provided, treat it as memory from earlier chats with this
user. Do not re-ask questions they already answered unless they want to change their mind.
Welcome them back briefly and continue from what you already know.

Return JSON matching the AuraTurn schema only. No markdown fences.
"""

MAX_STORED_MESSAGES = 40


class AuraChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AuraOption(BaseModel):
    id: str
    label: str


class AuraProfileDraft(BaseModel):
    prompt: str = ""
    topics: list[str] = Field(default_factory=list)
    anti_topics: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    theme_weights: dict[str, float] = Field(default_factory=dict)
    preferred_styles: list[str] = Field(default_factory=list)
    preferred_emotions: list[str] = Field(default_factory=list)


class AuraTurn(BaseModel):
    message: str
    options: list[AuraOption] = Field(default_factory=list)
    suggested_themes: list[str] = Field(default_factory=list)
    ready: bool = False
    profile: AuraProfileDraft | None = None


def _opening_turn(known_themes: list[str]) -> AuraTurn:
    theme_opts = known_themes[:4] or [
        "AI & ML",
        "deep space",
        "cyberpunk",
        "indie culture",
    ]
    options = [
        AuraOption(id=f"theme-{i}", label=label)
        for i, label in enumerate(theme_opts)
    ]
    options.extend(
        [
            AuraOption(id="mix", label="A mix — surprise me"),
            AuraOption(id="unsure", label="Not sure yet — help me explore"),
        ]
    )
    return AuraTurn(
        message=(
            "Hey — I'm Aura. One honest prompt and I'll start building your "
            "Interest DNA — the signal that shapes your feed. What pulls you in?"
        ),
        options=options,
        suggested_themes=theme_opts[:3],
        ready=False,
    )


def _fallback_turn(
    messages: list[AuraChatMessage],
    known_themes: list[str],
) -> AuraTurn:
    """Deterministic path when the LLM is unavailable."""
    user_turns = [m.content for m in messages if m.role == "user"]
    if not user_turns:
        return _opening_turn(known_themes)

    joined = " ".join(user_turns).lower()
    themes: list[str] = []
    for candidate in [
        "ai",
        "machine learning",
        "space",
        "astrophysics",
        "cyberpunk",
        "synthwave",
        "indie",
        "music",
        "games",
        "design",
        "science",
        "culture",
    ]:
        if candidate in joined and candidate not in themes:
            themes.append(candidate)
    for theme in known_themes:
        key = theme.lower()
        if key in joined and theme not in themes:
            themes.append(theme)
    if not themes:
        themes = (known_themes[:3] or ["curious finds", "practical AI", "culture"])

    if len(user_turns) < 2:
        return AuraTurn(
            message=(
                "Nice. What vibe do you want more of — deep dives, quick hits, "
                "or something in between?"
            ),
            options=[
                AuraOption(id="deep", label="Deep, thoughtful pieces"),
                AuraOption(id="quick", label="Short & punchy"),
                AuraOption(id="visual", label="Visual / atmospheric"),
                AuraOption(id="practical", label="Practical & useful"),
                AuraOption(id="weird", label="Weird & speculative"),
            ],
            suggested_themes=themes[:4],
            ready=False,
        )

    if len(user_turns) < 3:
        return AuraTurn(
            message=(
                "Got it. Anything you want less of — hype, generic tech news, "
                "or something else?"
            ),
            options=[
                AuraOption(id="less-hype", label="Less hype / clickbait"),
                AuraOption(id="less-generic", label="Less generic tech news"),
                AuraOption(id="less-politics", label="Less politics"),
                AuraOption(id="keep", label="Keep it open for now"),
                AuraOption(id="ready", label="I'm ready — build my profile"),
            ],
            suggested_themes=themes[:4],
            ready=False,
        )

    anti: list[str] = []
    if "hype" in joined or "clickbait" in joined:
        anti.append("hype")
    if "generic" in joined:
        anti.append("generic tech news")
    if "politics" in joined:
        anti.append("politics")

    weights = {
        t: round(85 - i * 12, 1) for i, t in enumerate(themes[:6])
    }
    prompt = (
        f"I'm into {', '.join(themes[:4])}. "
        + (
            f"Dial down {', '.join(anti)}. "
            if anti
            else "Keep the signal curious and specific. "
        )
        + "Prefer posts that feel personal and high-signal."
    )
    return AuraTurn(
        message=(
            "I think I've got you. Here's a profile I'll use to tune your feed — "
            "tap Apply when it feels right, or tell me what to change."
        ),
        options=[
            AuraOption(id="apply", label="Looks good — apply it"),
            AuraOption(id="more-visual", label="Make it more visual"),
            AuraOption(id="more-deep", label="Make it deeper"),
            AuraOption(id="retry", label="Ask me a different question"),
        ],
        suggested_themes=themes[:4],
        ready=True,
        profile=AuraProfileDraft(
            prompt=prompt.strip(),
            topics=themes[:6],
            anti_topics=anti,
            themes=themes[:6],
            theme_weights=weights,
            preferred_styles=["curious", "high-signal"],
            preferred_emotions=["inspired", "focused"],
        ),
    )


def draft_to_persona(draft: AuraProfileDraft) -> Persona:
    return Persona(
        summary=draft.prompt or "; ".join(draft.topics) or "curious reader",
        topics=list(draft.topics[:12]),
        anti_topics=list(draft.anti_topics[:12]),
        preferred_styles=list(draft.preferred_styles[:6]),
        preferred_emotions=list(draft.preferred_emotions[:6]),
    )


def _welcome_back_turn(
    prior: list[AuraChatMessage],
    known_themes: list[str],
) -> AuraTurn:
    """Deterministic re-entry when stored history exists and the UI opens fresh."""
    user_bits = [m.content for m in prior if m.role == "user"][-4:]
    hint = user_bits[-1] if user_bits else "what you liked last time"
    themes = known_themes[:4] or ["practical AI", "deep space", "indie culture"]
    return AuraTurn(
        message=(
            f"Welcome back — I still remember our chat about {hint[:120]}. "
            "Want to refine that signal, or explore a new angle?"
        ),
        options=[
            AuraOption(id="refine", label="Refine what we built"),
            AuraOption(id="new-angle", label="Try a new angle"),
            AuraOption(id="more-themes", label="Suggest new themes"),
            AuraOption(id="ready", label="Keep my current profile"),
        ],
        suggested_themes=themes[:3],
        ready=False,
    )


def merge_conversation_context(
    stored: list[AuraChatMessage],
    session: list[AuraChatMessage],
) -> list[AuraChatMessage]:
    """Combine persisted history with the live session for the LLM."""
    if not stored:
        return list(session)
    if not session:
        return list(stored)
    # Drop overlapping prefix: if session already includes a suffix of stored, don't double it.
    max_overlap = min(len(stored), len(session))
    overlap = 0
    for size in range(max_overlap, 0, -1):
        if all(
            stored[-size + i].role == session[i].role
            and stored[-size + i].content == session[i].content
            for i in range(size)
        ):
            overlap = size
            break
    if overlap:
        return list(stored) + list(session[overlap:])
    return list(stored) + list(session)


def _scripted_turn(
    messages: list[AuraChatMessage],
    prior: list[AuraChatMessage],
    themes: list[str],
) -> AuraTurn:
    """Last-resort deterministic replies when every LLM client fails."""
    if prior and not messages:
        return _welcome_back_turn(prior, themes)
    return _fallback_turn(
        merge_conversation_context(prior, messages) if prior else messages,
        themes,
    )


def chat_with_aura(
    messages: list[AuraChatMessage],
    *,
    known_themes: list[str] | None = None,
    llm: LLMClient | None = None,
    fallback_llm: LLMClient | None = None,
    prior_messages: list[AuraChatMessage] | None = None,
    current_profile: str | None = None,
) -> AuraTurn:
    """Run one Aura turn. Empty history returns the opening (or welcome-back) message.

    ``current_profile`` describes what the feed is tuned to right now, so refinements
    edit it instead of starting over.
    """
    themes = [t.strip() for t in (known_themes or []) if t and t.strip()]
    prior = list(prior_messages or [])
    context = merge_conversation_context(prior, messages)

    if not messages:
        if prior:
            # Ask the model for a short welcome-back turn using stored memory.
            context = prior
        else:
            return _opening_turn(themes)

    clients: list[LLMClient] = []
    for client in (llm, fallback_llm):
        if client is not None and client not in clients:
            clients.append(client)
    if not clients:
        return _scripted_turn(messages, prior, themes)

    history = "\n".join(f"{m.role}: {m.content}" for m in context[-24:])
    theme_line = ", ".join(themes[:16]) if themes else "(none yet)"
    resume_note = (
        "The user just reopened chat; greet them briefly using prior context "
        "and offer to refine — do not restart onboarding from scratch.\n"
        if (prior and not messages)
        else ""
    )
    profile_line = (
        f"The user's current profile (what their feed is tuned to now):\n{current_profile}\n\n"
        if current_profile
        else ""
    )
    prompt = (
        f"{AURA_SYSTEM_PROMPT}\n\n"
        f"Known corpus themes (prefer when relevant): {theme_line}\n\n"
        f"{profile_line}"
        f"{resume_note}"
        f"Conversation so far (includes stored memory):\n{history}\n\n"
        "Produce the next AuraTurn JSON."
    )
    for index, client in enumerate(clients):
        try:
            turn = client.generate_json(prompt, AuraTurn)
        except Exception as exc:  # noqa: BLE001
            next_client = clients[index + 1] if index + 1 < len(clients) else None
            if next_client is not None:
                logger.warning(
                    "Aura chat LLM failed (%s); trying secondary client",
                    exc,
                )
                continue
            logger.warning("Aura chat LLM failed (%s); using scripted fallback", exc)
            return _scripted_turn(messages, prior, themes)

        if not (turn.message or "").strip():
            next_client = clients[index + 1] if index + 1 < len(clients) else None
            if next_client is not None:
                logger.warning("Aura chat returned empty message; trying secondary client")
                continue
            return _scripted_turn(messages, prior, themes)
        if turn.ready and turn.profile is None:
            turn.ready = False
        return turn

    return _scripted_turn(messages, prior, themes)
