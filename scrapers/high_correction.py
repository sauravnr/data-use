"""
Correction for forecast daily highs, learned from DHM's measured highs.

The app shows the average of two Open-Meteo models (best_match and
icon_seamless). Checked against DHM's manual stations in Oct/Nov 2026, that
average put afternoon highs about 2.4 °C too low almost everywhere (lows were
fine). Correcting each city with its nearest station's recent bias cut the
average error from 2.8 °C to 0.9 °C in a 7-day backtest.

How it works:
  - DHM's evening report (issued 12:00 UTC, 17:45 NPT) has each station's
    high for that same day. Those highs are kept for 14 days in
    data/dhm_history.json.
  - For the same days and places, the two models' forecast highs come from
    Open-Meteo's historical-forecast API.
  - bias = measured high - model high, averaged per station over the last
    10 days (at least 3 days, else the station is skipped).
  - Each app city takes the bias of its nearest station if that is within
    15 km (5 km for cities above 1,500 m, where a few km can mean a very
    different height), otherwise the median of all station biases. DHM's
    station positions are rounded, so their height can't be looked up reliably.

The app adds the bias to the daily highs. Nothing is published until there
are at least 5 days of history.
"""
from __future__ import annotations

import math
import statistics

from common import fetch, read_json_if_exists, write_json

HISTORY_FILE = "dhm_history.json"
KEEP_DAYS = 14
BIAS_DAYS = 10
MIN_STATION_DAYS = 3
MIN_HISTORY_DAYS = 5
CITY_MAX_KM = 15
MOUNTAIN_CITY_M = 1500
MOUNTAIN_MAX_KM = 5
CLAMP = (-2.0, 8.0)
MODELS = ("best_match", "icon_seamless")   # must match WeatherScreen.js


def update_history(issue_date, stations):
    """Store today's measured highs from an evening report. Returns the history."""
    hist = read_json_if_exists(HISTORY_FILE, default={"days": {}, "stations": {}})
    hist.setdefault("days", {})
    hist.setdefault("stations", {})
    # Only the 12:00 UTC (evening) report carries that day's high.
    if issue_date and issue_date[11:13] == "12":
        day = issue_date[:10]
        highs = {s["name"]: s["max_temp"] for s in stations
                 if s.get("name") and s.get("max_temp") is not None}
        if highs:
            hist["days"][day] = highs
            for s in stations:
                if s.get("name") and s.get("lat") is not None and s.get("lon") is not None:
                    hist["stations"][s["name"]] = [s["lat"], s["lon"]]
            for old in sorted(hist["days"])[:-KEEP_DAYS]:
                del hist["days"][old]
            write_json(HISTORY_FILE, hist)
    return hist


def _model_highs(names, coords, start, end):
    """{model: {station: {date: high}}} from the historical-forecast API."""
    lat = ",".join(str(coords[n][0]) for n in names)
    lon = ",".join(str(coords[n][1]) for n in names)
    out = {}
    for model in MODELS:
        body = fetch(
            "https://historical-forecast-api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}&start_date={start}&end_date={end}"
            f"&daily=temperature_2m_max&models={model}&timezone=Asia%2FKathmandu"
        ).json()
        rows = body if isinstance(body, list) else [body]
        out[model] = {
            n: dict(zip(r["daily"]["time"], r["daily"]["temperature_2m_max"]))
            for n, r in zip(names, rows)
        }
    return out


def _km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def compute(hist, app_cities, previous=None):
    """The `high_correction` block for dhm.json, or None if not enough data."""
    days = sorted(hist.get("days", {}))[-BIAS_DAYS:]
    if len(days) < MIN_HISTORY_DAYS:
        print(f"[dhm] high correction: only {len(days)} days of history, not published", flush=True)
        return None
    # Same days as last run: nothing new to learn, keep the previous result.
    if previous and previous.get("last_day") == days[-1] and previous.get("days") == len(days):
        return previous

    coords = hist["stations"]
    names = sorted(n for n in coords if any(n in hist["days"][d] for d in days))
    models = _model_highs(names, coords, days[0], days[-1])

    station_bias = {}
    for n in names:
        errs = []
        for d in days:
            measured = hist["days"][d].get(n)
            vals = [models[m][n].get(d) for m in MODELS]
            if measured is None or any(v is None for v in vals):
                continue
            errs.append(measured - sum(vals) / len(vals))
        if len(errs) >= MIN_STATION_DAYS:
            station_bias[n] = statistics.mean(errs)
    if len(station_bias) < 5:
        print(f"[dhm] high correction: only {len(station_bias)} stations usable, not published", flush=True)
        return None
    national = statistics.median(station_bias.values())

    # City heights decide how close a station must be.
    city_elev = fetch("https://api.open-meteo.com/v1/elevation?latitude="
                      + ",".join(f"{lat:.4f}" for (_, lat, _) in app_cities)
                      + "&longitude=" + ",".join(f"{lon:.4f}" for (_, _, lon) in app_cities)
                      ).json()["elevation"]

    clamp = lambda v: round(min(CLAMP[1], max(CLAMP[0], v)), 1)
    cities, matched = {}, {}
    for i, (cid, lat, lon) in enumerate(app_cities):
        best = min(station_bias, key=lambda n: _km((lat, lon), coords[n]))
        max_km = MOUNTAIN_MAX_KM if city_elev[i] > MOUNTAIN_CITY_M else CITY_MAX_KM
        if _km((lat, lon), coords[best]) <= max_km:
            cities[cid] = clamp(station_bias[best])
            matched[cid] = best
        else:
            cities[cid] = clamp(national)
    print(f"[dhm] high correction: national {national:+.1f} °C from {len(station_bias)} stations, "
          f"{len(days)} days; own station for {sorted(matched)}", flush=True)
    return {
        "last_day": days[-1],
        "days": len(days),
        "national": clamp(national),
        "cities": cities,
        "stations": {n: round(b, 1) for n, b in sorted(station_bias.items())},
    }
