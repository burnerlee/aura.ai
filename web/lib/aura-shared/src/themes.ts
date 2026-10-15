/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

import type { CategoryMeta, FeedPost, InterestCategoryId, InterestVector } from "./types";

const THEME_PALETTE = [
  "#22d3ee",
  "#a855f7",
  "#f59e0b",
  "#f43f5e",
  "#34d399",
  "#60a5fa",
  "#fb7185",
  "#c084fc",
  "#fbbf24",
  "#2dd4bf",
  "#818cf8",
  "#e879f9",
] as const;

/** Seed theme colors (mirrors CATEGORIES in interest.ts). */
const SEED_COLORS: Record<string, string> = {
  cyberpunk: "#22d3ee",
  ai: "#a855f7",
  space: "#f59e0b",
  culture: "#f43f5e",
};

const SEED_LABELS: Record<string, string> = {
  cyberpunk: "Cyberpunk",
  ai: "AI / ML",
  space: "Space",
  culture: "Indie Pop",
};

function hashString(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

export function themeColor(id: InterestCategoryId): string {
  if (SEED_COLORS[id]) return SEED_COLORS[id];
  return THEME_PALETTE[hashString(id) % THEME_PALETTE.length];
}

export function themeMeta(id: InterestCategoryId): CategoryMeta {
  const label = SEED_LABELS[id] ?? (id.trim() || "General");
  return {
    id: id.trim() || "General",
    label,
    shortLabel: label.length > 22 ? `${label.slice(0, 20)}…` : label,
    color: themeColor(id),
    keywords: label
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter((part) => part.length > 2),
  };
}

/** Case-insensitive theme key used for dedupe / filtering. */
export function themeKey(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

export function categoriesMatch(
  a: string | null | undefined,
  b: string | null | undefined,
): boolean {
  const left = themeKey(a);
  const right = themeKey(b);
  return Boolean(left) && left === right;
}

function vectorWeight(vector: InterestVector, displayId: string): number {
  const exact = vector[displayId];
  if (typeof exact === "number") return exact;
  const key = themeKey(displayId);
  for (const [id, weight] of Object.entries(vector)) {
    if (themeKey(id) === key) return weight;
  }
  return 0;
}

/**
 * Themes that actually appear on the given posts (case-insensitive dedupe).
 * Ranked by the user's interest vector weight, then by post frequency.
 * Never invents empty chips from profile-only / seed keys.
 */
export function discoverThemes(
  posts: FeedPost[],
  vector: InterestVector = {},
  limit = 12,
): CategoryMeta[] {
  // key (lowercase) → { count, display label }
  const counts = new Map<string, { count: number; display: string }>();
  for (const post of posts) {
    const raw = post.category?.trim();
    if (!raw) continue;
    const key = themeKey(raw);
    if (!key || key === "general") continue;
    const prev = counts.get(key);
    if (!prev) {
      counts.set(key, { count: 1, display: raw });
      continue;
    }
    prev.count += 1;
    // Prefer a display form that isn't all-lowercase when both casings exist.
    if (prev.display === prev.display.toLowerCase() && raw !== raw.toLowerCase()) {
      prev.display = raw;
    }
  }

  const ranked = [...counts.entries()]
    .filter(([, entry]) => entry.count > 0)
    .sort((a, b) => {
      const weightDelta =
        vectorWeight(vector, b[1].display) - vectorWeight(vector, a[1].display);
      if (Math.abs(weightDelta) > 0.5) return weightDelta;
      return b[1].count - a[1].count;
    });

  return ranked.slice(0, limit).map(([, entry]) => themeMeta(entry.display));
}

export function formatRelativeTime(value: string, now = Date.now()): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  // Already humanized (demo posts).
  if (!/^\d{4}-\d{2}-\d{2}T/.test(trimmed) && Number.isNaN(Date.parse(trimmed))) {
    return trimmed;
  }
  const ms = Date.parse(trimmed);
  if (Number.isNaN(ms)) return trimmed;
  const deltaSec = Math.round((ms - now) / 1000);
  const abs = Math.abs(deltaSec);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (abs < 60) return rtf.format(deltaSec, "second");
  const mins = Math.round(deltaSec / 60);
  if (Math.abs(mins) < 60) return rtf.format(mins, "minute");
  const hours = Math.round(deltaSec / 3600);
  if (Math.abs(hours) < 48) return rtf.format(hours, "hour");
  const days = Math.round(deltaSec / 86400);
  if (Math.abs(days) < 30) return rtf.format(days, "day");
  const months = Math.round(deltaSec / 2_592_000);
  if (Math.abs(months) < 12) return rtf.format(months, "month");
  return rtf.format(Math.round(deltaSec / 31_536_000), "year");
}
