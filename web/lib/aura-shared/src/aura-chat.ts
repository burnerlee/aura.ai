/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

import { mergeThemesIntoVector, normalizeVector, parseInterestPrompt } from "./interest";
import type { InterestProfile, InterestVector } from "./types";

export type AuraRole = "user" | "assistant";

export interface AuraChatMessage {
  role: AuraRole;
  content: string;
}

export interface AuraOption {
  id: string;
  label: string;
}

export interface AuraProfileDraft {
  prompt: string;
  topics: string[];
  anti_topics: string[];
  themes: string[];
  theme_weights: Record<string, number>;
  preferred_styles?: string[];
  preferred_emotions?: string[];
}

export interface AuraTurn {
  message: string;
  options: AuraOption[];
  suggested_themes: string[];
  ready: boolean;
  profile: AuraProfileDraft | null;
}

function slugTheme(label: string): string {
  return label
    .trim()
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "") || "theme";
}

/** Map Aura's drafted profile into the local InterestProfile shape. */
export function interestProfileFromAura(
  draft: AuraProfileDraft,
  existingThemes: string[] = [],
): InterestProfile {
  const themeIds = [
    ...draft.themes.map(slugTheme),
    ...Object.keys(draft.theme_weights || {}).map(slugTheme),
    ...existingThemes,
  ].filter(Boolean);

  const raw: InterestVector = {};
  const weights = draft.theme_weights || {};
  const weightKeys = Object.keys(weights);
  if (weightKeys.length) {
    for (const [key, value] of Object.entries(weights)) {
      raw[slugTheme(key)] = Math.max(1, Number(value) || 1);
    }
  } else {
    draft.themes.forEach((theme, index) => {
      raw[slugTheme(theme)] = Math.max(5, 90 - index * 12);
    });
  }

  for (const anti of draft.anti_topics) {
    const id = slugTheme(anti);
    if (id) raw[id] = Math.min(raw[id] ?? 5, 5);
  }

  const vector = themeIds.length
    ? mergeThemesIntoVector(
        Object.keys(raw).length ? normalizeVector(raw) : {},
        themeIds,
      )
    : parseInterestPrompt(draft.prompt || "").vector;

  return {
    prompt: (draft.prompt || "").trim() || parseInterestPrompt("").prompt,
    vector,
    excludedCategories: draft.anti_topics.map(slugTheme).filter(Boolean),
  };
}

/** Local scripted Aura for demo mode / offline fallback. */
export function localAuraTurn(
  messages: AuraChatMessage[],
  knownThemes: string[] = [],
): AuraTurn {
  const userTurns = messages.filter((m) => m.role === "user").map((m) => m.content);
  const seed = knownThemes.slice(0, 4);
  const defaults = seed.length
    ? seed
    : ["AI & ML", "deep space", "cyberpunk", "indie culture"];

  if (!userTurns.length) {
    return {
      message:
        "Hey — I'm Aura. One honest prompt and I'll start building your Interest DNA — the signal that shapes your feed. What pulls you in?",
      options: [
        ...defaults.map((label, i) => ({ id: `theme-${i}`, label })),
        { id: "mix", label: "A mix — surprise me" },
        { id: "unsure", label: "Not sure yet — help me explore" },
      ],
      suggested_themes: defaults.slice(0, 3),
      ready: false,
      profile: null,
    };
  }

  const joined = userTurns.join(" ").toLowerCase();
  const themes: string[] = [];
  for (const candidate of [
    ...defaults,
    "practical AI",
    "indie games",
    "synthwave",
    "astrophysics",
    "design systems",
  ]) {
    const needle = candidate.toLowerCase().split(/\s+/)[0] ?? "";
    if (needle && joined.includes(needle) && !themes.includes(candidate)) {
      themes.push(candidate);
    }
  }
  if (!themes.length) themes.push(...defaults.slice(0, 3));

  if (userTurns.length < 2) {
    return {
      message:
        "Nice. What vibe do you want more of — deep dives, quick hits, or something in between?",
      options: [
        { id: "deep", label: "Deep, thoughtful pieces" },
        { id: "quick", label: "Short & punchy" },
        { id: "visual", label: "Visual / atmospheric" },
        { id: "practical", label: "Practical & useful" },
        { id: "weird", label: "Weird & speculative" },
      ],
      suggested_themes: themes.slice(0, 4),
      ready: false,
      profile: null,
    };
  }

  if (userTurns.length < 3 && !/ready|build|apply|done|that's me|thats me/i.test(joined)) {
    return {
      message:
        "Got it. Anything you want less of — hype, generic tech news, or something else?",
      options: [
        { id: "less-hype", label: "Less hype / clickbait" },
        { id: "less-generic", label: "Less generic tech news" },
        { id: "less-politics", label: "Less politics" },
        { id: "keep", label: "Keep it open for now" },
        { id: "ready", label: "I'm ready — build my profile" },
      ],
      suggested_themes: themes.slice(0, 4),
      ready: false,
      profile: null,
    };
  }

  const anti: string[] = [];
  if (/hype|clickbait/.test(joined)) anti.push("hype");
  if (/generic/.test(joined)) anti.push("generic tech news");
  if (/politics/.test(joined)) anti.push("politics");

  const theme_weights = Object.fromEntries(
    themes.slice(0, 6).map((t, i) => [slugTheme(t), 85 - i * 12]),
  );
  const prompt =
    `I'm into ${themes.slice(0, 4).join(", ")}. ` +
    (anti.length ? `Dial down ${anti.join(", ")}. ` : "Keep the signal curious and specific. ") +
    "Prefer posts that feel personal and high-signal.";

  return {
    message:
      "I think I've got you. Here's a profile I'll use to tune your feed — tap Apply when it feels right, or tell me what to change.",
    options: [
      { id: "apply", label: "Looks good — apply it" },
      { id: "more-visual", label: "Make it more visual" },
      { id: "more-deep", label: "Make it deeper" },
      { id: "retry", label: "Ask me a different question" },
    ],
    suggested_themes: themes.slice(0, 4),
    ready: true,
    profile: {
      prompt,
      topics: themes.slice(0, 6),
      anti_topics: anti,
      themes: themes.slice(0, 6).map(slugTheme),
      theme_weights,
      preferred_styles: ["curious", "high-signal"],
      preferred_emotions: ["inspired", "focused"],
    },
  };
}
