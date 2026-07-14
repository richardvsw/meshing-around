# -*- coding: utf-8 -*-
"""
!banjir — perkiraan debit sungai terdekat (3 hari), dari lokasimu.
Data debit dari Open-Meteo Flood API (modules.wx_meteo.get_flood_openmeteo).
River name is a separate lookup — Open-Meteo's flood API only returns a
discharge number for its nearest gridded river cell, no name — so this
queries OSM/Overpass for the nearest named waterway near the caller's own
coordinates as a best-effort label.
"""
import math

try:
    import requests
except ImportError:
    requests = None

from modules.log import logger
from modules.wx_meteo import get_flood_openmeteo

_OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
_HEADERS = {"User-Agent": "RiV-Bot-Meshtastic/1.0 (Indonesian mesh network river lookup)"}
_RIVER_SEARCH_RADIUS_M = 5000


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


_RIVER_CACHE_PATH = "/opt/meshing-around/data/river_names.json"


def _river_cache_key(lat, lon):
    # ~1km grid — the nearest river to a fixed spot never changes, so any
    # node that isn't moving hits the cache after its first lookup.
    return f"{round(lat, 2)},{round(lon, 2)}"


def _nearest_river_name(lat, lon):
    """Cache-first wrapper: Overpass is slow (~10s) and rate-limited, but the
    answer for a given location is permanent. Missing/no-river results are
    cached too (as null) so dead zones don't re-query every time."""
    import json, os
    key = _river_cache_key(lat, lon)
    cache = {}
    try:
        if os.path.exists(_RIVER_CACHE_PATH):
            with open(_RIVER_CACHE_PATH) as f:
                cache = json.load(f)
            if key in cache:
                return cache[key] or None
    except Exception as e:
        logger.debug(f"System: river name cache read failed: {e}")
        cache = {}

    name = _nearest_river_name_live(lat, lon)
    try:
        cache[key] = name
        with open(_RIVER_CACHE_PATH, "w") as f:
            json.dump(cache, f)
        os.chmod(_RIVER_CACHE_PATH, 0o666)
    except Exception as e:
        logger.debug(f"System: river name cache write failed: {e}")
    return name


def _nearest_river_name_live(lat, lon):
    if requests is None:
        return None
    query = (
        f"[out:json][timeout:10];"
        f'way["waterway"~"^(river|stream)$"]["name"]'
        f"(around:{_RIVER_SEARCH_RADIUS_M},{lat},{lon});"
        f"out center tags;"
    )
    for url in _OVERPASS_URLS:
        try:
            resp = requests.post(url, data={"data": query}, headers=_HEADERS, timeout=15)
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            best = None
            best_dist = None
            for el in elements:
                name = el.get("tags", {}).get("name")
                elat = el.get("lat", el.get("center", {}).get("lat"))
                elon = el.get("lon", el.get("center", {}).get("lon"))
                if not name or elat is None or elon is None:
                    continue
                dist = _haversine_km(lat, lon, elat, elon)
                if best_dist is None or dist < best_dist:
                    best, best_dist = name, dist
            return best
        except Exception as e:
            logger.debug(f"System: banjir river name lookup failed on {url}: {e}")
            continue
    return None


def get_banjir(message=None, lat=None, lon=None, gps_available=True):
    if lat is None or lon is None or not gps_available:
        return "📍 GPS kamu belum aktif — nyalakan GPS di node kamu dulu ya, baru minta info sungai lagi."

    report = get_flood_openmeteo(lat, lon)
    if not report.startswith("🌊 Debit Sungai Terdekat"):
        return report  # error / no-data message from wx_meteo, pass through as-is

    river_name = _nearest_river_name(lat, lon)
    if river_name:
        # OSM names usually already start with "Sungai"/"Kali" — avoid "Sungai Sungai X"
        if not river_name.lower().startswith(("sungai", "kali", "ci")):
            river_name = f"Sungai {river_name}"
        report = report.replace(
            "🌊 Debit Sungai Terdekat",
            f"🌊 {river_name} (perkiraan terdekat)",
            1,
        )
    return report
