import { useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent } from 'react';
import {
  ArrowDown, ArrowRight, ArrowUpRight, Bookmark, Check, Compass, Heart,
  House, Link as LinkIcon, MessageCircle, Plus, Search, Sparkles, ThumbsDown,
  Waves, X, FileText, PenLine, Code2, Image as ImageIcon, ExternalLink,
} from 'lucide-react';
import {
  adjustInterestVector, CATEGORIES, DEMO_POSTS, DEMO_PROFILE, categoriesMatch, discoverThemes,
  explainPostMatch, getEmbedPreview, interestProfileFromAura, matchPercent,
  mergeThemesIntoVector, normalizeVector, postSourceUrl, rankPosts, themeColor, themeKey, themeMeta,
  type AuraChatMessage, type AuraOption, type AuraTurn, type CategoryMeta,
  type FeedPost, type FeedbackDirection, type InterestCategoryId, type InterestProfile,
  type InterestVector,
} from '@workspace/aura-shared';
import { useRecommendationFeed } from '@/hooks/use-recommendation-feed';
import { shortUserId, shortUserLabel } from '@/lib/user-id';

const AURA_CHAT_KEY = 'aura:chat-complete:v1';
/** Matches the category step in adjustInterestVector. */
const AURA_POINT_STEP = 7;

type Section = 'feed' | 'discover' | 'saved';
type ComposerMode = 'short' | 'article' | 'embed';
type DraftPost = Omit<FeedPost, 'id' | 'publishedAt' | 'likes' | 'comments'>;
type AuraPointBurst = {
  id: number;
  themeId: InterestCategoryId;
  label: string;
  delta: number;
  color: string;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
};
const PROFILE_KEY = 'aura:interest-profile:v1';
const POSTS_KEY = 'aura:feed-posts:v1';
const SAVED_KEY = 'aura:saved:v1';
const SAVED_POSTS_KEY = 'aura:saved-posts:v1';

function categoryAccent(id: InterestCategoryId, _variant: 'current' | 'glass') {
  return themeColor(id);
}

function readLocal<T>(key: string, fallback: T): T {
  try {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) as T : fallback;
  } catch { return fallback; }
}
function Markdown({ source }: { source: string }) {
  const html = source
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>').replace(/^## (.+)$/gm, '<h2>$1</h2>').replace(/^# (.+)$/gm, '<h2>$1</h2>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/_(.+?)_/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>').replace(/\n/g, '<br />');
  return <div className="markdown-body" dangerouslySetInnerHTML={{ __html: html }} />;
}
/** Renormalize profile weights across themes that have real posts. */
function weightsForThemes(themes: CategoryMeta[], vector: InterestVector): InterestVector {
  if (!themes.length) return {};
  const raw: InterestVector = {};
  for (const theme of themes) {
    raw[theme.id] = Math.max(0.025, vector[theme.id] ?? 0.025);
  }
  return normalizeVector(raw);
}

