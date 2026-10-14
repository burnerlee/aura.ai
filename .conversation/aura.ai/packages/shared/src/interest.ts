import {
  CATEGORY_IDS,
  type FeedPost,
  type InterestCategoryId,
  type InterestProfile,
  type InterestVector,
  type ScrapedContentDocument,
} from "./types";

export const CATEGORIES = [
  {
    id: "cyberpunk",
    label: "Cyberpunk",
    shortLabel: "Cyberpunk",
    color: "#c3a7ff",
    keywords: [
      "cyberpunk", "cyber", "neon", "synthwave", "dystopia", "futurism",
      "science fiction", "sci-fi", "worldbuilding", "speculative", "night city",
    ],
  },
  {
    id: "ai",
    label: "AI & machine learning",
    shortLabel: "AI / ML",
    color: "#83e0c2",
    keywords: [
      "ai", "artificial intelligence", "machine learning", "deep learning",
      "llm", "language model", "neural", "robotics", "algorithm", "gpu",
      "generative", "computer vision", "deep tech",
    ],
  },
  {
    id: "space",
    label: "Astrophysics & space",
    shortLabel: "Space",
    color: "#84baff",
    keywords: [
      "astrophysics", "space", "astronomy", "cosmos", "nasa", "exoplanet",
      "black hole", "telescope", "galaxy", "planet", "physics", "orbit",
    ],
  },
  {
    id: "culture",
    label: "Indie culture",
    shortLabel: "Culture",
    color: "#f2a17e",
    keywords: [
      "indie", "music", "indie pop", "album", "playlist", "artist", "culture",
      "film", "cinema", "creative", "typography", "photography", "design",
    ],
  },
] as const;

export const INITIAL_PROFILE: InterestProfile = {
  prompt: "Cyberpunk, machine learning & deep tech. A little space, no generic takes.",
  vector: {
    cyberpunk: 30,
    ai: 34,
    space: 22,
    culture: 14,
  },
  excludedCategories: [],
};

const HARD_NEGATIONS = new Set(["avoid", "banish", "exclude", "no", "never", "not", "skip"]);

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function hasKeyword(text: string, keyword: string): boolean {
  const words = keyword
    .split(/\s+/)
    .map(escapeRegExp)
    .join("\\s+");
  return new RegExp(`\\b${words}\\b`, "i").test(text);
}

function appearsNegated(prompt: string, keyword: string): {
  negated: boolean;
  hard: boolean;
} {
  const words = keyword
    .split(/\s+/)
    .map(escapeRegExp)
    .join("\\s+");
  const match = new RegExp(
    `\\b(avoid|banish|exclude|no|never|not|skip|less|fewer|stop showing)\\b(?:\\s+\\w+){0,4}\\s+${words}`,
    "i",
  ).exec(prompt);

  if (!match) return { negated: false, hard: false };
  const trigger = match[1].toLowerCase();
  return { negated: true, hard: HARD_NEGATIONS.has(trigger) };
}

function normalizeVector(raw: Record<InterestCategoryId, number>): InterestVector {
  const safe = CATEGORY_IDS.map((id) => Math.max(0.025, raw[id]));
  const total = safe.reduce((sum, value) => sum + value, 0);
  const rounded = safe.map((value) => Math.round((value / total) * 1000) / 10);
  const difference = Math.round((100 - rounded.reduce((sum, value) => sum + value, 0)) * 10) / 10;
  rounded[0] = Math.round((rounded[0] + difference) * 10) / 10;

  return {
    cyberpunk: rounded[0],
    ai: rounded[1],
    space: rounded[2],
    culture: rounded[3],
  };
}

export function parseInterestPrompt(prompt: string): InterestProfile {
  const normalizedPrompt = prompt.trim();
  const lower = normalizedPrompt.toLowerCase();
  const raw = Object.fromEntries(CATEGORY_IDS.map((id) => [id, 0.7])) as Record<
    InterestCategoryId,
    number
  >;
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

  // A prompt with no known terms still gets a balanced, editable starting point.
  if (!hasKnownTerms) {
    for (const id of CATEGORY_IDS) raw[id] = 1;
  }

  return {
    prompt: normalizedPrompt || INITIAL_PROFILE.prompt,
    vector: normalizeVector(raw),
    excludedCategories,
  };
}

export function adjustInterestVector(
  vector: InterestVector,
  category: InterestCategoryId,
  direction: "up" | "down",
): InterestVector {
  const current = Object.fromEntries(
    CATEGORY_IDS.map((id) => [id, Math.max(0.1, vector[id])]),
  ) as Record<InterestCategoryId, number>;
  const currentTarget = current[category];
  const nextTarget = Math.max(
    2.5,
    Math.min(80, currentTarget + (direction === "up" ? 7 : -7)),
  );
  const otherTotal = CATEGORY_IDS.filter((id) => id !== category).reduce(
    (sum, id) => sum + current[id],
    0,
  );
  const remaining = 100 - nextTarget;
  const next = { ...current, [category]: nextTarget };

  for (const id of CATEGORY_IDS) {
    if (id !== category) next[id] = (current[id] / otherTotal) * remaining;
  }
  return normalizeVector(next);
}

export function classifyCategory(text: string): InterestCategoryId {
  const lower = text.toLowerCase();
  let bestCategory: InterestCategoryId = "ai";
  let bestScore = 0;

  for (const category of CATEGORIES) {
    const score = category.keywords.reduce(
      (sum, keyword) => sum + (hasKeyword(lower, keyword) ? 1 : 0),
      0,
    );
    if (score > bestScore) {
      bestScore = score;
      bestCategory = category.id;
    }
  }
  return bestCategory;
}

export function scorePost(post: FeedPost, profile: InterestProfile): number {
  if (profile.excludedCategories.includes(post.category)) return 0;
  const total = CATEGORY_IDS.reduce((sum, id) => sum + profile.vector[id], 0) || 100;
  const categoryShare = profile.vector[post.category] / total;
  const text = `${post.title ?? ""} ${post.body} ${post.tags.join(" ")}`.toLowerCase();
  const categoryMeta = CATEGORIES.find((item) => item.id === post.category);
  const lexicalHits = categoryMeta?.keywords.filter((word) => hasKeyword(text, word)).length ?? 0;
  return Math.min(1, categoryShare + Math.min(0.18, lexicalHits * 0.035));
}

export function rankPosts(posts: FeedPost[], profile: InterestProfile): FeedPost[] {
  return posts
    .map((post) => ({ post, score: scorePost(post, profile) }))
    .filter(({ score }) => score >= 0.045)
    .sort((a, b) => b.score - a.score)
    .map(({ post }) => post);
}

export function explainPostMatch(post: FeedPost, profile: InterestProfile): string {
  const category = CATEGORIES.find((item) => item.id === post.category);
  const share = Math.round(profile.vector[post.category]);
  const matchingTag = post.tags.find((tag) =>
    category?.keywords.some((keyword) => tag.toLowerCase().includes(keyword)),
  );

  return matchingTag
    ? `This matches your ${category?.label.toLowerCase()} signal (${share}%) through “${matchingTag}”.`
    : `This landed in ${category?.label.toLowerCase()}, currently ${share}% of your Interest DNA.`;
}

export function mapScrapedDocumentToPost(
  document: ScrapedContentDocument,
): FeedPost {
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
