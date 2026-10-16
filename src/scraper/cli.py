# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""CLI entrypoint: ``scraper`` / ``python -m scraper``."""

from __future__ import annotations

import json
import logging

import typer
from rich.console import Console
from rich.table import Table

from scraper import __version__
from scraper.config import get_settings
from scraper.connectors import list_connectors
from scraper.discovery import discover_substack
from scraper.discovery.substack import VALID_TIERS, BlogTarget
from scraper.models.tag import TagKind
from scraper.pipeline import run_scrape
from scraper.storage.mongodb import MongoDocumentStore
from scraper.storage.qdrant import QdrantVectorStore
from scraper.tags.service import TagService

app = typer.Typer(
    name="scraper",
    help="Multi-connector content scraper with embeddings and recommendations.",
    no_args_is_help=True,
)
tags_app = typer.Typer(
    help="Canonical tag vocabulary built from post facets.", no_args_is_help=True
)
app.add_typer(tags_app, name="tags")
console = Console()


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


@app.callback()
def main(
    log_level: str | None = typer.Option(
        None,
        "--log-level",
        help="Override LOG_LEVEL from settings (DEBUG, INFO, WARNING, ERROR).",
    ),
) -> None:
    settings = get_settings()
    _configure_logging(log_level or settings.log_level)


@app.command("version")
def version_cmd() -> None:
    """Print package version."""
    console.print(__version__)


@app.command("connectors")
def connectors_cmd() -> None:
    """List registered connectors."""
    table = Table(title="Connectors")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    for item in list_connectors():
        table.add_row(item["name"], item["description"])
    console.print(table)


@app.command("mongo-ping")
def mongo_ping() -> None:
    """Verify MongoDB connectivity."""
    with MongoDocumentStore() as store:
        ok = store.ping()
        if ok:
            console.print("[green]MongoDB OK[/green]")
            raise typer.Exit(0)
        console.print("[red]MongoDB unreachable[/red]")
        raise typer.Exit(1)


@app.command("mongo-reset")
def mongo_reset(
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm delete of all posts."),
) -> None:
    """Delete all documents in the posts collection (dev reset)."""
    if not yes:
        console.print("[yellow]Refusing to wipe without --yes[/yellow]")
        raise typer.Exit(2)
    with MongoDocumentStore() as store:
        if not store.ping():
            console.print("[red]MongoDB unreachable[/red]")
            raise typer.Exit(1)
        deleted = store.drop_all()
        store.ensure_indexes()
        console.print(f"[green]Deleted {deleted} posts[/green]")


@app.command("scrape")
def scrape_cmd(
    connector: str = typer.Argument(..., help="Connector name, e.g. substack"),
    source_id: str = typer.Argument(
        ...,
        help="Source identifier (Substack handle or publication URL).",
    ),
    limit: int | None = typer.Option(None, "--limit", "-n", help="Max posts to scrape."),
    offset: int = typer.Option(0, "--offset", help="Pagination offset."),
    no_full: bool = typer.Option(
        False,
        "--no-full",
        help="Skip per-post detail fetch (archive metadata only).",
    ),
    batch_size: int = typer.Option(25, "--batch-size", help="Mongo upsert batch size."),
) -> None:
    """Scrape a source and upsert documents into MongoDB."""
    summary = run_scrape(
        connector,
        source_id,
        limit=limit,
        offset=offset,
        fetch_full_content=not no_full,
        batch_size=batch_size,
    )
    console.print_json(json.dumps(summary))


@app.command("list-docs")
def list_docs_cmd(
    source: str = typer.Option("substack", "--source", "-s", help="Filter by source."),
    limit: int = typer.Option(10, "--limit", "-n"),
) -> None:
    """List stored posts (summary view)."""
    with MongoDocumentStore() as store:
        table = Table(title=f"Posts ({source})")
        table.add_column("external_id")
        table.add_column("title")
        table.add_column("author")
        table.add_column("url")

        for doc in store.list_by_source(source, limit=limit):
            author = (doc.get("author") or {}).get("name") or ""
            table.add_row(
                str(doc.get("external_id") or "")[:36],
                (doc.get("title") or "")[:50],
                author[:24],
                (doc.get("url") or doc.get("embed_url") or "")[:40],
            )
        console.print(table)
        console.print(f"Total: {store.count(source)}")


