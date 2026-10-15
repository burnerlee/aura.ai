import { useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent } from 'react';
import {
  ArrowDown, ArrowRight, ArrowUpRight, Bookmark, Check, Compass, Heart,
  House, Link as LinkIcon, MessageCircle, Plus, Search, Sparkles, ThumbsDown,
  Waves, X, FileText, PenLine, Code2, Image as ImageIcon, ExternalLink,
} from 'lucide-react';
import {
  adjustInterestVector, CATEGORIES, DEMO_POSTS, DEMO_PROFILE, explainPostMatch,
  getEmbedPreview, parseInterestPrompt, rankPosts,
  type FeedPost, type FeedbackDirection, type InterestCategoryId, type InterestProfile,
} from '@workspace/aura-shared';
import { useRecommendationFeed } from '@/hooks/use-recommendation-feed';
import { shortUserId, shortUserLabel } from '@/lib/user-id';

type Section = 'feed' | 'discover' | 'saved';
type ComposerMode = 'short' | 'article' | 'embed';
type DraftPost = Omit<FeedPost, 'id' | 'publishedAt' | 'likes' | 'comments'>;
const PROFILE_KEY = 'aura:interest-profile:v1';
const POSTS_KEY = 'aura:feed-posts:v1';
const SAVED_KEY = 'aura:saved:v1';

