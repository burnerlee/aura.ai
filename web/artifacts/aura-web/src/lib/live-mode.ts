/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

/** When true, AuraFeed stays on local demo data (no recommendation API). */
export function useDemoMode(): boolean {
  return import.meta.env.VITE_USE_DEMO === "1";
}
