/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { LogOut, User } from "lucide-react";

interface Account {
  name: string | null;
  email: string | null;
  picture: string | null;
}

interface AuthState {
  signed_in: boolean;
  google_enabled: boolean;
  account: Account | null;
}

const AUTH_ERRORS: Record<string, string> = {
  cancelled: "Sign-in was cancelled.",
  invalid_state: "That sign-in link expired. Please try again.",
  not_configured: "Google sign-in isn't configured on this server.",
  google_error: "Google couldn't complete the sign-in. Please try again.",
  sign_in_failed: "Something went wrong while signing you in. Please try again.",
};

function initials(name: string | null | undefined): string {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "";
  return parts.length === 1
    ? parts[0].slice(0, 2).toUpperCase()
    : (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Reads and strips the `auth_error` query param the OAuth callback appends on failure. */
function takeAuthError(): string | null {
  const url = new URL(window.location.href);
  const code = url.searchParams.get("auth_error");
  if (!code) return null;
  url.searchParams.delete("auth_error");
  window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  return AUTH_ERRORS[code] ?? AUTH_ERRORS["sign_in_failed"];
}

function GoogleMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"/>
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/>
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"/>
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z"/>
    </svg>
  );
}

export function AccountMenu({ demo, onOpenProfile }: { demo: boolean; onOpenProfile?: () => void }) {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (demo) return;
    const authError = takeAuthError();
    if (authError) {
      setError(authError);
      setOpen(true);
    }
    void fetch("/api/auth/me")
      .then(async (res) => (res.ok ? ((await res.json()) as AuthState) : null))
      .then(setAuth)
      .catch(() => setAuth(null));
  }, [demo]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const onPointer = (event: PointerEvent) => {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  const signIn = useCallback(() => {
    const returnTo = `${window.location.pathname}${window.location.search}`;
    window.location.assign(`/api/auth/google/start?return_to=${encodeURIComponent(returnTo)}`);
  }, []);

  const signOut = useCallback(async () => {
    setBusy(true);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
      window.location.reload();
    } finally {
      setBusy(false);
    }
  }, []);

  if (demo) {
    return <span className="user-avatar" title="Demo user">AM</span>;
  }

  const account = auth?.signed_in ? auth.account : null;
  const label = initials(account?.name);

  return (
    <div className="account-menu" ref={rootRef}>
      <button
        type="button"
        className={`user-avatar account-avatar ${account ? "signed-in" : ""}`}
        aria-label={account ? `Account: ${account.name ?? account.email ?? "signed in"}` : "Sign in"}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {account?.picture
          ? <img src={account.picture} alt="" referrerPolicy="no-referrer"/>
          : label || <User size={15}/>}
      </button>
      {open && (
        <div className="account-popover" role="dialog" aria-label="Account">
          {account ? (
            <>
              <div className="account-identity">
                <strong>{account.name ?? "Signed in"}</strong>
                {account.email && <span>{account.email}</span>}
              </div>
              <p className="account-copy">Your Interest DNA is saved to your account and follows you to any device.</p>
              <button type="button" className="account-action" onClick={() => void signOut()} disabled={busy}>
                <LogOut size={14}/> Sign out
              </button>
            </>
          ) : (
            <>
              <span className="eyebrow">SAVE YOUR PROFILE</span>
              <p className="account-copy">
                Your feed is learning on this device. Sign in to keep your Interest DNA and pick it up anywhere.
              </p>
              <button
                type="button"
                className="account-google"
                onClick={signIn}
                disabled={auth !== null && !auth.google_enabled}
              >
                <GoogleMark/> Continue with Google
              </button>
              {auth !== null && !auth.google_enabled && (
                <p className="account-note">{AUTH_ERRORS["not_configured"]}</p>
              )}
            </>
          )}
          {onOpenProfile && (
            <button type="button" className="account-action" onClick={() => { setOpen(false); onOpenProfile(); }}>
              <User size={14}/> Your profile
            </button>
          )}
          {error && <p className="account-error">{error}</p>}
        </div>
      )}
    </div>
  );
}
