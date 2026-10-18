#!/usr/bin/env python3
# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Apply curated category labels to Substack publications already scraped into MongoDB.

What it does:
- Builds a mapping of `publication_base_url` -> curated categories (from the user-provided list).
- For every matching post in Mongo (`source=substack`), it:
  - sets `metadata.category` (primary curated category label; first in list)
  - prepends curated categories into `categories` (while preserving existing categories like "newsletter")
- For posts already embedded (embedding_status=READY), it also updates the Qdrant payload's
  `categories` to keep semantic filters consistent.

This is intentionally conservative: it does not delete or overwrite non-category metadata.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable
from urllib.parse import urlparse

from scraper.models.document import EmbeddingStatus
from scraper.storage.mongodb import MongoDocumentStore
from scraper.storage.qdrant import QdrantVectorStore


def _normalize_base(url: str) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    if not parsed.netloc:
        return None
    scheme = parsed.scheme or "https"
    return f"{scheme}://{parsed.netloc}".rstrip("/")


def _variants(base_url: str) -> list[str]:
    """Return likely equivalents (www/no-www) for matching publication_base_url."""
    parsed = urlparse(base_url)
    host = parsed.netloc
    out = {base_url.rstrip("/")}
    if host.startswith("www."):
        out.add(f"{parsed.scheme}://{host.removeprefix('www.')}")
    else:
        out.add(f"{parsed.scheme}://www.{host}")
    return sorted(out)


def _dedupe_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        s = str(it).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


# Curated categories from the user message.
# NOTE: Non-Substack domains and substack search URLs are fine to keep here; they will match 0 docs.
CURATED: dict[str, list[str]] = {
    "Travel & place": [
        "https://carolineeden.substack.com/",
        "https://panachepress.substack.com/",
        "https://lover.substack.com/",
        "https://www.substack.com/search/Thoughtful%20Travel",
        "https://www.substack.com/search/Benthall%20Slow%20Travel",
        "https://www.substack.com/search/PASSAGES%20Toby%20Neal",
        "https://travelandculture.substack.com/",
        "https://theculturalconscience.substack.com/",
        "https://bobukiah.substack.com/",
        "https://fialka.substack.com/",
        "https://aculturalaffair.substack.com/",
        "https://dreamplanexperience.substack.com/",
        "https://gentlerhythms.substack.com/",
        "https://ginasjournal.substack.com/",
        "https://reverietraveljournal.substack.com/",
        "https://www.booksoncities.com/",
        "https://omnomnomdiary.substack.com/",
        "https://www.substack.com/search/Letters%20from%20a%20Wanderer",
        "https://www.substack.com/search/Departure%20Henah%20Velez",
        "https://www.substack.com/search/Carrying%20On%20Victoria%20M%20Walker",
    ],
    "Culture, art & ideas": [
        "https://www.substack.com/search/The%20Culturist",
        "https://www.blackbirdspyplane.com/",
        "https://www.theisolationjournals.com/",
        "https://www.themarginalian.org/",
        "https://www.substack.com/search/Books%20and%20Culture",
        "https://www.substack.com/search/Culture%20Vulture",
        "https://panachepress.substack.com/",
        "https://katyhessel.substack.com/",
        "https://sahanasrikanth27.substack.com/",
        "https://theculturalconscience.substack.com/",
        "https://ibcnewsletter.substack.com/",
        "https://shreyadadwal.substack.com/",
    ],
    "Anime / manga": [
        "https://theaccidentalotaku.substack.com/",
        "https://www.substack.com/search/Animenomics",
        "https://animationobsessive.substack.com/",
        "https://animeawakening.substack.com/",
        "https://www.substack.com/search/Anime%20Radar",
    ],
    "Games / gaming": [
        "https://newsletter.gamediscover.co/",
        "https://www.gamefile.news/",
        "https://aftermath.site/",
        "https://www.thegamesbusiness.com/",
        "https://www.filfre.net/",
    ],
    "Sports": [
        "https://thesportsletter.com/",
        "https://frontofficesports.com/",
        "https://www.theplayerstribune.com/",
        "https://www.theringer.com/",
        "https://defector.com/",
    ],
    "Food / cooking": [
        "https://carolinechambers.substack.com/",
        "https://smittenkitchen.com/",
        "https://www.nytimes.com/column/the-recipe",
        "https://thefoodsection.com/",
        "https://thecounter.org/",
    ],
    "Fashion & beauty": [
        "https://thecinch.substack.com/",
        "https://www.substack.com/search/Flesh%20World%20Jessica%20DeFino",
        "https://www.blackbirdspyplane.com/",
        "https://cupofjo.substack.com/",
        "https://www.substack.com/search/Fashion%20People",
    ],
    "Home & garden": [
        "https://www.substack.com/search/Home%20India%20Knight",
        "https://erinblegen.substack.com/",
        "https://www.substack.com/search/Aedicula",
        "https://www.theamericanpeasant.com/",
        "https://www.gardenista.com/",
    ],
    "Parenting / family": [
        "https://zawn.substack.com/",
        "https://www.motheruntitled.com/",
        "https://www.theisolationjournals.com/",
        "https://www.substack.com/search/Kids%20Faith%20Meredith%20Miller",
        "https://themomhour.com/",
    ],
    "Health / fitness / wellness": [
        "https://twopct.com/",
        "https://www.substack.com/search/The%20Habit%20Healers",
        "https://brainhealthkitchen.substack.com/",
        "https://susan-cain.com/",
        "https://ashleyneese.substack.com/",
    ],
    "Film & TV": [
        "https://www.hunterharris.com/",
        "https://www.substack.com/search/GOOD%20MOVIE%20Shea%20Serrano",
        "https://www.substack.com/search/Projections%20Sean%20Fennessey",
        "https://theankler.com/",
        "https://animationobsessive.substack.com/",
    ],
    "Music": [
        "https://aquariumdrunkard.com/",
        "https://www.hearingthings.co/",
        "https://www.thenewcue.com/",
        "https://www.blackbirdspyplane.com/",
        "https://www.talkhouse.com/",
    ],
    "Design": [
        "https://www.substack.com/search/WEARSTLERWORLD",
        "https://designbetterpodcast.com/",
        "https://www.theamericanpeasant.com/",
        "https://thecreativeindependent.com/",
        "https://www.densediscovery.com/",
    ],
    "Education": [
        "https://www.learningscientists.org/",
        "https://hechingerreport.org/",
        "https://www.themarginalian.org/",
        "https://worksinprogress.co/",
        "https://knowablemagazine.org/",
    ],
    "Faith / religion": [
        "https://www.substack.com/search/Faith%20Matters",
        "https://www.wayfaremagazine.org/",
        "https://www.substack.com/search/Reclaiming%20Faith%20Jennifer%20Butler",
        "https://thebiblefornormalpeople.com/",
        "https://www.themarginalian.org/",
    ],
    "Climate / environment": [
        "https://heatmap.news/",
        "https://www.volts.wtf/",
        "https://heated.world/",
        "https://www.substack.com/search/Climate%20Change%20and%20You",
        "https://www.substack.com/search/Good%20Climate%20News",
    ],
    "News & politics": [
        "https://heathercoxrichardson.substack.com/",
        "https://www.thefp.com/",
        "https://popular.info/",
        "https://zeteo.com/",
        "https://www.thebulwark.com/",
        "https://thedispatch.com/",
        "https://www.thehonestbroker.com/",
        "https://the-ink.com/",
        "https://www.liberalpatriot.com/",
        "https://www.slowboring.com/",
    ],
}


