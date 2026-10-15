import { CATEGORY_IDS, type FeedPost, type InterestCategoryId, type InterestProfile, type InterestVector } from './types';

export const CATEGORIES = [
  { id: 'cyberpunk', label: 'Cyberpunk', shortLabel: 'Cyberpunk', color: '#c3a7ff', keywords: ['cyberpunk','cyber','neon','synthwave','dystopia','futurism','science fiction','sci-fi','worldbuilding','speculative','night city'] },
  { id: 'ai', label: 'AI & machine learning', shortLabel: 'AI / ML', color: '#83e0c2', keywords: ['ai','artificial intelligence','machine learning','deep learning','llm','language model','neural','robotics','algorithm','gpu','generative','computer vision','deep tech'] },
  { id: 'space', label: 'Astrophysics & space', shortLabel: 'Space', color: '#84baff', keywords: ['astrophysics','space','astronomy','cosmos','nasa','exoplanet','black hole','telescope','galaxy','planet','physics','orbit'] },
  { id: 'culture', label: 'Indie culture', shortLabel: 'Culture', color: '#f2a17e', keywords: ['indie','music','indie pop','album','playlist','artist','culture','film','cinema','creative','typography','photography','design'] },
] as const;
export const INITIAL_PROFILE: InterestProfile = { prompt: 'Cyberpunk, machine learning & deep tech. A little space, no generic takes.', vector: { cyberpunk: 30, ai: 34, space: 22, culture: 14 }, excludedCategories: [] };
const HARD_NEGATIONS = new Set(['avoid','banish','exclude','no','never','not','skip']);
function escapeRegExp(value: string) { return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
function hasKeyword(text: string, keyword: string) {
  const words = keyword.split(/\s+/).map(escapeRegExp).join('\\s+');
  return new RegExp(`\\b${words}\\b`, 'i').test(text);
}
function appearsNegated(prompt: string, keyword: string) {
  const words = keyword.split(/\s+/).map(escapeRegExp).join('\\s+');
  const match = new RegExp(`\\b(avoid|banish|exclude|no|never|not|skip|less|fewer|stop showing)\\b(?:\\s+\\w+){0,4}\\s+${words}`, 'i').exec(prompt);
  if (!match) return { negated: false, hard: false };
  return { negated: true, hard: HARD_NEGATIONS.has(match[1].toLowerCase()) };
}
function normalizeVector(raw: Record<InterestCategoryId, number>): InterestVector {
  const safe = CATEGORY_IDS.map(id => Math.max(.025, raw[id]));
  const total = safe.reduce((sum, value) => sum + value, 0);
  const rounded = safe.map(value => Math.round((value / total) * 1000) / 10);
  rounded[0] = Math.round((rounded[0] + Math.round((100 - rounded.reduce((sum, value) => sum + value, 0)) * 10) / 10) * 10) / 10;
  return { cyberpunk: rounded[0], ai: rounded[1], space: rounded[2], culture: rounded[3] };
}
export function parseInterestPrompt(prompt: string): InterestProfile {
  const normalizedPrompt = prompt.trim(), lower = normalizedPrompt.toLowerCase();
  const raw = Object.fromEntries(CATEGORY_IDS.map(id => [id, .7])) as Record<InterestCategoryId, number>;
  const excludedCategories: InterestCategoryId[] = [];
  let hasKnownTerms = false;
  for (const category of CATEGORIES) {
    let positiveMatches = 0, negativeMatches = 0, hardNegative = false;
    for (const keyword of category.keywords) {
      if (!hasKeyword(lower, keyword)) continue;
      hasKnownTerms = true;
      const negation = appearsNegated(lower, keyword);
      if (negation.negated) { negativeMatches += 1; hardNegative ||= negation.hard; } else positiveMatches += 1;
    }
    raw[category.id] += positiveMatches * 1.15;
    raw[category.id] = Math.max(.025, raw[category.id] - negativeMatches * .9);
    if (hardNegative && negativeMatches > 0) { raw[category.id] = .025; excludedCategories.push(category.id); }
  }
  if (!hasKnownTerms) for (const id of CATEGORY_IDS) raw[id] = 1;
  return { prompt: normalizedPrompt || INITIAL_PROFILE.prompt, vector: normalizeVector(raw), excludedCategories };
}
export function adjustInterestVector(vector: InterestVector, category: InterestCategoryId, direction: 'up' | 'down'): InterestVector {
  const current = Object.fromEntries(CATEGORY_IDS.map(id => [id, Math.max(.1, vector[id])])) as Record<InterestCategoryId, number>;
  const nextTarget = Math.max(2.5, Math.min(80, current[category] + (direction === 'up' ? 7 : -7)));
  const otherTotal = CATEGORY_IDS.filter(id => id !== category).reduce((sum, id) => sum + current[id], 0);
  const next = { ...current, [category]: nextTarget }, remaining = 100 - nextTarget;
  for (const id of CATEGORY_IDS) if (id !== category) next[id] = current[id] / otherTotal * remaining;
  return normalizeVector(next);
}
export function classifyCategory(text: string): InterestCategoryId {
  const lower = text.toLowerCase(); let best: InterestCategoryId = 'ai', score = 0;
  for (const category of CATEGORIES) {
    const found = category.keywords.reduce((sum, keyword) => sum + (hasKeyword(lower, keyword) ? 1 : 0), 0);
    if (found > score) { score = found; best = category.id; }
  }
  return best;
}
export function scorePost(post: FeedPost, profile: InterestProfile) {
  if (profile.excludedCategories.includes(post.category)) return 0;
  const total = CATEGORY_IDS.reduce((sum, id) => sum + profile.vector[id], 0) || 100;
  const categoryShare = profile.vector[post.category] / total;
  const text = `${post.title ?? ''} ${post.body} ${post.tags.join(' ')}`.toLowerCase();
  const keywords = CATEGORIES.find(item => item.id === post.category)?.keywords ?? [];
  return Math.min(1, categoryShare + Math.min(.18, keywords.filter(word => hasKeyword(text, word)).length * .035));
}
export function rankPosts(posts: FeedPost[], profile: InterestProfile) {
  return posts.map(post => ({ post, score: scorePost(post, profile) })).filter(item => item.score >= .045).sort((a,b) => b.score-a.score).map(item => item.post);
}
export function explainPostMatch(post: FeedPost, profile: InterestProfile) {
  const category = CATEGORIES.find(item => item.id === post.category), share = Math.round(profile.vector[post.category]);
  const tag = post.tags.find(item => category?.keywords.some(keyword => item.toLowerCase().includes(keyword)));
  return tag ? `This matches your ${category?.label.toLowerCase()} signal (${share}%) through “${tag}”.` : `This landed in ${category?.label.toLowerCase()}, currently ${share}% of your Interest DNA.`;
}
