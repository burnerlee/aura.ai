# Aura — Pitch Deck Brief (self-explanatory submission)

**Hook:** *Feeds guess. Aura asks.*
**Tagline:** *A little less noise. A lot more you.*
**Audience:** a PPT designer (builds the slides) and Google engineers (read the deck on their own, with nobody presenting).
**Tone:** product-first, playful, skimmable — but every slide must stand alone and explain itself.

---

## How to read this document

This deck will be **submitted and read, not presented**. There is no speaker to fill gaps, so every slide carries its own explanation.

Each slide block contains:

- **Headline** — the one big line.
- **Subline** — one supporting sentence.
- **Body** — the explanatory copy that goes *on the slide*. Written as short paragraphs and bullets a reader can follow without context. This is the main content.
- **Callout** — a boxed side note (a "did you know", a definition, a number, or a reviewer-facing detail). Also on the slide.
- **Visual** — what the designer draws or screenshots.

Design guidance: body copy should sit at 14–18 pt in a two-column layout (text left, visual right) so slides stay readable without becoming walls of text. Tables are content, not decoration — keep them.

Everything described as "implemented" exists in this repository today. Anything aspirational is labelled *roadmap*.

**Length:** 20 slides + 2 appendix slides.

### Visual identity (from the shipped app)

| Token | Value |
|---|---|
| Background | `#0a0c0e` (deep), `#020203` (deepest) |
| Accent | Cyan `#22d3ee` |
| Secondary | Mint `#9be9c5`, AI violet `#a855f7` |
| Display font | Manrope |
| Label / mono font | DM Mono |
| Signature UI motifs | Interest DNA ring, match-% chips, Resonate / Banish buttons, "Why this?" badge, Aura chat bubble |

Mood: calm dark UI, soft glow, generous whitespace. The deck should feel like the opposite of a doomscroll.

---

## 1. Meet Aura

### Slide 1 — Title

**Headline:** Meet Aura.
**Subline:** A little less noise. A lot more you.

**Body:**

Aura is a personal reading feed that gets to know you by *talking* to you, finds long-form content from across the internet that fits what you said, and shows you — on every single card — why it chose it.

It was built on two convictions: a feed should be able to explain itself, and it should get better because you told it something, not because it tracked you.

**Callout:** Built on published research — DESSERT (NeurIPS 2023) for ranking, and a 2024 PLoS ONE study on dynamic user modelling — adapted for long-form text and deliberately run **without reinforcement learning**.

**Visual:** Black to deep-navy gradient, the `aura.` wordmark centred with a soft cyan halo, a faint Interest DNA ring behind it. Body text small, bottom-left. The slide should feel like an exhale.

---

## 2. What is Aura?

### Slide 2 — Aura in three verbs

**Headline:** Talk. Read. Tune.
**Subline:** A feed that learns you through a conversation, not a checkbox wall.

**Body:**

**1. Talk.** When you open Aura, you don't pick topics from a grid. You chat with it. Aura asks short questions with tap-friendly options — *"What pulls you in?"*, *"Deep dives or quick hits?"*, *"Anything you want less of?"* — and after three to five exchanges it drafts your **Interest DNA**: the topics you lean into, the things you want dialled down, your preferred depth and tone. You review it and tap Apply. The whole thing takes about 20 seconds, and Aura remembers it next time.

**2. Read.** Your **For You** feed ranks long-form posts — newsletters, essays, analysis — against that Interest DNA. Every card shows a **match %** and a **"Why this?"** badge that names the specific interest it matched (*"matched your AI/ML interest"*). You are never left guessing why something appeared.

**3. Tune.** Under every post: **Resonate** or **Banish**. Optionally add a reason chip — *less hype*, *too long*, *not this author*, *already know this*. Each tap visibly moves your Interest DNA ring, and the next feed reflects it. No retraining, no waiting days for the algorithm to "catch up".

**Callout:** The three verbs are the whole product. Everything else in this deck explains how we make each one honest: how the conversation becomes a ranking signal, how the ranking is computed, and how a tap changes it.

**Visual:** Three app screenshots in a row: the chat modal → the For You feed with match chips → the Resonate moment with a "+7 AI/ML" packet flying into the DNA ring. Each screenshot captioned with its verb.

### Slide 3 — What's inside

**Headline:** Everything in Aura serves one reader: you.
**Subline:** Nine surfaces, all wired to the same recommendation engine.

**Body:**

| Surface | What it does | Why it exists |
|---|---|---|
| **Chat with Aura** | Conversational onboarding that drafts your Interest DNA; remembers prior chats | Cold start without a checkbox wall |
| **For You** | Personalized feed ranked by set-to-set similarity | The main reading surface |
| **Why this?** | Per-card attribution: *"matched your AI/ML interest"* | Transparency on every rank |
| **Resonate / Banish** | Explicit feedback with optional reason chips | Precise, visible control |
| **Pairwise** | "Which one?" — two cards from different interests, pick one | Learns *relative* preference cheaply |
| **More like this** | Seeds a search from any post's own content | Explore sideways from a hit |
| **Discover** | Popular and fresh posts across the whole corpus | Escape your own bubble |
| **Create** | Share a thought, write an article, or embed a link | Community voice, ranked on merit |
| **Saved** | Keep posts close | Reading list |

Every surface calls the same live API: feed, pairwise, events, tune, onboard, Aura chat, similar, discover, and create-post. There is one ranking brain behind all of them, so what you teach Aura in one place applies everywhere.

**Callout:** Interest DNA is editable. Open the chat any time and say *"less politics, more design"* — Aura rewrites the profile and the feed re-ranks immediately.

**Visual:** Dark grid of nine rounded tiles, each with a tiny screenshot crop. Cyan outline on the three signature tiles: Chat, Why this?, Resonate/Banish.