function InterestPanel({ profile, themes, onEdit, variant, pointBurst }: {
  profile: InterestProfile;
  themes: CategoryMeta[];
  onEdit: () => void;
  variant: 'current' | 'glass';
  pointBurst?: AuraPointBurst | null;
}) {
  const radius = 48, circumference = 2 * Math.PI * radius;
  let offset = 0;
  const ring = themes;
  const display = useMemo(() => weightsForThemes(ring, profile.vector), [ring, profile.vector]);
  const burstActive = Boolean(pointBurst);
  const burstPlus = (pointBurst?.delta ?? 0) > 0;
  return <aside className={`interest-panel ${burstActive ? (burstPlus ? 'aura-burst-plus' : 'aura-burst-minus') : ''}`}>
    <div className="panel-heading"><div><span className="eyebrow">YOUR PROFILE</span><h2>Interest DNA</h2></div><button className="icon-button subtle-icon" aria-label="Edit interests" onClick={onEdit}><ArrowUpRight size={17}/></button></div>
    <div className={`dna-visual ${burstActive ? 'dna-pulse' : ''}`}>
      <svg className="dna-chart" viewBox="0 0 120 120" aria-label="Interest vector composition">
        <circle className="dna-track" cx="60" cy="60" r={radius} fill="none" strokeWidth="11"/>
        <g transform="rotate(-90 60 60)">{ring.map(category => { const segment = (display[category.id] ?? 0) / 100 * circumference, start = offset; offset += segment; return <circle key={category.id} cx="60" cy="60" r={radius} fill="none" stroke={categoryAccent(category.id, variant)} strokeWidth="11" strokeLinecap="round" strokeDasharray={`${Math.max(segment - 3,0)} ${circumference}`} strokeDashoffset={-start} className={`dna-segment ${pointBurst?.themeId === category.id ? 'dna-segment-hit' : ''}`}/>; })}</g>
      </svg>
      <div className="dna-center">
        <span className="dna-center-icon"><Sparkles size={14}/></span>
        {pointBurst
          ? <strong className={`dna-center-delta ${burstPlus ? 'plus' : 'minus'}`}>{burstPlus ? '+' : '−'}{Math.abs(pointBurst.delta)}</strong>
          : <strong>LIVE</strong>}
        <span>{pointBurst ? 'AURA' : 'VECTOR'}</span>
      </div>
      {pointBurst && (
        <span
          className={`aura-orbit-chip ${burstPlus ? 'plus' : 'minus'}`}
          style={{ '--burst-color': pointBurst.color } as CSSProperties}
          key={pointBurst.id}
        >
          {burstPlus ? '+' : '−'}{Math.abs(pointBurst.delta)} {pointBurst.label}
        </span>
      )}
    </div>
    <div className="interest-legend">{ring.length ? ring.map(category => {
      const hit = pointBurst?.themeId === category.id;
      return <div className={`interest-row ${hit ? (burstPlus ? 'row-hit-plus' : 'row-hit-minus') : ''}`} key={category.id}>
        <span className="interest-name"><i className="interest-dot" style={{ backgroundColor: categoryAccent(category.id, variant) }}/>{category.shortLabel}</span>
        <span className="interest-value">
          {Math.round(display[category.id] ?? 0)}%
          {hit && <em className={`aura-row-delta ${burstPlus ? 'plus' : 'minus'}`}>{burstPlus ? '+' : '−'}{Math.abs(pointBurst.delta)}</em>}
        </span>
      </div>;
    }) : <p className="vector-note">Themes appear once posts are in your feed.</p>}</div>
    <div className="interest-prompt"><span className="prompt-label"><Sparkles size={12}/> AURA LEARNED</span><p>“{profile.prompt}”</p><button className="text-action" onClick={onEdit}>Chat with Aura <ArrowUpRight size={13}/></button></div>
    <div className="vector-note"><span className="vector-pulse"/>Every resonate or banish updates this profile.</div>
  </aside>;
}
function PostCard({ post, profile, saved, onFeedback, onToggleSaved, variant, why, onSimilar }: {
  post: FeedPost; profile: InterestProfile; saved: boolean;
  variant: 'current' | 'glass';
  why?: string;
  onFeedback: (post: FeedPost, direction: FeedbackDirection, origin: DOMRect) => void;
  onToggleSaved: (post: FeedPost) => void;
  onSimilar?: (post: FeedPost) => void;
}) {
  const [showInsight, setShowInsight] = useState(false), [delta, setDelta] = useState(0), [signal, setSignal] = useState<FeedbackDirection | null>(null);
  const start = useRef<number | null>(null), category = themeMeta(post.category);
  const cardRef = useRef<HTMLElement | null>(null);
  const match = useMemo(() => matchPercent(post, profile), [post, profile]);
  const insight = useMemo(() => why || explainPostMatch(post, profile), [post, profile, why]);
  const sourceUrl = postSourceUrl(post);
  function emitFeedback(direction: FeedbackDirection) {
    const origin = cardRef.current?.getBoundingClientRect() ?? new DOMRect(window.innerWidth / 2, window.innerHeight / 2, 0, 0);
    setSignal(direction);
    onFeedback(post, direction, origin);
    window.setTimeout(() => setSignal(null), 1100);
  }
  function down(event: PointerEvent<HTMLElement>) {
    if (event.button !== 0 || (event.target as HTMLElement).closest('[data-no-swipe]')) return;
    start.current = event.clientX; event.currentTarget.setPointerCapture(event.pointerId); setSignal(null);
  }
  function move(event: PointerEvent<HTMLElement>) { if (start.current !== null) setDelta(Math.max(-140, Math.min(140, event.clientX - start.current))); }
  function up(event: PointerEvent<HTMLElement>) {
    if (start.current === null) return;
    const distance = event.clientX - start.current; start.current = null; setDelta(0);
    if (distance > 78) emitFeedback('resonate');
    if (distance < -78) emitFeedback('banish');
  }
  const categoryClass = category.id.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'general';
  return <article ref={cardRef} className={`post-card post-${post.kind} post-${categoryClass} signal-${signal ?? ''}`} style={{ transform: delta ? `translateX(${delta * .18}px) rotate(${delta * .012}deg)` : undefined }} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={() => { start.current = null; setDelta(0); }}>
    {signal && <div className={`signal-flash ${signal}`} aria-live="polite">{signal === 'resonate' ? <Check size={15}/> : <ThumbsDown size={15}/>} {signal === 'resonate' ? 'Resonated' : 'Banished'}</div>}
    {post.imageUrl ? (sourceUrl
      ? <a className="post-image" href={sourceUrl} target="_blank" rel="noopener noreferrer" data-no-swipe><img src={post.imageUrl} alt={post.imageAlt || post.title || 'Aura post image'} loading="lazy"/><div className="image-topline"><span className="category-chip" style={{ '--chip-color': categoryAccent(category.id, variant) } as CSSProperties}><i/>{category.shortLabel}</span><button type="button" className={`ai-badge ${showInsight ? 'active' : ''}`} data-no-swipe onClick={(event) => { event.preventDefault(); event.stopPropagation(); setShowInsight(!showInsight); }}><Sparkles size={12}/> Match insight</button></div></a>
      : <div className="post-image"><img src={post.imageUrl} alt={post.imageAlt || post.title || 'Aura post image'} loading="lazy"/><div className="image-topline"><span className="category-chip" style={{ '--chip-color': categoryAccent(category.id, variant) } as CSSProperties}><i/>{category.shortLabel}</span><button type="button" className={`ai-badge ${showInsight ? 'active' : ''}`} data-no-swipe onClick={() => setShowInsight(!showInsight)}><Sparkles size={12}/> Match insight</button></div></div>) :
      post.kind === 'image' ? <div className={`post-image art-${categoryClass}`} aria-label={post.imageAlt || post.title}><div className="image-topline"><span className="category-chip" style={{ '--chip-color': categoryAccent(category.id, variant) } as CSSProperties}><i/>{category.shortLabel}</span><button className={`ai-badge ${showInsight ? 'active' : ''}`} data-no-swipe onClick={() => setShowInsight(!showInsight)}><Sparkles size={12}/> Match insight</button></div><span className="art-orbit"/><span className="art-title">{post.category === 'space' ? 'FIELD NOTES / 04' : 'AFTER HOURS — 2049'}</span></div> : null}
    <div className="post-content"><div className="post-author-row"><div className="author-info"><span className="avatar" style={{ '--avatar-color': post.author.avatarColor } as CSSProperties}>{post.author.initials}</span><div className="author-copy"><span className="author-name">{post.author.name}{post.author.verified && <span className="verified-mark">✓</span>}</span><span className="author-meta">{post.author.handle} · {post.publishedAt}</span></div></div><button className="ai-badge compact-ai" onClick={() => setShowInsight(!showInsight)} data-no-swipe aria-expanded={showInsight}><Sparkles size={12}/> Why this?</button></div>
       {!post.imageUrl && post.kind !== 'image' && <div className="post-type-line"><span className="category-chip" style={{ '--chip-color': categoryAccent(category.id, variant) } as CSSProperties}><i/>{category.shortLabel}</span>{post.kind === 'embed' && post.platform && <span className="platform-label"><LinkIcon size={11}/>{post.platform}</span>}</div>}
      {post.title && (sourceUrl
        ? <h3 className="post-title"><a className="post-title-link" href={sourceUrl} target="_blank" rel="noopener noreferrer" data-no-swipe>{post.title}<ExternalLink size={13} className="post-title-external"/></a></h3>
        : <h3 className="post-title">{post.title}</h3>)}
      {post.kind === 'article' ? <div className="post-body" data-no-swipe><Markdown source={post.body}/></div> : <p className="post-body">{post.body}</p>}
        {post.kind === 'embed' && sourceUrl && (variant === 'glass' ?
          <div className="glass-embed-meta" data-no-swipe><span className="glass-source"><LinkIcon size={12}/>{post.platform || 'External link'} · source</span><a className="glass-open-original" href={sourceUrl} target="_blank" rel="noopener noreferrer">Open original <ExternalLink size={12}/></a></div> :
         <a className={`embed-preview embed-${post.platform?.toLowerCase() ?? 'link'}`} href={sourceUrl} target="_blank" rel="noreferrer" data-no-swipe><span className="embed-orbit"><ArrowUpRight size={15}/></span><span className="embed-copy"><strong>{post.platform || 'External link'}</strong><small>{sourceUrl.replace(/^https?:\/\//,'').replace(/\/$/,'')}</small></span><ExternalLink className="embed-arrow" size={14}/></a>)}
      {post.kind !== 'embed' && sourceUrl && <a className="post-open-source" href={sourceUrl} target="_blank" rel="noopener noreferrer" data-no-swipe>Open original <ExternalLink size={12}/></a>}
      <div className="post-meta-row">
        <span className="match-chip" title="Profile match"><Sparkles size={11}/>{match}% match</span>
        {post.tags.length > 0 && <div className="post-tags">{post.tags.slice(0,3).map(tag => <span key={tag}>#{tag.replace(/\s+/g,'')}</span>)}</div>}
      </div>
      {showInsight && <div className="insight-panel"><span className="insight-icon"><Sparkles size={13}/></span><p>{insight} <small>{why ? 'Recommendation explanation.' : 'Profile match · Interest DNA.'}</small></p></div>}
      <div className="post-footer"><div className="engagement"><span><Heart size={14}/>{post.likes.toLocaleString()}</span><span><MessageCircle size={14}/>{post.comments}</span>{onSimilar && <button className="text-action" data-no-swipe onClick={() => onSimilar(post)} style={{marginLeft:8}}><Sparkles size={12}/> More like this</button>}</div><div className="post-actions" data-no-swipe><button className={`save-button ${saved ? 'selected' : ''}`} onClick={() => onToggleSaved(post)} aria-label={saved ? 'Remove from collection' : 'Save to collection'}><Bookmark size={15} fill={saved ? 'currentColor' : 'none'}/></button><button className={`feedback-button resonate-button ${post.resonated ? 'selected' : ''}`} onClick={() => emitFeedback('resonate')} aria-label="Resonate with this post"><Heart size={14} fill={post.resonated ? 'currentColor' : 'none'}/><span>Resonate</span></button><button className={`feedback-button banish-button ${post.banished ? 'selected' : ''}`} onClick={() => emitFeedback('banish')} aria-label="Banish this post"><ThumbsDown size={14} fill={post.banished ? 'currentColor' : 'none'}/></button></div></div>
    </div>
  </article>;
}
function AuraChatModal({
  themes,
  variant,
  onClose,
  onApply,
  talkToAura,
}: {
  themes: CategoryMeta[];
  variant: 'current' | 'glass';
  onClose: () => void;
  onApply: (profile: InterestProfile, turn: AuraTurn, messages: AuraChatMessage[]) => void | Promise<void>;
  talkToAura: (messages: AuraChatMessage[], knownThemes: string[], apply?: boolean) => Promise<AuraTurn>;
}) {
  const knownThemes = useMemo(() => themes.map((t) => t.label || t.id), [themes]);
  const [messages, setMessages] = useState<AuraChatMessage[]>([]);
  const [turn, setTurn] = useState<AuraTurn | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [applying, setApplying] = useState(false);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const preview = useMemo(() => {
    if (!turn?.profile) return null;
    return interestProfileFromAura(turn.profile, themes.map((t) => t.id));
  }, [turn, themes]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', handler);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    void talkToAura([], knownThemes)
      .then((opening) => {
        if (cancelled) return;
        setTurn(opening);
        setMessages([{ role: 'assistant', content: opening.message }]);
      })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [knownThemes, talkToAura]);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, turn, busy]);

  async function send(text: string) {
    const content = text.trim();
    if (!content || busy || applying) return;
    const nextMessages: AuraChatMessage[] = [...messages, { role: 'user', content }];
    setMessages(nextMessages);
    setDraft('');
    setBusy(true);
    try {
      const next = await talkToAura(nextMessages, knownThemes);
      setTurn(next);
      setMessages((current) => [...current, { role: 'assistant', content: next.message }]);
    } finally {
      setBusy(false);
    }
  }

  async function pickOption(option: AuraOption) {
    if (option.id === 'apply' && turn?.ready && turn.profile) {
      setApplying(true);
      try {
        await onApply(
          preview ?? interestProfileFromAura(turn.profile, themes.map((t) => t.id)),
          turn,
          messages,
        );
      } finally {
        setApplying(false);
      }
      return;
    }
    await send(option.label);
  }

  async function applyProfile() {
    if (!turn?.profile || !preview) return;
    setApplying(true);
    try {
      await onApply(preview, turn, messages);
    } finally {
      setApplying(false);
    }
  }

  const previewThemes = themes.length ? themes : CATEGORIES.map((item) => themeMeta(item.id));
  const topThemes = preview
    ? previewThemes
        .filter((c) => (preview.vector[c.id] ?? 0) > 0)
        .sort((a, b) => (preview.vector[b.id] ?? 0) - (preview.vector[a.id] ?? 0))
        .slice(0, 3)
    : [];

  return <div className="modal-backdrop aura-chat-backdrop" role="presentation" onMouseDown={event => event.target === event.currentTarget && onClose()}>
    <section className="modal-card aura-chat-modal" role="dialog" aria-modal="true" aria-labelledby="aura-chat-title">
      <div className="modal-header aura-chat-header">
        <div className="modal-title-icon"><Sparkles size={18}/></div>
        <div><span className="eyebrow">MEET AURA</span><h2 id="aura-chat-title">Let’s find your signal.</h2></div>
        <button className="icon-button modal-close" aria-label="Close" onClick={onClose}><X size={18}/></button>
      </div>

      <div className="aura-chat-body">
        <div className="aura-chat-thread" ref={threadRef} aria-live="polite">
          {messages.map((msg, index) => (
            <div key={`${msg.role}-${index}`} className={`aura-bubble ${msg.role}`}>
              {msg.role === 'assistant' && <span className="aura-bubble-label">Aura</span>}
              <p>{msg.content}</p>
            </div>
          ))}
          {busy && (
            <div className="aura-bubble assistant aura-thinking" aria-busy="true" aria-label="Aura is thinking">
              <span className="aura-bubble-label">Aura</span>
              <div className="aura-thinking-row">
                <span className="aura-thinking-dots" aria-hidden="true"><i/><i/><i/></span>
                <span className="aura-thinking-label">Thinking</span>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="aura-chat-dock">
        {!!turn?.suggested_themes?.length && !turn.ready && (
          <div className="aura-theme-row">
            <span>Themes</span>
            {turn.suggested_themes.slice(0, 4).map((theme) => (
              <button key={theme} type="button" className="suggestion-chip" disabled={busy || applying} onClick={() => void send(`More ${theme}`)}>+ {theme}</button>
            ))}
          </div>
        )}
        {!!turn?.options?.length && !busy && (
          <div className="aura-options" role="group" aria-label="Quick replies">
            {turn.options.map((option) => (
              <button key={option.id} type="button" className="aura-option-chip" disabled={busy || applying} onClick={() => void pickOption(option)}>{option.label}</button>
            ))}
          </div>
        )}
        {preview && turn?.ready && (
          <div className="aura-profile-preview">
            <div className="aura-profile-preview-head">
              <span className="field-label">READY TO APPLY</span>
              <span className="preview-caption">from your chat</span>
            </div>
            <p className="aura-profile-summary">“{preview.prompt}”</p>
            {!!topThemes.length && (
              <div className="aura-profile-chips">
                {topThemes.map((category) => (
                  <span key={category.id} className="aura-profile-chip">
                    <i style={{ background: categoryAccent(category.id, variant) }}/>
                    {category.shortLabel}
                    <b>{Math.round(preview.vector[category.id] ?? 0)}</b>
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
        <form className="aura-chat-compose" onSubmit={(event) => { event.preventDefault(); void send(draft); }}>
          <label className="sr-only" htmlFor="aura-chat-input">Message Aura</label>
          <input id="aura-chat-input" className="aura-chat-input" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Type a reply, or tap an option…" disabled={busy || applying} autoFocus/>
          <button type="submit" className="button button-secondary" disabled={busy || applying || !draft.trim()}>Send</button>
        </form>
        <div className="modal-actions aura-chat-actions">
          <button className="button button-quiet" type="button" onClick={onClose}>Maybe later</button>
          <button className="button button-primary" type="button" disabled={!turn?.ready || !preview || applying} onClick={() => void applyProfile()}>
            <Check size={15}/> {applying ? 'Applying…' : 'Apply to my feed'}
          </button>
        </div>
      </div>
    </section>
  </div>;
}
function PairModal({ left, right, onClose, onPick, variant }: {
  left: FeedPost; right: FeedPost; variant: 'current' | 'glass';
  onClose: () => void;
  onPick: (winner: FeedPost, loser: FeedPost) => void;
}) {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);
  return <div className="modal-backdrop" role="presentation" onMouseDown={event => event.target === event.currentTarget && onClose()}>
    <section className="modal-card interest-modal" role="dialog" aria-modal="true" aria-labelledby="pair-modal-title" style={{ maxWidth: 720 }}>
      <div className="modal-header"><div className="modal-title-icon"><Waves size={18}/></div><div><span className="eyebrow">PAIRWISE SIGNAL</span><h2 id="pair-modal-title">Which feels more like you?</h2></div><button className="icon-button modal-close" aria-label="Close" onClick={onClose}><X size={18}/></button></div>
      <p className="modal-intro">Pick one. Aura uses the contrast to sharpen your feed — no wrong answer.</p>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        {[left, right].map((post, index) => {
          const other = index === 0 ? right : left;
          const category = themeMeta(post.category);
          return <button key={post.id} type="button" className="button button-secondary" style={{ display: 'block', textAlign: 'left', padding: 14, height: '100%' }} onClick={() => onPick(post, other)}>
            <span className="category-chip" style={{ '--chip-color': categoryAccent(category.id, variant) } as CSSProperties}><i/>{category.shortLabel}</span>
            <strong style={{ display: 'block', marginTop: 8 }}>{post.title || post.body.slice(0, 80)}</strong>
            <small style={{ display: 'block', marginTop: 6, opacity: 0.75 }}>{post.author.name}</small>
          </button>;
        })}
      </div>
      <div className="modal-actions"><button className="button button-quiet" onClick={onClose}>Skip</button></div>
    </section>
  </div>;
}
function ComposerModal({ onClose, onPublish, variant, live }: { onClose: () => void; onPublish: (post: DraftPost) => void; variant: 'current' | 'glass'; live?: boolean }) {
  const [mode,setMode] = useState<ComposerMode>('short'), [category,setCategory] = useState<InterestCategoryId>('ai'), [title,setTitle] = useState(''), [body,setBody] = useState(''), [url,setUrl] = useState(''), [previewMode,setPreviewMode] = useState<'write'|'preview'>('write');
  const preview = getEmbedPreview(url);
  useEffect(() => { const handler = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); }; window.addEventListener('keydown',handler); return () => window.removeEventListener('keydown',handler); }, [onClose]);
  const canPublish = mode === 'short' ? !!body.trim() : mode === 'article' ? !!(body.trim() && title.trim()) : !!preview && (variant !== 'glass' || !!body.trim());
  function publish() {
    if (!canPublish) return;
    const common = { category, author: { name:'Alex Morgan',handle:'@alexm',initials:'AM',avatarColor:'#829178' }, tags:[themeMeta(category).shortLabel], resonated:false, banished:false };
    const post: DraftPost = mode === 'embed' ? { ...common,kind:'embed',title:title.trim() || preview!.headline,body:body.trim() || 'Found this and thought it belonged in the conversation.',platform:preview!.platform === 'Link' ? undefined : preview!.platform,embedUrl:preview!.url } : { ...common,kind:mode,title:mode === 'article' ? title.trim() : undefined,body:body.trim() };
    onPublish(post);
  }
  const modes: { id: ComposerMode; label: string; Icon: typeof PenLine }[] = [{id:'short',label:'Quick thought',Icon:PenLine},{id:'article',label:'Long-form',Icon:FileText},{id:'embed',label:'Link embed',Icon:LinkIcon}];
  return <div className="modal-backdrop" role="presentation" onMouseDown={event => event.target === event.currentTarget && onClose()}><section className="modal-card composer-modal" role="dialog" aria-modal="true" aria-labelledby="composer-modal-title">
    <div className="modal-header composer-heading"><div className="modal-title-icon"><PenLine size={18}/></div><div><span className="eyebrow">THE OMNIBOX</span><h2 id="composer-modal-title">Put something out there.</h2></div><button className="icon-button modal-close" aria-label="Close" onClick={onClose}><X size={18}/></button></div>
    <div className="composer-tabs" role="tablist" aria-label="Post format">{modes.map(({id,label,Icon}) => <button key={id} role="tab" aria-selected={mode===id} className={`composer-tab ${mode===id?'active':''}`} onClick={() => setMode(id)}><Icon size={15}/>{label}</button>)}</div>
    <div className="composer-form"><div className="composer-category"><label className="field-label" htmlFor="post-category">FILE UNDER</label><select id="post-category" value={category} onChange={event => setCategory(event.target.value as InterestCategoryId)}>{CATEGORIES.map(item => <option value={item.id} key={item.id}>{item.label}</option>)}</select></div>
      {mode === 'short' && <><label className="field-label" htmlFor="quick-thought">YOUR THOUGHT <span>{body.length}/280</span></label><textarea id="quick-thought" value={body} onChange={event => setBody(event.target.value)} placeholder="A small idea worth passing along..." maxLength={280} rows={5} autoFocus/></>}
      {mode === 'article' && <><label className="field-label" htmlFor="article-title">TITLE</label><input id="article-title" value={title} onChange={event => setTitle(event.target.value)} placeholder="Give the idea a name"/><div className="editor-toolbar"><span><Code2 size={13}/> Markdown supported</span><div className="segmented-toggle"><button className={previewMode==='write'?'selected':''} onClick={() => setPreviewMode('write')}>Write</button><button className={previewMode==='preview'?'selected':''} onClick={() => setPreviewMode('preview')}>Preview</button></div></div>{previewMode==='write' ? <textarea className="article-editor" value={body} onChange={event => setBody(event.target.value)} placeholder={'Start with a point of view...\n\nUse **bold**, _italics_, links, or # headings.'} rows={9} autoFocus/> : <div className="markdown-preview">{body ? <Markdown source={body}/> : <p className="empty-preview">Your formatted article preview will appear here.</p>}</div>}</>}
       {mode === 'embed' && <><label className="field-label" htmlFor="embed-url">LINK URL</label><div className="input-with-icon"><LinkIcon size={16}/><input id="embed-url" type="url" value={url} onChange={event => setUrl(event.target.value)} placeholder="https://substack.com, x.com, or reddit.com" autoFocus/></div>{variant === 'glass' && <><label className="field-label glass-embed-title-label" htmlFor="embed-title">POST TITLE <span>OPTIONAL</span></label><input id="embed-title" value={title} onChange={event => setTitle(event.target.value)} placeholder="Add your own title"/></>}{preview ? <div className={`embed-live-preview ${variant === 'glass' ? 'glass-url-preview' : ''}`}><div className="embed-live-art">{preview.platform==='Substack'?<FileText size={21}/>:preview.platform==='Reddit'?<Sparkles size={21}/>:<ArrowUpRight size={21}/>}</div><div className="embed-live-copy"><span>{variant === 'glass' ? `URL DETAILS · ${preview.platform} (INFERRED)` : `${preview.platform} · ${preview.author}`}</span><strong>{title.trim() || preview.headline}</strong><small>{preview.hostname}</small></div>{variant !== 'glass' && <Check className="preview-check" size={16}/>}</div> : <div className="embed-empty-preview"><ImageIcon size={17}/>{variant === 'glass' ? 'Host and platform will be parsed from the URL only.' : 'A link card preview appears when you paste a valid URL.'}</div>}<label className={`field-label caption-label ${variant === 'glass' ? 'glass-post-text-label' : ''}`} htmlFor="embed-caption">{variant === 'glass' ? 'YOUR POST TEXT / EXCERPT' : 'ADD A THOUGHT'} <span>{variant === 'glass' ? 'REQUIRED' : 'OPTIONAL'}</span></label><textarea id="embed-caption" value={body} onChange={event => setBody(event.target.value)} placeholder={variant === 'glass' ? 'Write the context, excerpt, or point of view you want people to read.' : 'Why is this worth a look?'} rows={variant === 'glass' ? 5 : 3}/><p className="local-note">{variant === 'glass' ? 'Aura reads the address only. No external page content or metadata is fetched.' : 'Platform and link details are inferred from the URL only. No OpenGraph or OEmbed data is fetched.'}</p></>}
    </div><div className="composer-footer"><span><Sparkles size={13}/> {live ? 'Publishing indexes your post for recommendations.' : 'Your post will be added to this local demo feed.'}</span><button className="button button-primary" onClick={publish} disabled={!canPublish}>Publish <ArrowUpRight size={15}/></button></div>
  </section></div>;
}
export function AuraFeed({ variant = 'current' }: { variant?: 'current' | 'glass' }) {
  const [profile,setProfile] = useState<InterestProfile>(() => readLocal(PROFILE_KEY,DEMO_PROFILE));
  const [demoPosts,setDemoPosts] = useState<FeedPost[]>(() => readLocal(POSTS_KEY,DEMO_POSTS));
  const [savedIds,setSavedIds] = useState<string[]>(() => readLocal(SAVED_KEY,[]));
  const [savedPosts,setSavedPosts] = useState<Record<string, FeedPost>>(() => readLocal(SAVED_POSTS_KEY,{}));
  const [section,setSection] = useState<Section>('feed'), [activeCategory,setActiveCategory] = useState('all'), [search,setSearch] = useState('');
  const [searchOpen,setSearchOpen] = useState(false), [interestOpen,setInterestOpen] = useState(false), [composerOpen,setComposerOpen] = useState(false), [profilePopoverOpen,setProfilePopoverOpen] = useState(false), [toast,setToast] = useState('');
  const [pairOpen, setPairOpen] = useState(false);
  const [pairPosts, setPairPosts] = useState<[FeedPost, FeedPost] | null>(null);
  const [pointBurst, setPointBurst] = useState<AuraPointBurst | null>(null);
  const [flyBursts, setFlyBursts] = useState<AuraPointBurst[]>([]);
  const [navHit, setNavHit] = useState<'plus' | 'minus' | null>(null);
  const profilePopoverRef = useRef<HTMLDivElement | null>(null);
  const profileNavRef = useRef<HTMLButtonElement | null>(null);
  const toastTimer = useRef<number | undefined>(undefined);
  const searchTimer = useRef<number | undefined>(undefined);
  const burstTimer = useRef<number | undefined>(undefined);
  const navHitTimer = useRef<number | undefined>(undefined);
  const live = useRecommendationFeed(demoPosts);
  useEffect(() => {
    if (localStorage.getItem(AURA_CHAT_KEY)) return;
    setInterestOpen(true);
  }, []);
  function spawnAuraPoints(
    themeId: InterestCategoryId,
    direction: 'up' | 'down',
    origin?: DOMRect | null,
  ) {
    const meta = themeMeta(themeId);
    const from = origin ?? new DOMRect(window.innerWidth * 0.45, window.innerHeight * 0.55, 0, 0);
    const nav = profileNavRef.current?.getBoundingClientRect()
      ?? new DOMRect(window.innerWidth * 0.5, 38, 0, 0);
    const burst: AuraPointBurst = {
      id: Date.now() + Math.floor(Math.random() * 1000),
      themeId,
      label: meta.shortLabel,
      delta: direction === 'up' ? AURA_POINT_STEP : -AURA_POINT_STEP,
      color: categoryAccent(themeId, variant),
      fromX: from.left + from.width / 2,
      fromY: from.top + from.height / 2,
      toX: nav.left + nav.width / 2,
      toY: nav.top + nav.height / 2,
    };
    setFlyBursts((current) => [...current.slice(-3), burst]);
    if (burstTimer.current) window.clearTimeout(burstTimer.current);
    if (navHitTimer.current) window.clearTimeout(navHitTimer.current);
    // Land on the navbar profile control, then pulse Interest DNA.
    burstTimer.current = window.setTimeout(() => {
      setFlyBursts((current) => current.filter((item) => item.id !== burst.id));
      setPointBurst(burst);
      setNavHit(direction === 'up' ? 'plus' : 'minus');
      navHitTimer.current = window.setTimeout(() => {
        setPointBurst((current) => (current?.id === burst.id ? null : current));
        setNavHit(null);
      }, 900);
    }, 780);
  }
  const posts = live.demo ? demoPosts : live.posts;
  const themeSourcePosts = useMemo(() => {
    const byId = new Map<string, FeedPost>();
    for (const post of [...posts, ...live.discoverPosts, ...Object.values(savedPosts)]) {
      byId.set(post.id, post);
    }
    return [...byId.values()];
  }, [posts, live.discoverPosts, savedPosts]);
  /** Posts in the current section before signal filter — chips must come from this set. */
  const sectionPool = useMemo(() => {
    if (live.similarResults && live.similarResults.length) return live.similarResults;
    if (!live.demo && search.trim() && live.searchResults) return live.searchResults;
    if (section === 'saved') {
      return savedIds
        .map((id) => savedPosts[id] ?? posts.find((post) => post.id === id) ?? live.discoverPosts.find((post) => post.id === id))
        .filter((post): post is FeedPost => Boolean(post));
    }
    if (section === 'discover') return live.demo ? posts : live.discoverPosts;
    return posts;
  }, [live.similarResults, live.demo, live.searchResults, live.discoverPosts, search, section, savedIds, savedPosts, posts]);
  // DNA / Aura chat: all loaded content. Filter chips: only themes present in this section.
  const themes = useMemo(
    () => discoverThemes(themeSourcePosts, profile.vector, 10),
    [themeSourcePosts, profile.vector],
  );
  const filterThemes = useMemo(
    () => discoverThemes(sectionPool, profile.vector, 10),
    [sectionPool, profile.vector],
  );
  useEffect(() => {
    if (activeCategory === 'all') return;
    if (!filterThemes.some((theme) => categoriesMatch(theme.id, activeCategory))) {
      setActiveCategory('all');
    }
  }, [activeCategory, filterThemes]);
  useEffect(() => {
    if (live.demo) return;
    const ids = themes.map((item) => item.id);
    setProfile((current) => {
      const merged = mergeThemesIntoVector(current.vector, ids);
      if (Object.keys(merged).length === Object.keys(current.vector).length
        && Object.keys(merged).every((key) => Math.abs((merged[key] ?? 0) - (current.vector[key] ?? 0)) < 0.05)) {
        return current;
      }
      return { ...current, vector: merged };
    });
  }, [live.demo, themes]);
  useEffect(() => {
    if (!profilePopoverOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') setProfilePopoverOpen(false); };
    const closeOnOutside = (event: globalThis.PointerEvent) => {
      if (event.target instanceof Node && !profilePopoverRef.current?.contains(event.target) && !(event.target as Element).closest('.glass-profile-trigger')) setProfilePopoverOpen(false);
    };
    document.addEventListener('keydown', closeOnEscape);
    document.addEventListener('pointerdown', closeOnOutside);
    return () => { document.removeEventListener('keydown', closeOnEscape); document.removeEventListener('pointerdown', closeOnOutside); };
  }, [profilePopoverOpen]);
  useEffect(() => { localStorage.setItem(PROFILE_KEY,JSON.stringify(profile)); },[profile]);
  useEffect(() => { if (live.demo) localStorage.setItem(POSTS_KEY,JSON.stringify(demoPosts)); },[demoPosts, live.demo]);
  useEffect(() => {
    if (live.demo) return;
    if (searchTimer.current) window.clearTimeout(searchTimer.current);
    searchTimer.current = window.setTimeout(() => { void live.runSearch(search); }, 350);
    return () => { if (searchTimer.current) window.clearTimeout(searchTimer.current); };
  }, [search, live.demo, live.runSearch]);
  const visiblePosts = useMemo(() => {
    let result = rankPosts(sectionPool, profile);
    if (activeCategory !== 'all') {
      result = result.filter((post) => categoriesMatch(post.category, activeCategory));
    }
    if (live.demo && search.trim()) {
      const needle = search.trim().toLowerCase();
      result = result.filter(post => `${post.title ?? ''} ${post.body} ${post.author.name} ${post.tags.join(' ')}`.toLowerCase().includes(needle));
    }
    return result;
  }, [activeCategory, profile, sectionPool, search, live.demo]);
  function notify(message: string) { setToast(message); if (toastTimer.current) window.clearTimeout(toastTimer.current); toastTimer.current=window.setTimeout(() => setToast(''),2200); }
  function feedback(post: FeedPost, direction: FeedbackDirection, origin: DOMRect) {
    if (live.demo) {
      setDemoPosts(current => current.map(item => item.id !== post.id ? item : direction === 'resonate' ? { ...item,resonated:!item.resonated,banished:false,likes:item.likes+(item.resonated?-1:1) } : { ...item,banished:!item.banished,resonated:false }));
    } else {
      void live.recordFeedback(post, direction);
    }
    const vectorDir = direction === 'resonate' ? 'up' : 'down';
    setProfile(current => ({ ...current,vector:adjustInterestVector(current.vector,post.category,vectorDir) }));
    spawnAuraPoints(post.category, vectorDir, origin);
    const label=themeMeta(post.category).shortLabel; notify(direction==='resonate'?`+${AURA_POINT_STEP} Aura · more ${label}`:`−${AURA_POINT_STEP} Aura · less ${label}`);
  }
  function toggleSaved(post: FeedPost) {
    const was=savedIds.includes(post.id), next=was?savedIds.filter(id=>id!==post.id):[...savedIds,post.id];
    setSavedIds(next); localStorage.setItem(SAVED_KEY,JSON.stringify(next));
    setSavedPosts((current) => {
      const updated = { ...current };
      if (was) delete updated[post.id];
      else updated[post.id] = post;
      localStorage.setItem(SAVED_POSTS_KEY, JSON.stringify(updated));
      return updated;
    });
    if (!was) void live.recordSave(post, true);
    notify(was?'Removed from your collection':'Saved to your collection');
  }
  async function addPost(draft: DraftPost) {
    if (live.demo) {
      const next=[{...draft,id:`local-${Date.now()}`,publishedAt:'just now',likes:0,comments:0},...demoPosts];
      setDemoPosts(next);
      setSection('feed');setActiveCategory('all');setComposerOpen(false);notify('Your post is in the feed');
      return;
    }
    try {
      await live.publish(draft);
      setSection('feed');setActiveCategory('all');setComposerOpen(false);
      notify('Published — indexing for recommendations…');
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Publish failed');
    }
  }
  function chooseSection(next: Section) {
    live.clearSimilar();
    setSection(next);setActiveCategory('all');setSearch('');
  }
  async function openPair() {
    try {
      const pair = await live.fetchPair();
      if (pair.length < 2) { notify('Need more embedded posts for a pair'); return; }
      setPairPosts([pair[0], pair[1]]);
      setPairOpen(true);
    } catch { notify('Could not load a pair'); }
  }
  async function pickPair(winner: FeedPost, loser: FeedPost) {
    setPairOpen(false); setPairPosts(null);
    await live.preferPair(winner, loser);
    setProfile(current => ({ ...current, vector: adjustInterestVector(current.vector, winner.category, 'up') }));
    const nav = profileNavRef.current?.getBoundingClientRect() ?? null;
    spawnAuraPoints(winner.category, 'up', nav);
    notify(`+${AURA_POINT_STEP} Aura · preferred ${themeMeta(winner.category).shortLabel}`);
  }
  async function showSimilar(post: FeedPost) {
    try {
      await live.loadSimilar(post);
      setSection('feed');
      notify('Showing more like this');
    } catch { notify('Similar lookup failed'); }
  }
  function copyUserId() {
    if (live.demo) { notify('Demo mode — no remote user id'); return; }
    void navigator.clipboard?.writeText(live.userId);
    notify(`User id ${shortUserId(live.userId)} copied`);
  }
  const sectionTitle = live.similarResults
    ? 'More like this'
    : section==='saved'?'Your collection':section==='discover'?'Explore the signal':'For you';
  const avatarLabel = live.demo ? 'AM' : shortUserLabel(live.userId);
  return <div className={`aura-app ${variant === 'glass' ? 'aura-glass' : 'aura-current'}`}>
    <header className="topbar"><a className="brand" href="#" aria-label="Aura home" onClick={event=>{event.preventDefault();chooseSection('feed');}}><span className="brand-mark"><span/><i/></span><span className="brand-name">aura<span>.</span></span></a>
      {variant === 'glass' ? <button ref={profileNavRef} className={`interest-prompt-button glass-profile-trigger ${navHit ? `profile-nav-hit-${navHit}` : ''}`} aria-label="Open Interest DNA profile" aria-haspopup="dialog" aria-expanded={profilePopoverOpen} aria-controls="glass-profile-popover" onClick={()=>setProfilePopoverOpen(open=>!open)}><span className="prompt-spark"><Sparkles size={14}/></span><span className="prompt-button-copy"><small>YOUR PROFILE</small><strong>Interest DNA · {themes.length} themes</strong></span><span className="prompt-edit">{profilePopoverOpen ? 'CLOSE' : 'VIEW'} <ArrowDown size={11}/></span></button> :
      <button ref={profileNavRef} className={`interest-prompt-button ${navHit ? `profile-nav-hit-${navHit}` : ''}`} onClick={()=>setInterestOpen(true)}><span className="prompt-spark"><Sparkles size={14}/></span><span className="prompt-button-copy"><small>CHAT WITH AURA</small><strong>{profile.prompt}</strong></span><span className="prompt-edit">TUNE <ArrowRight size={11}/></span></button>}
      <div className="topbar-actions"><button className={`icon-button top-search ${searchOpen?'active':''}`} aria-label="Search the feed" onClick={()=>setSearchOpen(open=>!open)}><Search size={18}/></button><button className="icon-button notification-button" aria-label="Open pairwise preference" title="Pairwise pick" onClick={()=>void openPair()}><Waves size={18}/></button><button className="button button-primary create-button" onClick={()=>setComposerOpen(true)}><Plus size={16} strokeWidth={2.5}/><span>Create</span></button><button className="user-avatar" aria-label={live.demo ? 'Demo profile' : `Copy user id ${live.userId}`} title={live.demo ? 'Demo user' : live.userId} onClick={copyUserId}>{avatarLabel}</button></div>
    </header>
    {variant === 'glass' && profilePopoverOpen && <div className="glass-profile-popover" id="glass-profile-popover" ref={profilePopoverRef} role="dialog" aria-label="Interest DNA profile"><InterestPanel profile={profile} themes={themes} variant="glass" pointBurst={pointBurst} onEdit={()=>{setProfilePopoverOpen(false);setInterestOpen(true);}}/></div>}
    {searchOpen && <div className="search-bar"><Search size={16}/><input autoFocus value={search} onChange={event=>setSearch(event.target.value)} placeholder="Search ideas, people, or topics..." aria-label="Search ideas, people, or topics"/><button onClick={()=>{setSearch('');setSearchOpen(false);}} aria-label="Close search">×</button></div>}
    <div className="workspace"><aside className="left-rail"><span className="eyebrow rail-label">YOUR SPACE</span><nav className="main-nav" aria-label="Main navigation">
      <button className={section==='feed'?'active':''} onClick={()=>chooseSection('feed')}><House size={17}/><span>For you</span>{section==='feed'&&<i/>}</button><button className={section==='discover'?'active':''} onClick={()=>chooseSection('discover')}><Compass size={17}/><span>Discover</span>{section==='discover'&&<i/>}</button><button className={section==='saved'?'active':''} onClick={()=>chooseSection('saved')}><Bookmark size={17}/><span>Collection</span>{section==='saved'&&<i/>}</button></nav>
      <div className="rail-divider"/><div className="rail-section-heading"><span className="eyebrow">YOUR INTERESTS</span><button className="mini-edit" onClick={()=>setInterestOpen(true)} aria-label="Chat with Aura">+</button></div><div className="rail-categories">{filterThemes.map(category=><button className={`rail-category ${categoriesMatch(activeCategory, category.id)?'selected':''} ${pointBurst?.themeId===category.id ? ((pointBurst.delta>0)?'rail-hit-plus':'rail-hit-minus') : ''}`} key={themeKey(category.id)} onClick={()=>setActiveCategory(categoriesMatch(activeCategory, category.id)?'all':category.id)}><i style={{backgroundColor:categoryAccent(category.id, variant)}}/><span>{category.shortLabel}</span><small>{Math.round(profile.vector[category.id] ?? 0)}</small></button>)}</div>
      <button className="rail-create-card" onClick={()=>setComposerOpen(true)}><span className="rail-create-icon"><Plus size={16}/></span><strong>Make something</strong><small>A thought, a story, a link.</small></button><div className="rail-footer"><span className="rail-status-dot"/> A quieter corner of the internet.</div></aside>
      <main className="feed-main"><div className="feed-topline"><div className="feed-heading"><span className="eyebrow"><span className="live-dot"/> {live.similarResults ? 'SIMILARITY' : section==='discover' ? 'DISCOVER' : 'PERSONALIZED FOR YOU'}</span><h1>{sectionTitle}<span>.</span></h1><p>{live.similarResults ? <button className="text-action" onClick={() => live.clearSimilar()}>Clear similar · back to feed</button> : section==='saved'?'The posts you wanted to keep close.':section==='discover'?'Popular and recent posts across the corpus.':'A little less noise. A lot more you.'}</p></div><div className="feed-toolbar"><button className="filter-button" onClick={()=>setInterestOpen(true)}><Waves size={14}/><span>Chat with Aura</span><ArrowDown size={12}/></button><span className="feed-count"><b>{String(visiblePosts.length).padStart(2,'0')}</b> posts</span></div></div>
        <div className="feed-filter-row"><button className={`filter-chip ${activeCategory==='all'?'active':''}`} onClick={()=>setActiveCategory('all')}>All signals</button>{filterThemes.map(category=><button className={`filter-chip ${categoriesMatch(activeCategory, category.id)?'active':''}`} key={themeKey(category.id)} onClick={()=>setActiveCategory(categoriesMatch(activeCategory, category.id)?'all':category.id)}><i style={{backgroundColor:categoryAccent(category.id, variant)}}/>{category.shortLabel}</button>)}</div>
         {(section==='feed' && live.feedLoading) || (section==='discover' && live.discoverLoading) ? <div className="empty-state"><span className="empty-state-icon"><Sparkles size={22}/></span><h2>{section==='discover'?'Scanning the corpus…':'Tuning your feed…'}</h2><p>Loading recommendations.</p></div> : visiblePosts.length ? <div className="masonry-feed">{visiblePosts.map(post=><PostCard key={post.id} post={post} profile={profile} variant={variant} why={live.whyById[post.id]} onFeedback={feedback} saved={savedIds.includes(post.id)} onToggleSaved={toggleSaved} onSimilar={showSimilar}/>)}{section!=='saved'&&!live.similarResults&&<button className="feed-end-card" onClick={()=>chooseSection('discover')}><span className="end-card-icon"><Sparkles size={16}/></span><span><strong>Keep following your curiosity.</strong><small>Explore more posts in your orbit.</small></span><ArrowRight size={16}/></button>}</div> : <div className="empty-state"><span className="empty-state-icon"><Bookmark size={22}/></span><h2>{section==='saved'?'Nothing saved yet.': live.feedError ? 'Could not reach the recommendation API.' : 'No posts in this signal.'}</h2><p>{section==='saved'?'Save a post to keep it in your collection.': live.feedError ? 'Start scraper serve + api-server, or set VITE_USE_DEMO=1.' : 'Chat with Aura to reshape your signal.'}</p><button className="button button-secondary" onClick={()=>section==='saved'?chooseSection('feed'):setInterestOpen(true)}>{section==='saved'?'Back to your feed':'Chat with Aura'}</button></div>}
         {variant === 'current' && <div className="mobile-interest-card"><InterestPanel profile={profile} themes={themes} variant={variant} pointBurst={pointBurst} onEdit={()=>setInterestOpen(true)}/></div>}
       </main><div className="right-rail"><InterestPanel profile={profile} themes={themes} variant={variant} pointBurst={pointBurst} onEdit={()=>setInterestOpen(true)}/><div className="signal-tip"><div className="tip-heading"><span><Sparkles size={12}/></span> A small reminder</div><p>Chat with <b>Aura</b> to reshape your DNA, or use a quick <b>resonate</b> / <b>banish</b> while you browse.</p><button onClick={()=>setInterestOpen(true)}>Talk to Aura <ArrowRight size={12}/></button></div><div className="footer-links"><span>AURA · EARLY ACCESS</span><span>Made for curiosity <span className="tiny-heart">✳</span></span></div></div></div>
    <div className="aura-fly-layer" aria-hidden="true">
      {flyBursts.map((burst) => (
        <div key={burst.id} className="aura-fly-packet">
          {[0, 1, 2].map((index) => (
            <span
              key={`${burst.id}-dot-${index}`}
              className={`aura-fly-dot ${burst.delta > 0 ? 'plus' : 'minus'}`}
              style={{
                '--burst-color': burst.color,
                '--from-x': `${burst.fromX}px`,
                '--from-y': `${burst.fromY}px`,
                '--to-x': `${burst.toX}px`,
                '--to-y': `${burst.toY}px`,
                '--fly-delay': `${index * 55}ms`,
                '--fly-jitter': `${(index - 1) * 14}px`,
              } as CSSProperties}
            />
          ))}
          <span
            className={`aura-fly-chip ${burst.delta > 0 ? 'plus' : 'minus'}`}
            style={{
              '--burst-color': burst.color,
              '--from-x': `${burst.fromX}px`,
              '--from-y': `${burst.fromY}px`,
              '--to-x': `${burst.toX}px`,
              '--to-y': `${burst.toY}px`,
            } as CSSProperties}
          >
            <Sparkles size={12}/>
            {burst.delta > 0 ? '+' : '−'}{Math.abs(burst.delta)} Aura
          </span>
        </div>
      ))}
    </div>
     <nav className="mobile-nav" aria-label="Mobile navigation"><button className={section==='feed'?'active':''} onClick={()=>chooseSection('feed')}><House size={19}/><span>Feed</span></button><button className={section==='discover'?'active':''} onClick={()=>chooseSection('discover')}><Compass size={19}/><span>Explore</span></button><button className="mobile-compose" onClick={()=>setComposerOpen(true)} aria-label="Create post"><Plus size={21}/></button><button className={section==='saved'?'active':''} onClick={()=>chooseSection('saved')}><Bookmark size={19}/><span>Saved</span></button><button className={variant === 'glass' ? 'glass-profile-trigger' : ''} aria-label={variant === 'glass' ? 'Open Interest DNA profile' : 'Chat with Aura'} aria-haspopup={variant === 'glass' ? 'dialog' : undefined} aria-expanded={variant === 'glass' ? profilePopoverOpen : undefined} onClick={()=>variant === 'glass' ? setProfilePopoverOpen(open=>!open) : setInterestOpen(true)}><Waves size={19}/><span>Aura</span></button></nav>
     {interestOpen&&<AuraChatModal themes={themes} variant={variant} talkToAura={live.talkToAura} onClose={()=>setInterestOpen(false)} onApply={async (next, turn, chatMessages) => {
       const applied = await live.applyAuraProfile(turn, chatMessages, themes.map((t) => t.label || t.id));
       const profileToUse = applied ?? next;
       setProfile(profileToUse);
       localStorage.setItem(AURA_CHAT_KEY, '1');
       setInterestOpen(false);
       notify(live.demo ? 'Aura updated your Interest DNA' : 'Aura tuned your feed — refreshing');
     }}/>}{composerOpen&&<ComposerModal variant={variant} live={!live.demo} onClose={()=>setComposerOpen(false)} onPublish={addPost}/>}{pairOpen&&pairPosts&&<PairModal variant={variant} left={pairPosts[0]} right={pairPosts[1]} onClose={()=>{setPairOpen(false);setPairPosts(null);}} onPick={(winner,loser)=>{void pickPair(winner,loser);}}/>}
    {toast&&<div className="toast-message"><span className="toast-dot"/>{toast}</div>}
  </div>;
}
