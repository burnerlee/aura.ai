import { useMemo, useRef, useState, type CSSProperties, type PointerEvent } from "react";
import {
  ArrowBendUpRight,
  ArrowUpRight,
  BookmarkSimple,
  Check,
  ChatCircle,
  Heart,
  LinkSimple,
  Sparkle,
  ThumbsDown,
} from "@phosphor-icons/react";
import {
  CATEGORIES,
  explainPostMatch,
  type FeedbackDirection,
  type FeedPost,
  type InterestProfile,
} from "@aura/shared";
import ReactMarkdown from "react-markdown";

interface PostCardProps {
  post: FeedPost;
  profile: InterestProfile;
  onFeedback: (post: FeedPost, direction: FeedbackDirection) => void;
  saved: boolean;
  onToggleSaved: (post: FeedPost) => void;
}

export function PostCard({ post, profile, onFeedback, saved, onToggleSaved }: PostCardProps) {
  const [showInsight, setShowInsight] = useState(false);
  const [dragDelta, setDragDelta] = useState(0);
  const [signal, setSignal] = useState<FeedbackDirection | null>(null);
  const dragStart = useRef<number | null>(null);
  const category = CATEGORIES.find((item) => item.id === post.category)!;
  const insight = useMemo(() => explainPostMatch(post, profile), [post, profile]);

  function pointerDown(event: PointerEvent<HTMLElement>) {
    if (event.button !== 0 || (event.target as HTMLElement).closest("[data-no-swipe]")) return;
    dragStart.current = event.clientX;
    event.currentTarget.setPointerCapture(event.pointerId);
    setSignal(null);
  }

  function pointerMove(event: PointerEvent<HTMLElement>) {
    if (dragStart.current === null) return;
    setDragDelta(Math.max(-140, Math.min(140, event.clientX - dragStart.current)));
  }

  function pointerUp(event: PointerEvent<HTMLElement>) {
    if (dragStart.current === null) return;
    const finalDelta = event.clientX - dragStart.current;
    dragStart.current = null;
    setDragDelta(0);

    if (finalDelta > 78) {
      setSignal("resonate");
      onFeedback(post, "resonate");
    } else if (finalDelta < -78) {
      setSignal("banish");
      onFeedback(post, "banish");
    }
    window.setTimeout(() => setSignal(null), 1100);
  }

  function pointerCancel() {
    dragStart.current = null;
    setDragDelta(0);
  }

  const style = {
    transform: dragDelta ? `translateX(${dragDelta * 0.18}px) rotate(${dragDelta * 0.012}deg)` : undefined,
  };

  return (
    <article
      className={`post-card post-${post.kind} ${signal ? `signal-${signal}` : ""}`}
      style={style}
      onPointerDown={pointerDown}
      onPointerMove={pointerMove}
      onPointerUp={pointerUp}
      onPointerCancel={pointerCancel}
    >
      {signal && (
        <div className={`signal-flash ${signal}`} aria-live="polite">
          {signal === "resonate" ? <Check size={16} weight="bold" /> : <ThumbsDown size={16} weight="bold" />}
          {signal === "resonate" ? "Resonated" : "Banished"}
        </div>
      )}

      {post.imageUrl && (
        <div className="post-image">
          <img src={post.imageUrl} alt={post.imageAlt || post.title || "Aura post image"} loading="lazy" />
          <div className="image-topline">
            <span className="category-chip" style={{ "--chip-color": category.color } as CSSProperties}>
              <i />
              {category.shortLabel}
            </span>
            <button
              className={`ai-badge ${showInsight ? "active" : ""}`}
              onClick={() => setShowInsight((value) => !value)}
              data-no-swipe
              aria-expanded={showInsight}
            >
              <Sparkle size={13} weight="fill" /> Match insight
            </button>
          </div>
        </div>
      )}

      <div className="post-content">
        <div className="post-author-row">
          <div className="author-info">
            <span className="avatar" style={{ "--avatar-color": post.author.avatarColor } as CSSProperties}>
              {post.author.initials}
            </span>
            <div className="author-copy">
              <span className="author-name">
                {post.author.name}
                {post.author.verified && <span className="verified-mark">✓</span>}
              </span>
              <span className="author-meta">{post.author.handle} <span>·</span> {post.publishedAt}</span>
            </div>
          </div>
          <button
            className="ai-badge compact-ai"
            onClick={() => setShowInsight((value) => !value)}
            data-no-swipe
            aria-expanded={showInsight}
          >
            <Sparkle size={13} weight="fill" /> Why this?
          </button>
        </div>

        {!post.imageUrl && (
          <div className="post-type-line">
              <span className="category-chip" style={{ "--chip-color": category.color } as CSSProperties}>
              <i />
              {category.shortLabel}
            </span>
            {post.kind === "embed" && post.platform && (
              <span className="platform-label"><LinkSimple size={12} /> {post.platform}</span>
            )}
          </div>
        )}

        {post.title && <h3 className="post-title">{post.title}</h3>}
        {post.kind === "article" ? (
          <div className="post-body markdown-body"><ReactMarkdown>{post.body}</ReactMarkdown></div>
        ) : (
          <p className="post-body">{post.body}</p>
        )}

        {post.kind === "embed" && (
          <a className={`embed-preview embed-${post.platform?.toLowerCase() ?? "link"}`} href={post.embedUrl} target="_blank" rel="noreferrer" data-no-swipe>
            <span className="embed-orbit"><ArrowUpRight size={16} weight="bold" /></span>
            <span className="embed-copy">
              <strong>{post.platform || "External link"}</strong>
              <small>{post.embedUrl?.replace(/^https?:\/\//, "").replace(/\/$/, "")}</small>
            </span>
            <ArrowBendUpRight className="embed-arrow" size={16} />
          </a>
        )}

        {post.tags.length > 0 && (
          <div className="post-tags">
            {post.tags.slice(0, 3).map((tag) => <span key={tag}>#{tag.replace(/\s+/g, "")}</span>)}
          </div>
        )}

        {showInsight && (
          <div className="insight-panel">
            <span className="insight-icon"><Sparkle size={14} weight="fill" /></span>
            <p>{insight}</p>
          </div>
        )}

        <div className="post-footer">
          <div className="engagement">
            <span><Heart size={15} /> {post.likes.toLocaleString()}</span>
            <span><ChatCircle size={15} /> {post.comments}</span>
          </div>
          <div className="post-actions" data-no-swipe>
            <button
              className={`save-button ${saved ? "selected" : ""}`}
              onClick={() => onToggleSaved(post)}
              aria-label={saved ? "Remove from collection" : "Save to collection"}
              title={saved ? "Saved" : "Save"}
            >
              <BookmarkSimple size={16} weight={saved ? "fill" : "regular"} />
            </button>
            <button
              className={`feedback-button resonate-button ${post.resonated ? "selected" : ""}`}
              onClick={() => onFeedback(post, "resonate")}
              aria-label="Resonate with this post"
              title="Resonate"
            >
              <Heart size={15} weight={post.resonated ? "fill" : "regular"} />
              <span>Resonate</span>
            </button>
            <button
              className={`feedback-button banish-button ${post.banished ? "selected" : ""}`}
              onClick={() => onFeedback(post, "banish")}
              aria-label="Banish this post"
              title="Banish"
            >
              <ThumbsDown size={15} weight={post.banished ? "fill" : "regular"} />
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}
