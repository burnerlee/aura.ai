# Content Scraper + Recommendation Pipeline

Python multi-connector scraper that pulls posts from external sources into MongoDB, embeds them as multi-vector sets in Qdrant (Gemini), and serves personalized recommendations via a set-to-set query engine and LLM-synthesized user personas. No reinforcement learning.

## Architecture

```
Connector → MongoDB posts → ContentAdapter → EmbeddableContent
                                              ↓
                                    Chunker + Facets (LLM)
                                              ↓
                         Qdrant (chunks MaxSim, doc, facet)
                                              ↓
                    Query engine (ANN filter → set-to-set F=A∘σ)
                                              ↓
                         FastAPI / CLI  ←  User profile
                         (events, feed, persona, tune)
```

| Layer | Role |
|-------|------|
| **Connectors** | Source-specific fetch + normalize → `ContentDocument` |
| **Adapters** | Raw Mongo dict → typed `EmbeddableContent` (or `SkipReason`) |
| **Embedding** | Chunk + Gemini embed + LLM facets → Qdrant multivectors |
| **Query engine** | DESSERT-style two-stage retrieval (doc ANN → chunk MaxSim) |
| **Profile** | Implicit/explicit feedback → state, centroids, persona (no RL) |

### Paper mapping

- **DESSERT**: each post is a *set* of chunk embeddings; queries/users are weighted vector sets; score with MaxSim (`σ=max`) then weighted mean (`A`). Stage-1 ANN on `doc` vectors is the paper’s cheap filter; stage-2 Exact MaxSim rerank uses Qdrant multivectors + numpy for weights/negatives.
- **Social Image Rec (non-RL)**: style/emotion/personality facets via LLM; self-attention state update (Eq. 6–9); characteristic vector → our profile `QuerySet`; liked/disliked memory → negative vector set. Actor-Critic/DDPG dropped.

### Schema (MongoDB `posts`)

- **Identity:** `source`, `external_id`, `url`, `embed_url`, `canonical_url`
- **Content:** `title`, `subtitle`, `content`, `content_html`, `content_text`, `summary`
- **Author / taxonomy / engagement:** as before
- **Vector hooks:** `embedding_status`, `embedding_id`, `embedding_model`, `embedded_at`, `content_hash`, `chunk_count`, `facets`, `embedding_error`

Scrape upserts use `$set` of scraped fields only and `$setOnInsert: {embedding_status: pending}` so re-scrapes do not wipe embeddings.

### Qdrant collection `posts`

Named vectors: `chunks` (multivector MAX_SIM), `doc` (mean of chunks, HNSW), `facet`, `image` (optional). Payload carries `post_id`, filters, and facet summary fields.

## Prerequisites

- Python 3.11+
- Docker + Docker Compose
- Make
- `GEMINI_API_KEY` in `.env` (for embed / facets / persona / search)

## Quick start

```bash
make setup                    # .env, venv, deps, MongoDB, Qdrant
make scrape-substack SOURCE=platformer LIMIT=5
make list-docs LIMIT=5

# Dry-run adapter (no API calls)
scraper adapt substack <external_id>

# Embed pending posts (needs GEMINI_API_KEY)
make embed LIMIT=16
make embed-status

# Search / feed / API
make search QUERY="climate policy" K=5
scraper serve                 # http://localhost:8000/docs

# Web UI (three terminals)
make serve                    # Python API :8000
make web-api                  # Express BFF :5001 → :8000
make web-ui                   # aura-web :5173 (proxy /api → BFF)
# Offline UI only: make web-ui-demo   # VITE_USE_DEMO=1
```

### Manual smoke checklist

1. `make scrape-substack SOURCE=platformer LIMIT=5 && make embed LIMIT=16`
2. `make serve` + `make web-api` + `make web-ui`
3. For You shows hydrated cards; open **Why this?** for `why`
4. Resonate / banish updates signal; Discover lists popular/ready posts
5. Create a short post → toast “indexing…” → later appears in search/Discover
6. Waves icon → pairwise pick; **More like this** on a card
7. Avatar menu → **Continue with Google** keeps your Interest DNA; `make web-ui-demo` still works offline

### Identity and Google sign-in

