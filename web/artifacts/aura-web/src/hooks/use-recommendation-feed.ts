/*
 * Copyright (c) 2026 DevRev Inc. All rights reserved.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createPost,
  discoverPosts,
  getPost,
  getUserFeed,
  getUserPair,
  onboardUser,
  postUserEvents,
  searchPosts,
  similarPosts,
  tuneUser,
  type FeedCard,
} from "@workspace/api-client-react";
import {
  mapApiFeedCardToPost,
  type FeedPost,
  type FeedbackDirection,
  type InterestProfile,
} from "@workspace/aura-shared";
import { getOrCreateUserId } from "@/lib/user-id";
import { useDemoMode } from "@/lib/live-mode";

export type PublishDraft = Omit<FeedPost, "id" | "publishedAt" | "likes" | "comments">;

function cardsToPosts(cards: FeedCard[]): FeedPost[] {
  return cards.map((card) => mapApiFeedCardToPost(card));
}

function whyMap(cards: FeedCard[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const card of cards) {
    if (card.why) out[card.id] = card.why;
  }
  return out;
}

export function useRecommendationFeed(demoPosts: FeedPost[]) {
  const demo = useDemoMode();
  const userId = useMemo(() => (demo ? "demo" : getOrCreateUserId()), [demo]);
  const queryClient = useQueryClient();
  const [searchResults, setSearchResults] = useState<FeedPost[] | null>(null);
  const [searchWhy, setSearchWhy] = useState<Record<string, string>>({});
  const [localOverlay, setLocalOverlay] = useState<FeedPost[]>([]);
  const [similarResults, setSimilarResults] = useState<FeedPost[] | null>(null);
  const [similarSeedId, setSimilarSeedId] = useState<string | null>(null);
  const onboarded = useRef(false);

  const feedQuery = useQuery({
    queryKey: ["feed", userId],
    queryFn: () => getUserFeed(userId, { k: 40, explain: true }),
    enabled: !demo,
    staleTime: 15_000,
  });

  const discoverQuery = useQuery({
    queryKey: ["discover"],
    queryFn: () => discoverPosts({ k: 40, ready_only: true }),
    enabled: !demo,
    staleTime: 30_000,
  });

  useEffect(() => {
    if (demo || onboarded.current) return;
    onboarded.current = true;
    const key = `aura:onboarded:${userId}`;
    if (localStorage.getItem(key)) return;
    void onboardUser(userId, {
      free_text:
        "Curious reader exploring AI, culture, space, and cyberpunk signal.",
    })
      .then(() => localStorage.setItem(key, "1"))
      .catch(() => {
        onboarded.current = false;
      });
  }, [demo, userId]);

  const remotePosts = useMemo(() => {
    if (demo) return demoPosts;
    const fromApi = feedQuery.data ? cardsToPosts(feedQuery.data) : [];
    const ids = new Set(fromApi.map((p) => p.id));
    return [...localOverlay.filter((p) => !ids.has(p.id)), ...fromApi];
  }, [demo, demoPosts, feedQuery.data, localOverlay]);

  const discoverPostsMapped = useMemo(() => {
    if (demo) return demoPosts;
    return discoverQuery.data ? cardsToPosts(discoverQuery.data) : [];
  }, [demo, demoPosts, discoverQuery.data]);

  const whyById = useMemo(() => {
    if (demo) return {} as Record<string, string>;
    return { ...whyMap(feedQuery.data ?? []), ...searchWhy };
  }, [demo, feedQuery.data, searchWhy]);

  const runSearch = useCallback(
    async (query: string) => {
      if (demo) {
        setSearchResults(null);
        return;
      }
      const q = query.trim();
      if (!q) {
        setSearchResults(null);
        setSearchWhy({});
        return;
      }
      const cards = await searchPosts({ query: q, k: 30, explain: true });
      setSearchResults(cardsToPosts(cards));
      setSearchWhy(whyMap(cards));
    },
    [demo],
  );

  const recordFeedback = useCallback(
    async (post: FeedPost, direction: FeedbackDirection) => {
      if (demo) return;
      const event = direction === "resonate" ? "like" : "not_interested";
      await postUserEvents(userId, {
        events: [{ post_id: post.id, event }],
      });
      void queryClient.invalidateQueries({ queryKey: ["feed", userId] });
    },
    [demo, queryClient, userId],
  );

  const recordSave = useCallback(
    async (post: FeedPost, saved: boolean) => {
      if (demo || !saved) return;
      await postUserEvents(userId, {
        events: [{ post_id: post.id, event: "save" }],
      });
    },
    [demo, userId],
  );

  const publish = useCallback(
    async (draft: PublishDraft) => {
      if (demo) return null;
      const created = await createPost({
        kind: draft.kind,
        title: draft.title,
        body: draft.body,
        category: draft.category,
        embed_url: draft.embedUrl,
        platform: draft.platform,
        image_url: draft.imageUrl,
        user_id: userId,
        author_name: draft.author.name,
        wait_for_embed: false,
      });
      const post = mapApiFeedCardToPost(created.post);
      setLocalOverlay((current) => [post, ...current]);
      const postId = post.id;
      void (async () => {
        for (let i = 0; i < 12; i++) {
          await new Promise((r) => setTimeout(r, 1500));
          try {
            const card = await getPost(postId);
            if (
              card.embedding_status === "ready" ||
              card.embedding_status === "failed"
            ) {
              setLocalOverlay((current) =>
                current.map((p) =>
                  p.id === postId ? mapApiFeedCardToPost(card) : p,
                ),
              );
              void queryClient.invalidateQueries({ queryKey: ["feed", userId] });
              void queryClient.invalidateQueries({ queryKey: ["discover"] });
              break;
            }
          } catch {
            break;
          }
        }
      })();
      return post;
    },
    [demo, queryClient, userId],
  );

  const tune = useCallback(
    async (profile: InterestProfile) => {
      if (demo) return;
      await tuneUser(userId, { text: profile.prompt });
      void queryClient.invalidateQueries({ queryKey: ["feed", userId] });
    },
    [demo, queryClient, userId],
  );

  const fetchPair = useCallback(async (): Promise<FeedPost[]> => {
    if (demo) {
      return demoPosts.slice(0, 2);
    }
    const cards = await getUserPair(userId);
    return cardsToPosts(cards).slice(0, 2);
  }, [demo, demoPosts, userId]);

  const preferPair = useCallback(
    async (winner: FeedPost, loser: FeedPost) => {
      if (demo) return;
      await postUserEvents(userId, {
        events: [
          {
            post_id: winner.id,
            event: "pairwise",
            pair_post_id: loser.id,
          },
          {
            post_id: loser.id,
            event: "pairwise",
            pair_post_id: winner.id,
            text: "loser",
          },
        ],
      });
      void queryClient.invalidateQueries({ queryKey: ["feed", userId] });
    },
    [demo, queryClient, userId],
  );

  const loadSimilar = useCallback(
    async (post: FeedPost) => {
      if (demo) {
        const others = demoPosts.filter((p) => p.id !== post.id).slice(0, 8);
        setSimilarSeedId(post.id);
        setSimilarResults(others);
        return others;
      }
      const cards = await similarPosts(post.id, { k: 8 });
      const mapped = cardsToPosts(cards);
      setSimilarSeedId(post.id);
      setSimilarResults(mapped);
      return mapped;
    },
    [demo, demoPosts],
  );

  const clearSimilar = useCallback(() => {
    setSimilarResults(null);
    setSimilarSeedId(null);
  }, []);

  return {
    demo,
    userId,
    posts: remotePosts,
    discoverPosts: discoverPostsMapped,
    searchResults,
    similarResults,
    similarSeedId,
    whyById,
    feedLoading: !demo && feedQuery.isLoading,
    discoverLoading: !demo && discoverQuery.isLoading,
    feedError: !demo ? feedQuery.error : null,
    runSearch,
    recordFeedback,
    recordSave,
    publish,
    tune,
    fetchPair,
    preferPair,
    loadSimilar,
    clearSimilar,
  };
}
