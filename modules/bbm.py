import urllib.request
import json
import time
import re
import os
import logging

logger = logging.getLogger(__name__)

_API_URL = "https://pertaminapatraniaga.com/api/api/v1/post/get-by-slug/page/harga-terbaru-bbm"
_CACHE_FILE = "/opt/meshing-around/data/bbm_prices.json"
_CACHE_TTL = 6 * 3600

_cache_data = None
_cache_time = 0

_COL_MAP = {
    "product-table-pertamax-turbo": "Pertamax Turbo",
    "product-table-pertamax-green-95": "Pertamax Green 95",
    "product-table-pertamax.png": "Pertamax",
    "harga-produk-pertamax-pertashop": "Pertashop",
    "product-table-pertalite": "Pertalite",
    "product-table-pertamina-dex": "Pertamina Dex",
    "product-table-dexlite": "Dexlite",
    "harga-produk-bio-solar-non-subsidi": "Bio Solar",
    "harga-produk-bio-solar-subsidi": "Bio Solar Sub.",
}

_PRIORITY = [
    "Pertalite", "Pertamax", "Pertashop", "Pertamax Turbo", "Pertamax Green 95",
    "Bio Solar Sub.", "Bio Solar", "Dexlite", "Pertamina Dex",
]


def _col_name(url_key):
    for fragment, name in _COL_MAP.items():
        if fragment in url_key:
            return name
    return url_key.split("/")[-1].rsplit(".", 1)[0]


def _parse_response(raw):
    content = raw["data"]["content"]
    result = {}
    for node in content.values():
        if node.get("type", {}).get("resolvedName") != "ProductTable":
            continue
        for item in node["props"].get("items", []):
            for row in item.get("data", []):
                wilayah = row.get("WILAYAH", "").strip()
                if not wilayah:
                    continue
                if wilayah not in result:
                    result[wilayah] = {}
                for key, price in row.items():
                    if key == "WILAYAH":
                        continue
                    price = price.strip()
                    if price and price != "-":
                        result[wilayah][_col_name(key)] = price
    return result


def _load_cache_file():
    try:
        if os.path.exists(_CACHE_FILE):
            with open(_CACHE_FILE) as f:
                saved = json.load(f)
            return saved.get("data", {}), saved.get("time", 0)
    except Exception as e:
        logger.warning("BBM: cache file load error: %s", e)
    return {}, 0


def _save_cache_file(data):
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w") as f:
            json.dump({"data": data, "time": time.time()}, f)
    except Exception as e:
        logger.warning("BBM: cache file save error: %s", e)


def fetch_and_refresh():
    """Fetch fresh data from API and persist to disk. Called by daily scheduler."""
    global _cache_data, _cache_time
    logger.info("BBM: refreshing price cache from API")
    from modules.cache_status import record_status
    try:
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; MeshBot/1.0)",
        }
        req = urllib.request.Request(_API_URL, headers=headers)
        r = urllib.request.urlopen(req, timeout=20)
        raw = json.loads(r.read())
        data = _parse_response(raw)
        _cache_data = data
        _cache_time = time.time()
        _save_cache_file(data)
        logger.info("BBM: price cache refreshed, %d wilayah", len(data))
        record_status("hargabbm", ok=True, extra={"wilayah_count": len(data)})
        return data
    except Exception as e:
        record_status("hargabbm", ok=False, error=e)
        raise


def _get_data():
    """Returns (data, is_stale). is_stale is True when live fetch failed and
    we're serving a disk cache older than _CACHE_TTL — better than a bare
    error message during a prolonged outage, but the caller should say so."""
    global _cache_data, _cache_time
    now = time.time()

    # in-memory cache still valid
    if _cache_data and (now - _cache_time) < _CACHE_TTL:
        return _cache_data, False

    # try disk cache
    disk_data, disk_time = _load_cache_file()
    if disk_data and (now - disk_time) < _CACHE_TTL:
        _cache_data = disk_data
        _cache_time = disk_time
        return _cache_data, False

    # fetch fresh
    try:
        return fetch_and_refresh(), False
    except Exception as e:
        logger.error("BBM: fetch error, falling back to stale cache: %s", e)
        if disk_data:
            return disk_data, True
        raise


def _match_province(query, data):
    q = re.sub(r'^(prov\.?\s*|provinsi\s*)', '', query.lower().strip())
    best = None
    best_score = 0
    for wilayah in data:
        name = re.sub(r'^prov\.\s*', '', wilayah, flags=re.I).lower()
        name_simple = re.sub(r'\s+', ' ', name)
        if q == name_simple:
            return wilayah, data[wilayah]
        if q in name_simple or name_simple.startswith(q):
            score = len(q)
            if score > best_score:
                best = wilayah
                best_score = score
    if best:
        return best, data[best]
    return None, None


def _format_province(wilayah, prices, spbu_block=None):
    short_name = re.sub(r'^Prov\. ', '', wilayah)
    lines = [f"⛽ Harga BBM - {short_name}"]
    for prod in _PRIORITY:
        if prod in prices:
            lines.append(f"{prod}: Rp {prices[prod]}")
    for prod, price in prices.items():
        if prod not in _PRIORITY:
            lines.append(f"{prod}: Rp {price}")
    lines.append("📡 pertaminapatraniaga.com")
    if spbu_block:
        lines.append("")
        lines.append(spbu_block)
    return "\n".join(lines)


def _haversine_km(lat1, lon1, lat2, lon2):
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


_SPBU_DB_PATH = "/opt/meshing-around/data/emergency_facilities.db"


