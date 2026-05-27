"""
Scrape Nepal retail fuel prices, grouped by depot zone.

Primary: NepaliPatro NOC API — well-structured JSON keyed by city, reliable.
Fallback: noc.org.np/retailprice HTML scrape.

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


# Map raw HTML header labels -> internal product keys
PRODUCT_MAP_HTML = {
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

# NepaliPatro API "type" strings -> internal product keys
PRODUCT_MAP_API = [
    ("petrol", "petrol"),
    ("diesel", "diesel"),
    ("kerosene", "kerosene"),
    ("lp gas", "lpg"),
    ("lpg", "lpg"),
    ("atf", "jet_a1"),
    ("jet", "jet_a1"),
]


def _zone_for_city(city: str):
    """Bucket a city/depot name into one of our 3 published zones."""
    c = (city or "").lower()
    if any(x in c for x in ("kathmandu", "pokhara", "dipayal", "valley")):
        return ("kathmandu", "Kathmandu / Pokhara / Dipayal")
    if any(x in c for x in ("biratnagar", "charali", "birgunj", "amlekhgunj", "janakpur")):
        return ("terai", "Terai (Biratnagar / Charali / Birgunj)")
    if any(x in c for x in ("surkhet", "dang", "nepalgunj")):
        return ("surkhet", "Surkhet / Dang / Nepalgunj")
    return None


def from_nepalipatro_api():
    """NepaliPatro proxies the NOC table as JSON. Reliable and well-structured."""
    res = fetch(
        "https://api.nepalipatro.com.np/api/noc/public/prices?lang=en",
        headers={"Referer": "https://nepalipatro.com.np/"},
    )
    j = res.json()

    zones: dict = {}
    effective = j.get("last_updated_at")

    for entry in j.get("data", []) or []:
        city = entry.get("city", "")
        bucket = _zone_for_city(city)
        if not bucket:
            continue
        zone_key, default_label = bucket
        zone = zones.setdefault(zone_key, {"label": default_label, "cities": []})
        if city and city not in zone["cities"]:
            zone["cities"].append(city)

        for item in entry.get("detail", []) or []:
            t = (item.get("type") or "").lower()
            product = None
            for keyword, key in PRODUCT_MAP_API:
                if keyword in t:
                    product = key
                    break
            if not product:
                continue
            val = _num(item.get("price"))
            # First city wins per zone — keeps numbers stable when zones span multiple depots.
            if val is not None and product not in zone:
                zone[product] = val

    if not zones:
        raise ValueError("NepaliPatro NOC API returned no usable zones")

    return {
        "currency": "NPR",
        "unit_fuel": "per liter",
        "unit_lpg": "per cylinder",
        "effective": effective,
        "zones": zones,
    }


def from_noc_html():
    """
    Fallback: parse noc.org.np/retailprice directly.
    Often fragile (the markup changes), but useful if the API is down.
    """
    html = fetch("https://noc.org.np/retailprice").text
    soup = BeautifulSoup(html, "lxml")

    tables = soup.find_all("table")
    if not tables:
        raise ValueError("no <table> found on NOC retailprice page")

    zones: dict = {}
    effective = None

    for table in tables:
        headers = [
            h.get_text(" ", strip=True).lower() for h in table.find_all("th")
        ]
        if not headers:
            continue
        rows = table.find_all("tr")
        for row in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
            if len(cells) < len(headers):
                continue
            location_label = _detect_location(table, cells)
            if not location_label:
                continue
            bucket = _zone_for_city(location_label)
            if not bucket:
                continue
            zone_key, default_label = bucket
            zone = zones.setdefault(zone_key, {"label": default_label})
            for header, cell in zip(headers, cells):
                product_key = _product_for_header_html(header)
                if not product_key:
                    if "date" in header and not effective:
                        effective = cell
                    continue
                value = _num(cell)
                if value is not None and product_key not in zone:
                    zone[product_key] = value

    if not zones:
        raise ValueError("could not parse NOC table into known zones")

    return {
        "currency": "NPR",
        "unit_fuel": "per liter",
        "unit_lpg": "per cylinder",
        "effective": effective,
        "zones": zones,
    }


def _product_for_header_html(header: str):
    h = header.lower()
    if "df" in h or "duty-free" in h or "duty free" in h:
        return None
    for keyword, key in PRODUCT_MAP_HTML.items():
        if keyword in h:
            return key
    return None


def _detect_location(table, cells):
    caption = table.find("caption")
    if caption:
        return caption.get_text(" ", strip=True)
    prev = table.find_previous(["h1", "h2", "h3", "h4", "p", "strong"])
    if prev:
        text = prev.get_text(" ", strip=True)
        if any(
            city in text
            for city in (
                "Kathmandu",
                "Pokhara",
                "Dipayal",
                "Surkhet",
                "Dang",
                "Biratnagar",
                "Birgunj",
                "Nepalgunj",
                "Charali",
            )
        ):
            return text
    return cells[0] if cells else None


def main():
    payload = run_with_fallback(
        "fuel",
        [
            ("NepaliPatro NOC API", from_nepalipatro_api),
            ("Nepal Oil Corporation", from_noc_html),
        ],
    )
    write_json("fuel.json", payload)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
