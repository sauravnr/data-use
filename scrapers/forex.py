"""
Scrape NRB (Nepal Rastra Bank) foreign exchange rates.

NRB exposes a clean JSON API — no HTML scraping needed:
    https://www.nrb.org.np/api/forex/v1/rates?from=YYYY-MM-DD&to=YYYY-MM-DD&per_page=100&page=1

Output: data/forex.json
"""
from __future__ import annotations
import sys
from datetime import datetime, timezone

from common import fetch, now_iso, run_with_fallback, write_json

NRB_API = "https://www.nrb.org.np/api/forex/v1/rates"

# Nepali translations for currency names (matches what NRB publishes).
NE_NAMES = {
    "INR": "भारतीय रुपैयाँ",
    "USD": "अमेरिकी डलर",
    "EUR": "युरो",
    "GBP": "बेलायती पाउण्ड",
    "CHF": "स्विस फ्रांक",
    "AUD": "अष्ट्रेलियन डलर",
    "CAD": "क्यानेडियन डलर",
    "SGD": "सिंगापुरी डलर",
    "JPY": "जापानी येन",
    "CNY": "चिनियाँ युआन",
    "SAR": "साउदी रियाल",
    "QAR": "कतारी रियाल",
    "THB": "थाई बाहत",
    "AED": "युएई दिर्हाम",
    "MYR": "मलेसियन रिंगिट",
    "KRW": "कोरियन वोन",
    "SEK": "स्विडिश क्रोनर",
    "DKK": "डेनिस क्रोनर",
    "HKD": "हङकङ डलर",
    "KWD": "कुवेती दिनार",
    "BHD": "बहरेनी दिनार",
    "OMR": "ओमानी रियाल",
}

# ISO 4217 currency → ISO 3166-1 alpha-2 country (for flag emoji rendering).
COUNTRY_CODE = {
    "INR": "IN", "USD": "US", "EUR": "EU", "GBP": "GB",
    "CHF": "CH", "AUD": "AU", "CAD": "CA", "SGD": "SG",
    "JPY": "JP", "CNY": "CN", "SAR": "SA", "QAR": "QA",
    "THB": "TH", "AED": "AE", "MYR": "MY", "KRW": "KR",
    "SEK": "SE", "DKK": "DK", "HKD": "HK", "KWD": "KW",
    "BHD": "BH", "OMR": "OM",
}


def from_nrb_today():
    """Fetch today's rates. If today's not published yet, NRB returns empty."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _fetch_for_date(today)


def from_nrb_recent():
    """Fallback — request a 7-day window and take the latest published date."""
    from datetime import timedelta
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=7)
    return _fetch_for_date(start.isoformat(), end.isoformat())


def _fetch_for_date(start: str, end: str | None = None):
    end = end or start
    url = f"{NRB_API}?from={start}&to={end}&per_page=100&page=1"
    r = fetch(url, headers={"Accept": "application/json"})
    body = r.json()

    payload = (body.get("data") or {}).get("payload") or []
    if not payload:
        raise ValueError(f"NRB returned no rates for {start}..{end}")

    # Take the most recent date in the response
    latest = sorted(payload, key=lambda d: d.get("date", ""), reverse=True)[0]
    raw_rates = latest.get("rates") or []
    if not raw_rates:
        raise ValueError(f"NRB published {latest.get('date')} with empty rates")

    out_rates = []
    for r in raw_rates:
        cur = r.get("currency") or {}
        iso3 = (cur.get("iso3") or "").upper()
        if not iso3:
            continue
        out_rates.append({
            "iso3":    iso3,
            "name_en": cur.get("name") or iso3,
            "name_ne": NE_NAMES.get(iso3, cur.get("name") or iso3),
            "country": COUNTRY_CODE.get(iso3, ""),
            "unit":    int(cur.get("unit") or 1),
            "buy":     float(r["buy"])  if r.get("buy")  else None,
            "sell":    float(r["sell"]) if r.get("sell") else None,
        })

    return {
        "currency": "NPR",
        "as_of_date": latest.get("date"),
        "rates": out_rates,
    }


def main():
    payload = run_with_fallback("forex", [
        ("NRB",        from_nrb_today),
        ("NRB-recent", from_nrb_recent),
    ])
    write_json("forex.json", payload)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