---

## 3. Problems with current social media sites

### Slide 4 — The doomscroll receipt

**Headline:** Your feed doesn't know you. It knows what keeps you scrolling.
**Subline:** Two minutes on a typical feed, itemised.

**Body:**

```
09:41  Sponsored post for something you'll never buy
09:41  Rage bait — 12k comments, zero information
09:42  "Sensitive content — tap to view"
09:42  A celebrity you don't follow
09:43  The same hot take, fourth time today
09:43  A 40-second video you watched because it autoplayed
09:44  ...
```

None of these items were chosen because they fit *you*. They were chosen because people like you, on average, kept scrolling past things like this. The feed is optimising a proxy — attention — and attention is cheapest to capture with outrage, novelty, and interruption.

The result is a familiar feeling: you put the phone down twenty minutes later, slightly worse, with nothing you'd want to read again.

**Callout:** *"Tired of doomscrolling?"* is the first line of Aura's launch video for a reason — it is the problem everybody already recognises.

**Visual:** Grey, desaturated, slightly motion-blurred feed cards streaming past in the background (same look as scene 1 of the brag video). The receipt in mono font on top.

### Slide 5 — Four design choices that broke the feed

**Headline:** It isn't an accident. It's four decisions.
**Subline:** Each one is reasonable on its own. Together they produce the doomscroll.

**Body:**

**1. Optimised for attention, not taste.** Ranking models learn from clicks, dwell time, and engagement. Those are proxies for interest, and they are easily gamed by outrage and clickbait. The model is not wrong — it is faithfully maximising the wrong thing.

**2. Cold start is a checkbox wall.** *"Pick 5 topics."* *"Follow 20 accounts."* Then the system guesses for weeks. You can say "technology" but you cannot say *"deep, sceptical writing about AI — and no product-launch hype."*

**3. The model is a black box.** There is no "why" on any card and no honest way to say *"less of this, more depth"* and watch the feed move. Feedback buttons exist, but they feel like they go nowhere.

**4. One post, one vector.** Under the hood, most recommenders squash each post into a single embedding. A 3,000-word essay about *climate policy and AI governance* becomes one point in space — it cannot match either theme precisely, so your feed fills with near-misses that are "about" the right thing but never quite land.

**Callout:** Problem 4 is a technical problem with a technical answer. It is the reason Aura is built on **vector-set search** (Slides 8–11) instead of single-vector nearest-neighbour search.

**Visual:** Four cards, each with a crossed-out icon (eyeball, checkbox grid, black box, single dot). Card 4 shows a long article collapsing into one small dot.

---

## 4. How Aura solves it

### Slide 6 — Pain → fix

**Headline:** Aura asks. Aura explains. Aura listens. Aura curates.
**Subline:** Every broken decision from the last slide, replaced.

**Body:**

| Feeds today | Aura |
|---|---|
| Learns from clicks and dwell | **Asks you.** A 20-second chat produces an editable Interest DNA — the primary signal, not a guess from behaviour. |
| Checkbox onboarding | **Conversation.** Tap-friendly options, natural-language answers, memory across visits. You can say *"less hype"* and it means something. |
| Black-box ranking | **"Why this?" on every card** plus a visible match %. The reason names the specific interest that matched. |
| Feedback goes nowhere | **Resonate / Banish + reason chips** update your profile instantly and visibly move the Interest DNA ring. |
| Engagement-maximising reinforcement learning | **Deterministic ranking. Zero RL.** Every rank is a reproducible function of your profile — which is what makes "Why this?" possible. |
| One vector per post | **A post is a set of meanings; you are a set of interests.** Aura matches sets to sets, so a long essay can match on the part of it you actually care about. |
| Noise from everywhere | **Curated sources + layered filters** (Slide 18). Content comes from ranked publications, is cleaned on the way in, and is shaped by what you said no to. |

**Callout:** "Zero reinforcement learning" is a deliberate design stance, not a shortcut. Slide 13 explains why we removed the RL policy from the research we built on.

**Visual:** Left column greyed out and blurred; right column crisp, cyan-accented. A single arrow between them.

### Slide 7 — The 20-second onboarding, step by step

**Headline:** Say what you like. Watch the feed change.
**Subline:** One conversation takes a post from 6% match to 71%.

**Body:**

Here is a real onboarding flow from the app:

1. **Aura:** *"Hey — I'm Aura. One honest prompt and I'll start building your Interest DNA. What pulls you in?"* → user taps **AI & ML**.
2. **Aura:** *"Nice. What vibe do you want more of — deep dives, quick hits, or something in between?"* → **Deep, thoughtful pieces**.
3. **Aura:** *"Got it. Anything you want less of — hype, generic tech news, or something else?"* → **Less hype / clickbait**.
4. **Aura:** *"I think I've got you. Here's a profile I'll use to tune your feed — tap Apply when it feels right."* → **Apply**.

What Aura produced behind that last message is a structured profile: topics (*AI/ML*), anti-topics (*hype*), preferred styles (*deep, analytical*), preferred emotions, and a weight for each theme. That profile is summarised in one sentence, embedded into a **persona vector**, and added to your query set on the spot.

The same post card, before and after: the match chip goes from **6%** to **71%**, and "Why this?" now reads *"matched your persona interest"*. No retraining happened. The ranking function simply had better input.

**Callout:** If you come back tomorrow, Aura greets you with *"Welcome back — I still remember our chat about AI and deep pieces. Refine it, or explore a new angle?"* The conversation is stored with your profile, so you never restart onboarding.

**Visual:** Real chat-modal screenshots with cursor taps along the top; the same post card shown twice below (6% → 71%) with the match chip animating.

---

## 5. The recommendation engine that powers Aura

