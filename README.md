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
- **Extras:** `metadata` (source-specific fields; keep lean)
- **Vector hooks:** `embedding_status`, `embedding_id`, `embedding_model`

Empty / null fields are stripped on write. Only filled values land in MongoDB.

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

Every source (Medium, RSS, Reddit, …) is a **connector**: fetch source-specific data, normalize to `ContentDocument`, yield. The pipeline and Mongo layer stay untouched.

### Contract

| Piece | Requirement |
|-------|-------------|
| Class | Subclass `BaseConnector` |
| `name` | Unique lowercase string (becomes CLI name + Mongo `source`) |
| `description` | Short human string (shown in `scraper connectors`) |
| `scrape()` | Generator yielding `ContentDocument` |
| Config | Read `self.config` (`source_id`, `limit`, `offset`, `fetch_full_content`, `extras`) |
| Registration | `@register_connector` + import in `connectors/__init__.py` |

Reference implementation: `src/scraper/connectors/substack.py`.

### Checklist

1. **Create** `src/scraper/connectors/<name>.py`
2. **Implement** fetch + map → `ContentDocument` (see field guide below)
3. **Register** with `@register_connector`
4. **Import** the module in `src/scraper/connectors/__init__.py` (side-effect registration)
5. **Test** mapping / URL helpers under `tests/`
6. **Run** `scraper connectors` (your name should appear) then `scraper scrape <name> <source_id> --limit 2`
7. **Optional Makefile** target, e.g. `scrape-<name>`

### Minimal example

```python
# src/scraper/connectors/example_rss.py
# Copyright (c) 2026 DevRev Inc. All rights reserved.

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import httpx

from scraper.config import get_settings
from scraper.connectors.base import BaseConnector
from scraper.connectors.registry import register_connector
from scraper.models.document import Author, ContentDocument


@register_connector
class ExampleRssConnector(BaseConnector):
    name = "example_rss"
    description = "Scrape posts from a public RSS/Atom feed URL"

    def validate_config(self) -> None:
        super().validate_config()
        if not self.config.source_id.startswith(("http://", "https://")):
            raise ValueError("source_id must be a feed URL")

    def scrape(self) -> Iterator[ContentDocument]:
        settings = get_settings()
        # Replace with real RSS parsing (feedparser, etc.)
        # Here we illustrate the ContentDocument shape only.
        yielded = 0
        with httpx.Client(
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": settings.http_user_agent},
            follow_redirects=True,
        ) as client:
            _ = client.get(self.config.source_id)  # fetch feed…
            # for each item in feed:
            doc = ContentDocument(
                source=self.name,
                external_id="unique-stable-id",  # REQUIRED: stable across runs
                url="https://example.com/article",
                title="Article title",
                content="Full plain-text body…",
                content_html="<p>Full HTML body…</p>",
                content_text="Full plain-text body…",
                summary="Short teaser",
                author=Author(name="Jane Doe"),
                published_at=datetime.now(timezone.utc),
                categories=["example"],
                metadata={"feed_url": self.config.source_id},
            )
            yield doc
            yielded += 1
            if self.config.limit is not None and yielded >= self.config.limit:
                return
```

Register it:

```python
# src/scraper/connectors/__init__.py
from scraper.connectors import substack as _substack  # noqa: F401
from scraper.connectors import example_rss as _example_rss  # noqa: F401
```

Use it:

```bash
scraper connectors
scraper scrape example_rss https://example.com/feed.xml --limit 5
scraper list-docs --source example_rss -n 5
```

### Field guide (`ContentDocument`)

**Required for a useful row**

| Field | Notes |
|-------|--------|
| `source` | Must equal `self.name` |
| `external_id` | Stable unique id within that source (post id, guid, slug). Used for upserts |
| `title` | Display title |
| Prefer at least one of | `content` / `content_text` / `content_html` (full article for embeddings) |

**Strongly recommended**

| Field | Notes |
|-------|--------|
| `url` / `canonical_url` | Permalink |
| `embed_url` | If the platform has an embeddable URL |
| `author` | `Author(name=…)` at minimum |
| `published_at` | Timezone-aware `datetime` |
| `summary` | Short teaser when full body is huge or paywalled |
| `categories` / `tags` | For filtering later |

**Optional / source-specific**

| Field | Notes |
|-------|--------|
| `metadata` | Small dict only (slug, feed url, is_paid, …). Do **not** dump entire API responses |
| `raw` | Available on the model but **not persisted** to Mongo |
| `embedding_*` | Leave defaults; vector pipeline fills later |

`to_mongo()` drops nulls/blanks — only set fields you have.

### Config knobs (`ConnectorConfig`)

| Attr | Use |
|------|-----|
| `source_id` | Whatever your connector needs (URL, handle, channel id) |
| `limit` / `offset` | Pagination / “latest N” |
| `fetch_full_content` | Skip expensive detail fetches when `False` |
| `extras` | Free-form dict for connector-specific options |

Override `validate_config()` to fail fast on bad `source_id`.

### Conventions

- **Be polite:** respect `settings.request_delay_seconds` between requests; set a clear `User-Agent`.
- **Retries:** use `tenacity` (see Substack connector) for transient HTTP failures.
- **Idempotent upserts:** same `(source, external_id)` overwrites; never invent random ids per run.
- **Full article when possible:** recommendation/embedding work needs `content` / `content_html`, not teasers alone.
- **Paywalls / ToS:** only scrape what the source allows publicly; document limitations in the connector docstring.
- **No publication-only rows:** store articles/posts. Discovery helpers (like Substack leaderboards) should resolve to scrape targets, not Mongo blog cards.

### Optional: discovery helpers

If your source has a “trending” or directory API, add `src/scraper/discovery/<name>.py` that returns lightweight targets (see `BlogTarget` in `discovery/substack.py`), then wire a CLI command that loops `run_scrape("<connector>", target_id, …)`. Keep discovery out of the `posts` collection.

### Tests

Add focused unit tests (no network) for URL parsing and document mapping:

```python
# tests/test_example_rss.py
from scraper.connectors import get_connector, list_connectors
from scraper.connectors.base import ConnectorConfig

def test_registered():
    assert "example_rss" in {c["name"] for c in list_connectors()}

def test_validate_rejects_non_url():
    try:
        get_connector("example_rss", ConnectorConfig(source_id="not-a-url"))
        assert False, "expected ValueError"
    except ValueError:
        pass
```

Run: `make test` / `make lint`.

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
    ├── discovery/
    │   └── substack.py        # blog targets for discover→scrape
    └── connectors/
        ├── base.py            # BaseConnector + ConnectorConfig
        ├── registry.py
        └── substack.py        # reference connector
```

## Roadmap (later)

- [ ] Embedding worker → write vectors to a vector DB (e.g. Qdrant / Pinecone)
- [ ] Flip `embedding_status` from `pending` → `ready`
- [ ] Recommendation API over embeddings + metadata filters
- [ ] Additional connectors (RSS, Medium, X/Twitter, etc.)

## License

Copyright (c) 2026 DevRev Inc. All rights reserved.
