/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

import { randomUUID } from "node:crypto";
import type { CookieOptions, NextFunction, Request, Response } from "express";
import { logger } from "./logger";

/** Anonymous, server-minted identity: every visitor gets one without signing in. */
export const ANON_COOKIE = "aura_uid";
/** Signed account id, set only after a successful Google sign-in. */
export const ACCOUNT_COOKIE = "aura_aid";

const ONE_YEAR_MS = 1000 * 60 * 60 * 24 * 365;
const DEV_COOKIE_SECRET = "aura-dev-cookie-secret";

export function cookieSecret(): string {
  const secret = process.env["AURA_COOKIE_SECRET"]?.trim();
  if (secret) return secret;
  if (process.env["NODE_ENV"] === "production") {
    throw new Error("AURA_COOKIE_SECRET is required in production");
  }
  logger.warn("AURA_COOKIE_SECRET not set; using an insecure development secret");
  return DEV_COOKIE_SECRET;
}

export function baseCookieOptions(): CookieOptions {
  return {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env["NODE_ENV"] === "production",
    path: "/",
  };
}

export function setAnonCookie(res: Response, uid: string): void {
  res.cookie(ANON_COOKIE, uid, { ...baseCookieOptions(), maxAge: ONE_YEAR_MS });
}

export function setAccountCookie(res: Response, accountId: string): void {
  res.cookie(ACCOUNT_COOKIE, accountId, {
    ...baseCookieOptions(),
    maxAge: ONE_YEAR_MS,
    signed: true,
  });
}

export function clearAccountCookie(res: Response): void {
  res.clearCookie(ACCOUNT_COOKIE, baseCookieOptions());
}

/** Resolve the request's identity into `res.locals`, minting an anonymous id on first visit. */
export function identityMiddleware(req: Request, res: Response, next: NextFunction): void {
  const existing = (req.cookies?.[ANON_COOKIE] as string | undefined)?.trim();
  const uid = existing || randomUUID();
  if (!existing) setAnonCookie(res, uid);
  res.locals["aura_uid"] = uid;

  const accountId = req.signedCookies?.[ACCOUNT_COOKIE];
  if (typeof accountId === "string" && accountId) {
    res.locals["aura_aid"] = accountId;
  }
  next();
}
