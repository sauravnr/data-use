"""
Scrape METAR (aviation weather) for Nepal airports via NOAA AviationWeather.gov.

METAR reports are issued hourly at most major airports — instrumented,
calibrated, and far more accurate than global forecast models for the
station's immediate area.

What we get on top of Open-Meteo: visibility (km), dewpoint (humidity
ground-truth), wind gust, cloud ceiling, current weather phenomena
(rain/fog/etc), and barometric pressure (QNH).

Output: data/metar.json
"""
from __future__ import annotations
import sys

from common import fetch, now_iso, write_json

# Nepal airports that issue METAR. VNKT is the only one that's reliably
# active 24/7; VNPK and VNBW are newer internationals (opened 2022/2023)
# and report intermittently. The scraper tolerates missing stations.
NEPAL_ICAOS = [
    "VNKT",  # Tribhuvan / Kathmandu
    "VNPK",  # Pokhara International
    "VNBW",  # Gautam Buddha / Bhairahawa
    "VNVT",  # Biratnagar
    "VNJP",  # Janakpur
    "VNDH",  # Dhangadhi
    "VNNG",  # Nepalgunj
    "VNJS",  # Jomsom (limited)
    "VNLK",  # Lukla / Tenzing-Hillary
]

NOAA_URL = "https://aviationweather.gov/api/data/metar"


def _knots_to_kmh(kt):
    if kt is None: return None
    try:
        return round(float(kt) * 1.852, 1)
    except (TypeError, ValueError):
        return None


def _miles_to_km(mi):
    if mi is None: return None
    try:
        return round(float(mi) * 1.609, 1)
    except (TypeError, ValueError):
        return None


def _to_num(v):
    if v is None: return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_metars():
    ids = ",".join(NEPAL_ICAOS)
    r = fetch(NOAA_URL, params={"ids": ids, "format": "json", "hours": 3})
    return r.json() or []


def main():
    print(f"[metar] fetching {len(NEPAL_ICAOS)} Nepal airports...", flush=True)
    reports = fetch_metars()
    print(f"[metar]   got {len(reports)} raw reports", flush=True)

    # Keep only the latest report per ICAO
    latest = {}
    for rep in reports:
        icao = rep.get("icaoId")
        if not icao:
            continue
        ts = rep.get("obsTime") or 0
        if icao not in latest or ts > (latest[icao].get("obsTime") or 0):
            latest[icao] = rep

    stations = {}
    for icao, rep in latest.items():
        wdir = rep.get("wdir")
        # wdir can be "VRB" (variable) — represent as None
        wind_dir = None if wdir == "VRB" else _to_num(wdir)
        stations[icao] = {
            "icao":            icao,
            "name":            rep.get("name"),
            "lat":             _to_num(rep.get("lat")),
            "lon":             _to_num(rep.get("lon")),
            "elev_m":          _to_num(rep.get("elev")),
            "observed_at":     rep.get("reportTime"),
            "temp_c":          _to_num(rep.get("temp")),
            "dewpoint_c":      _to_num(rep.get("dewp")),
            "wind_dir_deg":    wind_dir,
            "wind_speed_kmh":  _knots_to_kmh(rep.get("wspd")),
            "wind_gust_kmh":   _knots_to_kmh(rep.get("wgst")),
            "visibility_km":   _miles_to_km(rep.get("visib")),
            "pressure_hpa":    _to_num(rep.get("altim")),
            "weather":         rep.get("wxString"),
            "flight_category": rep.get("fltCat"),   # VFR / MVFR / IFR / LIFR
            "raw":             rep.get("rawOb"),
        }

    if not stations:
        raise RuntimeError("METAR returned no usable reports")

    print(f"[metar]   {len(stations)} stations: {sorted(stations.keys())}", flush=True)

    payload = {
        "source":     "NOAA AviationWeather.gov / METAR",
        "updated_at": now_iso(),
        "stations":   stations,
    }
    write_json("metar.json", payload)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
