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

/** A canonical tag attached to a post (theme / topic / style). */
export interface PostTag {
  id: string;
  label: string;
  kind: "topic" | "style" | "theme";
}

export interface MatchFlag {
  kind: "aversion" | "affinity";
  label: string;
  ruleKey: string;
}

/**
 * Server-computed match. `percent` is relative: the post's percentile among everything
 * scored for this request (not the shown list). `null` means the pool was too small.
 */
export interface PostMatch {
  percent: number | null;
  fit: number;
  poolSize: number;
  reliable: boolean;
  components: Record<string, number>;
  topAttribution?: string;
  flags: MatchFlag[];
}

/** A post the user already reacted to that this one is being compared with. */
export interface InsightRef {
  postId: string;
  title: string;
  relation: "liked" | "skipped";
  similarity: number;
  sharedTopics: string[];
}

export interface InsightReason {
  kind: string;
  text: string;
}

/** Why a post is in the feed, built server-side only from facts about this user. */
export interface PostInsight {
  headline: string;
  summary: string;
  reasons: InsightReason[];
  references: InsightRef[];
}

export type ServerDnaRuleKind =
  | "topic"
  | "style"
  | "emotion"
  | "author"
  | "source"
  | "length"
  | "reading_level";

/** A pattern the user avoids (anti) or leans toward (affinity). */
export interface ServerDnaRule {
  kind: ServerDnaRuleKind;
  key: string;
  label?: string | null;
  strength?: number;
  source?: "chat" | "learned" | "confirmed";
  evidence_ids?: string[];
}

/** Interest DNA as the server owns it: weights keyed by theme id, summing to ~100. */
export interface ServerDna {
  weights: Record<string, number>;
  labels: Record<string, string>;
  anti: ServerDnaRule[];
  affinities: ServerDnaRule[];
  prompt: string;
  version: number;
}

/** Attribute of a just-skipped post, offered back as a one-tap chip. */
export interface ServerNoticed {
  kind: ServerDnaRuleKind;
  key: string;
  label: string;
  seen: number;
  negative: number;
}

export interface FeedPost {
  id: string;
  kind: PostKind;
  category: InterestCategoryId;
  /** Theme id behind `category` (the key into the server's Interest DNA). */
  categoryTagId?: string;
  /** Canonical topic / style tags generated from the content dataset. */
  canonicalTags?: PostTag[];
  /** Relative match from the server; absent in demo mode. */
  match?: PostMatch;
  /** Plain-language reasons this post is in the feed; personalized feed only. */
  insight?: PostInsight;
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
