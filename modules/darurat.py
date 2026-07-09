# -*- coding: utf-8 -*-
"""
!darurat — daftar nomor kontak darurat nasional Indonesia, plus fasilitas
terdekat (RS, polisi, pemadam kebakaran) jika lokasi GPS tersedia.

Nearest-facility lookup tries a local SQLite cache first (built by
scripts/fetch_emergency_facilities.py, refreshed weekly) — instant and
works offline. Falls back to a live Overpass query only if the cache is
missing or has no coverage for that area yet.
"""
import math
import os
import sqlite3

try:
    import requests
except ImportError:
    requests = None

from modules.log import logger

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "emergency_facilities.db"
)

_OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
_SEARCH_RADIUS_KM = 25  # area gunung/pedesaan sering jarang di OSM
# Overpass' Apache front-end 406s the default python-requests User-Agent.
_HEADERS = {"User-Agent": "RiV-Bot-Meshtastic/1.0 (Indonesian mesh network emergency lookup)"}

_TYPE_LABELS = {
    "hospital": ("🏥", "RS terdekat"),
    "police": ("👮", "Polisi terdekat"),
    "fire_station": ("🚒", "Damkar terdekat"),
}


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _best_by_type_from_rows(rows, lat, lon):
    best = {}
    for amenity, name, elat, elon in rows:
        dist = _haversine_km(lat, lon, elat, elon)
        if dist > _SEARCH_RADIUS_KM:
            continue
        if amenity not in best or dist < best[amenity][0]:
            best[amenity] = (dist, name)
    return best


def _nearest_from_cache(lat, lon):
    """Fast path: local SQLite cache. Returns best-by-type dict, or None if
    the cache doesn't exist / has no coverage here (caller falls back to
    live Overpass)."""
    if not os.path.exists(_DB_PATH):
        return None
    try:
        conn = sqlite3.connect(_DB_PATH)
        # bbox prefilter — 0.5deg (~55km) comfortably covers the 25km search
        # radius with margin, avoids a full-table haversine scan.
        box = 0.5
        rows = conn.execute(
            "SELECT type, name, lat, lon FROM facilities "
            "WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
            (lat - box, lat + box, lon - box, lon + box),
        ).fetchall()
        conn.close()
    except Exception as e:
        logger.warning(f"System: darurat cache read failed: {e}")
        return None

    if not rows:
        return None
    best = _best_by_type_from_rows(rows, lat, lon)
    return best or None


def _query_nearest_live(lat, lon):
    # A single nwr+regex clause is much lighter on the shared public Overpass
    # instance than six separate node/way `around` clauses — the latter
    # reliably 504'd under normal load during testing, this doesn't.
    query = (
        f'[out:json][timeout:20];'
        f'nwr["amenity"~"^(hospital|police|fire_station)$"]'
        f"(around:{_SEARCH_RADIUS_KM * 1000},{lat},{lon});"
        f"out center tags;"
    )
    last_error = None
    for url in _OVERPASS_URLS:
        try:
            resp = requests.post(url, data={"data": query}, headers=_HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except Exception as e:
            last_error = e
            continue
    raise last_error


def _nearest_from_live(lat, lon):
    if requests is None:
        return None
    try:
        elements = _query_nearest_live(lat, lon)
    except Exception as e:
        logger.warning(f"System: darurat live nearest-facility lookup failed: {e}")
        return None

    rows = []
    for el in elements:
        amenity = el.get("tags", {}).get("amenity")
        if amenity not in _TYPE_LABELS:
            continue
        elat = el.get("lat", el.get("center", {}).get("lat"))
        elon = el.get("lon", el.get("center", {}).get("lon"))
        if elat is None or elon is None:
            continue
        name = el.get("tags", {}).get("name", "Tanpa nama")
        rows.append((amenity, name, elat, elon))
    return _best_by_type_from_rows(rows, lat, lon) or None


def _format_nearest(best):
    lines = ["📍 Fasilitas Terdekat (OpenStreetMap):"]
    for amenity, (emoji, label) in _TYPE_LABELS.items():
        if amenity in best:
            dist, name = best[amenity]
            lines.append(f"{emoji} {label}: {name} (~{dist:.1f} km)")
    lines.append(
        "⚠️ Data crowdsource OSM, jarak garis lurus (bukan rute jalan) — "
        "bisa saja tidak akurat/tidak update. Tetap konfirmasi via 112 saat darurat."
    )
    return "\n".join(lines)


def _nearest_facilities_text(lat, lon):
    best = _nearest_from_cache(lat, lon)
    if best is None:
        best = _nearest_from_live(lat, lon)
    if not best:
        return (
            f"📍 Fasilitas terdekat: tidak ditemukan dlm radius {_SEARCH_RADIUS_KM}km\n"
            "(data OpenStreetMap mungkin belum lengkap di area ini)"
        )
    return _format_nearest(best)


def get_darurat(message=None, lat=None, lon=None, gps_available=True):
    base = (
        "🚨 Nomor Darurat Indonesia\n"
        "112 — Panggilan Darurat Nasional (semua jenis darurat, gratis dari HP tanpa pulsa/sinyal operator)\n"
        "115 — SAR / Basarnas (evakuasi gunung, laut, bencana)\n"
        "110 — Polisi\n"
        "113 — Pemadam Kebakaran\n"
        "118 — Ambulans (Yayasan AGD)\n"
        "119 — Ambulans (Kemenkes)\n"
        "129 — BNPB (bencana alam)\n"
        "123 — PLN (gangguan listrik)\n"
        "⚠️ 112 bisa dihubungi 24 jam dari HP manapun meski tanpa kartu SIM/sinyal operator, selama ada sinyal darurat"
    )

    if lat is None or lon is None:
        return base

    if not gps_available:
        return base + "\n\n📍 GPS kamu belum aktif — nyalakan GPS di node lalu !darurat lagi buat lihat fasilitas terdekat."

    nearest = _nearest_facilities_text(lat, lon)
    if nearest:
        return base + "\n\n" + nearest
    return base
