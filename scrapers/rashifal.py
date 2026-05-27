"""
Scrape today's daily rashifal (राशिफल) from a Nepali news site.

Strategy
--------
Most major Nepali news sites publish a single article per day that contains
all 12 rashis, each as a short paragraph under a rashi-named heading
(मेष / वृष / मिथुन / ... / मीन). We:

  1. Fetch the rashifal section listing page.
  2. Pick the first (most recent) article link from that page.
  3. Fetch the article and walk its heading + paragraph nodes in order.
  4. Whenever a node starts with a known rashi name, the text that follows
     (until the next rashi heading) becomes that rashi's prediction.

Sources are tried in order (Onlinekhabar → Setopati → Ratopati); the first
one that yields ≥ 9 of 12 rashis wins. If all sources fail, the previous
data/rashifal.json (if any) is left untouched.

Output: data/rashifal.json
  {
    "version": 1,
    "type": "daily",
    "published_date": "YYYY-MM-DD",  # source's publish date, best-effort
    "source": "Onlinekhabar",
    "source_url": "https://...",
    "updated_at": "...",
    "rashifal": {
      "mesh":      { "ne": "..." },
      "brish":     { "ne": "..." },
      ...
      "mina":      { "ne": "..." }
    }
  }
"""
from __future__ import annotations

import re
import sys
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common import (
    fetch,
    now_iso,
    read_json_if_exists,
    run_with_fallback,
    today_iso_date,
    write_json,
)

# Slug → Nepali keyword patterns. We match the keyword as a leading token in a
# heading/paragraph (case-sensitive on Devanagari). Some sites use "वृष", some
# "वृषभ"; some "कर्कट", some "कर्क" — handled with synonyms.
RASHI_PATTERNS = {
    "mesh":      ["मेष"],
    "brish":     ["वृष", "वृषभ"],
    "mithun":    ["मिथुन"],
    "karkat":    ["कर्कट", "कर्क"],
    "singha":    ["सिंह"],
    "kanya":     ["कन्या"],
    "tula":      ["तुला"],
    "brishchik": ["वृश्चिक"],
    "dhanu":     ["धनु"],
    "makar":     ["मकर"],
    "kumbha":    ["कुम्भ"],
    "mina":      ["मीन"],
}

# Order matters for first-match: longer keywords first so "वृषभ" wins over "वृष".
_PATTERN_ORDER = sorted(
    [(slug, p) for slug, ps in RASHI_PATTERNS.items() for p in ps],
    key=lambda x: -len(x[1]),
)


def _match_rashi(text: str):
    """Return (slug, matched_keyword) if `text` starts with a rashi name, else None.

    Heuristic: the rashi name should appear within the first ~25 characters
    of the text. Avoids false positives where a body paragraph mentions
    another rashi later in the sentence.
    """
    if not text:
        return None
    head = text[:30]
    for slug, kw in _PATTERN_ORDER:
        if kw in head:
            return slug, kw
    return None


def _strip_leading_rashi(text: str, kw: str) -> str:
    """If the rashi heading contains body text after the name (e.g.
    'मेष: तपाईंलाई आज ...'), strip the leading rashi label so the body is
    preserved cleanly."""
    idx = text.find(kw)
    if idx < 0:
        return text
    rest = text[idx + len(kw):]
    # Strip common separators: ":", "–", "-", whitespace, "राशी" annotation
    rest = re.sub(r"^[\s:|\-–—–—]+", "", rest)
    rest = re.sub(r"^राशी?[\s:|\-–—]*", "", rest)
    return rest.strip()


