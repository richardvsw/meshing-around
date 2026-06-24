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
    return data


def _get_data():
    global _cache_data, _cache_time
    now = time.time()

    # in-memory cache still valid
    if _cache_data and (now - _cache_time) < _CACHE_TTL:
        return _cache_data

    # try disk cache
    disk_data, disk_time = _load_cache_file()
    if disk_data and (now - disk_time) < _CACHE_TTL:
        _cache_data = disk_data
        _cache_time = disk_time
        return _cache_data

    # fetch fresh
    return fetch_and_refresh()


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


def _format_province(wilayah, prices):
    short_name = re.sub(r'^Prov\. ', '', wilayah)
    lines = [f"⛽ Harga BBM - {short_name}"]
    for prod in _PRIORITY:
        if prod in prices:
            lines.append(f"{prod}: Rp {prices[prod]}")
    for prod, price in prices.items():
        if prod not in _PRIORITY:
            lines.append(f"{prod}: Rp {price}")
    lines.append("📡 pertaminapatraniaga.com")
    return "\n".join(lines)


def get_bbm_prices(message, message_from_id=None, deviceID=1):
    """Handler for !hargabbm. Auto-detects province from GPS if no arg given."""
    text = message.strip()
    for prefix in ("!hargabbm", "hargabbm"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):].strip()
            break

    try:
        data = _get_data()
    except Exception as e:
        logger.error("BBM: fetch error: %s", e)
        return "❌ Gagal mengambil data harga BBM. Coba lagi nanti."

    # If user gave a province name, use it directly
    if text:
        wilayah, prices = _match_province(text, data)
        if not wilayah:
            return f"❌ Wilayah '{text}' tidak ditemukan.\nCoba: !hargabbm jawa barat"
        return _format_province(wilayah, prices)

    # No arg — try GPS auto-detect
    if message_from_id is not None:
        try:
            from modules.system import get_node_location
            from geopy.geocoders import Nominatim
            loc = get_node_location(message_from_id, deviceID)
            lat, lon = loc[0], loc[1]
            geolocator = Nominatim(user_agent="meshbot_bbm/1.0")
            geo = geolocator.reverse(f"{lat},{lon}", language="id", timeout=10)
            addr = geo.raw.get("address", {}) if geo else {}
            state = addr.get("state", "")
            if state:
                wilayah, prices = _match_province(state, data)
                if wilayah and prices:
                    return _format_province(wilayah, prices)
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
