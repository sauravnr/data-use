"""
Scrape Kalimati Fruits and Vegetable Market wholesale prices.
Source: https://kalimatimarket.gov.np/price

Output: data/vegetables.json
"""
from __future__ import annotations
import re
import sys

from bs4 import BeautifulSoup

from common import fetch, run_with_fallback, write_json

# Kalimati lists commodity names in Nepali only. We translate the most common
# items so the app can show English labels too. Unknown items fall through
# with their Nepali name only — that's fine.
NEPALI_TO_ENGLISH = {
    "गोलभेडा": "Tomato",
    "आलु": "Potato",
    "प्याज": "Onion",
    "गाजर": "Carrot",
    "काउली": "Cauliflower",
    "बन्दा": "Cabbage",
    "मूला": "Radish",
    "भन्टा": "Eggplant",
    "बैगन": "Eggplant",
    "भिण्डी": "Okra",
    "करेला": "Bitter gourd",
    "लौका": "Bottle gourd",
    "फर्सी": "Pumpkin",
    "खुर्सानी": "Chili",
    "अदुवा": "Ginger",
    "लसुन": "Garlic",
    "धनिया": "Coriander",
    "पालुङ्गो": "Spinach",
    "साग": "Greens",
    "मटर": "Peas",
    "कुरिलो": "Asparagus",
    "मशरुम": "Mushroom",
    "च्याउ": "Mushroom",
    "स्याउ": "Apple",
    "केरा": "Banana",
    "सुन्तला": "Orange",
    "अंगुर": "Grapes",
    "अनार": "Pomegranate",
    "आँप": "Mango",
    "नासपाती": "Pear",
    "मेवा": "Papaya",
    "अनानास": "Pineapple",
    "खरबुजा": "Melon",
    "तरबुजा": "Watermelon",
    "नरिवल": "Coconut",
    "निम्बु": "Lemon",
    "कागती": "Lemon",
    "रायो": "Mustard greens",
    "तोफु": "Tofu",
    "गुन्द्रुक": "Gundruk",
}


def _num(s):
    digits = re.sub(r"[^\d.]", "", str(s))
    if not digits:
        return None
    try:
        return float(digits)
    except ValueError:
        return None


def _translate(name_ne: str) -> str | None:
    """Find the first dictionary key that appears in the Nepali commodity name."""
    for key, english in NEPALI_TO_ENGLISH.items():
        if key in name_ne:
            return english
    return None


def from_kalimati():
    html = fetch("https://kalimatimarket.gov.np/price").text
    soup = BeautifulSoup(html, "lxml")

    # Kalimati's page has one main price table. Find the one with the most rows.
    candidate = None
    candidate_rows = 0
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) > candidate_rows:
            candidate = table
            candidate_rows = len(rows)
    if candidate is None or candidate_rows < 5:
        raise ValueError("could not find price table on Kalimati page")

    items = []
    for row in candidate.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
        # Expected: [commodity, unit, min, max, avg]
        if len(cells) < 5:
            continue
        name_ne, unit, raw_min, raw_max, raw_avg = cells[0], cells[1], cells[2], cells[3], cells[4]
        if not name_ne:
            continue
        mn, mx, avg = _num(raw_min), _num(raw_max), _num(raw_avg)
        if avg is None:
            continue
        items.append({
            "name_ne": name_ne,
            "name_en": _translate(name_ne),
            "unit": unit,
            "min": mn,
            "max": mx,
            "avg": avg,
        })

    if not items:
        raise ValueError("price table parsed 0 items")

    return {
        "currency": "NPR",
        "unit_default": "per kg",
        "count": len(items),
        "items": items,
    }


def main():
    payload = run_with_fallback("vegetables", [
        ("Kalimati Market", from_kalimati),
    ])
    write_json("vegetables.json", payload)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
