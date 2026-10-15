# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Event -> weight mapping. hold_ms is stored but unused by the default table."""

from __future__ import annotations

import math
from collections.abc import Callable

from scraper.models.user import EventType, FeedbackReason, Interaction, Persona

WEIGHT_VERSION_DEFAULT = "default_v1"
WEIGHT_VERSION_HOLD_LINEAR = "hold_linear_v1"
WEIGHT_VERSION_HOLD_LOG = "hold_log_v1"

WORDS_PER_MINUTE = 250.0


def compute_read_ratio(dwell_ms: int | None, word_count: int | None) -> float | None:
    if dwell_ms is None or not word_count or word_count <= 0:
        return None
    expected_ms = (word_count / WORDS_PER_MINUTE) * 60_000.0
    if expected_ms <= 0:
        return None
    return float(dwell_ms) / expected_ms


def weight_default(interaction: Interaction, *, word_count: int | None = None) -> float:
    event = interaction.event
    strength = interaction.strength or 1

    if event == EventType.LIKE:
        return 1.0 if strength >= 2 else 0.7
    if event == EventType.SAVE:
        return 1.0
    if event == EventType.CLICK_THROUGH:
        return 0.4
    if event == EventType.SHARE:
        return 0.5
    if event == EventType.OPEN:
        return 0.1
    if event == EventType.DWELL:
        ratio = interaction.read_ratio
        if ratio is None:
            ratio = compute_read_ratio(interaction.dwell_ms, word_count)
        if ratio is None or ratio < 0.15:
            return 0.0
        return min(1.0, max(0.0, ratio)) * 0.6
    if event == EventType.IMPRESSION:
        # Fast skip: visible < 1s and no open implied by caller
        if interaction.visible_ms is not None and interaction.visible_ms < 1000:
            return -0.1
        return 0.0
    if event == EventType.NOT_INTERESTED:
        return -1.0 if strength >= 2 else -0.6
    if event == EventType.PAIRWISE:
        # Positive weight for winner post; loser uses negative via pair_post_id convention
        # Caller sets weight sign by which post_id is the subject.
        return 0.5
    if event in (EventType.TUNE, EventType.EXPLANATION_FEEDBACK):
        return 0.0
    if event in (EventType.FOLLOW_AUTHOR, EventType.MUTE_AUTHOR, EventType.MUTE_SOURCE):
        return 0.0
    return 0.0


def weight_hold_linear(interaction: Interaction, *, word_count: int | None = None) -> float:
    """Experimental: scale like / not_interested by hold_ms (0–3000ms -> 0.5–1.0)."""
    base = weight_default(interaction, word_count=word_count)
    if interaction.event not in (EventType.LIKE, EventType.NOT_INTERESTED):
        return base
    hold = interaction.hold_ms or 0
    scale = 0.5 + 0.5 * min(1.0, max(0.0, hold / 3000.0))
    return base * scale if base >= 0 else base * scale


def weight_hold_log(interaction: Interaction, *, word_count: int | None = None) -> float:
    """Experimental: log-scaled hold duration multiplier."""
    base = weight_default(interaction, word_count=word_count)
    if interaction.event not in (EventType.LIKE, EventType.NOT_INTERESTED):
        return base
    hold = max(0, interaction.hold_ms or 0)
    scale = 0.5 + 0.5 * (math.log1p(hold) / math.log1p(3000.0))
    scale = min(1.0, max(0.5, scale))
    return base * scale if base >= 0 else base * scale


WEIGHT_FUNCTIONS: dict[str, Callable[..., float]] = {
    "default": weight_default,
    WEIGHT_VERSION_DEFAULT: weight_default,
    "hold_linear": weight_hold_linear,
    WEIGHT_VERSION_HOLD_LINEAR: weight_hold_linear,
    "hold_log": weight_hold_log,
    WEIGHT_VERSION_HOLD_LOG: weight_hold_log,
}


def compute_weight(
    interaction: Interaction,
    *,
    version: str = WEIGHT_VERSION_DEFAULT,
    word_count: int | None = None,
) -> float:
    fn = WEIGHT_FUNCTIONS.get(version, weight_default)
    return fn(interaction, word_count=word_count)


def is_explicit_negative(interaction: Interaction) -> bool:
    if interaction.event == EventType.NOT_INTERESTED:
        return True
    if interaction.reason in (FeedbackReason.TOO_LONG, FeedbackReason.LOW_QUALITY):
        return True
    return False


def apply_reason_actions(persona: Persona, interaction: Interaction) -> Persona:
    """Map reason chips onto persona fields (returns updated copy)."""
    if interaction.reason is None:
        return persona
    data = persona.model_dump()
    reason = interaction.reason

    if interaction.event == EventType.NOT_INTERESTED:
        if reason == FeedbackReason.TOPIC and interaction.text:
            topics = list(data.get("anti_topics") or [])
            if interaction.text not in topics:
                topics.append(interaction.text)
            data["anti_topics"] = topics
        if reason == FeedbackReason.AUTHOR:
            # Mute handled separately via muted_authors on profile service
            pass
        if reason == FeedbackReason.TOO_LONG:
            data["max_words"] = data.get("max_words") or 1500
        if reason == FeedbackReason.TONE:
            # Soft hint — leave preferred_styles for persona refresh to rewrite
            pass
    elif interaction.event == EventType.LIKE:
        if reason == FeedbackReason.TOPIC and interaction.text:
            topics = list(data.get("topics") or [])
            if interaction.text not in topics:
                topics.append(interaction.text)
            data["topics"] = topics
        if reason == FeedbackReason.STYLE and interaction.text:
            styles = list(data.get("preferred_styles") or [])
            if interaction.text not in styles:
                styles.append(interaction.text)
            data["preferred_styles"] = styles
    return Persona.model_validate(data)


def correlation(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    import numpy as np

    a = np.asarray(xs, dtype=np.float64)
    b = np.asarray(ys, dtype=np.float64)
    if a.std() < 1e-12 or b.std() < 1e-12:
        return None
    return float(np.corrcoef(a, b)[0, 1])
