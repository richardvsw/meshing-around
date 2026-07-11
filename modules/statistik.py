"""
!stat — statistik populasi node di mesh: sebaran hardware, role, dukungan
PKI, dan berapa banyak yang sudah pakai ID Node terdaftar sbg short name.

Node population comes from the live interface (passed in by the caller —
this module never opens its own radio/MQTT connection). The registration
registry is a community-maintained Google Sheet, published read-only and
fetched as CSV; refreshed here on a 6h cache to match how often the sheet
itself is actually re-published, cached to disk so a restart doesn't need
a fresh fetch immediately.
"""
import collections
import csv
import io
import json
import logging
import os
import time
import urllib.request

logger = logging.getLogger(__name__)

_REGISTRY_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vT_DJ8eDFqR9Hk5S5pEobXPatlhSV9VYSu6qDmdvm0kTZ0O-o4guqL4RJqOfaeOwVZ0eQhyGC1P0sv7/pub?output=csv"
)
_REGISTRY_FORM_URL = (
    "https://docs.google.com/forms/d/e/1FAIpQLSf4CzDN036ERnccpjjCIfNVkbMZb9ikoOeseZSRrovRLAmX2w/viewform"
)
_CACHE_FILE = "/opt/meshing-around/data/node_registry.json"
_CACHE_TTL = 6 * 3600  # sheet itself is only re-published ~every 6h

_cache_data = None
_cache_time = 0


def _load_cache_file():
    try:
        if os.path.exists(_CACHE_FILE):
            with open(_CACHE_FILE) as f:
                saved = json.load(f)
            return saved.get("data", {}), saved.get("time", 0)
    except Exception as e:
        logger.warning("Stat: registry cache file load error: %s", e)
    return {}, 0


def _save_cache_file(data):
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w") as f:
            json.dump({"data": data, "time": time.time()}, f)
    except Exception as e:
        logger.warning("Stat: registry cache file save error: %s", e)


def _fetch_registry_fresh():
    headers = {"User-Agent": "Mozilla/5.0 (compatible; RiV-Bot/1.0)"}
    req = urllib.request.Request(_REGISTRY_CSV_URL, headers=headers)
    raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="replace")
    registry = {}
    for row in csv.DictReader(io.StringIO(raw)):
        node_id = (row.get("ID Node") or "").strip().upper()
        city = (row.get("Kota Domisli Pendaftaran") or "").strip()
        if node_id:
            registry[node_id] = city
    return registry


def _get_registry():
    """Returns {ID_NODE: city}. Disk-cached 6h; falls back to a stale cache
    on fetch failure rather than showing no registry data at all."""
    global _cache_data, _cache_time
    now = time.time()

    if _cache_data and (now - _cache_time) < _CACHE_TTL:
        return _cache_data

    disk_data, disk_time = _load_cache_file()
    if disk_data and (now - disk_time) < _CACHE_TTL:
        _cache_data, _cache_time = disk_data, disk_time
        return _cache_data

    try:
        fresh = _fetch_registry_fresh()
        _cache_data, _cache_time = fresh, now
        _save_cache_file(fresh)
        return fresh
    except Exception as e:
        logger.warning("Stat: registry fetch failed, using stale/empty cache: %s", e)
        if disk_data:
            _cache_data, _cache_time = disk_data, disk_time
            return disk_data
        return {}


def get_statistik(nodes):
    """nodes: list of raw node dicts from an already-open interface.nodes
    (e.g. list(interfaceN.nodes.values())) — this module never connects on
    its own."""
    if not nodes:
        return "❌ Data node tidak tersedia saat ini."

    hw_counter = collections.Counter()
    shorts = []

    for n in nodes:
        user = n.get("user", {})
        hw_counter[user.get("hwModel", "?")] += 1
        short = (user.get("shortName") or "").strip().upper()
        if short:
            shorts.append(short)

    total = len(nodes)
    registry = _get_registry()
    matched_cities = collections.Counter()
    matched = 0
    for s in shorts:
        if s in registry:
            matched += 1
            if registry[s]:
                matched_cities[registry[s]] += 1

    lines = [f"📊 Statistik Mesh — {total} node dikenal", ""]

    lines.append("🔧 Hardware teratas:")
    for hw, cnt in hw_counter.most_common(6):
        lines.append(f"  {hw}: {cnt}")

    pct_reg = round(matched / total * 100) if total else 0
    lines.append("")
    lines.append(f"🪪 Pakai ID Node terdaftar: {matched}/{total} ({pct_reg}%)")
    if matched_cities:
        top_cities = ", ".join(f"{c} ({n})" for c, n in matched_cities.most_common(5))
        lines.append(f"   Kota teratas: {top_cities}")
    lines.append(f"   Belum terdaftar? Isi form: {_REGISTRY_FORM_URL}")

    return "\n".join(lines)
