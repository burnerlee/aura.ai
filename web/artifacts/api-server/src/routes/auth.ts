/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

import { createHash, randomBytes, randomUUID } from "node:crypto";
import { Router, type IRouter, type Request, type Response } from "express";
import { logger } from "../lib/logger";
import {
  baseCookieOptions,
  clearAccountCookie,
  setAccountCookie,
  setAnonCookie,
} from "../lib/session";
import { internalToken, upstreamBase } from "../lib/upstream";

const GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";
const GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token";
const GOOGLE_ISSUERS = new Set(["accounts.google.com", "https://accounts.google.com"]);
const DEFAULT_REDIRECT_URI = "http://localhost:5173/api/auth/google/callback";

const OAUTH_COOKIE = "aura_oauth";
const OAUTH_COOKIE_PATH = "/api/auth/google";
const OAUTH_COOKIE_MAX_AGE_MS = 1000 * 60 * 10;

interface GoogleConfig {
  clientId: string;
  clientSecret: string;
  redirectUri: string;
}

interface PendingSignIn {
  state: string;
  verifier: string;
  returnTo: string;
}

interface GoogleClaims {
  sub: string;
  email?: string;
  email_verified?: boolean;
  name?: string;
  picture?: string;
}

function googleConfig(): GoogleConfig | null {
  const clientId = process.env["GOOGLE_CLIENT_ID"]?.trim();
  const clientSecret = process.env["GOOGLE_CLIENT_SECRET"]?.trim();
  if (!clientId || !clientSecret) return null;
  return {
    clientId,
    clientSecret,
    redirectUri: process.env["GOOGLE_REDIRECT_URI"]?.trim() || DEFAULT_REDIRECT_URI,
  };
}

/** Only same-origin paths, so the callback can't be turned into an open redirect. */
function safeReturnTo(raw: unknown): string {
  if (typeof raw !== "string") return "/";
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\")) return "/";
  return raw;
}

function withParam(path: string, key: string, value: string): string {
  const url = new URL(path, "http://placeholder");
  url.searchParams.set(key, value);
  return `${url.pathname}${url.search}${url.hash}`;
}

function readPending(req: Request): PendingSignIn | null {
  const raw = req.signedCookies?.[OAUTH_COOKIE];
  if (typeof raw !== "string") return null;
  try {
    const parsed = JSON.parse(raw) as Partial<PendingSignIn>;
    if (!parsed.state || !parsed.verifier) return null;
    return {
      state: parsed.state,
      verifier: parsed.verifier,
      returnTo: safeReturnTo(parsed.returnTo),
    };
  } catch {
    return null;
  }
}

/**
 * The ID token comes straight from Google's token endpoint over TLS, which OIDC Core
 * §3.1.3.7 accepts in place of signature verification; issuer, audience and expiry
 * must still be checked.
 */
function claimsFromIdToken(idToken: string, clientId: string): GoogleClaims {
  const payload = idToken.split(".")[1];
  if (!payload) throw new Error("Malformed ID token");
  const claims = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as {
    iss?: string;
    aud?: string;
    exp?: number;
  } & GoogleClaims;
  if (!claims.iss || !GOOGLE_ISSUERS.has(claims.iss)) throw new Error("Unexpected ID token issuer");
  if (claims.aud !== clientId) throw new Error("ID token audience mismatch");
  if (!claims.exp || claims.exp * 1000 <= Date.now()) throw new Error("ID token expired");
  if (!claims.sub) throw new Error("ID token has no subject");
  return claims;
}

async function exchangeCode(
  config: GoogleConfig,
  code: string,
  verifier: string,
): Promise<GoogleClaims> {
  const resp = await fetch(GOOGLE_TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      code,
      client_id: config.clientId,
      client_secret: config.clientSecret,
      redirect_uri: config.redirectUri,
      grant_type: "authorization_code",
      code_verifier: verifier,
    }),
  });
  if (!resp.ok) {
    throw new Error(`Google token exchange failed (${resp.status}): ${await resp.text()}`);
  }
  const tokens = (await resp.json()) as { id_token?: string };
  if (!tokens.id_token) throw new Error("Google token response had no id_token");
  return claimsFromIdToken(tokens.id_token, config.clientId);
}

