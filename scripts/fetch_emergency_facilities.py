# -*- coding: utf-8 -*-
"""
Bulk-fetch hospital/police/fire_station/fuel locations for all of Indonesia from
OpenStreetMap (via Overpass), cache them into a local SQLite DB so !darurat's
nearest-facility lookup doesn't need a live network call per request.

Indonesia is split into a grid of small bbox cells — a single nationwide
query reliably 504s on the free public Overpass instance (confirmed during
testing), and even a 25km point-radius 6-clause query 504'd under load. This
uses the same lightweight single nwr+regex clause per cell that was proven
to work, run sequentially with a pause between cells to stay a good citizen
of the free instance.

Run manually: python3 fetch_emergency_facilities.py
Scheduled weekly via emergency-cache.timer (systemd).
"""
import sqlite3
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "emergency_facilities.db")

_OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
_HEADERS = {"User-Agent": "RiV-Bot-Meshtastic/1.0 (Indonesian mesh network emergency cache builder)"}

# Indonesia's bounding box, roughly. Split into 3-degree cells — small
# enough that even dense Java/Bali cells stay under the query load that
# reliably succeeded during testing.
LAT_MIN, LAT_MAX = -11.5, 6.5
LON_MIN, LON_MAX = 94.5, 141.5
CELL_SIZE = 3.0
PACE_SECONDS = 4  # delay between cells — avoid hammering the free instance


def _grid_cells():
    lat = LAT_MIN
    while lat < LAT_MAX:
        lon = LON_MIN
        while lon < LON_MAX:
            yield (lat, lon, min(lat + CELL_SIZE, LAT_MAX), min(lon + CELL_SIZE, LON_MAX))
            lon += CELL_SIZE
        lat += CELL_SIZE


def _query_cell(south, west, north, east):
    query = (
        f"[out:json][timeout:30];"
        f'nwr["amenity"~"^(hospital|police|fire_station|fuel)$"]'
        f"({south},{west},{north},{east});"
        f"out center tags;"
    )
    for url in _OVERPASS_URLS:
        try:
            resp = requests.post(url, data={"data": query}, headers=_HEADERS, timeout=45)
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except Exception as e:
            print(f"  cell ({south},{west})-({north},{east}) failed on {url}: {e}")
            continue
    return []


def _init_db(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS facilities (
        osm_id INTEGER PRIMARY KEY,
        type   TEXT NOT NULL,
        name   TEXT NOT NULL,
        lat    REAL NOT NULL,
        lon    REAL NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_facilities_latlon ON facilities(lat, lon)")
    conn.execute("""CREATE TABLE IF NOT EXISTS meta (
        key   TEXT PRIMARY KEY,
        value TEXT
    )""")
    conn.commit()


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    _init_db(conn)

    cells = list(_grid_cells())
    total_upserts = 0
    print(f"Fetching {len(cells)} grid cells covering Indonesia (hospital/police/fire_station/fuel)...")

    for i, (s, w, n, e) in enumerate(cells, 1):
        elements = _query_cell(s, w, n, e)
        for el in elements:
            tags = el.get("tags", {})
            amenity = tags.get("amenity")
            if amenity not in ("hospital", "police", "fire_station", "fuel"):
                continue
            lat = el.get("lat", el.get("center", {}).get("lat"))
            lon = el.get("lon", el.get("center", {}).get("lon"))
            if lat is None or lon is None:
                continue
            name = tags.get("name", "Tanpa nama")
            conn.execute(
                "INSERT OR REPLACE INTO facilities (osm_id, type, name, lat, lon) VALUES (?, ?, ?, ?, ?)",
                (el["id"], amenity, name, lat, lon),
            )
            total_upserts += 1
        conn.commit()
        print(f"[{i}/{len(cells)}] cell ({s},{w})-({n},{e}): +{len(elements)} elements, running total {total_upserts}")
        time.sleep(PACE_SECONDS)

    counts = dict(conn.execute("SELECT type, COUNT(*) FROM facilities GROUP BY type").fetchall())
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_updated', ?)", (str(int(time.time())),))
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('total_count', ?)", (str(sum(counts.values())),))
    conn.commit()
    conn.close()

    print(f"Done. Total facilities cached: {sum(counts.values())}")
    print(f"  hospital: {counts.get('hospital', 0)}")
    print(f"  police: {counts.get('police', 0)}")
    print(f"  fire_station: {counts.get('fire_station', 0)}")
    print(f"  fuel: {counts.get('fuel', 0)}")


if __name__ == "__main__":
    main()
