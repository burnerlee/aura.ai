/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

/** Seed theme ids used by the demo feed + interest prompt mapper. */
export const CATEGORY_IDS = ["cyberpunk", "ai", "space", "culture"] as const;

export type SeedCategoryId = (typeof CATEGORY_IDS)[number];
/** Live themes are free-form facet topics; seed ids remain valid. */
export type InterestCategoryId = string;
export type PostKind = "image" | "article" | "short" | "embed";
export type FeedbackDirection = "resonate" | "banish";

export interface CategoryMeta {
  id: InterestCategoryId;
  label: string;
  shortLabel: string;
  color: string;
  keywords: readonly string[];
}

/** Sparse interest weights keyed by theme id / facet topic. */
export type InterestVector = Record<string, number>;

export interface InterestProfile {
  prompt: string;
  vector: InterestVector;
  excludedCategories: InterestCategoryId[];
}

export interface Author {
  name: string;
  handle: string;
  initials: string;
  avatarColor: string;
  verified?: boolean;
}

export interface FeedPost {
  id: string;
  kind: PostKind;
  category: InterestCategoryId;
  author: Author;
  publishedAt: string;
  title?: string;
  body: string;
  imageUrl?: string;
  imageAlt?: string;
  platform?: "Substack" | "X" | "Reddit";
  /** Original source URL (blog / article). Prefer this for “open”. */
  url?: string;
  embedUrl?: string;
  tags: string[];
  likes: number;
  comments: number;
  /** Optional 0–1 recommendation score from the profile-powered API. */
  matchScore?: number;
  resonated?: boolean;
  banished?: boolean;
}

export interface ScrapedContentDocument {
  source: string;
  external_id: string;
  url?: string;
  embed_url?: string;
  canonical_url?: string;
  title?: string;
  subtitle?: string;
  content?: string;
  content_text?: string;
  summary?: string;
  author?: {
    name?: string;
    avatar_url?: string;
  };
  cover_image_url?: string;
  media_urls?: string[];
  tags?: string[];
  categories?: string[];
  published_at?: string;
  reaction_count?: number;
  comment_count?: number;
}
