/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

import {
  CATEGORY_IDS,
  type FeedPost,
  type InterestCategoryId,
  type InterestProfile,
  type InterestVector,
  type ScrapedContentDocument,
  type SeedCategoryId,
} from "./types";
import { themeMeta } from "./themes";

export const CATEGORIES = [
  {
    id: "cyberpunk" as const,
    label: "Cyberpunk",
    shortLabel: "Cyberpunk",
    color: "#22d3ee",
    keywords: [
      "cyberpunk",
      "cyber",
      "neon",
      "synthwave",
      "dystopia",
      "futurism",
      "science fiction",
      "sci-fi",
      "worldbuilding",
      "speculative",
      "night city",
    ],
  },
  {
    id: "ai" as const,
    label: "AI & machine learning",
    shortLabel: "AI / ML",
    color: "#a855f7",
    keywords: [
      "ai",
      "artificial intelligence",
      "machine learning",
      "deep learning",
      "llm",
      "language model",
      "neural",
      "robotics",
      "algorithm",
      "gpu",
      "generative",
      "computer vision",
      "deep tech",
    ],
  },
  {
    id: "space" as const,
    label: "Astrophysics & space",
    shortLabel: "Space",
    color: "#f59e0b",
    keywords: [
      "astrophysics",
      "space",
      "astronomy",
      "cosmos",
      "nasa",
      "exoplanet",
      "black hole",
      "telescope",
      "galaxy",
      "planet",
      "physics",
      "orbit",
    ],
  },
  {
    id: "culture" as const,
    label: "Indie pop & culture",
    shortLabel: "Indie Pop",
    color: "#f43f5e",
    keywords: [
      "indie",
      "music",
      "indie pop",
      "album",
      "playlist",
      "artist",
      "culture",
      "film",
      "cinema",
      "creative",
      "typography",
      "photography",
      "design",
    ],
  },
] as const;

const INITIAL_PROFILE: InterestProfile = {
  prompt: "Cyberpunk, machine learning & deep tech. A little space, no generic takes.",
  vector: { cyberpunk: 30, ai: 34, space: 22, culture: 14 },
  excludedCategories: [],
};
const HARD_NEGATIONS = new Set(["avoid", "banish", "exclude", "no", "never", "not", "skip"]);

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function hasKeyword(text: string, keyword: string): boolean {
  const words = keyword.split(/\s+/).map(escapeRegExp).join("\\s+");
  return new RegExp(`\\b${words}\\b`, "i").test(text);
}

function appearsNegated(
  prompt: string,
  keyword: string,
): { negated: boolean; hard: boolean } {
  const words = keyword.split(/\s+/).map(escapeRegExp).join("\\s+");
  const match = new RegExp(
    `\\b(avoid|banish|exclude|no|never|not|skip|less|fewer|stop showing)\\b(?:\\s+\\w+){0,4}\\s+${words}`,
    "i",
  ).exec(prompt);
  if (!match) return { negated: false, hard: false };
  return { negated: true, hard: HARD_NEGATIONS.has(match[1].toLowerCase()) };
}

export function normalizeVector(raw: InterestVector): InterestVector {
  const keys = Object.keys(raw);
  if (keys.length === 0) {
    return { ...INITIAL_PROFILE.vector };
  }
  const safe = keys.map((id) => Math.max(0.025, raw[id] ?? 0));
  const total = safe.reduce((sum, value) => sum + value, 0);
  const rounded = safe.map((value) => Math.round((value / total) * 1000) / 10);
  const drift =
    Math.round((100 - rounded.reduce((sum, value) => sum + value, 0)) * 10) / 10;
  rounded[0] = Math.round((rounded[0] + drift) * 10) / 10;
  return Object.fromEntries(keys.map((id, index) => [id, rounded[index]]));
}

export function parseInterestPrompt(prompt: string): InterestProfile {
  const normalizedPrompt = prompt.trim();
  const lower = normalizedPrompt.toLowerCase();
  const raw = Object.fromEntries(
    CATEGORY_IDS.map((id) => [id, 0.7]),
  ) as Record<SeedCategoryId, number>;
  const excludedCategories: InterestCategoryId[] = [];
  let hasKnownTerms = false;

  for (const category of CATEGORIES) {
    let positiveMatches = 0;
    let negativeMatches = 0;
    let hardNegative = false;

    for (const keyword of category.keywords) {
      if (!hasKeyword(lower, keyword)) continue;
      hasKnownTerms = true;
      const negation = appearsNegated(lower, keyword);
      if (negation.negated) {
        negativeMatches += 1;
        hardNegative ||= negation.hard;
      } else {
        positiveMatches += 1;
      }
    }

    raw[category.id] += positiveMatches * 1.15;
    raw[category.id] = Math.max(0.025, raw[category.id] - negativeMatches * 0.9);
    if (hardNegative && negativeMatches > 0) {
      raw[category.id] = 0.025;
      excludedCategories.push(category.id);
    }
  }

  if (!hasKnownTerms) {
    for (const id of CATEGORY_IDS) raw[id] = 1;
  }

  return {
    prompt: normalizedPrompt || INITIAL_PROFILE.prompt,
    vector: normalizeVector(raw),
    excludedCategories,
  };
}

/** Fold live post themes into the interest vector without dropping seed weights. */
export function mergeThemesIntoVector(
  vector: InterestVector,
  themeIds: InterestCategoryId[],
): InterestVector {
  const next = { ...vector };
  for (const id of themeIds) {
    const key = id.trim();
    if (!key || key in next) continue;
    next[key] = 8;
  }
  return normalizeVector(next);
}