> Slides 8–14 are written for the engineers reviewing this. They explain what the system does, which papers it is built on, what those papers found, and exactly how we adapted them. Equations are collected in Appendix A.

### Slide 8 — The core idea: sets to sets

**Headline:** A post is a set of meanings. A reader is a set of interests. Match sets to sets.
**Subline:** The single change that fixes "one post, one vector".

**Body:**

**How posts are represented.** Every post is split into chunks: a *head* chunk (title + subtitle + summary) and overlapping *body* windows of about 300 words with a 40-word overlap, up to 32 chunks per post. Each chunk is embedded separately with Gemini (768 dimensions). A post is therefore a **set** of chunk vectors — one per passage — not one averaged point. A 3,000-word essay that discusses climate policy for ten paragraphs and AI governance for eight keeps both themes intact.

**How readers are represented.** You are also a set — a **weighted, labelled set of query vectors**: your current **state** (what you've liked recently, attention-weighted), up to six **interest centroids** (clusters of what you've liked, each with a label such as *AI/ML* or *design*), and a **persona** vector (the embedded summary of what you told Aura in chat). Each vector has a weight that says how much it should count.

**How they are scored.** For each reader vector, find the single best-matching chunk in the post (the **MaxSim** operation). Then take the weighted mean of those best matches across all your vectors. This is exactly the structured score from the DESSERT paper — `F = A ∘ σ` with `σ = max` and `A = weighted mean` — and the same family as ColBERT's late interaction.

**Why it matters.** Single-vector search cannot tell *"mentions AI once"* from *"is about AI"*. Set-to-set scoring can, because it asks "does *some passage* of this post strongly match *this specific interest* of yours?" — and because the answer is per-interest, Aura can also say which interest won. That is where "Why this?" comes from.

**Callout:** **Set-to-set search** (vector set search with vector set queries) is a formal retrieval problem studied in DESSERT (NeurIPS 2023). Aura is an application of that problem to long-form recommendation.

**Visual:** Left: one article fanning out into several glowing dots labelled with passage topics. Right: one reader fanning into labelled dots (*state*, *AI/ML*, *design*, *persona*). Between them: thin lines from each reader dot to its single brightest article dot.

### Slide 9 — Architecture: from the open internet to your feed

**Headline:** Five hops from a public website to your For You feed.
**Subline:** The system as drawn on our whiteboard, with the two open questions answered.

**Body:**

```
 Connectors / Agents          New Post (Create)
        │                            │
        ▼                            ▼
   MongoDB `posts`  ◄── one canonical document shape for every source
        │
        ▼
 Embedding worker: adapter → chunker → Gemini embed → LLM facets
        │
        ▼
   Qdrant `posts`: named vectors  chunks (multi-vector, MaxSim) · doc · facet
        │
        ▼
 Query engine: Stage 1 ANN filter (doc / facet) → Stage 2 exact set-to-set MaxSim
               − negative penalty × recency → author cap → MMR → (optional LLM explain)
        │
        ▼
   FastAPI  ⇄  Express BFF  ⇄  Aura web (For You · Chat · Why this? · Create · Discover)
        ▲
   User profile: events → weights → state ⊕ centroids ⊕ persona → QuerySet
```

**Hop 1 — Collect.** Connectors and crawler agents (Slide 15) fetch posts from external platforms. User-created posts enter through the same door.

**Hop 2 — Store.** Everything lands in MongoDB as one canonical `ContentDocument`, regardless of source.

**Hop 3 — Embed.** A worker picks up pending posts, cleans them through a source-specific adapter, chunks them, embeds each chunk with Gemini, asks an LLM for facets (topics, style, emotion, personality appeal), and writes the vectors to Qdrant.

**Hop 4 — Rank.** The query engine runs two stages: a cheap approximate filter to find candidates, then an exact set-to-set score on those candidates, followed by penalties, recency, and diversity.

**Hop 5 — Serve.** A FastAPI service exposes feed, search, events, chat; a thin Express BFF sits in front of the React web app.

**Callout — the two whiteboard questions:**

*"Document structure?"* One shape for every source: identity (`source`, `external_id`, `url`), content (`title`, `content_text`, `summary`), author, taxonomy (`tags`, `categories`), engagement counts, and vector hooks (`embedding_status`, `chunk_count`, `facets`, `content_hash`). Unique on `(source, external_id)`. Re-scrapes only `$set` scraped fields and `$setOnInsert` the pending status, so a crawl can never erase an embedding.

*"What are the labels / identifiers on the embedding side?"* Each Qdrant point has three named vectors — `chunks` (the set), `doc` (mean of chunks, for fast filtering), `facet` (embedded facet summary) — and a payload with `post_id`, author, source, categories, `published_at`, `word_count`, and facet fields. Each *query* vector carries a `kind` and a human-readable `label` (`state`, a centroid label like *AI/ML*, `persona`, `query`, `seed`). That label is literally what "Why this?" displays.

**Visual:** Clean vertical pipeline, five boxes, cyan arrows. The two whiteboard questions as callout boxes beside the Database and Embedding boxes.

### Slide 10 — Research base #1: DESSERT — what the paper found

**Headline:** DESSERT: searching sets of vectors with set queries, fast.
**Citation:** Engels, Coleman, Lakshman, Shrivastava. *DESSERT: An Efficient Algorithm for Vector Set Search with Vector Set Queries.* NeurIPS 2023. arXiv:2210.15748.

**Body:**

**The problem it formalises.** Given a collection of vector *sets* `S_1 … S_N` and a query that is also a set `Q`, return the set that maximises a structured relevance score `F(Q, S) = A({ σ({ sim(q, x) : x ∈ S }) : q ∈ Q })`. The inner aggregation `σ` (usually `max`) scores one query vector against a whole set; the outer aggregation `A` (sum or weighted mean) combines across query vectors. ColBERT's late interaction is the special case `sim = cosine`, `σ = max`, `A = sum`.

