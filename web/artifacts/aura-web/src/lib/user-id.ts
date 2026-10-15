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
