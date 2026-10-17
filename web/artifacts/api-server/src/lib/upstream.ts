/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

/** Base URL of the Python FastAPI recommendation service. */
export function upstreamBase(): string {
  const raw =
    process.env["RECOMMENDATION_API_URL"] ?? "http://127.0.0.1:8000";
  return raw.replace(/\/$/, "");
}

/** Shared secret for BFF-only FastAPI routes; must match the Python AURA_INTERNAL_TOKEN. */
export function internalToken(): string | null {
  return process.env["AURA_INTERNAL_TOKEN"]?.trim() || null;
}
