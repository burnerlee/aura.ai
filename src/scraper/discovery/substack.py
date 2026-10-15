# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Discover trending Substack blogs, then scrape their posts (not the blogs themselves)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from scraper.config import get_settings

logger = logging.getLogger(__name__)

SUBSTACK_ROOT = "https://substack.com"
VALID_TIERS = ("rising", "all", "paid", "free")
Tier = Literal["rising", "all", "paid", "free"]
_PAGE_SIZE = 25


@dataclass(frozen=True)
class BlogTarget:
    """Lightweight pointer to a blog used only to drive post scraping."""

    publication_id: str
    name: str | None
    subdomain: str | None
    url: str | None
    author_name: str | None
    category_id: str | None
    category_name: str | None
    category_slug: str | None
    tier: str
    rank: int

    @property
    def scrape_source_id(self) -> str:
        if self.subdomain:
            return self.subdomain
        if self.url:
            return self.url
        return self.publication_id


class SubstackDiscovery:
    """Fetch category leaderboards from Substack's public API."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def discover(
        self,
        *,
        per_category: int = 5,
        tier: Tier = "rising",
        categories: list[str] | None = None,
        include_podcasts: bool = True,
    ) -> list[BlogTarget]:
        if per_category < 1:
            raise ValueError("per_category must be >= 1")
        if tier not in VALID_TIERS:
            raise ValueError(f"tier must be one of {VALID_TIERS}")

        with httpx.Client(
            headers={
                "User-Agent": self.settings.http_user_agent,
                "Accept": "application/json",
            },
            timeout=self.settings.http_timeout_seconds,
            follow_redirects=True,
        ) as client:
            cat_list = self._list_categories(client)
            selected = self._filter_categories(
                cat_list,
                categories_filter=categories,
                include_podcasts=include_podcasts,
            )
            logger.info(
                "Discovering up to %s blogs/category (tier=%s) across %s categories",
                per_category,
                tier,
                len(selected),
            )

            results: list[BlogTarget] = []
            for cat in selected:
                blogs = self._fetch_top_for_category(
                    client,
                    category=cat,
                    tier=tier,
                    limit=per_category,
                )
                results.extend(blogs)
                self._throttle()
            return results

    def _throttle(self) -> None:
        delay = self.settings.request_delay_seconds
        if delay > 0:
            time.sleep(delay)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _list_categories(self, client: httpx.Client) -> list[dict[str, Any]]:
        url = f"{SUBSTACK_ROOT}/api/v1/categories"
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise ValueError("Unexpected categories response")
        return data

    def _filter_categories(
        self,
        categories: list[dict[str, Any]],
        *,
        categories_filter: list[str] | None = None,
        include_podcasts: bool = True,
    ) -> list[dict[str, Any]]:
        wanted = {w.lower() for w in categories_filter} if categories_filter else None
        selected: list[dict[str, Any]] = []

        for cat in categories:
            if cat.get("deprecated"):
                continue
            cat_id = cat.get("id")
            slug = (cat.get("slug") or "").lower()
            is_podcast = cat_id == "podcast" or slug == "podcast"
            if is_podcast:
                if not include_podcasts:
                    continue
            elif cat.get("leaderboard_enabled") is False:
                continue

            if wanted is not None:
                id_str = str(cat_id).lower() if cat_id is not None else ""
                name = (cat.get("name") or "").lower()
                if id_str not in wanted and slug not in wanted and name not in wanted:
                    continue
            selected.append(cat)

        return selected

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _fetch_page(
        self,
        client: httpx.Client,
        *,
        category_id: str,
        tier: str,
        page: int,
    ) -> dict[str, Any]:
        url = f"{SUBSTACK_ROOT}/api/v1/category/public/{category_id}/{tier}"
        resp = client.get(url, params={"page": page})
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected leaderboard response")
        return data

    def _fetch_top_for_category(
        self,
        client: httpx.Client,
        *,
        category: dict[str, Any],
        tier: str,
        limit: int,
    ) -> list[BlogTarget]:
        cat_id = category.get("id")
        if cat_id is None:
            return []
        cat_id_str = str(cat_id)
        collected: list[BlogTarget] = []
        page = 0

        while len(collected) < limit:
            try:
                data = self._fetch_page(
                    client, category_id=cat_id_str, tier=tier, page=page
                )
            except httpx.HTTPError as exc:
                logger.warning(
                    "Leaderboard fetch failed for category %s (%s): %s",
                    category.get("name"),
                    cat_id_str,
                    exc,
                )
                break

            pubs = data.get("publications") or []
            if not pubs:
                break

            for idx, raw in enumerate(pubs):
                if len(collected) >= limit:
                    break
                if not isinstance(raw, dict):
                    continue
                rank = page * _PAGE_SIZE + idx + 1
                collected.append(
                    self._to_target(raw, category=category, tier=tier, rank=rank)
                )

            if not data.get("more"):
                break
            page += 1
            self._throttle()

        logger.info(
            "Category %s (%s): got %s blogs",
            category.get("name"),
            tier,
            len(collected),
        )
        return collected

    def _to_target(
        self,
        raw: dict[str, Any],
        *,
        category: dict[str, Any],
        tier: str,
        rank: int,
    ) -> BlogTarget:
        pub_id = raw.get("id")
        subdomain = raw.get("subdomain")
        base_url = raw.get("base_url")
        if not base_url and subdomain:
            base_url = f"https://{subdomain}.substack.com"
        elif not base_url and raw.get("custom_domain"):
            base_url = f"https://{raw['custom_domain']}"

        return BlogTarget(
            publication_id=str(pub_id) if pub_id is not None else (subdomain or ""),
            name=raw.get("name"),
            subdomain=subdomain,
            url=base_url,
            author_name=raw.get("author_name"),
            category_id=str(category.get("id")) if category.get("id") is not None else None,
            category_name=category.get("name"),
            category_slug=category.get("slug"),
            tier=tier,
            rank=rank,
        )


def discover_substack(
    *,
    per_category: int = 5,
    tier: Tier = "rising",
    categories: list[str] | None = None,
    include_podcasts: bool = True,
) -> list[BlogTarget]:
    return SubstackDiscovery().discover(
        per_category=per_category,
        tier=tier,
        categories=categories,
        include_podcasts=include_podcasts,
    )
