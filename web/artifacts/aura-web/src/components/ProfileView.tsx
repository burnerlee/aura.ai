/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Bookmark, Heart, MessageCircle, RotateCcw, Sparkles, ThumbsDown, User } from "lucide-react";
import { getUserProfile, listPosts } from "@workspace/api-client-react";
import {
  dnaLabel,
  mapApiFeedCardToPost,
  postSourceUrl,
  themeColor,
  type ServerDna,
} from "@workspace/aura-shared";

interface Account {
  name: string | null;
  email: string | null;
  picture: string | null;
}

/** The subset of `GET /users/{id}/profile` this view reads. */
interface ProfileDump {
  persona?: {
    summary?: string;
    topics?: string[];
    anti_topics?: string[];
    preferred_styles?: string[];
    preferred_emotions?: string[];
  };
  positive_ids?: string[];
  negative_ids?: string[];
  conversation_turns?: number;
  created_at?: string;
}

const LIKED_SHOWN = 8;

function useAccount(demo: boolean): Account | null {
  const [account, setAccount] = useState<Account | null>(null);
  useEffect(() => {
    if (demo) return;
    void fetch("/api/auth/me")
      .then(async (res) => (res.ok ? ((await res.json()) as { signed_in: boolean; account: Account | null }) : null))
      .then((auth) => setAccount(auth?.signed_in ? auth.account : null))
      .catch(() => setAccount(null));
  }, [demo]);
  return account;
}

function Chips({ items, tone }: { items: string[]; tone?: "avoid" }) {
  if (!items.length) return <p className="profile-muted">Nothing yet.</p>;
  return (
    <div className="profile-chips">
      {items.map((item) => (
        <span key={item} className={`profile-chip ${tone === "avoid" ? "avoid" : ""}`}>{item}</span>
      ))}
    </div>
  );
}

