export const CATEGORY_IDS = ['cyberpunk', 'ai', 'space', 'culture'] as const;
export type InterestCategoryId = (typeof CATEGORY_IDS)[number];
export type PostKind = 'image' | 'article' | 'short' | 'embed';
export type FeedbackDirection = 'resonate' | 'banish';
export interface CategoryMeta { id: InterestCategoryId; label: string; shortLabel: string; color: string; keywords: readonly string[] }
export interface InterestVector { cyberpunk: number; ai: number; space: number; culture: number }
export interface InterestProfile { prompt: string; vector: InterestVector; excludedCategories: InterestCategoryId[] }
export interface Author { name: string; handle: string; initials: string; avatarColor: string; verified?: boolean }
export interface FeedPost {
  id: string; kind: PostKind; category: InterestCategoryId; author: Author; publishedAt: string;
  title?: string; body: string; imageUrl?: string; imageAlt?: string;
  platform?: 'Substack' | 'X' | 'Reddit'; embedUrl?: string; tags: string[];
  likes: number; comments: number; resonated?: boolean; banished?: boolean;
}