Every visitor gets an anonymous, server-minted `aura_uid` cookie from the Express BFF; all feed
state is keyed on it with no login. Signing in with Google (avatar menu) maps the Google account
to a permanent `account_id` and merges the anonymous profile into it, so nothing curated before
sign-in is lost. The BFF owns all cookies and injects `X-Aura-UserId` upstream; FastAPI must not
be exposed directly.

Setup:

1. Google Cloud Console → APIs & Services → Credentials → OAuth client ID (Web application).
2. Add `http://localhost:5173/api/auth/google/callback` as an authorized redirect URI.
3. In `.env`, set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `AURA_COOKIE_SECRET` and
   `AURA_INTERNAL_TOKEN` (the last two: `openssl rand -hex 32`).
4. Restart `make serve` and `make web-api`. Open the app at `http://localhost:5173` (not a LAN IP),
   so the redirect URI matches.


## Makefile targets

| Target | Description |
|--------|-------------|
| `make setup` | `.env` + venv + install + MongoDB + Qdrant |
| `make mongo-up` / `qdrant-up` | Start services |
| `make scrape-substack` / `discover` | Scrape |
| `make embed` / `embed-status` | Embedding worker |
| `make reembed` | Move every post + user vector onto `LITELLM_EMBEDDING_MODEL` (run after changing it) |
| `scraper prune` | Drop indexed posts the adapters now skip (e.g. Reddit mod / recurring threads) |
| `scraper feed-check` | Personalization smoke test: two personas + a chat refinement, with overlap and source mix |
| `make tags` | Build the canonical tag vocabulary + themes from facets and tag every post |
| `make search QUERY=…` | Semantic search |
| `make serve` | FastAPI recommendation API |
| `make web-api` / `web-ui` / `web-ui-demo` | Express BFF + Aura UI |
| `make web-codegen` | Regenerate Orval client from OpenAPI |
| `make test` / `lint` | Tests / ruff |

## Configuration

See `.env.example`. Important vars:

| Variable | Default | Notes |
|----------|---------|-------|
| `GEMINI_API_KEY` | _(required)_ | Google AI Studio / Gemini API key |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-2` | Only used when `LITELLM_API_KEY` is unset |
| `LITELLM_EMBEDDING_MODEL` | `openai/text-embedding-3-small` | The one model for corpus, users and queries. No fallback: mixed models make scores meaningless |
| `SOURCE_MAX_SHARE` | `0.6` | Max share of a feed one source may take (only relevant posts fill freed slots) |
| `DOC_SIMILARITY_WEIGHT` | `0.5` | Blend of whole-post similarity into chunk MaxSim |
| `RECENCY_WEIGHT` | `0.1` | Max share of a score recency decay can remove; higher values rank by freshness, not interest |
| `GEMINI_LLM_MODEL` | `gemini-2.5-flash` | Facets + persona + Aura chat |
| `EMBEDDING_DIM` | `768` | MRL truncation |
| `QDRANT_URL` | `http://localhost:6333` | |
| `CHUNK_WORDS` / `MAX_CHUNKS_PER_POST` | `300` / `32` | |
| `FILTER_K` | `64` | Stage-1 candidate pool |
| `WEIGHT_VERSION` | `default_v1` | Live weight table (`hold_ms` unused) |
| `TAG_CLUSTER_THRESHOLD` | `0.85` | Cosine above which facet labels merge into one tag |
| `THEME_RESOLVE_THRESHOLD` | `0.75` | Cosine for mapping a free-form label to a theme via its nearest topic |
| `LLM_MAX_OUTPUT_TOKENS` | `8192` | Output cap for LiteLLM JSON calls (thinking models spend part of it on reasoning) |

## Content adapters

Mongo docs are unstructured at the edges. Adapters resolve fields into `EmbeddableContent`:

```bash
scraper adapt substack 219681543
```

- `DefaultContentAdapter` — fallback chains (`content_text` → `content` → strip HTML → `summary`)
- `SubstackContentAdapter` — skips non-posts, strips boilerplate, folds `section_name` into categories

Adding a connector: implement `BaseConnector`, and only add a `ContentAdapter` if field layout differs from the default chains.

## Embedding

```bash
scraper embed --limit 20
scraper embed --retry-failed
scraper embed --force --source substack
scraper embed-status
```

