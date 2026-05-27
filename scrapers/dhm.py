"""
Scrape DHM Nepal (Department of Hydrology and Meteorology) for real
station-based weather observations.

Two undocumented but stable JSON endpoints from dhm.gov.np/mfd:
  • /api/manual-observation
      Yesterday's 24-hour station summary — 19 major cities, with
      min/max temperature and total rainfall. Updated daily.
  • /api/sunrise-sunset?lat=X&lng=Y
      For any coordinate, returns the nearest AWOS station's *latest*
      temperature reading (hourly) plus sunrise/sunset for that location.

We hit manual-observation once and sunrise-sunset once per app city
(48 calls). All calls share a sane retry / backoff via common.fetch().

Output: data/dhm.json
"""
from __future__ import annotations
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import fetch, now_iso, write_json

BASE = "https://dhm.gov.np/mfd/api"

# The 48 cities the app supports — must stay in sync with
# NEPAL_CITIES in src/screens/WeatherScreen.js.
APP_CITIES = [
    # id, lat, lon
    ("kathmandu",     27.7172, 85.3240),
    ("lalitpur",      27.6644, 85.3188),
    ("bhaktapur",     27.6710, 85.4298),
    ("kirtipur",      27.6796, 85.2774),
    ("banepa",        27.6300, 85.5219),
    ("dhulikhel",     27.6217, 85.5439),
    ("pokhara",       28.2096, 83.9856),
    ("gorkha",        28.0000, 84.6333),
    ("bandipur",      27.9333, 84.4167),
    ("baglung",       28.2667, 83.5833),
    ("syangja",       28.0833, 83.8667),
    ("tansen",        27.8667, 83.5500),
    ("beni",          28.3500, 83.5667),
    ("butwal",        27.7000, 83.4486),
    ("bhairahawa",    27.5083, 83.4500),
    ("lumbini",       27.4833, 83.2767),
    ("nepalgunj",     28.0500, 81.6167),
    ("kapilvastu",    27.5544, 83.0481),
    ("dhangadhi",     28.7000, 80.5833),
    ("mahendranagar", 28.9646, 80.1825),
    ("tikapur",       28.5269, 81.1241),
    ("birendranagar", 28.6000, 81.6333),
    ("jumla",         29.2747, 82.1839),
    ("simikot",       29.9694, 81.8231),
    ("bharatpur",     27.6766, 84.4321),
    ("hetauda",       27.4287, 85.0326),
    ("birgunj",       27.0104, 84.8807),
    ("janakpur",      26.7288, 85.9249),
    ("rajbiraj",      26.5400, 86.7494),
    ("lahan",         26.7194, 86.4933),
    ("siraha",        26.6531, 86.2069),
    ("biratnagar",    26.4525, 87.2718),
    ("dharan",        26.8125, 87.2790),
    ("itahari",       26.6650, 87.2718),
    ("damak",         26.6610, 87.7000),
    ("birtamod",      26.6403, 87.9858),
    ("kakarvitta",    26.6450, 88.1631),
    ("ilam",          26.9077, 87.9269),
    ("phidim",        27.1500, 87.7500),
    ("taplejung",     27.3500, 87.6700),
    ("namche",        27.8042, 86.7140),
    ("lukla",         27.6869, 86.7314),
    ("jomsom",        28.7833, 83.7333),
    ("muktinath",     28.8167, 83.8667),
    ("manang",        28.6667, 84.0167),
    ("charikot",      27.6717, 86.0531),
    ("okhaldhunga",   27.3167, 86.5000),
    ("salleri",       27.5022, 86.5836),
]


def _safe(d, *path, default=None):
    cur = d
    for p in path:
        if cur is None:
            return default
        if isinstance(cur, dict):
            cur = cur.get(p)
        else:
            return default
    return cur if cur is not None else default


def fetch_manual_observations():
    """Daily 24-hour summary for 19 stations."""
    r = fetch(f"{BASE}/manual-observation")
    body = r.json()
    return {
        "issue_date": body.get("issue_date"),
        "stations": [
            {
                "id":         s.get("id"),
                "name":       s.get("name"),
                "lat":        s.get("latitude"),
                "lon":        s.get("longitude"),
                "min_temp":   s.get("min_temperature"),
                "max_temp":   s.get("max_temperature"),
                "rainfall":   s.get("rainfall"),
            }
            for s in (body.get("stations") or [])
        ],
    }


def fetch_city_reading(city_id, lat, lon):
    """Nearest AWOS station + current reading + sunrise/sunset for one city."""
    r = fetch(f"{BASE}/sunrise-sunset?lat={lat}&lng={lon}")
    body = r.json()
    station = body.get("station") or {}
    latest = station.get("latest_value") or {}
    # distance is in metres; convert to km with one decimal
    dist_m = station.get("distance")
    dist_km = round(dist_m / 1000.0, 2) if isinstance(dist_m, (int, float)) else None
    return {
        "city_id":              city_id,
        "sunrise":              body.get("sunrise"),
        "sunset":               body.get("sunset"),
        "station_id":           station.get("id"),
        "station_name":         station.get("name"),
        "station_lat":          _to_float(station.get("latitude")),
        "station_lon":          _to_float(station.get("longitude")),
        "station_distance_km":  dist_km,
        "station_direction":    station.get("station_direction"),
        "current_temp":         _to_float(latest.get("value")),
        "observed_at":          latest.get("datetime"),
    }


def _to_float(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def main():
    print("[dhm] fetching manual observations...", flush=True)
    manual = fetch_manual_observations()
    print(f"[dhm]   got {len(manual['stations'])} station summaries", flush=True)

    print(f"[dhm] fetching {len(APP_CITIES)} per-city readings (parallel)...", flush=True)
    city_readings = {}
    failures = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=8) as ex:
        future_to_city = {
            ex.submit(fetch_city_reading, cid, lat, lon): cid
            for (cid, lat, lon) in APP_CITIES
        }
        for fut in as_completed(future_to_city):
            cid = future_to_city[fut]
            try:
                city_readings[cid] = fut.result()
            except Exception as exc:
                failures += 1
                print(f"[dhm]   ! {cid}: {exc}", flush=True)

    elapsed = time.time() - start
    print(f"[dhm]   {len(city_readings)} ok, {failures} failed in {elapsed:.1f}s", flush=True)

    if not city_readings and not manual["stations"]:
        raise RuntimeError("DHM returned no usable data")

    payload = {
        "source":       "DHM Nepal",
        "updated_at":   now_iso(),
        "issue_date":   manual["issue_date"],
        "observations": manual["stations"],
        "city_readings": city_readings,
    }
    write_json("dhm.json", payload)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