export function adjustInterestVector(
  vector: InterestVector,
  category: InterestCategoryId,
  direction: "up" | "down",
): InterestVector {
  const keys = Object.keys(vector).length ? Object.keys(vector) : [...CATEGORY_IDS];
  const current: InterestVector = Object.fromEntries(
    keys.map((id) => [id, Math.max(0.1, vector[id] ?? 0.1)]),
  );
  if (!(category in current)) current[category] = 8;
  const ids = Object.keys(current);
  const nextTarget = Math.max(
    2.5,
    Math.min(80, current[category] + (direction === "up" ? 7 : -7)),
  );
  const otherTotal = ids
    .filter((id) => id !== category)
    .reduce((sum, id) => sum + current[id], 0);
  const next = { ...current, [category]: nextTarget };
  const remaining = 100 - nextTarget;
  for (const id of ids) {
    if (id !== category) {
      next[id] = otherTotal > 0 ? (current[id] / otherTotal) * remaining : remaining / (ids.length - 1);
    }
  }
  return normalizeVector(next);
}

export function classifyCategory(text: string): InterestCategoryId {
  const lower = text.toLowerCase();
  let best: InterestCategoryId = "ai";
  let score = 0;

  for (const category of CATEGORIES) {
    const found = category.keywords.reduce(
      (sum, keyword) => sum + (hasKeyword(lower, keyword) ? 1 : 0),
      0,
    );
    if (found > score) {
      score = found;
      best = category.id;
    }
  }
  return best;
}

export function scorePost(post: FeedPost, profile: InterestProfile): number {
  if (profile.excludedCategories.includes(post.category)) return 0;
  const ids = Object.keys(profile.vector);
  const total = ids.reduce((sum, id) => sum + (profile.vector[id] ?? 0), 0) || 100;
  const categoryKey = post.category?.trim() || "";
  let categoryShare = (profile.vector[categoryKey] ?? 0) / total;
  // Soft-match free-form facet labels against profile theme keys.
  if (categoryShare < 0.02 && categoryKey) {
    const lower = categoryKey.toLowerCase();
    let best = 0;
    for (const [id, weight] of Object.entries(profile.vector)) {
      const lid = id.toLowerCase();
      if (lower.includes(lid) || lid.includes(lower)) {
        best = Math.max(best, weight / total);
      }
    }
    categoryShare = best;
  }
  const text = `${post.title ?? ""} ${post.body} ${post.tags.join(" ")}`.toLowerCase();
  const keywords = themeMeta(post.category).keywords;
  const keywordBoost = Math.min(
    0.18,
    keywords.filter((word) => hasKeyword(text, word)).length * 0.035,
  );
  // Always give a small floor so ranked lists stay populated; excluded above.
  return Math.min(1, Math.max(0.05, categoryShare + keywordBoost));
}

/** 0–100 match percentage driven by the user interest profile (or API score). */
export function matchPercent(post: FeedPost, profile: InterestProfile): number {
  return Math.round(scorePost(post, profile) * 100);
}

export function rankPosts(posts: FeedPost[], profile: InterestProfile): FeedPost[] {
  return posts
    .map((post) => {
      // API feed scores are profile-powered; prefer them for ordering when present.
      const api = post.matchScore;
      const score =
        typeof api === "number" && Number.isFinite(api) && api > 0
          ? api
          : scorePost(post, profile);
      return { post, score };
    })
    .filter((item) => item.score >= 0.045 || (item.post.matchScore ?? 0) > 0)
    .sort((a, b) => b.score - a.score)
    .map((item) => item.post);
}

export function explainPostMatch(post: FeedPost, profile: InterestProfile): string {
  const category = themeMeta(post.category);
  const match = matchPercent(post, profile);
  const share = Math.round(profile.vector[post.category] ?? 0);
  const matchingTag = post.tags.find((tag) =>
    category.keywords.some((keyword) => tag.toLowerCase().includes(keyword)),
  );
  if (matchingTag) {
    return `About ${match}% match — your ${category.label.toLowerCase()} signal (${share}% of DNA) via “${matchingTag}”.`;
  }
  return `About ${match}% match with your profile. Filed under ${category.label.toLowerCase()} (${share}% of Interest DNA).`;
}

export function mapScrapedDocumentToPost(document: ScrapedContentDocument): FeedPost {
  const title = document.title?.trim() || document.subtitle?.trim() || "Untitled post";
  const body =
    document.summary?.trim() ||
    document.content_text?.trim() ||
    document.content?.trim() ||
    "Open the source to read the full post.";
  const tags = [...(document.categories ?? []), ...(document.tags ?? [])];
  const category = classifyCategory(`${title} ${body} ${tags.join(" ")}`);
  const source = document.source.toLowerCase();

  return {
    id: `${document.source}:${document.external_id}`,
    kind: "article",
    category,
    author: {
      name: document.author?.name || "Aura discovery",
      handle: `@${source}`,
      initials: (document.author?.name || source).slice(0, 2).toUpperCase(),
      avatarColor: "#626b7a",
    },
    publishedAt: document.published_at || new Date().toISOString(),
    title,
    body,
    imageUrl: document.cover_image_url || document.media_urls?.[0],
    imageAlt: title,
    platform: source === "substack" ? "Substack" : undefined,
    embedUrl: document.embed_url || document.canonical_url || document.url,
    tags: tags.slice(0, 5),
    likes: document.reaction_count || 0,
    comments: document.comment_count || 0,
  };
}