def _parse_article(html: str) -> dict:
    """Walk the article and return { slug: { 'ne': text } } for every rashi
    we could identify."""
    soup = BeautifulSoup(html, "lxml")

    # Prefer the main article body if we can find it; falls back to <body>.
    body = (
        soup.select_one("article")
        or soup.select_one(".entry-content")
        or soup.select_one(".article-content")
        or soup.select_one(".content")
        or soup.body
        or soup
    )

    # Walk text-bearing block elements in document order.
    nodes = body.select("h1, h2, h3, h4, h5, h6, p, li, strong, b")

    out: dict[str, dict] = {}
    current_slug = None
    current_parts: list[str] = []

    def flush():
        nonlocal current_slug, current_parts
        if current_slug and current_parts:
            text = " ".join(p for p in current_parts if p).strip()
            # Collapse internal whitespace runs.
            text = re.sub(r"\s+", " ", text)
            if text and current_slug not in out:
                out[current_slug] = {"ne": text}
        current_parts = []

    for node in nodes:
        text = node.get_text(" ", strip=True)
        if not text:
            continue

        matched = _match_rashi(text)
        # Treat as a section header when the matched keyword is near the
        # start AND the line is short-ish (typical heading length).
        if matched and len(text) < 120:
            flush()
            slug, kw = matched
            current_slug = slug
            extra = _strip_leading_rashi(text, kw)
            current_parts = [extra] if extra else []
        elif current_slug:
            current_parts.append(text)

    flush()
    return out


def _find_latest_article(section_url: str) -> str:
    """Scan the section listing and return the URL of the most recent post."""
    html = fetch(section_url).text
    soup = BeautifulSoup(html, "lxml")

    # Try a few generic selectors that match typical news-site listings.
    selectors = [
        "article h2 a[href]",
        "article h3 a[href]",
        ".post-title a[href]",
        ".entry-title a[href]",
        "h2.title a[href]",
        "main article a[href]",
        "article a[href]",
    ]
    for sel in selectors:
        link = soup.select_one(sel)
        if link and link.get("href"):
            return urljoin(section_url, link["href"])
    raise RuntimeError(f"No article link found on {section_url}")


def _validate(rashifal: dict, source: str) -> dict:
    """Ensure we got at least 9 of 12 rashis, otherwise reject the source."""
    if len(rashifal) < 9:
        raise RuntimeError(
            f"{source} yielded only {len(rashifal)}/12 rashis — likely a parsing miss"
        )
    return rashifal


def from_onlinekhabar() -> dict:
    section = "https://www.onlinekhabar.com/section/rashifal"
    article_url = _find_latest_article(section)
    article_html = fetch(article_url).text
    rashifal = _validate(_parse_article(article_html), "Onlinekhabar")
    return {
        "type": "daily",
        "rashifal": rashifal,
        "source_url": article_url,
    }


def from_setopati() -> dict:
    # Setopati's social section has a rashifal sub-page.
    section = "https://www.setopati.com/social/rashifal"
    article_url = _find_latest_article(section)
    article_html = fetch(article_url).text
    rashifal = _validate(_parse_article(article_html), "Setopati")
    return {
        "type": "daily",
        "rashifal": rashifal,
        "source_url": article_url,
    }


def from_ratopati() -> dict:
    section = "https://ratopati.com/category/rashifal"
    article_url = _find_latest_article(section)
    article_html = fetch(article_url).text
    rashifal = _validate(_parse_article(article_html), "Ratopati")
    return {
        "type": "daily",
        "rashifal": rashifal,
        "source_url": article_url,
    }


def from_annapurnapost() -> dict:
    section = "https://annapurnapost.prixacdn.net/category/jyotish"
    article_url = _find_latest_article(section)
    article_html = fetch(article_url).text
    rashifal = _validate(_parse_article(article_html), "Annapurna Post")
    return {
        "type": "daily",
        "rashifal": rashifal,
        "source_url": article_url,
    }


def main():
    payload = run_with_fallback(
        "rashifal",
        [
            ("Onlinekhabar",     from_onlinekhabar),
            ("Setopati",         from_setopati),
            ("Ratopati",         from_ratopati),
            ("Annapurna Post",   from_annapurnapost),
        ],
    )
    payload["version"] = 1
    payload["published_date"] = today_iso_date()
    payload["updated_at"] = now_iso()

    # Only write if rashifal text actually changed (avoid empty commits when
    # the cron fires multiple times in a day and the source hasn't published
    # a new article yet).
    existing = read_json_if_exists("rashifal.json", default={}) or {}
    if existing.get("rashifal") == payload.get("rashifal"):
        print("[skip] rashifal unchanged — keeping existing file", flush=True)
        return

    write_json("rashifal.json", payload)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Log and exit non-zero so the calling workflow step records it as
        # failed, but don't crash the whole job (the workflow uses `|| true`).
        print(f"[err] rashifal scrape failed: {e}", flush=True)
        sys.exit(1)