def _nearest_spbu_from_cache(lat, lon, limit=3, radius_km=15):
    """Fast path: same nationwide SQLite cache !darurat uses (fetched
    weekly via scripts/fetch_emergency_facilities.py, which now also pulls
    amenity=fuel). Returns None if the cache doesn't exist or has no
    coverage here — caller falls back to a live Overpass query."""
    import os
    if not os.path.exists(_SPBU_DB_PATH):
        return None
    try:
        import sqlite3
        conn = sqlite3.connect(_SPBU_DB_PATH)
        box = 0.3  # ~33km bbox prefilter, comfortably covers a 15km radius
        rows = conn.execute(
            "SELECT name, lat, lon FROM facilities WHERE type='fuel' "
            "AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
            (lat - box, lat + box, lon - box, lon + box),
        ).fetchall()
        conn.close()
    except Exception as e:
        logger.debug("BBM: SPBU cache read failed: %s", e)
        return None

    if not rows:
        return None
    candidates = [(_haversine_km(lat, lon, r[1], r[2]), r[0], r[1], r[2]) for r in rows]
    candidates = [c for c in candidates if c[0] <= radius_km]
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[:limit]


def _nearest_spbu_from_live(lat, lon, limit=3, radius_km=15):
    try:
        import requests
        headers = {"User-Agent": "RiV-Bot-Meshtastic/1.0 (Indonesian mesh network SPBU lookup)"}
        query = (
            f'[out:json][timeout:15];'
            f'nwr["amenity"="fuel"]'
            f"(around:{radius_km * 1000},{lat},{lon});"
            f"out center tags;"
        )
        elements = None
        for url in ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"):
            try:
                resp = requests.post(url, data={"data": query}, headers=headers, timeout=20)
                resp.raise_for_status()
                elements = resp.json().get("elements", [])
                break
            except Exception as e:
                logger.debug("BBM: SPBU lookup failed on %s: %s", url, e)
                elements = None
                continue
        if not elements:
            return None

        candidates = []
        for el in elements:
            tags = el.get("tags", {})
            name = tags.get("name") or tags.get("brand") or "SPBU"
            elat = el.get("lat", el.get("center", {}).get("lat"))
            elon = el.get("lon", el.get("center", {}).get("lon"))
            if elat is None or elon is None:
                continue
            dist = _haversine_km(lat, lon, elat, elon)
            candidates.append((dist, name, elat, elon))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])
        return candidates[:limit]
    except Exception as e:
        logger.warning("BBM: SPBU live lookup failed: %s", e)
        return None


def _nearest_spbu_block(lat, lon, limit=3, radius_km=15):
    candidates = _nearest_spbu_from_cache(lat, lon, limit, radius_km)
    if candidates is None:
        candidates = _nearest_spbu_from_live(lat, lon, limit, radius_km)
    if not candidates:
        return None

    lines = ["⛽ SPBU Terdekat:"]
    for dist, name, elat, elon in candidates:
        lines.append(f"  {name} (~{dist:.1f} km)")
        lines.append(f"    maps.google.com/?q={elat:.5f},{elon:.5f}")
    return "\n".join(lines)


def get_bbm_prices(message, message_from_id=None, deviceID=1):
    """Handler for !hargabbm. Auto-detects province from GPS if no arg given."""
    text = message.strip()
    for prefix in ("!hargabbm", "hargabbm"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):].strip()
            break

    try:
        data, is_stale = _get_data()
    except Exception as e:
        logger.error("BBM: fetch error: %s", e)
        return "❌ Gagal mengambil data harga BBM. Coba lagi nanti."

    stale_note = "\n⚠️ Data mungkin gak up-to-date (gagal ambil data terbaru)" if is_stale else ""

    # Fetch location once (regardless of whether a province was typed
    # explicitly) — used both for GPS auto-detect and the nearest-SPBU block.
    lat = lon = None
    if message_from_id is not None:
        try:
            from modules.system import get_node_location
            import modules.settings as my_settings
            loc = get_node_location(message_from_id, deviceID)
            if not (loc[0] == my_settings.latitudeValue and loc[1] == my_settings.longitudeValue):
                lat, lon = loc[0], loc[1]
        except Exception as e:
            logger.debug("BBM: location fetch error: %s", e)

    spbu_block = _nearest_spbu_block(lat, lon) if (lat is not None and lon is not None) else None

    # If user gave a province name, use it directly
    if text:
        wilayah, prices = _match_province(text, data)
        if not wilayah:
            return f"❌ Wilayah '{text}' tidak ditemukan.\nCoba: !hargabbm jawa barat"
        return _format_province(wilayah, prices, spbu_block) + stale_note

    # No arg — try GPS auto-detect
    if lat is not None and lon is not None:
        try:
            from geopy.geocoders import Nominatim
            geolocator = Nominatim(user_agent="meshbot_bbm/1.0")
            geo = geolocator.reverse(f"{lat},{lon}", language="id", timeout=10)
            addr = geo.raw.get("address", {}) if geo else {}
            state = addr.get("state", "")
            if state:
                wilayah, prices = _match_province(state, data)
                if wilayah and prices:
                    return _format_province(wilayah, prices, spbu_block) + stale_note
        except Exception as e:
            logger.warning("BBM: GPS auto-detect error: %s", e)

    # Fallback: show usage
    provinces = sorted(
        re.sub(r'^Prov\. ', '', w) for w in data if not w.startswith("Free Trade")
    )
    sample = ", ".join(provinces[:5])
    return (
        "⛽ Harga BBM per wilayah\n"
        "Ketik: !hargabbm <provinsi>\n"
        f"Contoh: !hargabbm jawa barat\n"
        f"({len(data)} wilayah: {sample}, ...)"
    )
