"""Shared helpers for all scrapers."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Browser-like UA — some Nepali gov sites block default python-requests UA.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ne;q=0.8",
}

TIMEOUT = 20


def fetch(url, **kw):
    """GET with sensible defaults. Raises on non-2xx."""
    headers = {**DEFAULT_HEADERS, **kw.pop("headers", {})}
    r = requests.get(url, headers=headers, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(filename, payload):
    """Atomically overwrite data/<filename> with payload."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / filename
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(out_path)
    print(f"[ok] wrote {out_path}", flush=True)


def run_with_fallback(name, scrapers):
    """
    Try each scraper in order until one succeeds.
    `scrapers` is a list of (label, callable) — each callable returns a payload dict
    or raises an exception.
    """
    errors = []
    for label, fn in scrapers:
        try:
            print(f"[try] {name}: {label}", flush=True)
            payload = fn()
            payload["source"] = label
            payload["updated_at"] = now_iso()
            return payload
        except Exception as exc:
            print(f"[fail] {label}: {exc}", flush=True)
            errors.append(f"{label}: {exc}")
    raise RuntimeError(
        f"All sources failed for {name}. Tried:\n  - " + "\n  - ".join(errors)
    )