def main() -> int:
    base_to_categories: dict[str, list[str]] = defaultdict(list)
    for category, urls in CURATED.items():
        for u in urls:
            base = _normalize_base(u)
            if not base:
                continue
            # Skip the Substack search host; it's not a publication base url we store.
            if urlparse(base).netloc.lower() == "www.substack.com":
                continue
            base_to_categories[base].append(category)

    # Coalesce duplicates (e.g. Panache Press appears twice) while preserving category order.
    base_to_categories = {
        base: _dedupe_keep_order(cats) for base, cats in base_to_categories.items()
    }

    store = MongoDocumentStore()
    if not store.ping():
        raise RuntimeError("Cannot reach MongoDB. Run `make mongo-up`.")
    store.ensure_indexes()
    vectors = QdrantVectorStore()
    vectors.ensure_collection()

    updated_posts = 0
    updated_ready_payloads = 0
    publications_touched = 0

    for base_url, curated_categories in sorted(base_to_categories.items()):
        variants = _variants(base_url)
        filt = {
            "source": "substack",
            "metadata.publication_base_url": {"$in": variants},
        }
        docs = list(
            store.collection.find(
                filt,
                {
                    "_id": 1,
                    "external_id": 1,
                    "categories": 1,
                    "embedding_status": 1,
                },
            )
        )
        if not docs:
            continue
        publications_touched += 1

        primary = curated_categories[0]
        for doc in docs:
            existing = doc.get("categories") or []
            if not isinstance(existing, list):
                existing = []
            existing_clean = _dedupe_keep_order(str(x) for x in existing if x)
            # Prepend curated categories so UI chips and fallback category selection prefer them.
            new_categories = _dedupe_keep_order([*curated_categories, *existing_clean])

            store.collection.update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "categories": new_categories,
                        "metadata.category": primary,
                    }
                },
            )
            updated_posts += 1

            if doc.get("embedding_status") == EmbeddingStatus.READY.value:
                external_id = str(doc.get("external_id") or "")
                if external_id:
                    vectors.set_payload(
                        "substack",
                        external_id,
                        {"categories": new_categories},
                    )
                    updated_ready_payloads += 1

    print(
        {
            "publications_touched": publications_touched,
            "posts_updated": updated_posts,
            "qdrant_payloads_updated_for_ready_posts": updated_ready_payloads,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

