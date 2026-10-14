import { useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  Bell,
  BookmarkSimple,
  Compass,
  House,
  MagnifyingGlass,
  Plus,
  Sparkle,
  WaveSine,
} from "@phosphor-icons/react";
import {
  adjustInterestVector,
  CATEGORIES,
  rankPosts,
  type FeedbackDirection,
  type FeedPost,
  type InterestProfile,
} from "@aura/shared";
import { ComposerModal, InterestModal } from "./components/Modals";
import { InterestPanel } from "./components/InterestPanel";
import { PostCard } from "./components/PostCard";
import { loadPosts, loadProfile, savePosts, saveProfile } from "./lib/persistence";

type Section = "feed" | "discover" | "saved";

export default function App() {
  const [profile, setProfile] = useState<InterestProfile>(loadProfile);
  const [posts, setPosts] = useState<FeedPost[]>(loadPosts);
  const [savedIds, setSavedIds] = useState<string[]>(() => {
    try {
      return JSON.parse(window.localStorage.getItem("aura:saved:v1") || "[]") as string[];
    } catch {
      return [];
    }
  });
  const [section, setSection] = useState<Section>("feed");
  const [activeCategory, setActiveCategory] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [interestOpen, setInterestOpen] = useState(false);
  const [composerOpen, setComposerOpen] = useState(false);
  const [toast, setToast] = useState("");

  useEffect(() => saveProfile(profile), [profile]);
  useEffect(() => savePosts(posts), [posts]);

  const visiblePosts = useMemo(() => {
    let result =
      section === "saved"
        ? posts.filter((post) => savedIds.includes(post.id))
        : section === "discover"
          ? [...posts].sort((a, b) => b.likes - a.likes)
          : rankPosts(posts, profile);

    if (activeCategory !== "all") {
      result = result.filter((post) => post.category === activeCategory);
    }
    if (search.trim()) {
      const needle = search.trim().toLowerCase();
      result = result.filter((post) =>
        `${post.title ?? ""} ${post.body} ${post.author.name} ${post.tags.join(" ")}`
          .toLowerCase()
          .includes(needle),
      );
    }
    return result;
  }, [activeCategory, posts, profile, savedIds, search, section]);

  function notify(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(""), 2200);
  }

  function handleFeedback(post: FeedPost, direction: FeedbackDirection) {
    setPosts((current) =>
      current.map((item) => {
        if (item.id !== post.id) return item;
        if (direction === "resonate") {
          return {
            ...item,
            resonated: !item.resonated,
            banished: false,
            likes: item.likes + (item.resonated ? -1 : 1),
          };
        }
        return { ...item, banished: !item.banished, resonated: false };
      }),
    );
    setProfile((current) => ({
      ...current,
      vector: adjustInterestVector(
        current.vector,
        post.category,
        direction === "resonate" ? "up" : "down",
      ),
    }));
    const category = CATEGORIES.find((item) => item.id === post.category)?.shortLabel;
    notify(direction === "resonate" ? `More ${category} in your signal` : `Less ${category} in your signal`);
  }

  function toggleSaved(post: FeedPost) {
    const alreadySaved = savedIds.includes(post.id);
    const next = alreadySaved
      ? savedIds.filter((id) => id !== post.id)
      : [...savedIds, post.id];
    setSavedIds(next);
    window.localStorage.setItem("aura:saved:v1", JSON.stringify(next));
    notify(alreadySaved ? "Removed from your collection" : "Saved to your collection");
  }

  function addPost(post: Omit<FeedPost, "id" | "publishedAt" | "likes" | "comments">) {
    const nextPost: FeedPost = {
      ...post,
      id: `local-${Date.now()}`,
      publishedAt: "just now",
      likes: 0,
      comments: 0,
    };
    const next = [nextPost, ...posts];
    setPosts(next);
    savePosts(next);
    setSection("feed");
    setActiveCategory("all");
    setComposerOpen(false);
    notify("Your post is in the feed");
  }

  function chooseSection(nextSection: Section) {
    setSection(nextSection);
    setActiveCategory("all");
    setSearch("");
  }

  const sectionTitle =
    section === "saved" ? "Your collection" : section === "discover" ? "Explore the signal" : "For you";

  return (
    <div className="aura-app">
      <header className="topbar">
        <a className="brand" href="#" aria-label="Aura home" onClick={() => chooseSection("feed")}>
          <span className="brand-mark"><span /><i /></span>
          <span className="brand-name">aura<span>.</span></span>
        </a>

        <button className="interest-prompt-button" onClick={() => setInterestOpen(true)}>
          <span className="prompt-spark"><Sparkle size={15} weight="fill" /></span>
          <span className="prompt-button-copy">
            <small>YOUR SIGNAL</small>
            <strong>{profile.prompt}</strong>
          </span>
          <span className="prompt-edit">EDIT <ArrowRight size={12} weight="bold" /></span>
        </button>

        <div className="topbar-actions">
          <button
            className={`icon-button top-search ${searchOpen ? "active" : ""}`}
            aria-label="Search the feed"
            onClick={() => setSearchOpen((open) => !open)}
          >
            <MagnifyingGlass size={19} />
          </button>
          <button className="icon-button notification-button" aria-label="Notifications" onClick={() => notify("You’re all caught up")}>
            <Bell size={19} />
            <i />
          </button>
          <button className="button button-primary create-button" onClick={() => setComposerOpen(true)}>
            <Plus size={17} weight="bold" /> <span>Create</span>
          </button>
          <button className="user-avatar" aria-label="Alex Morgan profile" onClick={() => notify("Profile settings are coming soon")}>AM</button>
        </div>
      </header>

      {searchOpen && (
        <div className="search-bar">
          <MagnifyingGlass size={17} />
          <input
            autoFocus
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search ideas, people, or topics..."
            aria-label="Search ideas, people, or topics"
          />
          <button onClick={() => { setSearch(""); setSearchOpen(false); }} aria-label="Close search">×</button>
        </div>
      )}

      <div className="workspace">
        <aside className="left-rail">
          <span className="eyebrow rail-label">YOUR SPACE</span>
          <nav className="main-nav" aria-label="Main navigation">
            <button className={section === "feed" ? "active" : ""} onClick={() => chooseSection("feed")}>
              <House size={18} weight={section === "feed" ? "fill" : "regular"} />
              <span>For you</span>
              {section === "feed" && <i />}
            </button>
            <button className={section === "discover" ? "active" : ""} onClick={() => chooseSection("discover")}>
              <Compass size={18} weight={section === "discover" ? "fill" : "regular"} />
              <span>Discover</span>
              {section === "discover" && <i />}
            </button>
            <button className={section === "saved" ? "active" : ""} onClick={() => chooseSection("saved")}>
              <BookmarkSimple size={18} weight={section === "saved" ? "fill" : "regular"} />
              <span>Collection</span>
              {section === "saved" && <i />}
            </button>
          </nav>

          <div className="rail-divider" />
          <div className="rail-section-heading">
            <span className="eyebrow">YOUR INTERESTS</span>
            <button className="mini-edit" onClick={() => setInterestOpen(true)} aria-label="Edit interests">+</button>
          </div>
          <div className="rail-categories">
            {CATEGORIES.map((category) => (
              <button
                className={`rail-category ${activeCategory === category.id ? "selected" : ""}`}
                key={category.id}
                onClick={() => { setActiveCategory(activeCategory === category.id ? "all" : category.id); setSection("feed"); }}
              >
                <i style={{ backgroundColor: category.color }} />
                <span>{category.shortLabel}</span>
                <small>{Math.round(profile.vector[category.id])}</small>
              </button>
            ))}
          </div>

          <button className="rail-create-card" onClick={() => setComposerOpen(true)}>
            <span className="rail-create-icon"><Plus size={17} weight="bold" /></span>
            <strong>Make something</strong>
            <small>A thought, a story, a link.</small>
          </button>

          <div className="rail-footer">
            <span className="rail-status-dot" /> A quieter corner of the internet.
          </div>
        </aside>

        <main className="feed-main">
          <div className="feed-topline">
            <div className="feed-heading">
              <span className="eyebrow"><span className="live-dot" /> PERSONALIZED FOR YOU</span>
              <h1>{sectionTitle}<span>.</span></h1>
              <p>{section === "saved" ? "The posts you wanted to keep close." : "A little less noise. A lot more you."}</p>
            </div>
            <div className="feed-toolbar">
              <button className="filter-button" onClick={() => setInterestOpen(true)}>
                <WaveSine size={15} /> <span>Signal active</span> <ArrowDown size={13} />
              </button>
              <span className="feed-count"><b>{visiblePosts.length.toString().padStart(2, "0")}</b> posts</span>
            </div>
          </div>

          <div className="feed-filter-row">
            <button className={`filter-chip ${activeCategory === "all" ? "active" : ""}`} onClick={() => setActiveCategory("all")}>All signals</button>
            {CATEGORIES.map((category) => (
              <button
                className={`filter-chip ${activeCategory === category.id ? "active" : ""}`}
                key={category.id}
                onClick={() => setActiveCategory(activeCategory === category.id ? "all" : category.id)}
              >
                <i style={{ backgroundColor: category.color }} />{category.shortLabel}
              </button>
            ))}
          </div>

          {visiblePosts.length > 0 ? (
            <div className="masonry-feed">
              {visiblePosts.map((post) => (
                <PostCard
                  key={post.id}
                  post={post}
                  profile={profile}
                  onFeedback={handleFeedback}
                  saved={savedIds.includes(post.id)}
                  onToggleSaved={toggleSaved}
                />
              ))}
              {section !== "saved" && (
                <button className="feed-end-card" onClick={() => chooseSection("discover")}>
                  <span className="end-card-icon"><Sparkle size={17} weight="fill" /></span>
                  <span><strong>Keep following your curiosity.</strong><small>Explore more posts in your orbit.</small></span>
                  <ArrowRight size={17} />
                </button>
              )}
            </div>
          ) : (
            <div className="empty-state">
              <span className="empty-state-icon"><BookmarkSimple size={23} /></span>
              <h2>{section === "saved" ? "Nothing saved yet." : "No posts in this signal."}</h2>
              <p>{section === "saved" ? "Save a post to keep it in your collection." : "Try another topic or adjust your interest prompt."}</p>
              <button className="button button-secondary" onClick={() => section === "saved" ? chooseSection("feed") : setInterestOpen(true)}>
                {section === "saved" ? "Back to your feed" : "Tune your interests"}
              </button>
            </div>
          )}

          <div className="mobile-interest-card">
            <InterestPanel profile={profile} onEdit={() => setInterestOpen(true)} />
          </div>
        </main>

        <div className="right-rail">
          <InterestPanel profile={profile} onEdit={() => setInterestOpen(true)} />
          <div className="signal-tip">
            <div className="tip-heading"><span><Sparkle size={13} weight="fill" /></span> A small reminder</div>
            <p>Your feed is yours to shape. A quick <b>resonate</b> or <b>banish</b> helps Aura learn what feels right.</p>
            <button onClick={() => setInterestOpen(true)}>Adjust your signal <ArrowRight size={13} /></button>
          </div>
          <div className="footer-links">
            <span>AURA · EARLY ACCESS</span>
            <span>Made for curiosity <span className="tiny-heart">✳</span></span>
          </div>
        </div>
      </div>

      <nav className="mobile-nav" aria-label="Mobile navigation">
        <button className={section === "feed" ? "active" : ""} onClick={() => chooseSection("feed")}><House size={20} weight={section === "feed" ? "fill" : "regular"} /><span>Feed</span></button>
        <button className={section === "discover" ? "active" : ""} onClick={() => chooseSection("discover")}><Compass size={20} weight={section === "discover" ? "fill" : "regular"} /><span>Explore</span></button>
        <button className="mobile-compose" onClick={() => setComposerOpen(true)} aria-label="Create post"><Plus size={22} weight="bold" /></button>
        <button className={section === "saved" ? "active" : ""} onClick={() => chooseSection("saved")}><BookmarkSimple size={20} weight={section === "saved" ? "fill" : "regular"} /><span>Saved</span></button>
        <button onClick={() => setInterestOpen(true)}><WaveSine size={20} /><span>DNA</span></button>
      </nav>

      {interestOpen && (
        <InterestModal
          profile={profile}
          onClose={() => setInterestOpen(false)}
          onSave={(nextProfile) => {
            setProfile(nextProfile);
            saveProfile(nextProfile);
            setInterestOpen(false);
            notify("Your Interest DNA has been updated");
          }}
        />
      )}
      {composerOpen && (
        <ComposerModal
          onClose={() => setComposerOpen(false)}
          onPublish={addPost}
        />
      )}
      {toast && <div className="toast-message"><span className="toast-dot" />{toast}</div>}
    </div>
  );
}
