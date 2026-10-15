/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

import type { FeedPost, InterestCategoryId, PostKind } from "./types";
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

export function mapApiFeedCardToPost(card: ApiFeedCard): FeedPost {
  const sourceUrl = card.url || card.embed_url || undefined;
  return {
    id: card.id,
    kind: asKind(card.kind),
    category: asCategory(card.category),
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