export function ProfileView({
  userId,
  demo,
  dna,
  savedCount,
  onChat,
  onOpenSaved,
  onReset,
}: {
  userId: string;
  demo: boolean;
  dna: ServerDna | null;
  savedCount: number;
  onChat: () => void;
  onOpenSaved: () => void;
  onReset: () => Promise<void>;
}) {
  const account = useAccount(demo);
  const [resetting, setResetting] = useState(false);
  const profileQuery = useQuery({
    queryKey: ["profile", userId],
    queryFn: async () => (await getUserProfile(userId)) as ProfileDump,
    enabled: !demo,
  });
  const profile = profileQuery.data;
  const likedIds = (profile?.positive_ids ?? []).slice(-LIKED_SHOWN).reverse();
  const likedQuery = useQuery({
    queryKey: ["profile", userId, "liked", likedIds],
    queryFn: () => listPosts({ ids: likedIds }),
    enabled: !demo && likedIds.length > 0,
  });
  const liked = (likedQuery.data ?? []).map(mapApiFeedCardToPost);

  if (demo) {
    return (
      <div className="empty-state">
        <span className="empty-state-icon"><User size={22}/></span>
        <h2>Profiles need the live backend.</h2>
        <p>Demo mode keeps your Interest DNA in this browser only.</p>
      </div>
    );
  }

  const persona = profile?.persona ?? {};
  const themes = dna
    ? Object.entries(dna.weights).sort((a, b) => b[1] - a[1]).slice(0, 8)
    : [];
  const avoiding = [
    ...(persona.anti_topics ?? []),
    ...(dna?.anti ?? []).map((rule) => rule.label || rule.key),
  ].filter((item, index, all) => item && all.indexOf(item) === index);
  const vibes = [...(persona.preferred_styles ?? []), ...(persona.preferred_emotions ?? [])];
  const isEmpty = !persona.summary && !themes.length && !likedIds.length;

  async function reset() {
    if (!window.confirm("Forget your Interest DNA, reactions and Aura chat history? This can't be undone.")) return;
    setResetting(true);
    try {
      await onReset();
    } finally {
      setResetting(false);
    }
  }

  return (
    <div className="profile-view">
      <section className="profile-card profile-identity">
        <span className="profile-avatar">
          {account?.picture ? <img src={account.picture} alt="" referrerPolicy="no-referrer"/> : <User size={22}/>}
        </span>
        <div>
          <h2>{account?.name ?? "Guest reader"}</h2>
          <p className="profile-muted">
            {account?.email ?? "Your profile lives on this device. Sign in from the avatar menu to keep it."}
          </p>
        </div>
        <div className="profile-stats">
          <span><Heart size={13}/><b>{profile?.positive_ids?.length ?? 0}</b> resonated</span>
          <span><ThumbsDown size={13}/><b>{profile?.negative_ids?.length ?? 0}</b> banished</span>
          <span><Bookmark size={13}/><b>{savedCount}</b> saved</span>
          <span><MessageCircle size={13}/><b>{profile?.conversation_turns ?? 0}</b> Aura messages</span>
        </div>
      </section>

      {isEmpty && !profileQuery.isLoading ? (
        <div className="empty-state">
          <span className="empty-state-icon"><Sparkles size={22}/></span>
          <h2>Aura doesn't know you yet.</h2>
          <p>One sentence about what you like is enough to start.</p>
          <button className="button button-primary" onClick={onChat}>Chat with Aura</button>
        </div>
      ) : (
        <>
          <section className="profile-card">
            <div className="profile-card-head">
              <span className="eyebrow"><Sparkles size={11}/> WHAT AURA KNOWS ABOUT YOU</span>
              <button className="text-action" onClick={onChat}>Refine in chat <ArrowUpRight size={13}/></button>
            </div>
            <p className="profile-summary">“{persona.summary || dna?.prompt || "No summary yet."}”</p>
            <h3>Leaning into</h3>
            <Chips items={persona.topics ?? []}/>
            <h3>Avoiding</h3>
            <Chips items={avoiding} tone="avoid"/>
            {!!vibes.length && (<><h3>Reading vibe</h3><Chips items={vibes}/></>)}
          </section>

          <section className="profile-card">
            <div className="profile-card-head"><span className="eyebrow">INTEREST DNA</span></div>
            {themes.length ? (
              <div className="profile-bars">
                {themes.map(([key, weight]) => {
                  const label = dna ? dnaLabel(dna, key) : key;
                  return (
                    <div className="profile-bar" key={key}>
                      <span>{label}</span>
                      <i><em style={{ width: `${Math.min(100, weight)}%`, background: themeColor(label) }}/></i>
                      <b>{Math.round(weight)}%</b>
                    </div>
                  );
                })}
              </div>
            ) : <p className="profile-muted">Themes appear after your first chat or reaction.</p>}
          </section>

          <section className="profile-card">
            <div className="profile-card-head">
              <span className="eyebrow">RECENTLY RESONATED</span>
              {savedCount > 0 && <button className="text-action" onClick={onOpenSaved}>Your collection <ArrowUpRight size={13}/></button>}
            </div>
            {liked.length ? (
              <ul className="profile-liked">
                {liked.map((post) => {
                  const href = postSourceUrl(post);
                  return (
                    <li key={post.id}>
                      <span className="profile-source">{post.platform ?? post.author.handle}</span>
                      {href
                        ? <a href={href} target="_blank" rel="noreferrer">{post.title ?? post.body.slice(0, 90)}</a>
                        : <span>{post.title ?? post.body.slice(0, 90)}</span>}
                    </li>
                  );
                })}
              </ul>
            ) : <p className="profile-muted">Resonate with a post and it shows up here.</p>}
          </section>
        </>
      )}

      <section className="profile-card profile-danger">
        <div>
          <h3>Start over</h3>
          <p className="profile-muted">Forget your Interest DNA, reactions and Aura's memory of your chats.</p>
        </div>
        <button className="button button-secondary" onClick={() => void reset()} disabled={resetting}>
          <RotateCcw size={14}/> {resetting ? "Resetting…" : "Reset profile"}
        </button>
      </section>
    </div>
  );
}
