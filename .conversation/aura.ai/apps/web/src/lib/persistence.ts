import { DEMO_POSTS, DEMO_PROFILE, type FeedPost, type InterestProfile } from "@aura/shared";

const PROFILE_KEY = "aura:interest-profile:v1";
const POSTS_KEY = "aura:feed-posts:v1";

function readJson<T>(key: string, fallback: T): T {
  try {
    const value = window.localStorage.getItem(key);
    return value ? (JSON.parse(value) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function loadProfile(): InterestProfile {
  return readJson(PROFILE_KEY, DEMO_PROFILE);
}

export function saveProfile(profile: InterestProfile): void {
  window.localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
}

export function loadPosts(): FeedPost[] {
  return readJson(POSTS_KEY, DEMO_POSTS);
}

export function savePosts(posts: FeedPost[]): void {
  window.localStorage.setItem(POSTS_KEY, JSON.stringify(posts));
}
