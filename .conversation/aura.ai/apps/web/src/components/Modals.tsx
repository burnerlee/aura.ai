import { useEffect, useState } from "react";
import {
  Article,
  ArrowUpRight,
  Check,
  Code,
  ImageSquare,
  LinkSimple,
  NotePencil,
  Sparkle,
  X,
} from "@phosphor-icons/react";
import ReactMarkdown from "react-markdown";
import {
  CATEGORIES,
  getEmbedPreview,
  parseInterestPrompt,
  type FeedPost,
  type InterestCategoryId,
  type InterestProfile,
} from "@aura/shared";

interface InterestModalProps {
  profile: InterestProfile;
  onClose: () => void;
  onSave: (profile: InterestProfile) => void;
}

export function InterestModal({ profile, onClose, onSave }: InterestModalProps) {
  const [prompt, setPrompt] = useState(profile.prompt);
  const preview = parseInterestPrompt(prompt);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="modal-card interest-modal" role="dialog" aria-modal="true" aria-labelledby="interest-modal-title">
        <div className="modal-header">
          <div className="modal-title-icon"><Sparkle size={18} weight="fill" /></div>
          <div>
            <span className="eyebrow">PERSONALIZE YOUR SIGNAL</span>
            <h2 id="interest-modal-title">Tell Aura what matters.</h2>
          </div>
          <button className="icon-button modal-close" aria-label="Close" onClick={onClose}><X size={18} /></button>
        </div>
        <p className="modal-intro">Write it like you’d tell a friend. Add what you want more of — and what you’re ready to leave behind.</p>
        <label className="field-label" htmlFor="interest-prompt">YOUR INTEREST PROMPT</label>
        <textarea
          id="interest-prompt"
          className="prompt-input"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="I’m into independent game worlds, practical AI research, and music that feels a little off-center..."
          rows={4}
          autoFocus
        />
        <div className="suggestion-row">
          <span>Try</span>
          {["less generic tech", "more astrophysics", "indie pop"].map((suggestion) => (
            <button
              className="suggestion-chip"
              key={suggestion}
              onClick={() => setPrompt((current) => {
                const clean = current.trim().replace(/[.!?]+$/, "");
                return `${clean}${clean ? ", " : ""}${suggestion}`;
              })}
            >
              + {suggestion}
            </button>
          ))}
        </div>
        <div className="vector-preview">
          <div className="vector-preview-head">
            <span className="field-label">LIVE VECTOR PREVIEW</span>
            <span className="preview-caption">Updates as you type</span>
          </div>
          {CATEGORIES.map((category) => (
            <div className="preview-row" key={category.id}>
              <span>{category.shortLabel}</span>
              <div className="preview-track">
                <span style={{ width: `${preview.vector[category.id]}%`, background: category.color }} />
              </div>
              <strong>{Math.round(preview.vector[category.id])}%</strong>
            </div>
          ))}
        </div>
        <div className="modal-actions">
          <button className="button button-quiet" onClick={onClose}>Cancel</button>
          <button className="button button-primary" onClick={() => onSave(preview)}>
            <Check size={16} weight="bold" /> Apply to my feed
          </button>
        </div>
        <p className="local-note">This demo translates phrases into a local, editable interest profile. No prompt leaves this browser.</p>
      </section>
    </div>
  );
}

type ComposerMode = "short" | "article" | "embed";
type DraftPost = Omit<FeedPost, "id" | "publishedAt" | "likes" | "comments">;

interface ComposerModalProps {
  onClose: () => void;
  onPublish: (post: DraftPost) => void;
}

