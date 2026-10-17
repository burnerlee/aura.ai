# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Batch scrape a curated list of Substack(-like) publications.

This script:
- normalizes each URL to an origin (scheme://host)
- preflights whether it looks like a Substack publication by calling /api/v1/archive
- runs `scraper scrape substack <origin> --limit N` for publications that pass

Non-Substack sites or Substack search URLs are skipped (with a reason).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

import httpx


URLS: list[str] = [
    # Travel & place
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
    # Culture, art & ideas
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
    # Anime / manga
    "https://theaccidentalotaku.substack.com/",
    "https://www.substack.com/search/Animenomics",
    "https://animationobsessive.substack.com/",
    "https://animeawakening.substack.com/",
    "https://www.substack.com/search/Anime%20Radar",
    # Games / gaming
    "https://newsletter.gamediscover.co/",
    "https://www.gamefile.news/",
    "https://aftermath.site/",
    "https://www.thegamesbusiness.com/",
    "https://www.filfre.net/",
    # Sports
    "https://thesportsletter.com/",
    "https://frontofficesports.com/",
    "https://www.theplayerstribune.com/",
    "https://www.theringer.com/",
    "https://defector.com/",
    # Food / cooking
    "https://carolinechambers.substack.com/",
    "https://smittenkitchen.com/",
    "https://www.nytimes.com/column/the-recipe",
    "https://thefoodsection.com/",
    "https://thecounter.org/",
    # Fashion & beauty
    "https://thecinch.substack.com/",
    "https://www.substack.com/search/Flesh%20World%20Jessica%20DeFino",
    "https://www.blackbirdspyplane.com/",
    "https://cupofjo.substack.com/",
    "https://www.substack.com/search/Fashion%20People",
    # Home & garden
    "https://www.substack.com/search/Home%20India%20Knight",
    "https://erinblegen.substack.com/",
    "https://www.substack.com/search/Aedicula",
    "https://www.theamericanpeasant.com/",
    "https://www.gardenista.com/",
    # Parenting / family
    "https://zawn.substack.com/",
    "https://www.motheruntitled.com/",
    "https://www.theisolationjournals.com/",
    "https://www.substack.com/search/Kids%20Faith%20Meredith%20M%20Miller",
    "https://themomhour.com/",
    # Health / fitness / wellness
    "https://twopct.com/",
    "https://www.substack.com/search/The%20Habit%20Healers",
    "https://brainhealthkitchen.substack.com/",
    "https://susan-cain.com/",
    "https://ashleyneese.substack.com/",
    # Film & TV
    "https://www.hunterharris.com/",
    "https://www.substack.com/search/GOOD%20MOVIE%20Shea%20Serrano",
    "https://www.substack.com/search/Projections%20Sean%20Fennessey",
    "https://theankler.com/",
    "https://animationobsessive.substack.com/",
    # Music
    "https://aquariumdrunkard.com/",
    "https://www.hearingthings.co/",
    "https://www.thenewcue.com/",
    "https://www.blackbirdspyplane.com/",
    "https://www.talkhouse.com/",
    # Design
    "https://www.substack.com/search/WEARSTLERWORLD",
    "https://designbetterpodcast.com/",
    "https://www.theamericanpeasant.com/",
    "https://thecreativeindependent.com/",
    "https://www.densediscovery.com/",
    # Education
    "https://www.learningscientists.org/",
    "https://hechingerreport.org/",
    "https://www.themarginalian.org/",
    "https://worksinprogress.co/",
    "https://knowablemagazine.org/",
    # Faith / religion
    "https://www.substack.com/search/Faith%20Matters",
    "https://www.wayfaremagazine.org/",
    "https://www.substack.com/search/Reclaiming%20Faith%20Jennifer%20Butler",
    "https://thebiblefornormalpeople.com/",
    "https://www.themarginalian.org/",
    # Climate / environment
    "https://heatmap.news/",
    "https://www.volts.wtf/",
    "https://heated.world/",
    "https://www.substack.com/search/Climate%20Change%20and%20You",
    "https://www.substack.com/search/Good%20Climate%20News",
    # News & politics
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
]


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    base_url: str
    reason: str | None = None


def _normalize_base(url: str) -> str | None:
    raw = url.strip()
    if not raw:
        return None
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    if not parsed.netloc:
        return None
    scheme = parsed.scheme or "https"
    return f"{scheme}://{parsed.netloc}"


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        key = item.strip().rstrip("/")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def preflight_substack_publication(base_url: str, client: httpx.Client) -> PreflightResult:
    """Return ok if /api/v1/archive responds with a JSON list."""
    try:
        url = f"{base_url.rstrip('/')}/api/v1/archive"
        resp = client.get(url, params={"sort": "new", "offset": 0, "limit": 1})
        if resp.status_code in (401, 403):
            return PreflightResult(ok=False, base_url=base_url, reason=f"blocked_http_{resp.status_code}")
        if resp.status_code >= 400:
            return PreflightResult(ok=False, base_url=base_url, reason=f"http_{resp.status_code}")
        data = resp.json()
        if isinstance(data, list):
            return PreflightResult(ok=True, base_url=base_url)
        return PreflightResult(ok=False, base_url=base_url, reason=f"non_list_json_{type(data)}")
    except Exception as exc:  # noqa: BLE001
        return PreflightResult(ok=False, base_url=base_url, reason=f"error_{type(exc).__name__}")


def main() -> int:
    limit_per = int(os.environ.get("SUBSTACK_SCRAPE_LIMIT", "5"))
    delay_s = float(os.environ.get("SUBSTACK_SCRAPE_DELAY_S", "0.25"))
    scraper_bin = os.environ.get("SCRAPER_BIN", os.path.join(".venv", "bin", "scraper"))
    only_substack_dot_com = os.environ.get("ONLY_SUBSTACK_DOT_COM", "1") == "1"
    stream_scraper_output = os.environ.get("STREAM_SCRAPER_OUTPUT", "0") == "1"
    preflight_timeout_s = float(os.environ.get("PREFLIGHT_TIMEOUT_S", "10"))

    urls = _dedupe(URLS)
    bases = _dedupe([b for u in urls if (b := _normalize_base(u))])
    if only_substack_dot_com:
        filtered: list[str] = []
        for base in bases:
            host = urlparse(base).netloc.lower()
            if host == "www.substack.com":
                continue
            if host.endswith(".substack.com"):
                filtered.append(base)
        bases = filtered
        print(f"[filter] ONLY_SUBSTACK_DOT_COM=1 -> {len(bases)} candidates", flush=True)

    client = httpx.Client(
        headers={
            "User-Agent": os.environ.get("HTTP_USER_AGENT", "content-scraper/0.1 (+local batch)"),
            "Accept": "application/json,text/html,*/*",
        },
        timeout=preflight_timeout_s,
        follow_redirects=True,
    )

    ok: list[str] = []
    skipped: dict[str, str] = {}
    for idx, base in enumerate(bases, start=1):
        print(f"[preflight] {idx}/{len(bases)} {base}", flush=True)
        r = preflight_substack_publication(base, client)
        if r.ok:
            ok.append(r.base_url)
        else:
            skipped[r.base_url] = r.reason or "unknown"

    print(
        json.dumps({"candidates": len(bases), "scrapable": len(ok), "skipped": len(skipped)}, indent=2),
        flush=True,
    )

    results: list[dict[str, object]] = []
    for idx, base in enumerate(ok, start=1):
        cmd = [scraper_bin, "scrape", "substack", base, "--limit", str(limit_per)]
        print(f"\n[scrape] {idx}/{len(ok)}", flush=True)
        print(f"==> {' '.join(cmd)}", flush=True)
        started = time.time()
        if stream_scraper_output:
            proc = subprocess.run(cmd, check=False, text=True)
        else:
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        duration = round(time.time() - started, 2)
        stdout_tail = None
        stderr_tail = None
        if not stream_scraper_output:
            stdout_tail = (proc.stdout or "").strip()[-600:]
            stderr_tail = (proc.stderr or "").strip()[-600:]
        results.append(
            {
                "base_url": base,
                "ok": proc.returncode == 0,
                "code": proc.returncode,
                "seconds": duration,
                "stdout_tail": stdout_tail,
                "stderr_tail": stderr_tail,
            }
        )
        if delay_s > 0:
            time.sleep(delay_s)

    summary = {
        "limit_per": limit_per,
        "scraped_ok": sum(1 for r in results if r["ok"]),
        "scraped_failed": sum(1 for r in results if not r["ok"]),
        "skipped": skipped,
    }
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

