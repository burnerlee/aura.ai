# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""CLI entrypoint: ``scraper`` / ``python -m scraper``."""

from __future__ import annotations

import json
import logging
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from scraper import __version__
from scraper.config import get_settings
from scraper.connectors import list_connectors
from scraper.discovery import discover_substack
from scraper.discovery.substack import VALID_TIERS, BlogTarget
from scraper.pipeline import run_scrape
from scraper.storage.mongodb import MongoDocumentStore

app = typer.Typer(
    name="scraper",
    help="Multi-connector content scraper with MongoDB storage.",
    no_args_is_help=True,
)
console = Console()


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


@app.callback()
def main(
    log_level: Optional[str] = typer.Option(
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
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Max posts to scrape."),
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
    category: Optional[list[str]] = typer.Option(
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
    """Find top blogs via leaderboards, then scrape their articles into MongoDB.

    Blog/publication rows are not stored — only full posts.
    """
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


if __name__ == "__main__":
    app()
