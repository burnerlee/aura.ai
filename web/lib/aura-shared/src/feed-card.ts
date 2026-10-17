/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

import type { FeedPost, InterestCategoryId, PostInsight, PostKind, PostMatch } from "./types";
import { formatRelativeTime } from "./themes";

/** Snake_case card from the Python / BFF recommendation API. */
export interface ApiFeedCard {
  id: string;
  kind: PostKind | string;
  category: string;
  author: {
    name: string;
    handle: string;
    initials: string;
    avatar_color?: string;
    verified?: boolean;
  };
  published_at: string;
  title?: string | null;
  body: string;
  image_url?: string | null;
  image_alt?: string | null;
  platform?: string | null;
  embed_url?: string | null;
  tags: string[];
  likes: number;
  comments: number;
  source: string;
  external_id: string;
  url?: string | null;
  embedding_status: string;
  embedding_error?: string | null;
  score?: number | null;
  why?: string | null;
  per_query_scores?: Record<string, number>;
  category_tag_id?: string | null;
  canonical_tags?: { id: string; label: string; kind: "topic" | "style" | "theme" }[];
  insight?: {
    headline: string;
    summary: string;
    reasons: { kind: string; text: string }[];
    references: {
      post_id: string;
      title: string;
      relation: "liked" | "skipped";
      similarity: number;
      shared_topics?: string[];
    }[];
  } | null;
  match?: {
    percent?: number | null;
    fit: number;
    pool_size: number;
    reliable: boolean;
    components: Record<string, number>;
    top_attribution?: string | null;
    flags: { kind: "aversion" | "affinity"; label: string; rule_key: string }[];
  } | null;
}

function asCategory(value: string): InterestCategoryId {
  const trimmed = value?.trim();
  return trimmed || "General";
}

function asKind(value: string): PostKind {
  if (value === "image" || value === "article" || value === "short" || value === "embed") {
    return value;
  }
  return "short";
}

function asPlatform(
  value: string | null | undefined,
): FeedPost["platform"] {
  if (value === "Substack" || value === "X" || value === "Reddit") return value;
  if (value?.toLowerCase() === "substack") return "Substack";
  if (value === "Twitter" || value?.toLowerCase() === "x") return "X";
  if (value?.toLowerCase() === "reddit") return "Reddit";
  return undefined;
}

/** Best URL to open the original post / blog in a new tab. */
export function postSourceUrl(post: Pick<FeedPost, "url" | "embedUrl">): string | undefined {
  const raw = (post.url || post.embedUrl || "").trim();
  return raw || undefined;
}

function mapMatch(match: ApiFeedCard["match"]): PostMatch | undefined {
  if (!match) return undefined;
  return {
    percent: typeof match.percent === "number" ? match.percent : null,
    fit: match.fit,
    poolSize: match.pool_size,
    reliable: match.reliable,
    components: match.components ?? {},
    topAttribution: match.top_attribution ?? undefined,
    flags: (match.flags ?? []).map((flag) => ({
      kind: flag.kind,
      label: flag.label,
      ruleKey: flag.rule_key,
    })),
  };
}

function mapInsight(insight: ApiFeedCard["insight"]): PostInsight | undefined {
  if (!insight) return undefined;
  return {
    headline: insight.headline,
    summary: insight.summary,
    reasons: insight.reasons ?? [],
    references: (insight.references ?? []).map((ref) => ({
      postId: ref.post_id,
      title: ref.title,
      relation: ref.relation,
      similarity: ref.similarity,
      sharedTopics: ref.shared_topics ?? [],
    })),
  };
}

export function mapApiFeedCardToPost(card: ApiFeedCard): FeedPost {
  const sourceUrl = card.url || card.embed_url || undefined;
  return {
    id: card.id,
    kind: asKind(card.kind),
    category: asCategory(card.category),
    categoryTagId: card.category_tag_id ?? undefined,
    canonicalTags: card.canonical_tags,
    match: mapMatch(card.match),
    insight: mapInsight(card.insight),
    author: {
      name: card.author.name,
      handle: card.author.handle,
      initials: card.author.initials,
      avatarColor: card.author.avatar_color || "#626b7a",
      verified: card.author.verified,
    },
    publishedAt: formatRelativeTime(card.published_at),
    title: card.title ?? undefined,
    body: card.body,
    imageUrl: card.image_url ?? undefined,
    imageAlt: card.image_alt ?? undefined,
    platform: asPlatform(card.platform),
    url: sourceUrl,
    embedUrl: card.embed_url ?? sourceUrl,
    tags: card.tags ?? [],
    likes: card.likes ?? 0,
    comments: card.comments ?? 0,
    matchScore:
      typeof card.score === "number" && Number.isFinite(card.score)
        ? card.score
        : undefined,
  };
}