async function linkAccount(claims: GoogleClaims, anonymousId: string): Promise<string> {
  const token = internalToken();
  if (!token) throw new Error("AURA_INTERNAL_TOKEN is not set");
  const resp = await fetch(`${upstreamBase()}/identity/google/link`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-aura-internal-token": token },
    body: JSON.stringify({
      subject: claims.sub,
      email: claims.email ?? null,
      email_verified: Boolean(claims.email_verified),
      name: claims.name ?? null,
      picture: claims.picture ?? null,
      anonymous_id: anonymousId || null,
    }),
  });
  if (!resp.ok) {
    throw new Error(`Account link failed (${resp.status}): ${await resp.text()}`);
  }
  const body = (await resp.json()) as { account_id?: string };
  if (!body.account_id) throw new Error("Account link returned no account_id");
  return body.account_id;
}

const router: IRouter = Router();

router.get("/auth/google/start", (req: Request, res: Response) => {
  const config = googleConfig();
  if (!config) {
    res.status(501).json({
      detail: "Google sign-in is not configured (set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET).",
    });
    return;
  }
  const state = randomBytes(16).toString("base64url");
  const verifier = randomBytes(32).toString("base64url");
  const pending: PendingSignIn = {
    state,
    verifier,
    returnTo: safeReturnTo(req.query["return_to"]),
  };
  res.cookie(OAUTH_COOKIE, JSON.stringify(pending), {
    ...baseCookieOptions(),
    path: OAUTH_COOKIE_PATH,
    maxAge: OAUTH_COOKIE_MAX_AGE_MS,
    signed: true,
  });
  const params = new URLSearchParams({
    client_id: config.clientId,
    redirect_uri: config.redirectUri,
    response_type: "code",
    scope: "openid email profile",
    state,
    code_challenge: createHash("sha256").update(verifier).digest("base64url"),
    code_challenge_method: "S256",
    prompt: "select_account",
  });
  res.redirect(`${GOOGLE_AUTH_URL}?${params.toString()}`);
});

router.get("/auth/google/callback", async (req: Request, res: Response) => {
  const pending = readPending(req);
  res.clearCookie(OAUTH_COOKIE, { ...baseCookieOptions(), path: OAUTH_COOKIE_PATH });
  const returnTo = pending?.returnTo ?? "/";
  const fail = (reason: string) => res.redirect(withParam(returnTo, "auth_error", reason));

  const config = googleConfig();
  if (!config) {
    fail("not_configured");
    return;
  }
  const { code, state, error } = req.query;
  if (typeof error === "string") {
    fail(error === "access_denied" ? "cancelled" : "google_error");
    return;
  }
  if (!pending || typeof code !== "string" || state !== pending.state) {
    fail("invalid_state");
    return;
  }

  try {
    const claims = await exchangeCode(config, code, pending.verifier);
    const accountId = await linkAccount(claims, String(res.locals["aura_uid"] ?? ""));
    setAccountCookie(res, accountId);
    // The anonymous history now lives on the account; signing out later starts clean.
    setAnonCookie(res, randomUUID());
    res.redirect(returnTo);
  } catch (err) {
    logger.error({ err }, "Google sign-in failed");
    fail("sign_in_failed");
  }
});

router.get("/auth/me", async (_req: Request, res: Response) => {
  const googleEnabled = googleConfig() !== null;
  const accountId = res.locals["aura_aid"] as string | undefined;
  if (!accountId) {
    res.json({ signed_in: false, google_enabled: googleEnabled, account: null });
    return;
  }
  try {
    const resp = await fetch(`${upstreamBase()}/identity/account`, {
      headers: { accept: "application/json", "x-aura-userid": accountId },
    });
    if (resp.status === 404) {
      clearAccountCookie(res);
      res.json({ signed_in: false, google_enabled: googleEnabled, account: null });
      return;
    }
    if (!resp.ok) throw new Error(`Account lookup failed (${resp.status})`);
    const account = (await resp.json()) as { name?: string; email?: string; picture?: string };
    res.json({
      signed_in: true,
      google_enabled: googleEnabled,
      account: {
        name: account.name ?? null,
        email: account.email ?? null,
        picture: account.picture ?? null,
      },
    });
  } catch (err) {
    logger.error({ err }, "Account lookup failed");
    res.status(502).json({ detail: "Recommendation API unreachable" });
  }
});

router.post("/auth/logout", (_req: Request, res: Response) => {
  clearAccountCookie(res);
  setAnonCookie(res, randomUUID());
  res.json({ ok: true });
});

export default router;
