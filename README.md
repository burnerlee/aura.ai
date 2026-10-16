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
make web-api                  # Express BFF :5000 → :8000
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
7. Avatar copies anonymous `user_id`; `make web-ui-demo` still works offline


## Makefile targets

| Target | Description |
|--------|-------------|
| `make setup` | `.env` + venv + install + MongoDB + Qdrant |
| `make mongo-up` / `qdrant-up` | Start services |
| `make scrape-substack` / `discover` | Scrape |
| `make embed` / `embed-status` | Embedding worker |
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
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-2` | |
| `GEMINI_LLM_MODEL` | `gemini-2.5-flash` | Facets + persona + Aura chat |
| `EMBEDDING_DIM` | `768` | MRL truncation |
| `QDRANT_URL` | `http://localhost:6333` | |
| `CHUNK_WORDS` / `MAX_CHUNKS_PER_POST` | `300` / `32` | |
| `FILTER_K` | `64` | Stage-1 candidate pool |
| `WEIGHT_VERSION` | `default_v1` | Live weight table (`hold_ms` unused) |

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

API (see `/docs`): `POST /search`, `GET /posts/{id}/similar`, `GET /users/{id}/feed`, `GET /users/{id}/pair`, `POST /users/{id}/events`, `POST /users/{id}/tune`, `POST /users/{id}/onboard`, `POST /users/{id}/persona/refresh`.

## Project layout

```text
src/scraper/
├── adapters/          # Mongo raw → EmbeddableContent
├── embedding/         # chunker, facets, worker
├── llm/gemini.py
├── query/             # scoring, engine
├── profile/           # weights, state, clusters, persona, service
├── eval/offline.py
├── api/app.py
├── connectors/
├── storage/           # mongodb, qdrant
└── models/
```

## License

Copyright (c) 2026 DevRev Inc. All rights reserved.
