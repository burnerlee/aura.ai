/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

import type {
  CategoryMeta,
  FeedPost,
  InterestProfile,
  InterestVector,
  PostTag,
  ServerDna,
} from "./types";
import { matchPercent } from "./interest";
import { themeKey, themeMeta } from "./themes";

const EMPTY_PROMPT = "Chat with Aura to build your Interest DNA";

/** `custom:deep-space` / `theme:ai` -> `deep space` / `ai` (fallback display label). */
export function humanizeKey(key: string): string {
  const tail = key.includes(":") ? key.slice(key.indexOf(":") + 1) : key;
  return tail.replace(/[-_]+/g, " ").trim();
}

export function dnaLabel(dna: ServerDna, key: string): string {
  return dna.labels[key] || humanizeKey(key);
}

/** The server DNA in the shape the UI renders. Posts' `category` is the theme label. */
export function dnaToProfile(dna: ServerDna): InterestProfile {
  const vector: InterestVector = {};
  for (const [key, weight] of Object.entries(dna.weights)) {
    vector[dnaLabel(dna, key)] = weight;
  }
  return {
    prompt: dna.prompt.trim() || EMPTY_PROMPT,
    vector,
    excludedCategories: dna.anti
      .filter((rule) => rule.kind === "topic" && rule.source !== "learned")
      .map((rule) => rule.label || humanizeKey(rule.key)),
  };
}

/** Profile shown before the DNA has loaded. */
export const EMPTY_PROFILE: InterestProfile = {
  prompt: EMPTY_PROMPT,
  vector: {},
  excludedCategories: [],
};

/** Heaviest DNA themes, for the ring and legend. */
export function dnaThemes(dna: ServerDna | null | undefined, limit = 10): CategoryMeta[] {
  if (!dna) return [];
  return Object.entries(dna.weights)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([key]) => themeMeta(dnaLabel(dna, key)));
}

/** Theme id for a displayed label (the DNA is edited by id, shown by label). */
export function dnaKeyForLabel(dna: ServerDna, label: string): string | undefined {
  const wanted = themeKey(label);
  return Object.keys(dna.weights).find((key) => themeKey(dnaLabel(dna, key)) === wanted);
}

/**
 * The percent a card should show: the server's relative match when it scored the post.
 * Otherwise the keyword/DNA-share heuristic, but only when `heuristic` is on (demo mode):
 * with a live backend an unscored post shows no number rather than an invented one.
 */
export function cardMatchPercent(
  post: FeedPost,
  profile: InterestProfile,
  { heuristic }: { heuristic: boolean },
): number | null {
  if (post.match) return post.match.percent;
  return heuristic ? matchPercent(post, profile) : null;
}

/** Topic and style tags worth showing as chips: not the theme, which the category chip is. */
export function displayTags(post: FeedPost, limit = 3): PostTag[] {
  const tags = (post.canonicalTags ?? []).filter((tag) => tag.kind !== "theme");
  const topics = tags.filter((tag) => tag.kind === "topic").slice(0, limit - 1);
  const styles = tags.filter((tag) => tag.kind === "style").slice(0, 1);
  return [...topics, ...styles].slice(0, limit);
}

/** Plain-language reading of a relative match, for the "Why this?" panel. */
export function explainRelativeMatch(post: FeedPost): string {
  const match = post.match;
  if (!match) return "";
  const parts: string[] = [];
  if (match.percent === null) {
    parts.push("Not enough posts were scored to rank this one yet.");
  } else {
    const top = Math.max(1, 100 - match.percent);
    const lead = `Top ${top}% of the ${match.poolSize} posts we considered for you`;
    parts.push(
      match.topAttribution
        ? `${lead}, mostly your ${match.topAttribution} interest.`
        : `${lead}.`,
    );
    if (!match.reliable) parts.push("The pool is small, so treat this as rough.");
  }
  const avoid = match.flags.filter((flag) => flag.kind === "aversion").map((f) => f.label);
  const lean = match.flags.filter((flag) => flag.kind === "affinity").map((f) => f.label);
  if (avoid.length) parts.push(`Heads up: ${avoid.join(", ")} — usually not your style.`);
  if (lean.length) parts.push(`A plus: you tend to like ${lean.join(", ")}.`);
  return parts.join(" ");
}
