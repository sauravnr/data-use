"""
Scrape gold & silver rates published daily by FENEGOSIDA.
Primary:  fenegosida.org (often down — that's why we have fallbacks)
Fallback: sharesansar.com/bullion (republishes FENEGOSIDA rates)

Output: data/gold_silver.json
"""
from __future__ import annotations
import re
import sys

from bs4 import BeautifulSoup

from common import fetch, run_with_fallback, write_json

# 1 tola = 11.6638 grams (the Nepali jeweller-standard)
TOLA_GRAMS = 11.6638


def _to_int(s) -> int:
    """'Rs. 2,93,700' or '293,700' -> 293700."""
    digits = re.sub(r"[^\d]", "", str(s))
    if not digits:
        raise ValueError(f"no digits in {s!r}")
    return int(digits)


def _per_10g(per_tola: int) -> int:
    return round(per_tola / TOLA_GRAMS * 10)


# ----- Primary: FENEGOSIDA --------------------------------------------------
def from_fenegosida():
    """
    FENEGOSIDA shows rates in a table on the homepage. Columns vary but
    typically include: Hallmark (Fine) Gold, Tejabi Gold, Silver — each per tola.
    """
    html = fetch("https://www.fenegosida.org/").text
    soup = BeautifulSoup(html, "lxml")

    rates = {}
    # Look for any table containing the words 'gold'/'silver'/'tola'
    for table in soup.find_all("table"):
        text = table.get_text(" ", strip=True).lower()
        if not any(w in text for w in ("gold", "silver", "सुन", "चाँदी")):
            continue
        for row in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            label = cells[0].lower()
            try:
                value = _to_int(cells[1])
            except ValueError:
                continue
            if "fine" in label or "hallmark" in label or "हल" in label:
                rates["fine_gold_per_tola"] = value
            elif "tejabi" in label or "तेजाबी" in label:
                rates["tejabi_gold_per_tola"] = value
            elif "silver" in label or "चाँदी" in label:
                rates["silver_per_tola"] = value

    if "fine_gold_per_tola" not in rates or "silver_per_tola" not in rates:
        raise ValueError("could not parse FENEGOSIDA table")

    return _build_payload(rates)


# ----- Fallback: ShareSansar ------------------------------------------------
def from_sharesansar():
    """
    ShareSansar shows rates in a 'Bullion Price' panel. We grab numbers near
    the keywords 'Fine Gold', 'Tejabi', 'Silver'.
    """
    html = fetch("https://www.sharesansar.com/bullion").text
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    def grab(label_regex):
        m = re.search(label_regex + r"[^\d]{0,30}(\d[\d,]{2,})", text, re.IGNORECASE)
        if not m:
            raise ValueError(f"no match for {label_regex!r}")
        return _to_int(m.group(1))

    rates = {
        "fine_gold_per_tola":  grab(r"fine\s*gold"),
        "tejabi_gold_per_tola": grab(r"tejabi\s*gold"),
        "silver_per_tola":     grab(r"silver"),
    }
    return _build_payload(rates)


def _build_payload(rates: dict) -> dict:
    """Add per-10g conversions and shape the final payload."""
    out = {
        "currency": "NPR",
        "rates": {
            "fine_gold_per_tola":   rates["fine_gold_per_tola"],
            "fine_gold_per_10g":    _per_10g(rates["fine_gold_per_tola"]),
            "silver_per_tola":      rates["silver_per_tola"],
            "silver_per_10g":       _per_10g(rates["silver_per_tola"]),
        },
    }
    if "tejabi_gold_per_tola" in rates:
        out["rates"]["tejabi_gold_per_tola"] = rates["tejabi_gold_per_tola"]
        out["rates"]["tejabi_gold_per_10g"]  = _per_10g(rates["tejabi_gold_per_tola"])
    return out


def main():
    payload = run_with_fallback("gold_silver", [
        ("FENEGOSIDA",  from_fenegosida),
        ("ShareSansar", from_sharesansar),
    ])
    write_json("gold_silver.json", payload)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