export function ComposerModal({ onClose, onPublish }: ComposerModalProps) {
  const [mode, setMode] = useState<ComposerMode>("short");
  const [category, setCategory] = useState<InterestCategoryId>("ai");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [url, setUrl] = useState("");
  const [previewMode, setPreviewMode] = useState<"write" | "preview">("write");
  const preview = getEmbedPreview(url);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  function publish() {
    if (mode === "short" && !body.trim()) return;
    if (mode === "article" && (!title.trim() || !body.trim())) return;
    if (mode === "embed" && !preview) return;

    const common = {
      category,
      author: {
        name: "Alex Morgan",
        handle: "@alexm",
        initials: "AM",
        avatarColor: "#829178",
      },
      tags: [CATEGORIES.find((item) => item.id === category)?.shortLabel ?? "Aura"],
      resonated: false,
      banished: false,
    };

    const post: DraftPost =
      mode === "embed"
        ? {
            ...common,
            kind: "embed",
            title: title.trim() || preview!.headline,
            body: body.trim() || "Found this and thought it belonged in the conversation.",
            platform: preview!.platform === "Link" ? undefined : preview!.platform,
            embedUrl: preview!.url,
          }
        : {
            ...common,
            kind: mode,
            title: mode === "article" ? title.trim() : undefined,
            body: body.trim(),
          };

    onPublish(post);
  }

  const modes: { id: ComposerMode; label: string; icon: typeof NotePencil }[] = [
    { id: "short", label: "Quick thought", icon: NotePencil },
    { id: "article", label: "Long-form", icon: Article },
    { id: "embed", label: "Link embed", icon: LinkSimple },
  ];

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="modal-card composer-modal" role="dialog" aria-modal="true" aria-labelledby="composer-modal-title">
        <div className="modal-header composer-heading">
          <div className="modal-title-icon"><NotePencil size={18} weight="fill" /></div>
          <div>
            <span className="eyebrow">THE OMNIBOX</span>
            <h2 id="composer-modal-title">Put something out there.</h2>
          </div>
          <button className="icon-button modal-close" aria-label="Close" onClick={onClose}><X size={18} /></button>
        </div>

        <div className="composer-tabs" role="tablist" aria-label="Post format">
          {modes.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              role="tab"
              aria-selected={mode === id}
              className={`composer-tab ${mode === id ? "active" : ""}`}
              onClick={() => setMode(id)}
            >
              <Icon size={16} weight={mode === id ? "fill" : "regular"} /> {label}
            </button>
          ))}
        </div>

        <div className="composer-form">
          <div className="composer-category">
            <label className="field-label" htmlFor="post-category">FILE UNDER</label>
            <select id="post-category" value={category} onChange={(event) => setCategory(event.target.value as InterestCategoryId)}>
              {CATEGORIES.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}
            </select>
          </div>

          {mode === "short" && (
            <>
              <label className="field-label" htmlFor="quick-thought">YOUR THOUGHT <span>{body.length}/280</span></label>
              <textarea
                id="quick-thought"
                value={body}
                onChange={(event) => setBody(event.target.value)}
                placeholder="A small idea worth passing along..."
                maxLength={280}
                rows={5}
                autoFocus
              />
            </>
          )}

          {mode === "article" && (
            <>
              <label className="field-label" htmlFor="article-title">TITLE</label>
              <input
                id="article-title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Give the idea a name"
              />
              <div className="editor-toolbar">
                <span><Code size={14} /> Markdown supported</span>
                <div className="segmented-toggle">
                  <button className={previewMode === "write" ? "selected" : ""} onClick={() => setPreviewMode("write")}>Write</button>
                  <button className={previewMode === "preview" ? "selected" : ""} onClick={() => setPreviewMode("preview")}>Preview</button>
                </div>
              </div>
              {previewMode === "write" ? (
                <textarea
                  className="article-editor"
                  value={body}
                  onChange={(event) => setBody(event.target.value)}
                  placeholder={"Start with a point of view...\n\nUse **bold**, _italics_, links, or # headings."}
                  rows={9}
                  autoFocus
                />
              ) : (
                <div className="markdown-preview markdown-body">
                  {body ? <ReactMarkdown>{body}</ReactMarkdown> : <p className="empty-preview">Your formatted article preview will appear here.</p>}
                </div>
              )}
            </>
          )}

          {mode === "embed" && (
            <>
              <label className="field-label" htmlFor="embed-url">LINK URL</label>
              <div className="input-with-icon">
                <LinkSimple size={17} />
                <input
                  id="embed-url"
                  type="url"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="https://substack.com, x.com, or reddit.com"
                  autoFocus
                />
              </div>
              {preview ? (
                <div className="embed-live-preview">
                  <div className="embed-live-art">
                    {preview.platform === "Substack" ? <Article size={23} /> : preview.platform === "Reddit" ? <Sparkle size={23} /> : <ArrowUpRight size={23} />}
                  </div>
                  <div className="embed-live-copy">
                    <span>{preview.platform} · {preview.author}</span>
                    <strong>{title.trim() || preview.headline}</strong>
                    <small>{preview.hostname}</small>
                  </div>
                  <Check className="preview-check" size={17} weight="bold" />
                </div>
              ) : (
                <div className="embed-empty-preview"><ImageSquare size={19} /> A link card preview appears when you paste a valid URL.</div>
              )}
              <label className="field-label caption-label" htmlFor="embed-caption">ADD A THOUGHT <span>OPTIONAL</span></label>
              <textarea
                id="embed-caption"
                value={body}
                onChange={(event) => setBody(event.target.value)}
                placeholder="Why is this worth a look?"
                rows={3}
              />
              <p className="local-note">Preview identifies the platform and URL from the link. Live OpenGraph metadata needs an API endpoint.</p>
            </>
          )}
        </div>

        <div className="composer-footer">
          <span><Sparkle size={14} weight="fill" /> Your post will be added to this local demo feed.</span>
          <button className="button button-primary" onClick={publish} disabled={!canPublish(mode, body, title, preview)}>
            Publish <ArrowUpRight size={16} weight="bold" />
          </button>
        </div>
      </section>
    </div>
  );
}

function canPublish(
  mode: ComposerMode,
  body: string,
  title: string,
  preview: ReturnType<typeof getEmbedPreview>,
): boolean {
  if (mode === "short") return Boolean(body.trim());
  if (mode === "article") return Boolean(body.trim() && title.trim());
  return Boolean(preview);
}
