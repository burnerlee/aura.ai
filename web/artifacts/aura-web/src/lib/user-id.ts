/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

const USER_KEY = "aura:user-id:v1";

/** Stable anonymous user id for /users/{id}/* recommendation routes. */
export function getOrCreateUserId(): string {
  try {
    const existing = localStorage.getItem(USER_KEY);
    if (existing) return existing;
    const id =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `anon-${Date.now().toString(36)}`;
    localStorage.setItem(USER_KEY, id);
    return id;
  } catch {
    return "anonymous";
  }
}

/** Short label for avatar / toasts (first 2 + last 2 of uuid segment). */
export function shortUserLabel(userId: string): string {
  const compact = userId.replace(/-/g, "");
  if (compact.length < 4) return compact.toUpperCase().padEnd(2, "X").slice(0, 2);
  return (compact.slice(0, 1) + compact.slice(-1)).toUpperCase();
}

export function shortUserId(userId: string): string {
  if (userId.length <= 12) return userId;
  return `${userId.slice(0, 8)}…`;
}