Pipeline per doc: adapter → chunk (head + body windows) → Gemini document embeddings → optional LLM facets → Qdrant upsert → Mongo `embedding_status=ready`.

## Query engine

```bash
scraper search "systems design essays" -k 10
scraper similar <mongo_post_object_id> -k 5
```

Two-stage: ANN on `doc`/`facet` → fetch `chunks` → weighted MaxSim − negative penalty × recency → author diversity → MMR. Optional `--explain` LLM rerank.

## User profile & feedback

Layered signals (implicit volume + explicit precision + reason chips):

| Event | Weight (default) |
|-------|------------------|
| `like` strength 1/2 | 0.7 / 1.0 |
| `save` | 1.0 |
| `dwell` (read_ratio≥0.15) | read_ratio×0.6 |
| fast skip (`impression` <1s) | −0.1 |
| `not_interested` 1/2 | −0.6 / −1.0 |
| `pairwise` winner/loser | +0.5 / −0.3 |

Swipe `hold_ms` is **stored** for offline analysis but **not** used by the live weight table. Compare with:

```bash
scraper eval --weights default
scraper reweigh --weights hold_linear
```

```bash
scraper event demo <post_id> like --strength 2
scraper feed demo -k 10 --explain
scraper persona demo --refresh
```

API (see `/docs`): `POST /search`, `GET /posts/{id}/similar`, `GET /users/{id}/feed`, `GET /users/{id}/pair`, `POST /users/{id}/events`, `POST /users/{id}/tune`, `POST /users/{id}/onboard`, `POST /users/{id}/persona/refresh`, `GET /tags`, `GET|PATCH /users/{id}/dna`, `POST /users/{id}/dna/import`.

## Tags, themes & Interest DNA

Facet labels written by the LLM are free-form ("AI", "ai", "Artificial Intelligence"), so everything that needs a stable vocabulary keys on a **canonical tag** instead:

```bash
make tags                      # or: scraper tags build [--threshold 0.85] [--dry-run] [--no-apply]
scraper tags list --kind theme
```

- **Topic / style tags**: facet labels clustered by embedding cosine. Ids look like `topic:artificial-intelligence`; existing canonical labels stay put across rebuilds, and a retired id keeps a `merged_into` link.
- **Themes**: a coarse level (about a dozen) the LLM groups the topic tags into (embedding k-means is the fallback). A post's primary theme becomes its card `category`, and **Interest DNA is keyed by theme**, so the ring stays readable instead of fragmenting into hundreds of one-post tags.
- Posts carry `canonical_tags` / `tag_ids` (Mongo and Qdrant payload). New posts are tagged as they are embedded.

**Interest DNA** is owned by the server (`UserProfile.dna`): weights over theme ids summing to ~100, plus `anti` / `affinity` rules. It is built from the Aura chat, moved by every resonate / banish, edited with `PATCH /users/{id}/dna` (optimistic `base_version`), and its top themes are also retrieval queries, so the DNA you see is the DNA that ranks.

**Match %** is relative and computed by the engine: the post's percentile of `fit = similarity - aversion + affinity` (no recency) among *every candidate scored for the request*, capped at 98. Cards carry the breakdown in `match` (`components`, `top_attribution`, `flags`, `pool_size`). Feedback sent with the `match_percent` the card showed counts for more when the match was confident and wrong.

**Learning from the post, not just the theme.** Each reaction stores a snapshot of the post (style, tone, length, author, topic tags). Per attribute, the skip rate is compared with the user's own baseline; large lifts become `learned` anti rules (and affinities), which the UI offers to confirm or dismiss. After a banish the response includes `noticed` chips for one-tap avoidance. Dismissed rules are not proposed again.


## Project layout

```text
src/scraper/
├── adapters/          # Mongo raw → EmbeddableContent
├── embedding/         # chunker, facets, worker
├── llm/gemini.py
├── query/             # scoring, engine
├── profile/           # weights, state, clusters, persona, dna, patterns, service
├── tags/              # canonical tag vocabulary, themes
├── eval/offline.py
├── api/app.py
├── connectors/
├── storage/           # mongodb, qdrant
└── models/
```

## License

Copyright (c) 2026 DevRev Inc. All rights reserved.
