"""
Scrape today's daily rashifal (राशिफल) for all 12 rashis.

Sources — fallback chain, deliberately NOT the big calendar apps
(Hamro Patro / Nepali Patro) and not the price-scraper sites:

  1. Ashesh.com.np rashifal widget — all 12 rashis in a single request,
     each in a `.rashifal_value` block, in standard order.
  2. Ratopati.com per-rashi daily pages — one request per rashi; the daily
     reading lives in the `#today` tab. Used only if Ashesh fails.

The first source that yields enough rashis wins. If all sources fail, the
previous data/rashifal.json (if any) is left untouched.

Output: data/rashifal.json
  {
    "version": 1,
    "type": "daily",
    "published_date": "YYYY-MM-DD",
    "source": "Ashesh.com.np",
    "source_url": "https://...",
    "updated_at": "...",
    "rashifal": { "mesh": { "ne": "..." }, ..., "mina": { "ne": "..." } }
  }
"""
from __future__ import annotations

import re
import sys

from bs4 import BeautifulSoup

from common import (
    fetch,
    now_iso,
    read_json_if_exists,
    run_with_fallback,
    today_iso_date,
    write_json,
)

# App's canonical slug order (src/screens/RashifalScreen.js). Both sources are
# mapped onto these — the app reads `.ne` per slug.
SLUGS = [
    "mesh", "brish", "mithun", "karkat", "singha", "kanya",
    "tula", "brishchik", "dhanu", "makar", "kumbha", "mina",
]


def _clean(text: str) -> str:
    # \s in Python's re also collapses non-breaking spaces (\xa0) the sources
    # sprinkle in, so &nbsp;/&ndash; entity noise disappears here.
    return re.sub(r"\s+", " ", text or "").strip()


def _validate(rashifal: dict, source: str) -> dict:
    """Reject a source that parsed fewer than 9 of 12 rashis (likely a miss)."""
    if len(rashifal) < 9:
        raise RuntimeError(f"{source} yielded only {len(rashifal)}/12 rashis")
    return rashifal


def from_ashesh() -> dict:
    """All 12 rashis come back in document order from one widget page."""
    soup = BeautifulSoup(fetch("https://www.ashesh.com.np/rashifal/widget.php").text, "lxml")
    values = [_clean(v.get_text(" ", strip=True)) for v in soup.select(".rashifal_value")]
    values = [v for v in values if v]
    if len(values) < 12:
        raise RuntimeError(f"ashesh: expected 12 rashi texts, got {len(values)}")

    rashifal = {slug: {"ne": text} for slug, text in zip(SLUGS, values[:12])}
    return {
        "type": "daily",
        "rashifal": _validate(rashifal, "Ashesh.com.np"),
        "source_url": "https://www.ashesh.com.np/rashifal/",
    }


# Ratopati spells two slugs differently.
_RATOPATI_SLUG = {"brishchik": "brischik", "mina": "meen"}


def from_ratopati() -> dict:
    """One request per rashi; the daily reading lives in the #today tab."""
    rashifal: dict[str, dict] = {}
    for slug in SLUGS:
        rslug = _RATOPATI_SLUG.get(slug, slug)
        try:
            soup = BeautifulSoup(fetch(f"https://www.ratopati.com/rashifal/{rslug}").text, "lxml")
            node = soup.select_one("#today")
            if node is None:
                continue
            text = _clean(" ".join(_clean(p.get_text(" ", strip=True)) for p in node.select("p")))
            if len(text) >= 40:
                rashifal[slug] = {"ne": text}
        except Exception as exc:  # one bad page shouldn't sink the whole source
            print(f"[warn] ratopati {rslug}: {exc}", flush=True)

    return {
        "type": "daily",
        "rashifal": _validate(rashifal, "Ratopati.com"),
        "source_url": "https://www.ratopati.com/rashifal",
    }


def main():
    payload = run_with_fallback(
        "rashifal",
        [
            ("Ashesh.com.np", from_ashesh),
            ("Ratopati.com", from_ratopati),
        ],
    )
    payload["version"] = 1
    payload["published_date"] = today_iso_date()
    payload["updated_at"] = now_iso()

    # Skip the write when the readings are identical to the last run, so the
    # twice-daily / 2-hourly cron doesn't churn empty commits.
    existing = read_json_if_exists("rashifal.json", default={}) or {}
    if existing.get("rashifal") == payload.get("rashifal"):
        print("[skip] rashifal unchanged — keeping existing file", flush=True)
        return

    write_json("rashifal.json", payload)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Non-zero so the workflow step records the failure, but the job's
        # `|| true` keeps other scrapers running and last-known-good in place.
        print(f"[err] rashifal scrape failed: {e}", flush=True)
        sys.exit(1)
