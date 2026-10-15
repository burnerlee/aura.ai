export const CATEGORY_IDS = ["cyberpunk", "ai", "space", "culture"] as const;

export type InterestCategoryId = (typeof CATEGORY_IDS)[number];
export type PostKind = "image" | "article" | "short" | "embed";
export type FeedbackDirection = "resonate" | "banish";

export interface CategoryMeta {
  id: InterestCategoryId;
  label: string;
  shortLabel: string;
  color: string;
  keywords: readonly string[];
}

export interface InterestVector {
  cyberpunk: number;
  ai: number;
  space: number;
  culture: number;
}

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
  embedUrl?: string;
  tags: string[];
  likes: number;
  comments: number;
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
