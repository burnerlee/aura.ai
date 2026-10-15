/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

import { Router, type IRouter, type Request, type Response } from "express";
import { logger } from "../lib/logger";

const router: IRouter = Router();

function upstreamBase(): string {
  const raw =
    process.env["RECOMMENDATION_API_URL"] ?? "http://127.0.0.1:8000";
  return raw.replace(/\/$/, "");
}

/**
 * Forward /api/* (except routes registered earlier, e.g. /healthz) to the
 * Python FastAPI recommendation service.
 */
router.all("/{*splat}", async (req: Request, res: Response) => {
  const base = upstreamBase();
  // req.originalUrl includes /api prefix + query string
  const upstreamPath = req.originalUrl.replace(/^\/api/, "") || "/";
  const target = `${base}${upstreamPath}`;

  const headers: Record<string, string> = {
    accept: req.get("accept") || "application/json",
  };
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