function categoryAccent(id: InterestCategoryId, variant: 'current' | 'glass') {
  if (variant === 'glass') return { cyberpunk: '#22d3ee', culture: '#f43f5e', ai: '#a855f7', space: '#f59e0b' }[id];
  return CATEGORIES.find(category => category.id === id)?.color ?? '#9be9c5';
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
function InterestPanel({ profile, onEdit, variant }: { profile: InterestProfile; onEdit: () => void; variant: 'current' | 'glass' }) {
  const radius = 48, circumference = 2 * Math.PI * radius;
  let offset = 0;
  return <aside className="interest-panel">
    <div className="panel-heading"><div><span className="eyebrow">YOUR PROFILE</span><h2>Interest DNA</h2></div><button className="icon-button subtle-icon" aria-label="Edit interests" onClick={onEdit}><ArrowUpRight size={17}/></button></div>
    <div className="dna-visual"><svg className="dna-chart" viewBox="0 0 120 120" aria-label="Interest vector composition">
      <circle className="dna-track" cx="60" cy="60" r={radius} fill="none" strokeWidth="11"/>
      <g transform="rotate(-90 60 60)">{CATEGORIES.map(category => { const segment = profile.vector[category.id] / 100 * circumference, start = offset; offset += segment; return <circle key={category.id} cx="60" cy="60" r={radius} fill="none" stroke={categoryAccent(category.id, variant)} strokeWidth="11" strokeLinecap="round" strokeDasharray={`${Math.max(segment - 3,0)} ${circumference}`} strokeDashoffset={-start} className="dna-segment"/>; })}</g>
    </svg><div className="dna-center"><span className="dna-center-icon"><Sparkles size={14}/></span><strong>LIVE</strong><span>VECTOR</span></div></div>
    <div className="interest-legend">{CATEGORIES.map(category => <div className="interest-row" key={category.id}><span className="interest-name"><i className="interest-dot" style={{ backgroundColor: categoryAccent(category.id, variant) }}/>{category.shortLabel}</span><span className="interest-value">{Math.round(profile.vector[category.id])}%</span></div>)}</div>
    <div className="interest-prompt"><span className="prompt-label"><Sparkles size={12}/> ACTIVE SIGNAL</span><p>“{profile.prompt}”</p><button className="text-action" onClick={onEdit}>Tune your feed <ArrowUpRight size={13}/></button></div>
    <div className="vector-note"><span className="vector-pulse"/>Every resonate or banish updates this profile.</div>
  </aside>;
}
function PostCard({ post, profile, saved, onFeedback, onToggleSaved, variant, why, onSimilar }: {
  post: FeedPost; profile: InterestProfile; saved: boolean;
  variant: 'current' | 'glass';
  why?: string;
  onFeedback: (post: FeedPost, direction: FeedbackDirection) => void;
  onToggleSaved: (post: FeedPost) => void;
  onSimilar?: (post: FeedPost) => void;
}) {
  const [showInsight, setShowInsight] = useState(false), [delta, setDelta] = useState(0), [signal, setSignal] = useState<FeedbackDirection | null>(null);
  const start = useRef<number | null>(null), category = CATEGORIES.find(item => item.id === post.category)!;
  const insight = useMemo(() => why || explainPostMatch(post, profile), [post, profile, why]);
  function down(event: PointerEvent<HTMLElement>) {
    if (event.button !== 0 || (event.target as HTMLElement).closest('[data-no-swipe]')) return;
    start.current = event.clientX; event.currentTarget.setPointerCapture(event.pointerId); setSignal(null);
  }
  function move(event: PointerEvent<HTMLElement>) { if (start.current !== null) setDelta(Math.max(-140, Math.min(140, event.clientX - start.current))); }
  function up(event: PointerEvent<HTMLElement>) {
    if (start.current === null) return;
    const distance = event.clientX - start.current; start.current = null; setDelta(0);
    if (distance > 78) { setSignal('resonate'); onFeedback(post, 'resonate'); }
    if (distance < -78) { setSignal('banish'); onFeedback(post, 'banish'); }
    window.setTimeout(() => setSignal(null), 1100);
  }
  return <article className={`post-card post-${post.kind} post-${post.category} signal-${signal ?? ''}`} style={{ transform: delta ? `translateX(${delta * .18}px) rotate(${delta * .012}deg)` : undefined }} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={() => { start.current = null; setDelta(0); }}>
    {signal && <div className={`signal-flash ${signal}`} aria-live="polite">{signal === 'resonate' ? <Check size={15}/> : <ThumbsDown size={15}/>} {signal === 'resonate' ? 'Resonated' : 'Banished'}</div>}
    {post.imageUrl ? <div className="post-image"><img src={post.imageUrl} alt={post.imageAlt || post.title || 'Aura post image'} loading="lazy"/><div className="image-topline"><span className="category-chip" style={{ '--chip-color': categoryAccent(category.id, variant) } as CSSProperties}><i/>{category.shortLabel}</span><button className={`ai-badge ${showInsight ? 'active' : ''}`} data-no-swipe onClick={() => setShowInsight(!showInsight)}><Sparkles size={12}/> Match insight</button></div></div> :
      post.kind === 'image' ? <div className={`post-image art-${post.category}`} aria-label={post.imageAlt || post.title}><div className="image-topline"><span className="category-chip" style={{ '--chip-color': categoryAccent(category.id, variant) } as CSSProperties}><i/>{category.shortLabel}</span><button className={`ai-badge ${showInsight ? 'active' : ''}`} data-no-swipe onClick={() => setShowInsight(!showInsight)}><Sparkles size={12}/> Match insight</button></div><span className="art-orbit"/><span className="art-title">{post.category === 'space' ? 'FIELD NOTES / 04' : 'AFTER HOURS — 2049'}</span></div> : null}
    <div className="post-content"><div className="post-author-row"><div className="author-info"><span className="avatar" style={{ '--avatar-color': post.author.avatarColor } as CSSProperties}>{post.author.initials}</span><div className="author-copy"><span className="author-name">{post.author.name}{post.author.verified && <span className="verified-mark">✓</span>}</span><span className="author-meta">{post.author.handle} · {post.publishedAt}</span></div></div><button className="ai-badge compact-ai" onClick={() => setShowInsight(!showInsight)} data-no-swipe aria-expanded={showInsight}><Sparkles size={12}/> Why this?</button></div>
       {!post.imageUrl && post.kind !== 'image' && <div className="post-type-line"><span className="category-chip" style={{ '--chip-color': categoryAccent(category.id, variant) } as CSSProperties}><i/>{category.shortLabel}</span>{post.kind === 'embed' && post.platform && <span className="platform-label"><LinkIcon size={11}/>{post.platform}</span>}</div>}
      {post.title && <h3 className="post-title">{post.title}</h3>}
      {post.kind === 'article' ? <div className="post-body"><Markdown source={post.body}/></div> : <p className="post-body">{post.body}</p>}
        {post.kind === 'embed' && post.embedUrl && (variant === 'glass' ?
          <div className="glass-embed-meta" data-no-swipe><span className="glass-source"><LinkIcon size={12}/>{post.platform || 'External link'} · source</span><a className="glass-open-original" href={post.embedUrl} target="_blank" rel="noopener noreferrer">Open original <ExternalLink size={12}/></a></div> :
         <a className={`embed-preview embed-${post.platform?.toLowerCase() ?? 'link'}`} href={post.embedUrl} target="_blank" rel="noreferrer" data-no-swipe><span className="embed-orbit"><ArrowUpRight size={15}/></span><span className="embed-copy"><strong>{post.platform || 'External link'}</strong><small>{post.embedUrl.replace(/^https?:\/\//,'').replace(/\/$/,'')}</small></span><ExternalLink className="embed-arrow" size={14}/></a>)}
      {post.tags.length > 0 && <div className="post-tags">{post.tags.slice(0,3).map(tag => <span key={tag}>#{tag.replace(/\s+/g,'')}</span>)}</div>}
      {showInsight && <div className="insight-panel"><span className="insight-icon"><Sparkles size={13}/></span><p>{insight} <small>{why ? 'Recommendation explanation.' : 'Local match explanation · not generated by an LLM.'}</small></p></div>}
      <div className="post-footer"><div className="engagement"><span><Heart size={14}/>{post.likes.toLocaleString()}</span><span><MessageCircle size={14}/>{post.comments}</span>{onSimilar && <button className="text-action" data-no-swipe onClick={() => onSimilar(post)} style={{marginLeft:8}}><Sparkles size={12}/> More like this</button>}</div><div className="post-actions" data-no-swipe><button className={`save-button ${saved ? 'selected' : ''}`} onClick={() => onToggleSaved(post)} aria-label={saved ? 'Remove from collection' : 'Save to collection'}><Bookmark size={15} fill={saved ? 'currentColor' : 'none'}/></button><button className={`feedback-button resonate-button ${post.resonated ? 'selected' : ''}`} onClick={() => onFeedback(post,'resonate')} aria-label="Resonate with this post"><Heart size={14} fill={post.resonated ? 'currentColor' : 'none'}/><span>Resonate</span></button><button className={`feedback-button banish-button ${post.banished ? 'selected' : ''}`} onClick={() => onFeedback(post,'banish')} aria-label="Banish this post"><ThumbsDown size={14} fill={post.banished ? 'currentColor' : 'none'}/></button></div></div>
    </div>
  </article>;
}
function InterestModal({ profile, onClose, onSave, variant }: { profile: InterestProfile; onClose: () => void; onSave: (profile: InterestProfile) => void; variant: 'current' | 'glass' }) {
  const [prompt, setPrompt] = useState(profile.prompt), preview = parseInterestPrompt(prompt);
  useEffect(() => { const handler = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); }; window.addEventListener('keydown',handler); return () => window.removeEventListener('keydown',handler); }, [onClose]);
  return <div className="modal-backdrop" role="presentation" onMouseDown={event => event.target === event.currentTarget && onClose()}><section className="modal-card interest-modal" role="dialog" aria-modal="true" aria-labelledby="interest-modal-title">
    <div className="modal-header"><div className="modal-title-icon"><Sparkles size={18}/></div><div><span className="eyebrow">PERSONALIZE YOUR SIGNAL</span><h2 id="interest-modal-title">Tell Aura what matters.</h2></div><button className="icon-button modal-close" aria-label="Close" onClick={onClose}><X size={18}/></button></div>
    <p className="modal-intro">Write it like you’d tell a friend. Add what you want more of — and what you’re ready to leave behind.</p>
    <label className="field-label" htmlFor="interest-prompt">YOUR INTEREST PROMPT</label><textarea id="interest-prompt" className="prompt-input" value={prompt} onChange={event => setPrompt(event.target.value)} placeholder="I’m into independent game worlds, practical AI research, and music that feels a little off-center..." rows={4} autoFocus/>
    <div className="suggestion-row"><span>Try</span>{['less generic tech','more astrophysics','indie pop'].map(suggestion => <button className="suggestion-chip" key={suggestion} onClick={() => setPrompt(current => `${current.trim().replace(/[.!?]+$/,'')}${current.trim() ? ', ' : ''}${suggestion}`)}>+ {suggestion}</button>)}</div>
    <div className="vector-preview"><div className="vector-preview-head"><span className="field-label">LIVE VECTOR PREVIEW</span><span className="preview-caption">Deterministic local mapper</span></div>{CATEGORIES.map(category => <div className="preview-row" key={category.id}><span>{category.shortLabel}</span><div className="preview-track"><span style={{ width:`${preview.vector[category.id]}%`,background:categoryAccent(category.id, variant) }}/></div><strong>{Math.round(preview.vector[category.id])}%</strong></div>)}</div>
    <div className="modal-actions"><button className="button button-quiet" onClick={onClose}>Cancel</button><button className="button button-primary" onClick={() => onSave(preview)}><Check size={15}/> Apply to my feed</button></div><p className="local-note">Your prompt maps to a local, editable interest profile. Nothing leaves this browser.</p>
  </section></div>;
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
          const category = CATEGORIES.find(item => item.id === post.category)!;
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
    const common = { category, author: { name:'Alex Morgan',handle:'@alexm',initials:'AM',avatarColor:'#829178' }, tags:[CATEGORIES.find(item => item.id === category)?.shortLabel ?? 'Aura'], resonated:false, banished:false };
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
  const [section,setSection] = useState<Section>('feed'), [activeCategory,setActiveCategory] = useState('all'), [search,setSearch] = useState('');
  const [searchOpen,setSearchOpen] = useState(false), [interestOpen,setInterestOpen] = useState(false), [composerOpen,setComposerOpen] = useState(false), [profilePopoverOpen,setProfilePopoverOpen] = useState(false), [toast,setToast] = useState('');
  const [pairOpen, setPairOpen] = useState(false);
  const [pairPosts, setPairPosts] = useState<[FeedPost, FeedPost] | null>(null);
  const profilePopoverRef = useRef<HTMLDivElement | null>(null);
  const toastTimer = useRef<number | undefined>(undefined);
  const searchTimer = useRef<number | undefined>(undefined);
  const live = useRecommendationFeed(demoPosts);
  const posts = live.demo ? demoPosts : live.posts;
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
    let result: FeedPost[];
    if (live.similarResults && live.similarResults.length) {
      result = live.similarResults;
    } else if (!live.demo && search.trim() && live.searchResults) {
      result = live.searchResults;
    } else if (section === 'saved') {
      result = posts.filter(post => savedIds.includes(post.id));
    } else if (section === 'discover') {
      result = live.demo
        ? [...posts].sort((a, b) => b.likes - a.likes)
        : live.discoverPosts;
    } else if (live.demo) {
      result = rankPosts(posts, profile);
    } else {
      result = posts;
    }
    if (activeCategory !== 'all') result = result.filter(post => post.category === activeCategory);
    if (live.demo && search.trim()) {
      const needle = search.trim().toLowerCase();
      result = result.filter(post => `${post.title ?? ''} ${post.body} ${post.author.name} ${post.tags.join(' ')}`.toLowerCase().includes(needle));
    }
    return result;
  },[activeCategory,posts,profile,savedIds,search,section,live.demo,live.searchResults,live.discoverPosts,live.similarResults]);
  function notify(message: string) { setToast(message); if (toastTimer.current) window.clearTimeout(toastTimer.current); toastTimer.current=window.setTimeout(() => setToast(''),2200); }
  function feedback(post: FeedPost,direction: FeedbackDirection) {
    if (live.demo) {
      setDemoPosts(current => current.map(item => item.id !== post.id ? item : direction === 'resonate' ? { ...item,resonated:!item.resonated,banished:false,likes:item.likes+(item.resonated?-1:1) } : { ...item,banished:!item.banished,resonated:false }));
    } else {
      void live.recordFeedback(post, direction);
    }
    setProfile(current => ({ ...current,vector:adjustInterestVector(current.vector,post.category,direction==='resonate'?'up':'down') }));
    const label=CATEGORIES.find(item=>item.id===post.category)?.shortLabel; notify(direction==='resonate'?`More ${label} in your signal`:`Less ${label} in your signal`);
  }
  function toggleSaved(post: FeedPost) {
    const was=savedIds.includes(post.id), next=was?savedIds.filter(id=>id!==post.id):[...savedIds,post.id];
    setSavedIds(next); localStorage.setItem(SAVED_KEY,JSON.stringify(next));
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
    notify(`Preferred ${CATEGORIES.find(c => c.id === winner.category)?.shortLabel ?? 'that'} signal`);
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
      {variant === 'glass' ? <button className="interest-prompt-button glass-profile-trigger" aria-label="Open Interest DNA profile" aria-haspopup="dialog" aria-expanded={profilePopoverOpen} aria-controls="glass-profile-popover" onClick={()=>setProfilePopoverOpen(open=>!open)}><span className="prompt-spark"><Sparkles size={14}/></span><span className="prompt-button-copy"><small>YOUR PROFILE</small><strong>Interest DNA · 4 signals</strong></span><span className="prompt-edit">{profilePopoverOpen ? 'CLOSE' : 'VIEW'} <ArrowDown size={11}/></span></button> :
      <button className="interest-prompt-button" onClick={()=>setInterestOpen(true)}><span className="prompt-spark"><Sparkles size={14}/></span><span className="prompt-button-copy"><small>YOUR SIGNAL</small><strong>{profile.prompt}</strong></span><span className="prompt-edit">EDIT <ArrowRight size={11}/></span></button>}
      <div className="topbar-actions"><button className={`icon-button top-search ${searchOpen?'active':''}`} aria-label="Search the feed" onClick={()=>setSearchOpen(open=>!open)}><Search size={18}/></button><button className="icon-button notification-button" aria-label="Open pairwise preference" title="Pairwise pick" onClick={()=>void openPair()}><Waves size={18}/></button><button className="button button-primary create-button" onClick={()=>setComposerOpen(true)}><Plus size={16} strokeWidth={2.5}/><span>Create</span></button><button className="user-avatar" aria-label={live.demo ? 'Demo profile' : `Copy user id ${live.userId}`} title={live.demo ? 'Demo user' : live.userId} onClick={copyUserId}>{avatarLabel}</button></div>
    </header>
    {variant === 'glass' && profilePopoverOpen && <div className="glass-profile-popover" id="glass-profile-popover" ref={profilePopoverRef} role="dialog" aria-label="Interest DNA profile"><InterestPanel profile={profile} variant="glass" onEdit={()=>{setProfilePopoverOpen(false);setInterestOpen(true);}}/></div>}
    {searchOpen && <div className="search-bar"><Search size={16}/><input autoFocus value={search} onChange={event=>setSearch(event.target.value)} placeholder="Search ideas, people, or topics..." aria-label="Search ideas, people, or topics"/><button onClick={()=>{setSearch('');setSearchOpen(false);}} aria-label="Close search">×</button></div>}
    <div className="workspace"><aside className="left-rail"><span className="eyebrow rail-label">YOUR SPACE</span><nav className="main-nav" aria-label="Main navigation">
      <button className={section==='feed'?'active':''} onClick={()=>chooseSection('feed')}><House size={17}/><span>For you</span>{section==='feed'&&<i/>}</button><button className={section==='discover'?'active':''} onClick={()=>chooseSection('discover')}><Compass size={17}/><span>Discover</span>{section==='discover'&&<i/>}</button><button className={section==='saved'?'active':''} onClick={()=>chooseSection('saved')}><Bookmark size={17}/><span>Collection</span>{section==='saved'&&<i/>}</button></nav>
      <div className="rail-divider"/><div className="rail-section-heading"><span className="eyebrow">YOUR INTERESTS</span><button className="mini-edit" onClick={()=>setInterestOpen(true)} aria-label="Edit interests">+</button></div><div className="rail-categories">{CATEGORIES.map(category=><button className={`rail-category ${activeCategory===category.id?'selected':''}`} key={category.id} onClick={()=>{setActiveCategory(activeCategory===category.id?'all':category.id);setSection('feed');}}><i style={{backgroundColor:categoryAccent(category.id, variant)}}/><span>{category.shortLabel}</span><small>{Math.round(profile.vector[category.id])}</small></button>)}</div>
      <button className="rail-create-card" onClick={()=>setComposerOpen(true)}><span className="rail-create-icon"><Plus size={16}/></span><strong>Make something</strong><small>A thought, a story, a link.</small></button><div className="rail-footer"><span className="rail-status-dot"/> A quieter corner of the internet.</div></aside>
      <main className="feed-main"><div className="feed-topline"><div className="feed-heading"><span className="eyebrow"><span className="live-dot"/> {live.similarResults ? 'SIMILARITY' : section==='discover' ? 'DISCOVER' : 'PERSONALIZED FOR YOU'}</span><h1>{sectionTitle}<span>.</span></h1><p>{live.similarResults ? <button className="text-action" onClick={() => live.clearSimilar()}>Clear similar · back to feed</button> : section==='saved'?'The posts you wanted to keep close.':section==='discover'?'Popular and recent posts across the corpus.':'A little less noise. A lot more you.'}</p></div><div className="feed-toolbar"><button className="filter-button" onClick={()=>setInterestOpen(true)}><Waves size={14}/><span>Signal active</span><ArrowDown size={12}/></button><span className="feed-count"><b>{String(visiblePosts.length).padStart(2,'0')}</b> posts</span></div></div>
        <div className="feed-filter-row"><button className={`filter-chip ${activeCategory==='all'?'active':''}`} onClick={()=>setActiveCategory('all')}>All signals</button>{CATEGORIES.map(category=><button className={`filter-chip ${activeCategory===category.id?'active':''}`} key={category.id} onClick={()=>setActiveCategory(activeCategory===category.id?'all':category.id)}><i style={{backgroundColor:categoryAccent(category.id, variant)}}/>{category.shortLabel}</button>)}</div>
         {(section==='feed' && live.feedLoading) || (section==='discover' && live.discoverLoading) ? <div className="empty-state"><span className="empty-state-icon"><Sparkles size={22}/></span><h2>{section==='discover'?'Scanning the corpus…':'Tuning your feed…'}</h2><p>Loading recommendations.</p></div> : visiblePosts.length ? <div className="masonry-feed">{visiblePosts.map(post=><PostCard key={post.id} post={post} profile={profile} variant={variant} why={live.whyById[post.id]} onFeedback={feedback} saved={savedIds.includes(post.id)} onToggleSaved={toggleSaved} onSimilar={showSimilar}/>)}{section!=='saved'&&!live.similarResults&&<button className="feed-end-card" onClick={()=>chooseSection('discover')}><span className="end-card-icon"><Sparkles size={16}/></span><span><strong>Keep following your curiosity.</strong><small>Explore more posts in your orbit.</small></span><ArrowRight size={16}/></button>}</div> : <div className="empty-state"><span className="empty-state-icon"><Bookmark size={22}/></span><h2>{section==='saved'?'Nothing saved yet.': live.feedError ? 'Could not reach the recommendation API.' : 'No posts in this signal.'}</h2><p>{section==='saved'?'Save a post to keep it in your collection.': live.feedError ? 'Start scraper serve + api-server, or set VITE_USE_DEMO=1.' : 'Try another topic or adjust your interest prompt.'}</p><button className="button button-secondary" onClick={()=>section==='saved'?chooseSection('feed'):setInterestOpen(true)}>{section==='saved'?'Back to your feed':'Tune your interests'}</button></div>}
         {variant === 'current' && <div className="mobile-interest-card"><InterestPanel profile={profile} variant={variant} onEdit={()=>setInterestOpen(true)}/></div>}
       </main><div className="right-rail"><InterestPanel profile={profile} variant={variant} onEdit={()=>setInterestOpen(true)}/><div className="signal-tip"><div className="tip-heading"><span><Sparkles size={12}/></span> A small reminder</div><p>Your feed is yours to shape. A quick <b>resonate</b> or <b>banish</b> helps Aura learn what feels right.</p><button onClick={()=>setInterestOpen(true)}>Adjust your signal <ArrowRight size={12}/></button></div><div className="footer-links"><span>AURA · EARLY ACCESS</span><span>Made for curiosity <span className="tiny-heart">✳</span></span></div></div></div>
     <nav className="mobile-nav" aria-label="Mobile navigation"><button className={section==='feed'?'active':''} onClick={()=>chooseSection('feed')}><House size={19}/><span>Feed</span></button><button className={section==='discover'?'active':''} onClick={()=>chooseSection('discover')}><Compass size={19}/><span>Explore</span></button><button className="mobile-compose" onClick={()=>setComposerOpen(true)} aria-label="Create post"><Plus size={21}/></button><button className={section==='saved'?'active':''} onClick={()=>chooseSection('saved')}><Bookmark size={19}/><span>Saved</span></button><button className={variant === 'glass' ? 'glass-profile-trigger' : ''} aria-label={variant === 'glass' ? 'Open Interest DNA profile' : 'Edit interests'} aria-haspopup={variant === 'glass' ? 'dialog' : undefined} aria-expanded={variant === 'glass' ? profilePopoverOpen : undefined} onClick={()=>variant === 'glass' ? setProfilePopoverOpen(open=>!open) : setInterestOpen(true)}><Waves size={19}/><span>DNA</span></button></nav>
     {interestOpen&&<InterestModal profile={profile} variant={variant} onClose={()=>setInterestOpen(false)} onSave={next=>{setProfile(next);setInterestOpen(false);void live.tune(next);notify(live.demo?'Your Interest DNA has been updated':'Tuned — refreshing recommendations');}}/>}{composerOpen&&<ComposerModal variant={variant} live={!live.demo} onClose={()=>setComposerOpen(false)} onPublish={addPost}/>}{pairOpen&&pairPosts&&<PairModal variant={variant} left={pairPosts[0]} right={pairPosts[1]} onClose={()=>{setPairOpen(false);setPairPosts(null);}} onPick={(winner,loser)=>{void pickPair(winner,loser);}}/>}
    {toast&&<div className="toast-message"><span className="toast-dot"/>{toast}</div>}
  </div>;
}
