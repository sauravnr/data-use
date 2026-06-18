"""
Scrape the NEPSE symbol -> sector map for the IPO app's Portfolio screen.

The app ships a hand-curated fallback list, but newly-listed companies would be
stuck showing "Others" until the next app release. This feed fixes that: the app
fetches data/sectors.json on open and layers it over its bundled list, so new
listings get the right sector with no app update.

Sector is resolved per listed symbol with a priority chain, most trustworthy
first:
  1. The previous sectors.json entry  -> authoritative, never reclassified.
     (Preserves the app's curated mapping and keeps results stable.)
  2. ShareSansar's sectorwise-share-price page -> NEPSE's own grouping. Only the
     most-traded symbols per sector are server-rendered there, but those are
     exactly the ones users tend to hold.
  3. A keyword heuristic on the company name -> backstops the long tail (new
     hydropower / microfinance / insurance listings are unambiguous by name).
  4. "Others".

Sources (all confirmed-stable server-rendered HTML, same site issues.py uses):
  - https://www.sharesansar.com/today-share-price     -> full listed universe
  - https://www.sharesansar.com/sectorwise-share-price -> authoritative sectors
  - https://www.sharesansar.com/company-list           -> symbol -> company name

Last-known-good is preserved: a source failure or a suspiciously small result
will not overwrite the existing file.
"""
import re

from common import fetch, now_iso, read_json_if_exists, write_json

OUT_FILE = "sectors.json"

TODAY_PRICE_URL = "https://www.sharesansar.com/today-share-price"
SECTORWISE_URL = "https://www.sharesansar.com/sectorwise-share-price"
COMPANY_LIST_URL = "https://www.sharesansar.com/company-list"

# ShareSansar sector heading -> the exact label the app's bundled list uses.
SS_SECTOR_MAP = {
    "Commercial Bank": "Commercial Banks",
    "Development Bank": "Development Banks",
    "Finance": "Finance Companies",
    "Microfinance": "Microfinance",
    "Life Insurance": "Life Insurance",
    "Non-Life Insurance": "Non-Life Insurance",
    "Hydropower": "Hydropower",
    "Hotel & Tourism": "Hotels and Tourism",
    "Manufacturing and Processing": "Manufacturing and Processing",
    "Investment": "Investment",
    "Mutual Fund": "Mutual Funds",
    "Trading": "Trading",
    "Promoter Share": "Promoter Shares",
    "Others": "Others",
    # The app has no dedicated bucket for these; fold into Others.
    "Corporate Debentures": "Others",
    "Government Bonds": "Others",
}

# Ordered most-specific first; first match wins. Used only for symbols neither
# already known nor present in the authoritative sectorwise grouping.
NAME_RULES = [
    (r"\blaghubitta\b|microfinance|micro finance|bittiya sanstha", "Microfinance"),
    (r"hydro|jalvidhyut|jal vidhyut|power compan|\bbidhyut\b|urja|\benergy\b", "Hydropower"),
    (r"non.?life|general insurance|nonlife", "Non-Life Insurance"),
    (r"life insurance|jeevan beema|\blife\b", "Life Insurance"),
    (r"\binsurance\b|beema", "Non-Life Insurance"),
    (r"development bank", "Development Banks"),
    (r"\bfinance\b", "Finance Companies"),
    (r"mutual fund|\bscheme\b|\byojana\b", "Mutual Funds"),
    (r"investment", "Investment"),
    (r"hotel|resort|tourism|hospitalit", "Hotels and Tourism"),
    (r"manufactur|cement|steel|sugar|distiller|brewer|industr|processing|"
     r"\bfoods?\b|textile|polymer|\bpipe", "Manufacturing and Processing"),
    (r"trading|\btrade\b", "Trading"),
    (r"\bbank\b", "Commercial Banks"),  # plain "... Bank Limited"
]

PROMOTER_SUFFIXES = ("P", "PO")


def classify_by_name(symbol: str, name: str) -> str:
    sym = symbol.upper()
    if len(sym) > 3 and sym.endswith(PROMOTER_SUFFIXES):
        return "Promoter Shares"
    low = name.lower()
    for pattern, label in NAME_RULES:
        if re.search(pattern, low):
            return label
    return "Others"


def fetch_listed_symbols() -> set:
    """Every currently-listed symbol, from the today-share-price table."""
    html = fetch(TODAY_PRICE_URL).text
    syms = {s.upper() for s in re.findall(r'/company/([A-Za-z0-9]+)"', html)}
    if len(syms) < 150:
        raise RuntimeError(f"today-share-price returned only {len(syms)} symbols")
    return syms


def fetch_symbol_names() -> dict:
    """{SYMBOL: company name} from the company-list inline JSON."""
    html = fetch(COMPANY_LIST_URL).text
    objs = re.findall(
        r'\{"id":\d+,"symbol":"([^"]+)","companyname":"([^"]*)"\}', html
    )
    return {sym.upper(): name for sym, name in objs}


def fetch_authoritative_sectors() -> dict:
    """
    {SYMBOL: app-sector-label} for the symbols ShareSansar renders under each
    sector heading on sectorwise-share-price. Partial (top rows per sector) but
    authoritative for what it covers.
    """
    html = fetch(SECTORWISE_URL).text
    # Locate each sector heading, then grab the /company/SYM links that follow it
    # up to the next heading.
    heads = []
    for raw_label, app_label in SS_SECTOR_MAP.items():
        # Headings render with & as &amp;
        needle = raw_label.replace("&", "&amp;")
        m = re.search(r"<h[1-5][^>]*>\s*" + re.escape(needle) + r"\s*</h[1-5]>", html)
        if m:
            heads.append((m.start(), app_label))
    heads.sort()
    out = {}
    for i, (pos, label) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(html)
        for sym in re.findall(r'/company/([A-Za-z0-9]+)"', html[pos:end]):
            out[sym.upper()] = label
    return out


def build() -> dict:
    prior = read_json_if_exists(OUT_FILE, default={}) or {}
    known = dict(prior.get("data", {})) if isinstance(prior, dict) else {}

    listed = fetch_listed_symbols()
    authoritative = fetch_authoritative_sectors()  # may be partial
    names = fetch_symbol_names()

    result = dict(known)  # last-known-good: never drop a symbol we had
    added = 0
    for sym in listed:
        if sym in result:
            continue  # already authoritative — keep it stable
        if sym in authoritative:
            result[sym] = authoritative[sym]
        else:
            result[sym] = classify_by_name(sym, names.get(sym, ""))
        added += 1

    result = dict(sorted(result.items()))
    print(
        f"[ok] sectors: {len(result)} symbols "
        f"({added} new; {len(authoritative)} authoritative this run)",
        flush=True,
    )
    return {
        "source": "sharesansar:sectorwise+today-share-price",
        "updated_at": now_iso(),
        "count": len(result),
        "data": result,
    }


def main():
    payload = build()
    if payload["count"] < 150:
        raise RuntimeError(f"refusing to write only {payload['count']} symbols")
    write_json(OUT_FILE, payload)


if __name__ == "__main__":
    main()
