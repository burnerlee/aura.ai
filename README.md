# Content Scraper

Python multi-connector scraper that pulls posts/content from external sources and stores normalized documents in MongoDB. Built for a future embeddings + recommendation pipeline.

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│  CLI / Make │────▶│  Connector       │────▶│  MongoDB    │
│             │     │  (substack, …)   │     │  posts      │
└─────────────┘     └──────────────────┘     └─────────────┘
                              │
                              ▼
                    ContentDocument
                    (normalized schema)
```

| Layer | Role |
|-------|------|
| **Connectors** | Source-specific fetch + normalize → `ContentDocument` |
| **Pipeline** | Batch scrape → upsert into MongoDB |
| **Storage** | Single MongoDB `posts` collection; unique `(source, external_id)` |
| **Future** | `embedding_status` / `embedding_id` fields reserved for vector DB |

### Schema (MongoDB `posts`)

All connectors write the same `ContentDocument` shape into **`content_scraper.posts`**:

- **Identity:** `source`, `external_id`, `url`, `embed_url`, `canonical_url`
- **Content:** `title`, `subtitle`, `content`, `content_html`, `content_text`, `summary`
- **Author:** `author.{name,external_id,url,bio,avatar_url,metadata}`
- **Media / taxonomy:** `cover_image_url`, `media_urls`, `tags`, `categories`, `audience`
- **Timestamps:** `published_at`, `updated_at`, `scraped_at`
- **Engagement:** `word_count`, `reaction_count`, `comment_count`
- **Extras:** `metadata`, `raw` (full source payload)
- **Vector hooks:** `embedding_status`, `embedding_id`, `embedding_model`

## Prerequisites

- Python 3.11+ (`make` prefers `python3.12` / `python3.11` over system `python3`)
- Docker + Docker Compose
- Make

## Quick start

```bash
# 1. Full setup: .env, venv, deps, MongoDB
make setup

# 2. List connectors
make connectors

# 3. Scrape a Substack publication (public posts)
make scrape-substack SOURCE=platformer LIMIT=5

# 4. Inspect stored docs
make list-docs LIMIT=5
```

Equivalent CLI:

```bash
source .venv/bin/activate
scraper scrape substack platformer --limit 5
# or full URL:
scraper scrape substack https://www.lennysnewsletter.com --limit 3
scraper list-docs --source substack -n 10
```

## Makefile targets

| Target | Description |
|--------|-------------|
| `make setup` | `.env` + venv + install + MongoDB up + ping |
| `make mongo-up` / `mongo-down` | Start / stop MongoDB |
| `make mongo-reset` | Stop MongoDB and delete volume data |
| `make ping` | App-level MongoDB health check |
| `make connectors` | List registered connectors |
| `make scrape-substack SOURCE=… LIMIT=…` | Run Substack connector |
| `make list-docs` | Preview documents in MongoDB |
| `make install-dev` | Install with pytest / ruff |
| `make lint` / `make test` | Lint / tests |
| `make clean` | Remove venv and caches |

## Configuration

Copy `.env.example` → `.env` (done by `make env` / `make setup`):

| Variable | Default | Notes |
|----------|---------|-------|
| `MONGO_HOST` | `localhost` | |
| `MONGO_PORT` | `27017` | |
| `MONGO_USER` / `MONGO_PASSWORD` | `scraper` / `scraper` | Docker root user (`authSource=admin`) |
| `MONGO_DB` | `content_scraper` | |
| `MONGO_COLLECTION` | `posts` | |
| `MONGO_URI` | _(unset)_ | Overrides host/user/password when set |
| `REQUEST_DELAY_SECONDS` | `0.5` | Politeness delay between post fetches |
| `HTTP_TIMEOUT_SECONDS` | `30` | |
| `LOG_LEVEL` | `INFO` | |

Connection URI used by the app:

```text
mongodb://scraper:scraper@localhost:27017/content_scraper?authSource=admin
```

## Discover → scrape posts

Leaderboards are used only to **find blogs**. We then scrape their **articles** into MongoDB. Blog/publication rows are not stored.

```bash
# Top 5 rising blogs per category → scrape 3 latest posts each
make discover PER_CATEGORY=5 POSTS=3 TIER=rising

# CLI
scraper discover substack --per-category 5 --posts 3 --tier rising
scraper discover substack -n 2 -p 3 -c technology -c business
scraper discover substack -n 5 --dry-run   # list blogs only, no Mongo writes
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--per-category` / `-n` | `5` | Blogs to take from each category |
| `--posts` / `-p` | `3` | Latest articles to scrape per unique blog |
| `--tier` / `-t` | `rising` | `rising` \| `all` \| `paid` \| `free` |
| `--category` / `-c` | all | Filter by slug/id/name (repeatable) |
| `--dry-run` | off | List blogs only; do not scrape |
| `--json` | off | Machine-readable output |

Uses `GET /api/v1/categories` + leaderboards, then each blog’s archive/post APIs.

## Substack connector

Uses Substack’s public JSON API (no API key for public posts):

1. `GET {publication}/api/v1/archive?sort=new&limit=&offset=` — list posts  
2. `GET {publication}/api/v1/posts/{slug}` — full `body_html` + author bylines  

`source_id` accepts:

- Handle: `platformer`
- Substack host: `platformer.substack.com`
- Full URL / custom domain: `https://www.lennysnewsletter.com`

`embed_url` is set to `{publication}/embed/p/{slug}`.

Paywalled posts may return truncated body content depending on Substack’s public response.

## Adding a connector

1. Create `src/scraper/connectors/<name>.py`
2. Subclass `BaseConnector`, set `name`, implement `scrape()` yielding `ContentDocument`
3. Decorate with `@register_connector`
4. Import the module from `connectors/__init__.py` so it registers

```python
from scraper.connectors.base import BaseConnector
from scraper.connectors.registry import register_connector
from scraper.models.document import ContentDocument

@register_connector
class MyConnector(BaseConnector):
    name = "my_source"
    description = "..."

    def scrape(self):
        yield ContentDocument(
            source=self.name,
            external_id="...",
            title="...",
            content="...",
            embed_url="...",
            author=...,
            metadata={...},
        )
```

## Project layout

```text
.
├── Makefile
├── README.md
├── docker-compose.yml
├── pyproject.toml
├── .env.example
├── scripts/mongo-init.js      # indexes on first boot
└── src/scraper/
    ├── cli.py                 # typer CLI
    ├── config.py
    ├── pipeline.py
    ├── models/document.py     # ContentDocument schema
    ├── storage/mongodb.py
    └── connectors/
        ├── base.py
        ├── registry.py
        └── substack.py
```

## Roadmap (later)

- [ ] Embedding worker → write vectors to a vector DB (e.g. Qdrant / Pinecone)
- [ ] Flip `embedding_status` from `pending` → `ready`
- [ ] Recommendation API over embeddings + metadata filters
- [ ] Additional connectors (RSS, Medium, X/Twitter, etc.)

## License

Copyright (c) 2026 DevRev Inc. All rights reserved.
