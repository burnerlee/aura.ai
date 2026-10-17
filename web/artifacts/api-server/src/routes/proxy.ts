/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

import { Router, type IRouter, type Request, type Response } from "express";
import { logger } from "../lib/logger";
import { upstreamBase } from "../lib/upstream";

const router: IRouter = Router();

/** FastAPI routes only the BFF itself may call (it adds the internal token). */
function isBffOnly(path: string): boolean {
  let decoded = path;
  try {
    decoded = decodeURIComponent(path);
  } catch {
    // keep the raw path
  }
  return decoded.toLowerCase().includes("/identity/google/");
}

/**
 * Forward /api/* (except routes registered earlier, e.g. /healthz) to the
 * Python FastAPI recommendation service.
 */
router.all("/{*splat}", async (req: Request, res: Response) => {
  const base = upstreamBase();
  // req.originalUrl includes /api prefix + query string
  const upstreamPath = req.originalUrl.replace(/^\/api/, "") || "/";
  if (isBffOnly(upstreamPath)) {
    res.status(404).json({ detail: "Not found" });
    return;
  }
  const target = `${base}${upstreamPath}`;

  const anonId = String(res.locals["aura_uid"] || "").trim();
  const accountId = String(res.locals["aura_aid"] || "").trim();
  const effectiveUserId = accountId || anonId;

  const headers: Record<string, string> = {
    accept: req.get("accept") || "application/json",
  };
  if (effectiveUserId) {
    headers["x-aura-userid"] = effectiveUserId;
  }

  const contentType = req.get("content-type");
  if (contentType) {
    headers["content-type"] = contentType;
  }

  const init: RequestInit = {
    method: req.method,
    headers,
  };

  if (req.method !== "GET" && req.method !== "HEAD" && req.method !== "OPTIONS") {
    if (req.body !== undefined && req.body !== null) {
      init.body =
        typeof req.body === "string" ? req.body : JSON.stringify(req.body);
      if (!headers["content-type"]) {
        headers["content-type"] = "application/json";
      }
    }
  }

  try {
    const upstream = await fetch(target, init);
    const body = Buffer.from(await upstream.arrayBuffer());
    const upstreamType = upstream.headers.get("content-type");
    res.status(upstream.status);
    if (upstreamType) {
      res.setHeader("content-type", upstreamType);
    }
    res.send(body);
  } catch (err) {
    logger.error({ err, target }, "Recommendation upstream proxy failed");
    res.status(502).json({
      detail: `Recommendation API unreachable at ${base}. Is scraper serve running?`,
    });
  }
});

export default router;
