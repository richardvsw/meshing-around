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
import subprocess
import sys
import time
import urllib.request

logger = logging.getLogger(__name__)

# Renders the PNG infographic and uploads it to imgbb (see the script for
# details) — run as a subprocess, not imported, so its PIL/network/
# rsvg-convert work stays out of the long-running bot process and a slow
# or failing run can't take mesh_bot down with it.
_STAT_IMAGE_SCRIPT = "/opt/meshing-around/scripts/generate_stat_image.py"
_STAT_IMAGE_TIMEOUT = 90

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
        name = (row.get("Nama Asli Lengkap") or "").strip()
        if node_id:
            registry[node_id] = {"city": city, "name": name}
    return registry


def _get_registry():
    """Returns {ID_NODE: {"city":..., "name":...}}. Disk-cached 6h; falls
    back to a stale cache on fetch failure rather than showing no registry
    data at all."""
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


def _generate_stat_image_url(caller_short):
    """Runs generate_stat_image.py (which fetches its own node data from
    rivbot-ui's REST API, independent of the live interface nodes used for
    the text stats above) and returns the imgbb URL it printed, or None on
    any failure/timeout — the text reply is always sent either way."""
    try:
        args = [sys.executable, _STAT_IMAGE_SCRIPT]
        if caller_short:
            args.append(caller_short)
        result = subprocess.run(args, capture_output=True, text=True, timeout=_STAT_IMAGE_TIMEOUT)
        for line in result.stdout.splitlines():
            if line.startswith("URL: "):
                return line[len("URL: "):].strip()
        logger.warning("Stat: image script produced no URL (rc=%s): %s",
                        result.returncode, result.stderr[-500:])
    except Exception as e:
        logger.warning("Stat: image generation/upload failed: %s", e)
    return None


def get_statistik(nodes, caller_num=None):
    """nodes: list of raw node dicts from an already-open interface.nodes
    (e.g. list(interfaceN.nodes.values())) — this module never connects on
    its own. caller_num: the requesting node's numeric id (message_from_id),
    used only to look up their own registered name for a personal greeting —
    not required for the aggregate stats."""
    if not nodes:
        return "❌ Data node tidak tersedia saat ini."

    hw_counter = collections.Counter()
    shorts = []
    caller_short = None

    for n in nodes:
        user = n.get("user", {})
        hw_counter[user.get("hwModel", "?")] += 1
        short = (user.get("shortName") or "").strip().upper()
        if short:
            shorts.append(short)
        if caller_num is not None and n.get("num") == caller_num:
            caller_short = short

    total = len(nodes)
    registry = _get_registry()
    matched_cities = collections.Counter()
    matched = 0
    for s in shorts:
        entry = registry.get(s)
        if entry:
            matched += 1
            if entry.get("city"):
                matched_cities[entry["city"]] += 1

    lines = []
    caller_entry = registry.get(caller_short) if caller_short else None
    if caller_entry and caller_entry.get("name"):
        lines.append(f"👋 Halo {caller_entry['name']} ({caller_short})! Node kamu terdaftar.")
        lines.append("")

    lines.append(f"📊 Statistik Mesh — {total} node dikenal")
    lines.append("")

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

    image_url = _generate_stat_image_url(caller_short)
    if image_url:
        lines.append("")
        lines.append(f"📸 Grafik lengkap: {image_url}")

    return "\n".join(lines)