@app.command("discover")
def discover_cmd(
    connector: str = typer.Argument("substack", help="Discovery backend (currently: substack)."),
    per_category: int = typer.Option(
        5,
        "--per-category",
        "-n",
        help="Max blogs to take from each category.",
    ),
    tier: str = typer.Option(
        "rising",
        "--tier",
        "-t",
        help="Leaderboard tier: rising | all | paid | free.",
    ),
    category: list[str] | None = typer.Option(
        None,
        "--category",
        "-c",
        help="Filter by category slug, id, or name (repeatable). Default: all.",
    ),
    no_podcasts: bool = typer.Option(False, "--no-podcasts", help="Skip Podcasts category."),
    posts: int = typer.Option(
        3,
        "--posts",
        "-p",
        help="How many latest articles to scrape per unique blog.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Only list discovered blogs; do not scrape or write to MongoDB.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
) -> None:
    """Find top blogs via leaderboards, then scrape their articles into MongoDB."""
    if connector.lower() != "substack":
        console.print(f"[red]Unsupported discover connector: {connector}[/red]")
        raise typer.Exit(2)
    if tier not in VALID_TIERS:
        console.print(f"[red]Invalid tier '{tier}'. Use one of: {', '.join(VALID_TIERS)}[/red]")
        raise typer.Exit(2)

    blogs = discover_substack(
        per_category=per_category,
        tier=tier,  # type: ignore[arg-type]
        categories=category,
        include_podcasts=not no_podcasts,
    )

    unique: dict[str, BlogTarget] = {}
    for blog in blogs:
        unique.setdefault(blog.publication_id, blog)

    scrape_summaries: list[dict] = []
    if not dry_run:
        with MongoDocumentStore() as store:
            if not store.ping():
                console.print("[red]MongoDB unreachable[/red]")
                raise typer.Exit(1)
            store.ensure_indexes()
            for blog in unique.values():
                source_id = blog.scrape_source_id
                try:
                    scrape_summaries.append(
                        run_scrape("substack", source_id, limit=posts, store=store)
                    )
                except Exception as exc:  # noqa: BLE001
                    scrape_summaries.append({"source_id": source_id, "error": str(exc)})

    payload = {
        "discovered_blogs": len(blogs),
        "unique_blogs": len(unique),
        "tier": tier,
        "per_category": per_category,
        "posts_per_blog": posts,
        "dry_run": dry_run,
        "collection": "posts",
        "blogs": [
            {
                "publication_id": b.publication_id,
                "name": b.name,
                "subdomain": b.subdomain,
                "url": b.url,
                "author_name": b.author_name,
                "category_name": b.category_name,
                "category_slug": b.category_slug,
                "tier": b.tier,
                "rank": b.rank,
            }
            for b in blogs
        ],
        "scrape": scrape_summaries,
    }

    if as_json:
        console.print_json(json.dumps(payload))
        return

    table = Table(title=f"Substack discover → scrape posts ({tier}, {per_category}/cat)")
    table.add_column("rank", justify="right")
    table.add_column("category")
    table.add_column("blog")
    table.add_column("subdomain", style="cyan")
    table.add_column("author")

    for blog in blogs:
        table.add_row(
            str(blog.rank),
            (blog.category_name or "")[:24],
            (blog.name or "")[:40],
            blog.subdomain or "",
            (blog.author_name or "")[:24],
        )
    console.print(table)

    scraped_ok = sum(1 for s in scrape_summaries if "error" not in s)
    scraped_posts = sum(int(s.get("scraped", 0)) for s in scrape_summaries if "error" not in s)
    console.print(
        f"Blogs listed: {len(blogs)}  |  Unique blogs: {len(unique)}"
        + (
            f"  |  scraped {scraped_posts} posts from {scraped_ok} blogs"
            if not dry_run
            else "  |  dry-run (nothing written)"
        )
    )


@app.command("adapt")
def adapt_cmd(
    source: str = typer.Argument(..., help="Source name, e.g. substack"),
    external_id: str = typer.Argument(..., help="Post external_id"),
) -> None:
    """Dry-run content adapter: print EmbeddableContent or SkipReason."""
    from scraper.adapters import get_adapter
    from scraper.models.embeddable import SkipReason

    with MongoDocumentStore() as store:
        raw = store.get(source, external_id)
        if not raw:
            console.print(f"[red]Not found: {source}/{external_id}[/red]")
            raise typer.Exit(1)
        result = get_adapter(source).adapt(raw)
        if isinstance(result, SkipReason):
            console.print(f"[yellow]SkipReason: {result.value}[/yellow]")
            raise typer.Exit(0)
        console.print_json(result.model_dump_json())


@app.command("embed")
def embed_cmd(
    limit: int | None = typer.Option(None, "--limit", "-n"),
    source: str | None = typer.Option(None, "--source", "-s"),
    retry_failed: bool = typer.Option(False, "--retry-failed"),
    force: bool = typer.Option(False, "--force", help="Re-embed even if ready."),
) -> None:
    """Embed pending posts into Qdrant."""
    from scraper.embedding.worker import run_embed

    summary = run_embed(
        limit=limit, source=source, retry_failed=retry_failed, force=force
    )
    console.print_json(json.dumps(summary))


@app.command("embed-status")
def embed_status_cmd(
    source: str | None = typer.Option(None, "--source", "-s"),
) -> None:
    """Show embedding status counts."""
    with MongoDocumentStore() as store:
        stats = store.embedding_stats(source)
        console.print_json(json.dumps(stats))


@tags_app.command("build")
def tags_build_cmd(
    threshold: float | None = typer.Option(
        None,
        "--threshold",
        help="Cosine above which labels merge (default: TAG_CLUSTER_THRESHOLD).",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview merges; write nothing."),
    no_apply: bool = typer.Option(False, "--no-apply", help="Skip re-tagging posts."),
) -> None:
    """Cluster facet topics/styles into canonical tags, then tag every embedded post."""
    with MongoDocumentStore() as store:
        if not store.ping():
            console.print("[red]MongoDB unreachable[/red]")
            raise typer.Exit(1)
        store.ensure_indexes()
        vectors = QdrantVectorStore()
        try:
            summary = TagService(store=store, vectors=vectors).rebuild(
                threshold=threshold, dry_run=dry_run, apply=not no_apply
            )
        finally:
            vectors.close()
    console.print_json(json.dumps(summary, default=str))


@tags_app.command("apply")
def tags_apply_cmd(
    source: str | None = typer.Option(None, "--source", "-s"),
    limit: int | None = typer.Option(None, "--limit", "-n"),
) -> None:
    """Re-resolve posts against the stored vocabulary (Mongo + Qdrant payload)."""
    with MongoDocumentStore() as store:
        if not store.ping():
            console.print("[red]MongoDB unreachable[/red]")
            raise typer.Exit(1)
        store.ensure_indexes()
        vectors = QdrantVectorStore()
        try:
            summary = TagService(store=store, vectors=vectors).apply(source=source, limit=limit)
        finally:
            vectors.close()
    console.print_json(json.dumps(summary))


@tags_app.command("list")
def tags_list_cmd(
    kind: TagKind | None = typer.Option(None, "--kind", "-k"),
    limit: int = typer.Option(40, "--limit", "-n"),
) -> None:
    """Show the canonical vocabulary, most common first."""
    with MongoDocumentStore() as store:
        table = Table(title="Canonical tags")
        table.add_column("id", style="cyan")
        table.add_column("kind")
        table.add_column("posts", justify="right")
        table.add_column("aliases")
        for tag in store.list_tags(kind=kind, min_docs=1, include_merged=False, limit=limit):
            table.add_row(tag.id, tag.kind.value, str(tag.doc_count), ", ".join(tag.aliases[:5]))
        console.print(table)


@app.command("search")
def search_cmd(
    query: str = typer.Argument(..., help="Search text"),
    k: int = typer.Option(10, "--k", "-k"),
    source: str | None = typer.Option(None, "--source", "-s"),
    explain: bool = typer.Option(False, "--explain"),
) -> None:
    """Semantic search over embedded posts."""
    from scraper.query.engine import RecommendationEngine
    from scraper.query.types import Filters

    engine = RecommendationEngine()
    filters = Filters(sources=[source]) if source else None
    results = engine.search(query, k=k, filters=filters, explain=explain)
    table = Table(title=f"Search: {query}")
    table.add_column("score", justify="right")
    table.add_column("title")
    table.add_column("author")
    table.add_column("why")
    for r in results:
        table.add_row(
            f"{r.score:.3f}",
            (r.payload.get("title") or r.post_id)[:60],
            (r.payload.get("author_name") or "")[:24],
            (r.reason or "")[:40],
        )
    console.print(table)


@app.command("similar")
def similar_cmd(
    post_id: str = typer.Argument(..., help="Mongo post ObjectId or Qdrant point id"),
    k: int = typer.Option(10, "--k", "-k"),
) -> None:
    """Find posts similar to a seed post."""
    from scraper.query.engine import RecommendationEngine

    engine = RecommendationEngine()
    results = engine.similar(post_id, k=k)
    console.print_json(json.dumps([r.model_dump() for r in results]))


@app.command("serve")
def serve_cmd(
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    """Start the FastAPI recommendation server."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "scraper.api.app:app",
        host=host or settings.api_host,
        port=port or settings.api_port,
        reload=False,
    )


@app.command("event")
def event_cmd(
    user: str = typer.Argument(...),
    post_id: str = typer.Argument(...),
    event: str = typer.Argument(..., help="like|not_interested|open|skip|save|dwell"),
    strength: int = typer.Option(1, "--strength"),
    hold_ms: int | None = typer.Option(None, "--hold-ms"),
    reason: str | None = typer.Option(None, "--reason"),
) -> None:
    """Record a user interaction event."""
    from scraper.models.user import EventType, FeedbackReason, Interaction
    from scraper.profile.service import UserProfileService

    mapping = {
        "like": EventType.LIKE,
        "dislike": EventType.NOT_INTERESTED,
        "not_interested": EventType.NOT_INTERESTED,
        "skip": EventType.IMPRESSION,
        "open": EventType.OPEN,
        "save": EventType.SAVE,
        "dwell": EventType.DWELL,
    }
    if event not in mapping:
        console.print(f"[red]Unknown event: {event}[/red]")
        raise typer.Exit(2)
    interaction = Interaction(
        user_id=user,
        post_id=post_id,
        event=mapping[event],
        strength=strength,
        hold_ms=hold_ms,
        reason=FeedbackReason(reason) if reason else None,
        visible_ms=500 if event == "skip" else None,
    )
    profile = UserProfileService().record_event(interaction)
    console.print_json(
        json.dumps(
            {
                "user_id": profile.user_id,
                "persona_version": profile.persona_version,
                "positives": len(profile.positive_ids),
                "negatives": len(profile.negative_ids),
            }
        )
    )


@app.command("feed")
def feed_cmd(
    user: str = typer.Argument(...),
    k: int = typer.Option(10, "--k", "-k"),
    explain: bool = typer.Option(False, "--explain"),
) -> None:
    """Personalized feed for a user."""
    from scraper.profile.service import UserProfileService

    results = UserProfileService().feed(user, k=k, explain=explain)
    table = Table(title=f"Feed: {user}")
    table.add_column("score", justify="right")
    table.add_column("title")
    table.add_column("why")
    for r in results:
        table.add_row(
            f"{r.score:.3f}",
            (r.payload.get("title") or r.post_id)[:60],
            (r.reason or "")[:50],
        )
    console.print(table)


@app.command("persona")
def persona_cmd(
    user: str = typer.Argument(...),
    refresh: bool = typer.Option(False, "--refresh"),
) -> None:
    """Show or refresh a user's persona."""
    from scraper.profile.service import UserProfileService

    svc = UserProfileService()
    profile = svc.refresh_persona(user) if refresh else svc.get_or_create(user)
    console.print_json(profile.persona.model_dump_json())


@app.command("eval")
def eval_cmd(
    k: int = typer.Option(10, "--k", "-k"),
    weights: str = typer.Option("default", "--weights"),
) -> None:
    """Offline leave-last-out metrics + hold_ms correlation."""
    from scraper.eval.offline import hold_ms_correlation_report, leave_last_out_metrics
    from scraper.profile.service import UserProfileService

    svc = UserProfileService()

    def recommend_fn(user_id: str, k: int = 10, exclude_last: str | None = None):
        results = svc.feed(user_id, k=k)
        if exclude_last:
            results = [r for r in results if r.post_id != exclude_last]
        return results

    with MongoDocumentStore() as store:
        metrics = leave_last_out_metrics(store, recommend_fn=recommend_fn, k=k)
        corr = hold_ms_correlation_report(store)
        console.print_json(json.dumps({"weights": weights, **metrics, **corr}))


@app.command("reweigh")
def reweigh_cmd(
    weights: str = typer.Option("default", "--weights"),
) -> None:
    """Recompute interaction weights from raw fields."""
    from scraper.eval.offline import reweigh_interactions

    with MongoDocumentStore() as store:
        summary = reweigh_interactions(store, version=weights)
        console.print_json(json.dumps(summary))


if __name__ == "__main__":
    app()
