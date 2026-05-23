"""
Scrape Nepal Oil Corporation retail fuel prices.
Source: https://noc.org.np/retailprice (public, no login)

Output: data/fuel.json
"""
from __future__ import annotations
import re
import sys

from bs4 import BeautifulSoup

from common import fetch, run_with_fallback, write_json


def _num(s):
    digits = re.sub(r"[^\d.]", "", str(s))
    if not digits:
        return None
    try:
        return float(digits)
    except ValueError:
        return None


# Map raw header labels -> our internal product keys
PRODUCT_MAP = {
    "petrol": "petrol",
    "ms": "petrol",
    "diesel": "diesel",
    "hsd": "diesel",
    "kerosene": "kerosene",
    "sko": "kerosene",
    "lpg": "lpg",
    "atf": "jet_a1",
    "jet": "jet_a1",
}


def from_noc():
    """
    The /retailprice page shows the most-recent row of a price table.
    We grab the first data row of the main table and map columns by header.
    """
    html = fetch("https://noc.org.np/retailprice").text
    soup = BeautifulSoup(html, "lxml")

    tables = soup.find_all("table")
    if not tables:
        raise ValueError("no <table> found on NOC retailprice page")

    # Each table contains rows like: location | date | petrol | diesel | kerosene | LPG ...
    zones = {}
    effective = None

    for table in tables:
        headers = [
            h.get_text(" ", strip=True).lower()
            for h in table.find_all("th")
        ]
        if not headers:
            continue
        rows = table.find_all("tr")
        for row in rows[1:]:  # skip header row
            cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
            if len(cells) < len(headers):
                continue
            # Pick a location label (NOC sometimes labels each table; otherwise
            # the first cell is the location/depot group).
            location_label = _detect_location(table, cells)
            if not location_label:
                continue

            zone_key = _zone_key(location_label)
            zone = zones.setdefault(zone_key, {"label": location_label})

            for header, cell in zip(headers, cells):
                product_key = _product_for_header(header)
                if not product_key:
                    if "date" in header and not effective:
                        effective = cell
                    continue
                value = _num(cell)
                if value is not None:
                    zone[product_key] = value

    if not zones:
        raise ValueError("could not parse NOC table")

    return {
        "currency": "NPR",
        "unit_fuel": "per liter",
        "unit_lpg": "per cylinder",
        "effective": effective,
        "zones": zones,
    }


def _product_for_header(header: str):
    h = header.lower()
    for keyword, key in PRODUCT_MAP.items():
        if keyword in h:
            # ATF / Jet A-1 has duty-paid and duty-free variants — keep just one
            if "df" in h or "duty-free" in h or "duty free" in h:
                return None
            return key
    return None


def _detect_location(table, cells):
    """Look for a caption / preceding heading that names the depot group."""
    caption = table.find("caption")
    if caption:
        return caption.get_text(" ", strip=True)
    prev = table.find_previous(["h1", "h2", "h3", "h4", "p", "strong"])
    if prev:
        text = prev.get_text(" ", strip=True)
        if any(city in text for city in (
            "Kathmandu", "Pokhara", "Dipayal", "Surkhet", "Dang",
            "Biratnagar", "Birgunj", "Nepalgunj", "Charali",
        )):
            return text
    # Fallback: first cell of the row
    return cells[0] if cells else None


def _zone_key(label: str) -> str:
    """Group depot labels into our 3 buckets."""
    l = label.lower()
    if "kathmandu" in l or "pokhara" in l or "dipayal" in l:
        return "kathmandu"
    if "surkhet" in l or "dang" in l:
        return "surkhet_dang"
    return "eastern_depots"


def main():
    payload = run_with_fallback("fuel", [
        ("Nepal Oil Corporation", from_noc),
    ])
    write_json("fuel.json", payload)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
