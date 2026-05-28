"""
Scrape Nepal share-issue listings.

Upcoming / existing issues: ShareSansar's existing-issues DataTables endpoint
  GET https://www.sharesansar.com/existing-issues?type=N  -> clean JSON
  type map: ipo=1, fpo=2, rightshare=3, mutualfund=4, ipolocal=5,
            bondsAndDeb=7, ipomigrant=8

Current issues (live application counts): CDSC's server-rendered table
  https://cdsc.com.np/ipolist

Outputs:
  data/issues_upcoming.json  -> { updated_at, categories: { ipo: [...], ... } }
  data/issues_current.json   -> { updated_at, data: [...] }

Each issue row matches the shape the app already renders:
  upcoming: symbol, company, units, price, openingDate, closingDate, status, manager
  current:  company, manager, units, applicants, appliedUnits, amount,
            openingDate, closingDate, lastUpdate
"""
from __future__ import annotations
import re
import sys
from datetime import date

import requests
from bs4 import BeautifulSoup

from common import DEFAULT_HEADERS, TIMEOUT, now_iso, write_json

SHARESANSAR_URL = "https://www.sharesansar.com/existing-issues"

# App category key -> ShareSansar `type` query value.
CATEGORY_TYPES = {
    "ipo": 1,
    "fpo": 2,
    "rightshare": 3,
    "mutualfund": 4,
    "ipolocal": 5,
    "bondsAndDeb": 7,
    "ipomigrant": 8,
}

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value) -> str:
    if not value:
        return ""
    return _TAG_RE.sub("", str(value)).strip()


def _clean_number(value) -> str:
    """'2870000.00' -> '2870000'; keep as string (the app formats it)."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    s = re.sub(r"\.0+$", "", s)
    return s


def _derive_status(opening: str, closing: str) -> str:
    """
    Map opening/closing dates to the text status the app's badge expects
    ("Open" / "Closed" / "Coming Soon"). Date-based so it never depends on a
    fragile source-specific status code.
    """
    today = date.today().isoformat()
    if opening and today < opening:
        return "Coming Soon"
    if closing and today > closing:
        return "Closed"
    if opening and closing and opening <= today <= closing:
        return "Open"
    # No usable dates — leave blank so the UI just omits the badge.
    return ""


def _datatables_params(type_num: int) -> dict:
    """ShareSansar's DataTables server-side processing needs the full param
    set, otherwise it returns 0 records."""
    # NOTE: ShareSansar rejects large page sizes (length>50 returns HTTP 202
    # with zero records), so keep length at 50 and trim/sort in Python.
    params = {
        "draw": "1",
        "start": "0",
        "length": "50",
        "search[value]": "",
        "search[regex]": "false",
        "type": str(type_num),
        "order[0][column]": "0",
        "order[0][dir]": "desc",
    }
    for c in range(0, 17):
        params[f"columns[{c}][data]"] = str(c)
        params[f"columns[{c}][name]"] = ""
        params[f"columns[{c}][searchable]"] = "true"
        params[f"columns[{c}][orderable]"] = "true"
        params[f"columns[{c}][search][value]"] = ""
        params[f"columns[{c}][search][regex]"] = "false"
    return params


def from_sharesansar():
    session = requests.Session()
    session.headers.update(
        {
            **DEFAULT_HEADERS,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": SHARESANSAR_URL,
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }
    )
    # Prime cookies.
    session.get(SHARESANSAR_URL, timeout=TIMEOUT)

    categories: dict[str, list] = {}
    total_rows = 0
    for key, type_num in CATEGORY_TYPES.items():
        try:
            res = session.get(
                SHARESANSAR_URL, params=_datatables_params(type_num), timeout=TIMEOUT
            )
            rows = res.json().get("data", []) or []
        except Exception:
            rows = []

        items = []
        for r in rows:
            company = r.get("company") or {}
            opening = (r.get("opening_date") or "").strip()
            closing = (r.get("closing_date") or "").strip()
            symbol = _strip_html(company.get("symbol"))
            name = _strip_html(company.get("companyname"))
            if not name and not symbol:
                continue
            price = _clean_number(r.get("issue_price"))
            # Book-building issues use a range instead of a flat price.
            price_range = (r.get("price_range") or "").strip()
            if (not price or price == "0") and price_range and price_range != "to":
                price = price_range
            items.append(
                {
                    "symbol": symbol,
                    "company": name,
                    "units": _clean_number(r.get("total_units")),
                    "price": price,
                    "openingDate": opening,
                    "closingDate": closing,
                    "status": _derive_status(opening, closing),
                    "manager": (r.get("issue_manager") or "").strip(),
                }
            )
        # Newest first, then keep a recent window (upcoming + open + recently
        # closed) — drops years of historical issues the source also returns.
        items.sort(key=lambda x: x["openingDate"] or "", reverse=True)
        items = items[:25]
        categories[key] = items
        total_rows += len(items)

    if total_rows == 0:
        raise ValueError("ShareSansar returned no rows across any category")

    return {"categories": categories}


def scrape_current():
    """CDSC ipolist is server-rendered; parse the table directly."""
    res = requests.get(
        "https://cdsc.com.np/ipolist", headers=DEFAULT_HEADERS, timeout=TIMEOUT
    )
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "lxml")
    table = soup.select_one("#listall table") or soup.find("table")
    if not table:
        raise ValueError("no current-issues table found on CDSC ipolist")

    items = []
    for row in table.select("tbody tr"):
        cols = [c.get_text(strip=True) for c in row.select("td")]
        if len(cols) < 10:
            continue
        items.append(
            {
                "company": cols[1],
                "manager": cols[2],
                "units": _clean_number(cols[3]),
                "applicants": cols[4],
                "appliedUnits": _clean_number(cols[5]),
                "amount": _clean_number(cols[6]),
                "openingDate": cols[7],
                "closingDate": cols[8],
                "lastUpdate": cols[9],
            }
        )
    return items


def main():
    # Upcoming / existing issues (ShareSansar). If it fails entirely, keep the
    # previous snapshot rather than overwriting with nothing.
    try:
        upcoming = from_sharesansar()
        upcoming["source"] = "ShareSansar"
        upcoming["updated_at"] = now_iso()
        write_json("issues_upcoming.json", upcoming)
    except Exception as exc:
        print(f"[fail] upcoming: {exc}", file=sys.stderr)

    # Current issues (CDSC).
    try:
        current = scrape_current()
        write_json(
            "issues_current.json",
            {"source": "CDSC", "updated_at": now_iso(), "data": current},
        )
    except Exception as exc:
        print(f"[fail] current: {exc}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