**Why ordinary nearest-neighbour search fails.** The paper gives two reasons. First, a single strong match between one query vector and one set vector does not mean the sets are similar — a shared keyword creates a false positive. Second, flattening every vector into one index turns a million documents of a thousand tokens each into a billion-point search.

**The algorithm.** Each set is sketched with `L` locality-sensitive-hash tables. At query time, similarity between a query vector and each set vector is estimated by counting hash collisions; `σ` and `A` are then applied to the estimates. A cheap **filter stage** — a k-means centroid inverted index, probing `filter_probe` centroids per query vector and keeping the top `filter_k` sets — narrows the collection before scoring.

**The guarantees.** For any `(α, β)`-maximal `σ` (max is the canonical case) and weighted-linear `A`, `L = O(log(N · m_q · m / δ))` tables suffice to return the top set with probability `1 − δ`. Query time is `O(m_q · d · log(…) + m_q · N · log(…))` against brute force `O(m_q · m · N · d)`.

**The results.** 10–50× faster than optimised brute force on synthetic sets. On MS MARCO, **2–5× faster than PLAID** (ColBERT's optimised engine): 9.5 ms vs 45.1 ms at k=10, 22.7 ms vs 100 ms at k=1000, with a few points of recall loss. Similar wins on LoTTE. A single-vector **ScaNN baseline reached only 0.77 Recall@1000** — the paper's own evidence that single vectors are not enough.

**Callout:** The lesson we took: represent documents as sets, score with `max` inside and a weighted mean outside, and always run a cheap filter before the exact score.

**Visual:** Left: the paper's Figure-1 concept (sets → hash sketches → collision counts). Right: a mini bar chart of the MS MARCO latencies (DESSERT 9.5 / 15.5 ms vs PLAID 45.1 ms).

### Slide 11 — How Aura adapted DESSERT

**Headline:** We kept the problem and the two-stage shape. We swapped the index.
**Subline:** Chunks instead of tokens, Qdrant instead of LSH sketches — and everything else stays.

**Body:**

| DESSERT | Aura (implemented) | Why |
|---|---|---|
| Document = set of token embeddings | Post = set of **chunk** embeddings (head + 300-word windows, 40-word overlap, ≤ 32 chunks) | Keeps sets small (`m ≤ 32`) so exact scoring is cheap, and each element is a readable passage that can serve as evidence |
| Query = set of vectors | Reader = labelled, weighted `QuerySet` (state · centroids · persona). Free-text search and "More like this" build their own query sets (one embedded query, or the seed post's chunks) | One scoring function serves feed, search, and similarity |
| `σ = max` (MaxSim) | `set_similarity(…, sigma="max")`; `softmax_mean` and `top_k_mean` also implemented | Max is the paper's canonical `(α,β)`-maximal case |
| `A` = sum / weighted linear mean | **Weighted mean**; weights encode how much each interest counts | Directly the Section 4.2 instantiation |
| Stage 1: k-means inverted index, top `filter_k` | Stage 1: **Qdrant HNSW ANN** on `doc` (mean of chunks) and `facet` vectors, `FILTER_K = 64` per reader vector; the union of hits is the candidate pool | Same role as the paper's lossy pre-filter, using a production vector DB |
| Stage 2: LSH sketch score (TinyTables) | Stage 2: **exact MaxSim** over fetched `chunks` multivectors | Our corpus is far below the 10⁶-set scale where sketches pay off; exact is simpler and gives exact attributions |
| Pure relevance score | `(F − 0.35 · negPenalty) × recency(half-life 30 d)` → author cap 3 → MMR (λ = 0.7) → optional LLM explain/rerank | A feed needs memory of dislikes, freshness, and variety on top of relevance |

**What falls out for free.** Because Stage 2 computes `σ` separately for every reader vector, the per-interest scores already exist. "Why this?" is just the label of the reader vector with the highest inner score. We did not add an explanation model; the explanation is a by-product of the ranking math.

**Callout:** *Roadmap:* if the corpus grows to the point where exact MaxSim dominates latency, DESSERT's LSH sketches are the drop-in replacement for Stage 2. The filter → rerank structure stays the same.

**Visual:** Three-column table with a colour code: mint = kept as-is, cyan = swapped, violet = added.

### Slide 12 — Research base #2: Social Image Recommendation — what the paper found

**Headline:** Preferences drift. Model the reader as a moving state.
**Citation:** Ahmadkhani S., Moghaddam M. E. *A social image recommendation system based on deep reinforcement learning.* PLoS ONE 19(4): e0300059, 2024.

**Body:**

**The problem it addresses.** Most social image recommenders assume preferences are fixed and struggle when a user has little history. Tastes drift, so the system should update after every interaction and should be able to start from almost nothing.

**Three feature families beyond raw visuals.** The authors extract, for every image: an **emotion** vector over eight classes (amusement, anger, awe, contentment, disgust, excitement, fear, sadness); a **personality appeal** vector over the Big Five traits (attributed, i.e. "what kind of person this appeals to"); and a **style** vector over 15 Flickr styles. Their fine-tuned EfficientNetB1 reached 66.7% emotion accuracy; VGG19 trait classifiers reached 58–64%. Ablations show each family improves recommendations over visual-only baselines.

**A new state representation (Equations 6–9).** This is the part we found most transferable. When the user likes a recommended item `x_i`, the new state is the average of that item and a **self-attention** over the user's liked history: compute `w'_ij = x_iᵀ x_j` against each previously liked `x_j`, normalise with softmax, and set `s = (x_i + Σ_j w_ij · x_j) / 2`. If the item was not liked, the state is simply the mean of the liked set. The system can start from a single liked item, which is the paper's answer to cold start.

**The policy.** On top of that state, an Actor-Critic **DDPG** agent chooses recommendations in an MDP with a ±1 like/dislike reward, a replay buffer, discount γ = 0.3, and a LASSO pre-filter each episode.

**The results.** Roughly **7–10% higher Recall@k and Precision@k** (top 100) than visual-only and style-only baselines on a 20-user / 4,000-image Flickr set, holding at 40 users. The authors also report that their method had the **highest training time** of all methods compared.

**Callout:** Two ideas travel well from images to text: describe each item by *how it feels and who it is for*, not only what it is about; and update the user's state with attention over their history rather than a flat average.

**Visual:** Left: the paper's Fig. 2 idea — one newly liked item attending over a row of previously liked items with weights. Right: three facet chips (Emotion · Personality · Style) and a "+7–10%" callout.

### Slide 13 — How Aura adapted it, and why we dropped the RL

**Headline:** We kept the facets and the attention state. We dropped the policy network.
**Subline:** Same user model, deterministic ranking.

**Body:**

| Paper | Aura (implemented) |
|---|---|
| Emotion / personality / style CNNs on images | **LLM facet extraction on text.** For every post, an LLM produces `PostFacets`: topics; styles from a fixed vocabulary (analytical, narrative, listicle, tutorial, opinion, humorous, investigative, personal, technical, news); the **same eight emotions** as scores; **Big Five appeal** in [0, 1]; reading level; audience; a one-line appeal |
| Characteristic vector per item | Facet text embedded → Qdrant `facet` vector (used in Stage-1 filtering); persona summary embedded → `persona_vector` (used in the reader's query set) |
| Self-attention state update (Eqs. 6–9) | `update_state()` — **identical structure**, run on the `doc` vectors of the last 50 liked posts after every positive event. On a like, state = (liked item + softmax-attention over liked history) / 2 |
| Liked / disliked memory | `positive_ids` → k-means **interest centroids** (k = 6) plus the state; `negative_ids` (last 30) → **negative penalty** subtracted at scoring time; "already know" → excluded from future feeds |
| Binary ±1 reward | **Layered event weights** (Slide 14): likes, saves, dwell, fast skips, not-interested, pairwise picks — each with its own weight and a version tag |
| Cold start from one liked image | **Aura chat** → persona vector in a single conversation; optional seed posts |
| Actor-Critic / DDPG / replay buffer | **Dropped.** Ranking is a deterministic function of the reader's `QuerySet`. |

**Why we removed the reinforcement learning:**

1. **Sample efficiency.** The paper trains 400 episodes × 100 recommendations per user with dense ±1 labels. Long-form readers give sparse, slow feedback — a handful of taps per session. An online policy would spend weeks exploring the wrong half of the corpus before it converged.
2. **Explainability is a product requirement.** "Why this?" must attribute a rank to a named interest. A deterministic scorer provides that exactly; a policy network's action vector does not.
3. **Offline evaluation without shipping risk.** Event weights are a versioned table (`default_v1` live; `hold_linear_v1`, `hold_log_v1` experimental). `scraper eval` and `scraper reweigh` compare versions on logged interactions. We can improve the model without live exploration on real users.
4. **The paper's own cost note.** Its RL stack had the highest training time of every method compared. The measurable wins came from the facets and the attention state — and we kept both.

**Callout:** The personalization is still *dynamic*. Every like re-runs the self-attention state update and re-clusters your interests; every tenth event or any "tune" re-synthesises your persona. What changed is that the *ranking* on top of that state is deterministic and inspectable.

**Visual:** Same kept / swapped / dropped colour code as Slide 11. A greyed-out, crossed-through chip reading "Actor · Critic · Replay buffer".

### Slide 14 — The reader as a query set: the live loop

**Headline:** Every tap edits the query. Nothing retrains.
**Subline:** How a Resonate becomes a different feed, in order.

**Body:**

```
Resonate / Banish / dwell / pairwise / tune / chat
        ↓
Event → weight (versioned table, right)
        ↓
Positive set ──► self-attention state   (weight 0.35, label "state")
            ──► interest centroids      (weight 0.4 × cluster weight, labels e.g. "AI/ML")
Negative set ──► negative penalty       (0.35 × max cosine to disliked posts)
Every 10 events or any tune ──► LLM persona refresh ──► persona vector (weight 0.25, label "persona")
        ↓
QuerySet = state ⊕ centroids ⊕ persona  →  engine.recommend(…)  →  For You
```

**Step by step.** (1) You tap Resonate on a post. (2) The event is logged with a weight from the table. (3) Because the weight is positive, the post's `doc` vector joins your positive set; the self-attention state update runs over your last 50 liked posts, and your interest centroids are re-clustered. (4) If this was your tenth weighted event — or if you typed a "tune" instruction — an LLM rewrites your persona from your liked and disliked titles, their facets, your reason chips, and your tune text, and the summary is re-embedded. (5) Your next feed request builds a fresh `QuerySet` from state, centroids, and persona, and the engine scores the corpus against it.

**The weight table (`default_v1`):**

| Signal | Weight |
|---|---|
| Resonate (strength 1 / 2) | +0.7 / +1.0 |
| Save | +1.0 |
| Share · click-through · open | +0.5 · +0.4 · +0.1 |
| Dwell (read ratio ≥ 0.15) | read_ratio × 0.6 |
| Fast skip (visible < 1 s) | −0.1 |
| Banish (strength 1 / 2) | −0.6 / −1.0 |
| Pairwise winner / loser | +0.5 / −0.3 |
| Reason chips | *topic* → adds to (anti-)topics · *too long* → 1,500-word cap · *author* → mute · *style* → preferred styles · *already know* → never show again |

**Callout:** Swipe pressure (`hold_ms`) is logged but **not** used by the live table. We keep it for offline analysis so we can test whether "pressed longer = meant it more" holds before trusting it in production.

**Visual:** Loop diagram on the left with the Interest DNA ring at its centre; the weight table on the right. One "+7 AI/ML" packet shown entering the ring.

---

## 6. How Aura collects interesting content for you

### Slide 15 — Meet the agents

**Headline:** Our agents never sleep.
**Subline:** Tech Geek, Sports Freak, Hollywood Gossip Queen and friends comb the internet 24/7 so you don't have to.

**Body:**

Aura doesn't wait for people to post inside it. A crew of category-scoped **crawler agents** goes out to the most-read publishing platforms on the internet — starting with Substack — and brings back the best long-form writing in each beat.

| Agent | Beat | What they bring back |
|---|---|---|
| **Tech Geek** | Technology | Deep dives on AI, systems, product, engineering culture |
| **Wall Street Watcher** | Finance · Business | Markets, strategy, operator essays |
| **Lab Coat** | Science | Research explainers, new findings, methods |
| **Sports Freak** | Sports | Tactics, analysis, long-form fandom |
| **Hollywood Gossip Queen** | Culture · Entertainment | Film, TV, music, celebrity |
| **Culture Vulture** | Culture · Arts | Criticism, essays, ideas |

**How an agent works.** Each agent owns one or more categories. It walks that category's public **leaderboards** on the platform — across tiers (*rising*, *all*, *paid*, *free*) — picks the top publications, and scrapes their recent posts. Every post is normalised into Aura's single `ContentDocument` shape and handed to the embedding worker. Agents are polite and idempotent: requests are rate-limited and retried with exponential back-off, and writes are upserts keyed on `(source, external_id)`, so an agent can loop forever without duplicating or damaging anything already indexed.

**Callout:** Tell Aura in chat that you're into *indie games* and *deep space*, and the agents' corners of the internet that match those themes start flowing into your feed. Content you never knew to search for finds you.

**Visual:** Six playful illustrated avatars on dark tiles (friendly robots with a cap, a lab coat, a headset, a microphone…). Behind them a faint world map with glowing dots funnelling into a single `aura.` node.

### Slide 16 — Many sources. One document. One index.

**Headline:** From the messy open web to one clean shape.
**Subline:** Why adding a new source is a small job, and why a crawl can never break the index.

**Body:**

**Connectors today.** Substack (publication scrape + category discovery) and Aura-native posts from the Create button (Slide 17). Both write the same `ContentDocument`.

**Adapters clean every post before it is embedded.** The Substack adapter skips anything that isn't a post, strips *"Thanks for reading / Subscribe / Share this post"* boilerplate, folds the publication's section into categories, and drops stubs under 40 words. A default adapter handles sources whose fields already line up.

**Adding a source** means implementing one `BaseConnector` (fetch + normalise) and — only if the field layout is unusual — one `ContentAdapter`. The registry picks them up automatically. *Roadmap:* Medium, RSS, arXiv, YouTube transcripts.

**The embedding worker** takes pending posts in batches: adapter → chunker → Gemini embeddings → LLM facets → Qdrant upsert → mark `embedding_status = ready`. Failures are recorded per post and retried; a content hash prevents re-embedding unchanged posts.

**Ownership boundaries.** Scrapers own scraped fields; the embedding worker owns vector fields. The storage layer enforces this: a re-scrape `$set`s only scraped fields and `$setOnInsert`s the pending status, so the most aggressive crawl cannot erase an embedding.

**Callout:** One shape in, one index out. The feed, search, "More like this", and Discover all read from the same Qdrant collection — a newsletter essay and a reader's 80-word thought are stored, embedded, and scored identically.

**Visual:** Source logos / icons on the left flowing into a single document card in the middle, then into the Qdrant index on the right. Small lock icons on the vector fields.

---

## 7. Share your own thoughts with the community

### Slide 17 — Create

**Headline:** Say it. Aura ranks it like everything else.
**Subline:** No follower count required.

**Body:**

Aura isn't only a reader. The **Create** button opens a composer with three modes:

1. **Short thought** — a few lines and a theme. For the idea you'd otherwise lose.
2. **Article** — title plus a markdown body with live preview. For the essay you've been meaning to write.
3. **Embed a link** — paste a URL; Aura pulls the preview card. For sharing something great you found elsewhere.

**What happens when you post.** Your post is stored as `source = aura` with `embedding_status = pending` — the same two fields every scraped post starts with. You see a toast: *"Posted — indexing…"*. The embedding worker picks it up, chunks it, embeds it, extracts its facets, and writes it to the index. Within seconds it is searchable, visible in Discover, and eligible for other readers' For You feeds.

**Why this matters.** Because your post goes through the exact same chunk → embed → facet path as a 3,000-word newsletter and is scored by the same set-to-set math, it competes on **relevance, not reach**. A sharp 80-word thought that matches a reader's interest precisely can outrank a famous author's filler for that reader. There is no follower graph to climb first.

**Callout:** Community posts carry the same "Why this?" attribution as everything else. If your thought shows up in someone's feed, they'll see exactly which of their interests it matched.

**Visual:** The real composer modal with its three tabs; beside it a small timeline showing a user post travelling the same pipeline as a scraped essay (MongoDB → embed → Qdrant → feed).

---

## 8. Content filtered so you don't have to worry

### Slide 18 — Quiet by design

**Headline:** Irrelevant and inappropriate content, filtered in layers.
**Subline:** Curated at the source. Cleaned on the way in. Shaped by you. Explained at the end.

**Body:**

| Layer | What it removes | How it works (implemented) |
|---|---|---|
| **1. Source curation** | Random accounts, spam, bots | Agents pull only from ranked category leaderboards of real publications — not from an open firehose |
| **2. Structural cleaning** | Stubs, non-posts, boilerplate | Adapters skip non-posts, strip subscribe/thanks text, drop bodies under 40 words |
| **3. Your filters** | Things *you* said no to | Banish → negative-memory penalty on anything similar; mute author / mute source; anti-topics from chat or reason chips; "already know" → never shown again; "too long" → 1,500-word cap; seen posts never repeat |
| **4. Facet-aware ranking** | Tone you didn't ask for | Every post carries emotion scores (anger, disgust, fear…), style labels (listicle / opinion vs analytical / investigative) and audience. These feed the `facet` index and the persona synthesis that learns what you dial down, so "less hype" has a concrete signal to act on |
| **5. Transparency** | Mystery | "Why this?" on every card; your Interest DNA is visible and editable; nothing is ranked that can't be explained |

**Reading the stack.** Layers 1 and 2 decide what *enters* the system at all. Layer 3 is personal: it is built entirely from things you explicitly told Aura, and it is the strongest filter because it is yours. Layer 4 is what makes vague preferences like "less hype" or "calmer" actionable — the facets give the system a vocabulary for tone, not just topic. Layer 5 is the check on everything above it: if a post gets through, you can see why, and you can act on it.

**Callout — what this is and isn't.** Today's safety story is *curation + cleaning + personal control + facet-aware ranking + transparency*. It is **not** a dedicated moderation classifier. Because every post already has LLM-extracted emotion and style facets, adding explicit safety labels and a hard policy filter is a schema-compatible next step (*roadmap*). We would rather state that plainly than overclaim.

**Visual:** Five translucent horizontal layers stacked like a filter stack; grey noise particles enter at the top and only a few clean cyan cards reach the bottom. Each layer labelled.

---

## Closing

### Slide 19 — Feeds guess. Aura asks.

**Headline:** Feeds guess. Aura asks.
**Subline:** Set-to-set ranking · LLM personas · zero reinforcement learning.

**Body:**

**What Aura is.** A personal long-form feed that learns you through a conversation, ranks posts as sets of meanings against you as a set of interests, explains every rank, and lets you correct it with a tap.

**What it is built on.** DESSERT's formulation of vector-set search (NeurIPS 2023) for the ranking core; the facet triad and self-attention state from Ahmadkhani & Moghaddam (PLoS ONE 2024) for the user model — with the reinforcement-learning policy deliberately removed in favour of deterministic, attributable scoring.

**What is implemented today.** Substack crawling with category agents, the canonical document pipeline, Gemini chunk embeddings and LLM facets in Qdrant, the two-stage set-to-set engine, the full feedback loop (events → state → centroids → persona), conversational onboarding with memory, Create, Discover, Pairwise, "More like this", and "Why this?" — all wired through a live API to the Aura web app.

**Where we'd value review.** (1) Is chunk-level late interaction the right granularity for long-form, or should we go finer? (2) At what corpus scale does DESSERT's LSH sketch stage become worth adding over exact MaxSim in Qdrant? (3) How should LLM-extracted facets be calibrated against human labels before they are trusted for hard safety filtering?

**Visual:** The `aura.` wordmark, the tagline *"A little less noise. A lot more you."*, and a QR / link to the demo video. Body copy in a quiet column on the left.

### Slide 20 — Roadmap

**Headline:** What's next.
**Subline:** Every item below plugs into the existing shape — no rewrites.

**Body:**

| Area | Next | Why it fits |
|---|---|---|
| Connectors | Medium, RSS, arXiv, YouTube transcripts | One `BaseConnector` each; same `ContentDocument` |
| Agents | Scheduled per-category crawl loops with freshness targets | Crawls are already idempotent and rate-limited |
| Retrieval | DESSERT-style LSH sketches for Stage 2 at scale | Filter → rerank structure already in place |
| Safety | Explicit safety facets + hard policy filter; calibrate LLM facets against human labels | Facets already extracted per post |
| Evaluation | Offline nDCG and pairwise win-rate on logged interactions; A/B weight tables | Events are logged with weight versions today |
| Privacy | On-device persona draft; interaction retention policy | Persona is a short text + one vector |

**Visual:** Six tiles, each with a small icon and a "fits because…" footnote.

---

## Appendix A — Equations (backup slide)

**Headline:** The math on one page.

**DESSERT relevance score (Engels et al., Def. 1.1 and Sec. 4.2).** The query `Q` and the document `S` are both sets of vectors. For each query vector, take its maximum cosine similarity to any document vector; then take the weighted mean across query vectors.

\[
F(Q,S) = A\big(\{\sigma(\{\mathrm{sim}(q,x) : x \in S\}) : q \in Q\}\big),
\qquad
\sigma = \max,\qquad
A = \frac{1}{\sum_j w_j}\sum_j w_j\,\sigma(\cdot)
\]

**Aura production score (`src/scraper/query/engine.py`, `scoring.py`).** Subtract a penalty proportional to how close the post is to anything you banished, then decay by age with a 30-day half-life.

\[
\mathrm{final}(Q,S) = \Big(F(Q,S) - 0.35\cdot\max_{n \in \mathrm{Neg}} \cos(\bar S, n)\Big)\cdot 2^{-\mathrm{age}_{\mathrm{days}}/30}
\]

Then: at most 3 posts per author → MMR with \(\lambda = 0.7\) for list diversity → optional LLM rerank of the top 10.

**"Why this?" attribution.** The label shown is that of the reader vector whose best-chunk match was highest.

\[
\mathrm{label}^\star = \arg\max_{q \in Q}\ \sigma(\{\cos(q,x): x \in S\})
\]

**Social Image Rec state update (Ahmadkhani & Moghaddam, Eqs. 6–9; `src/scraper/profile/state.py`).** On a like, the new state is the average of the liked item and a softmax-attention over the liked history.

\[
w'_{ij} = x_i^\top x_j,\qquad
w_{ij} = \frac{e^{w'_{ij}}}{\sum_j e^{w'_{ij}}},\qquad
s = \frac{x_i + \sum_j w_{ij}\,x_j}{2}\ \ (\text{on like}),\qquad
s = \mathrm{mean}(\mathrm{PositiveState})\ \ (\text{otherwise})
\]

**Reader query set (`build_query_set`).** Each entry is (vector, weight, label).

\[
Q = \{(s, 0.35, \text{"state"})\}\ \cup\ \{(c_k, 0.4\,w_k, \ell_k)\}_{k \le 6}\ \cup\ \{(p, 0.25, \text{"persona"})\}
\]

---

## Appendix B — Implementation facts (backup slide)

**Headline:** Numbers a reviewer may ask about.

| Question | Answer |
|---|---|
| Embedding model | Gemini embeddings, 768-d (MRL truncation) |
| LLM for facets / persona / chat | Gemini 2.5 Flash (via Gemini API or LiteLLM) |
| Chunking | head chunk + 300-word windows, 40-word overlap, ≤ 32 chunks, ≥ 40-word bodies |
| Vector store | Qdrant, named vectors `chunks` (multivector, MAX_SIM), `doc`, `facet`, optional `image` |
| Stage-1 candidates | `FILTER_K = 64` per reader vector, union of hits |
| Diversity | author cap 3, MMR λ = 0.7 |
| Recency | half-life 30 days, multiplicative |
| Negative memory | last 30 banished posts, penalty scale 0.35 |
| Interest centroids | k-means-style, k = 6, over last 50 liked `doc` vectors |
| Persona refresh | every 10 weighted events, or on any *tune* |
| Weight versions | `default_v1` (live), `hold_linear_v1`, `hold_log_v1` (offline) |
| Storage | MongoDB `posts`, `users`, `interactions` |
| API | FastAPI: `/search`, `/discover`, `/posts`, `/posts/{id}/similar`, `/users/{id}/feed`, `/pair`, `/events`, `/tune`, `/onboard`, `/profile`, `/persona/refresh`, `/aura/chat` |
| Front end | React + Vite (`aura-web`), Express BFF, Orval-generated client from OpenAPI |

---

## Appendix C — References

1. Joshua Engels, Benjamin Coleman, Vihan Lakshman, Anshumali Shrivastava. **DESSERT: An Efficient Algorithm for Vector Set Search with Vector Set Queries.** NeurIPS 2023. arXiv:2210.15748. Code: github.com/ThirdAIResearch/Dessert
2. Somaye Ahmadkhani, Mohsen Ebrahimi Moghaddam. **A social image recommendation system based on deep reinforcement learning.** PLoS ONE 19(4): e0300059, 2024. doi:10.1371/journal.pone.0300059
3. Omar Khattab, Matei Zaharia. **ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT.** SIGIR 2020. (The late-interaction instance DESSERT generalises; Aura's chunk-level MaxSim is in this family.)
4. This repository: `README.md`, `src/scraper/query/`, `src/scraper/profile/`, `src/scraper/embedding/`, `src/scraper/discovery/`, `web/artifacts/aura-web/`.

---

## Appendix D — Designer checklist

**Slide order**

1. Meet Aura (title)
2. Talk · Read · Tune
3. What's inside
4. The doomscroll receipt
5. Four design choices that broke the feed
6. Pain → fix
7. The 20-second onboarding
8. Core idea — sets to sets
9. Architecture (whiteboard)
10. DESSERT — findings
11. DESSERT → Aura
12. Social Image Rec — findings
13. Social Image Rec → Aura, why no RL
14. The reader as a query set + weight table
15. Meet the agents
16. Many sources, one document
17. Create
18. Quiet by design (filters)
19. Closing + review questions
20. Roadmap
A. Equations (backup)
B. Implementation facts (backup)

**Layout rules for a read-only deck**

- Two-column default: body text left (≈55%), visual right (≈45%). Headline full width.
- Body copy 14–18 pt; never below 12 pt. If it doesn't fit, split the slide — do not shrink the text.
- Callouts are boxed, cyan-bordered, placed under the visual.
- Tables on Slides 3, 6, 11, 13, 14, 15, 18 and 20 *are* the content; keep every row, style them as cards if needed.
- Use the app's real screenshots wherever a UI is mentioned. Demo mode (`make web-ui-demo`) gives a fully populated feed.
- Bold the first phrase of each paragraph so a skimmer can read only the bold and still follow the story.

---

## Appendix E — One-paragraph abstract (for the submission form)

Aura is a personal reading feed that learns a user through a short conversation instead of a checkbox wall, then ranks long-form posts gathered from across the internet by category-scoped crawler agents. Every post is represented as a set of chunk embeddings plus LLM-extracted style, emotion and personality facets; every reader is a weighted, labelled set of interest vectors (self-attention state, interest centroids, and an LLM-synthesised persona). Candidates are retrieved with a cheap document-level ANN filter and re-ranked with exact set-to-set MaxSim, following the DESSERT formulation of vector-set search, with a negative-memory penalty, recency, author diversity and MMR. User modelling adapts the facet triad and self-attention state update from recent social image recommendation research while deliberately omitting its reinforcement-learning policy, so every rank stays deterministic and attributable: each card can answer "Why this?", every Resonate or Banish visibly updates the user's Interest DNA, and users can publish their own posts into the same index on equal footing.
