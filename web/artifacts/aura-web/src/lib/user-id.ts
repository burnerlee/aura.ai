/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

/**
 * Placeholder path user id.
 *
 * Real identity is server-issued and stored in an HttpOnly cookie (`aura_uid` / `aura_aid`)
 * by the Express BFF. The backend resolves the effective user id from headers injected
 * by the BFF, so the browser never needs direct access to the identifier.
 */
export function getOrCreateUserId(): string {
  return "me";
}
