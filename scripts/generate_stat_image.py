#!/usr/bin/env python3
"""Render !stat's data as a PNG infographic (for eventual imgbb upload +
link-share over the mesh, since Meshtastic can't send images directly).

Device icons come from Meshtastic's own public device-hardware API — the
same data flasher.meshtastic.org itself uses — no API key needed:
  https://api.meshtastic.org/resource/deviceHardware  ({hwModelSlug: ...,
  images: ["slug.svg"]}), served from https://flasher.meshtastic.org/img/
  devices/{file}. SVGs are rasterized via the system rsvg-convert binary
  (librsvg2-bin) since PIL can't render SVG itself; results are cached to
  disk so this doesn't re-fetch/re-rasterize every run.

Otherwise pure PIL, no matplotlib/numpy — keeps the dependency footprint
small on a server that otherwise has no image-processing libs at all.
"""
import base64
import collections
import configparser
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/opt/meshing-around")

from PIL import Image, ImageDraw, ImageFont
import staticmap

WIB = timezone(timedelta(hours=7))
FONT_DIR = "/usr/share/fonts/truetype/dejavu"
OUT_PATH = "/opt/meshing-around/data/stat_snapshot.png"
_CONFIG_PATH = "/opt/meshing-around/config.ini"

_DEVICE_HW_URL = "https://api.meshtastic.org/resource/deviceHardware"
_DEVICE_HW_CACHE = "/opt/meshing-around/data/device_hardware.json"
_DEVICE_HW_TTL = 7 * 86400  # this list changes rarely — new hardware releases, not daily

# City name -> (lat, lon), geocoded once via Nominatim (same free/no-key
# service !hargabbm and !dimana already use elsewhere in this project) and
# cached indefinitely — city centroids don't move.
_CITY_COORDS_CACHE = "/opt/meshing-around/data/city_coords.json"
_ICON_DIR = "/opt/meshing-around/data/device_icons"
_ICON_SIZE = 34

# ── OpenStreetMap basemap tiles ─────────────────────────────────────────────
# Real street/place-name tiles instead of a hand-drawn map. OSM's tile usage
# policy (operations.osmfoundation.org/policies/tiles/) requires a real
# identifying User-Agent and, importantly, caching — this script only ever
# needs a small, near-fixed set of tiles (fixed national view + one zoom
# level per requester city), so a permanent disk cache keeps repeat !stat
# calls from re-fetching anything at all.
_OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
_OSM_USER_AGENT = "RiV-Bot-StatImage/1.0 (Meshtastic community bot; contact via github.com/richardvsw/meshing-around)"
_TILE_CACHE_DIR = "/opt/meshing-around/data/osm_tiles"
_OSM_ATTRIBUTION = "© OpenStreetMap contributors"


class _CachedStaticMap(staticmap.StaticMap):
    """Disk-caches every tile fetch, forever — tiles for a fixed view (the
    national map) or a city centroid (zoom insets) don't go stale on any
    timescale that matters here, and this is what makes repeat !stat runs
    not hammer OSM's tile servers at all."""

    def get(self, url, **kwargs):
        os.makedirs(_TILE_CACHE_DIR, exist_ok=True)
        key = hashlib.sha1(url.encode()).hexdigest()
        path = f"{_TILE_CACHE_DIR}/{key}.png"
        if os.path.exists(path):
            with open(path, "rb") as f:
                return 200, f.read()
        status, content = super().get(url, **kwargs)
        if status == 200:
            with open(path, "wb") as f:
                f.write(content)
        return status, content


def _mercator_xy(lon, lat, zoom, tile_size=256):
    lat_rad = math.radians(max(min(lat, 85.05), -85.05))  # web mercator's own valid range
    n = 2 ** zoom
    x = (lon + 180) / 360 * n * tile_size
    y = (1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n * tile_size
    return x, y


def _fit_osm_view(lon_min, lon_max, lat_min, lat_max, w, h, pad=0.15, max_zoom=17, axis="both"):
    """Picks the highest OSM zoom level at which the padded bbox still fits
    within a w x h box, plus a projector matching what StaticMap.render()
    produces for that (zoom, center) — so pins/labels line up with the
    fetched tile image without needing staticmap's own marker drawing.

    axis="both" requires both dimensions to fit (safe default — nothing
    gets cropped off). axis="width" only requires the width to fit and
    lets the taller dimension overflow (extra context above/below, never
    cropped since render() always fills the box) — for a bbox whose aspect
    ratio is far more extreme than the panel's own (Indonesia is ~2.7:1;
    a national-map panel is usually squarer), "both" tends to drop a whole
    zoom level early and leave a lot of unused margin on the tighter axis."""
    lon_span, lat_span = lon_max - lon_min, lat_max - lat_min
    lon_min -= lon_span * pad
    lon_max += lon_span * pad
    lat_min -= lat_span * pad
    lat_max += lat_span * pad
    center_lon, center_lat = (lon_min + lon_max) / 2, (lat_min + lat_max) / 2

    zoom = 0
    for z in range(max_zoom, -1, -1):
        x0, y0 = _mercator_xy(lon_min, lat_max, z)
        x1, y1 = _mercator_xy(lon_max, lat_min, z)
        fits_w = abs(x1 - x0) <= w
        fits_h = abs(y1 - y0) <= h
        if fits_w and (axis == "width" or fits_h):
            zoom = z
            break

    cx, cy = _mercator_xy(center_lon, center_lat, zoom)

    def project(lat, lon):
        x, y = _mercator_xy(lon, lat, zoom)
        return w / 2 + (x - cx), h / 2 + (y - cy)

    return zoom, center_lon, center_lat, project


def _render_osm_basemap(w, h, lon_min, lon_max, lat_min, lat_max, pad=0.15, axis="both"):
    """Returns (RGB tile image sized exactly w x h, project fn) for the
    given bbox, or (None, None) on any fetch failure — callers fall back to
    a plain water-colored panel rather than crashing the whole render."""
    zoom, center_lon, center_lat, project = _fit_osm_view(lon_min, lon_max, lat_min, lat_max, w, h, pad, axis=axis)
    try:
        m = _CachedStaticMap(w, h, url_template=_OSM_TILE_URL,
                              headers={"User-Agent": _OSM_USER_AGENT},
                              tile_request_timeout=15)
        tile_img = m.render(zoom=zoom, center=(center_lon, center_lat)).convert("RGB")
        return tile_img, project
    except Exception as e:
        print(f"OSM tile fetch failed: {e}")
        return None, project


def _get_device_hardware():
    """Returns {"by_slug": {hwModelSlug: [images]}, "num_to_slug": {hwModel
    (int, as str since JSON keys are strings): hwModelSlug}}. Disk-cached 7d.

    The int->slug map matters: mqtt_tap.py's node dict sometimes has the raw
    numeric hwModel (e.g. 43) instead of the resolved string ("HELTEC_V3")
    for a given node — without normalizing through this, the same physical
    hardware type gets split into two separate bars in the chart."""
    try:
        if os.path.exists(_DEVICE_HW_CACHE):
            age = time.time() - os.path.getmtime(_DEVICE_HW_CACHE)
            if age < _DEVICE_HW_TTL:
                with open(_DEVICE_HW_CACHE) as f:
                    return json.load(f)
    except Exception:
        pass
    try:
        raw = json.load(urllib.request.urlopen(_DEVICE_HW_URL, timeout=15))
        mapping = {
            "by_slug": {d["hwModelSlug"]: d.get("images") or [] for d in raw if d.get("hwModelSlug")},
            "num_to_slug": {str(d["hwModel"]): d["hwModelSlug"] for d in raw
                            if d.get("hwModelSlug") and d.get("hwModel") is not None},
        }
        os.makedirs(os.path.dirname(_DEVICE_HW_CACHE), exist_ok=True)
        with open(_DEVICE_HW_CACHE, "w") as f:
            json.dump(mapping, f)
        return mapping
    except Exception as e:
        print(f"device hardware fetch failed: {e}")
        # stale cache beats no icons at all
        try:
            with open(_DEVICE_HW_CACHE) as f:
                return json.load(f)
        except Exception:
            return {"by_slug": {}, "num_to_slug": {}}


def _normalize_hw(hw, hw_map):
    """int hwModel -> its slug string, so it merges with nodes that already
    reported the resolved string for the same hardware. Passes strings and
    unmapped values through unchanged."""
    if isinstance(hw, str):
        return hw
    return hw_map["num_to_slug"].get(str(hw), f"hwModel {hw}")


def _get_device_icon(slug, hw_map):
    """Returns a PIL Image (RGBA, _ICON_SIZE square) for this hwModelSlug.
    Falls back to flasher.meshtastic.org's own generic "unknown device" icon
    (the same grey "?" placeholder the web flasher itself shows) rather than
    leaving blank space, for anything with no specific image — including
    genuinely made-up/custom hardware, since a fallback icon reads as "we
    checked, there's nothing", not as a broken image."""
    images = hw_map["by_slug"].get(slug) or []
    icon_key = slug if images else "__unknown__"

    os.makedirs(_ICON_DIR, exist_ok=True)
    # Render at 4x then downscale in PIL (LANCZOS) rather than trusting
    # rsvg-convert's own scaling — crisper small icons.
    render_size = _ICON_SIZE * 4
    png_path = f"{_ICON_DIR}/{icon_key}.png"
    if not os.path.exists(png_path):
        image_file = images[0] if images else "unknown.svg"
        svg_url = f"https://flasher.meshtastic.org/img/devices/{image_file}"
        svg_path = f"{_ICON_DIR}/{icon_key}.svg"
        try:
            urllib.request.urlretrieve(svg_url, svg_path)
            # -w/-h + --keep-aspect-ratio = fit WITHIN that box, doesn't
            # force a square/distort non-square device outlines.
            subprocess.run(
                ["rsvg-convert", "-w", str(render_size), "-h", str(render_size),
                 "--keep-aspect-ratio", "-b", "none", svg_path, "-o", png_path],
                check=True, timeout=15)
        except Exception as e:
            print(f"icon fetch/render failed for {slug}: {e}")
            return None
        finally:
            if os.path.exists(svg_path):
                os.remove(svg_path)

    try:
        icon = Image.open(png_path).convert("RGBA")
        icon.thumbnail((render_size, render_size), Image.LANCZOS)
        scale = min(_ICON_SIZE / icon.width, _ICON_SIZE / icon.height)
        icon = icon.resize((max(1, int(icon.width * scale)), max(1, int(icon.height * scale))), Image.LANCZOS)
        canvas = Image.new("RGBA", (_ICON_SIZE, _ICON_SIZE), (0, 0, 0, 0))
        canvas.paste(icon, ((_ICON_SIZE - icon.width) // 2, (_ICON_SIZE - icon.height) // 2), icon)
        return canvas
    except Exception as e:
        print(f"icon load failed for {slug}: {e}")
        return None

# ── palette (matches the rivbot-ui dark theme) ───────────────────────────────
BG        = (12, 17, 23)
SURF      = (19, 26, 34)
SURF2     = (27, 37, 48)
BORDER    = (38, 51, 65)
TEXT      = (231, 237, 243)
MUTED     = (132, 148, 163)
FAINT     = (86, 99, 111)
ACCENT    = (69, 217, 174)
ACCENT_DK = (42, 143, 116)

W, H = 1220, 1800  # upper bound only — final image is always cropped to actual content height
SIDEBAR_W = 340  # right column: personal zoom-inset panel

# ── map styling — real OSM tiles (their own light basemap colors), so labels
# drawn on top need dark text + a light halo for legibility, the opposite of
# the old hand-drawn dark map. MAP_WATER is only used as a placeholder fill
# while a tile is loading / if a fetch fails. ───────────────────────────────
MAP_WATER  = (170, 211, 223)  # OSM's own default sea color, as a fallback fill
MAP_LABEL  = (40, 40, 40)     # dark label text, reads well over OSM tiles
MAP_HALO   = (255, 255, 255)  # light halo for legibility over roads/land
PIN_OTHER  = (227, 179, 65)   # nearby-node pins in the zoom inset (distinct from the requester's own pin)
PIN_UNKNOWN = (150, 155, 158)  # neutral gray for the "no location" slice of the coverage card
PIN_HEAD_R = 9  # teardrop head radius, px

# ── position sources — every plotted node is tagged with where its
# coordinates actually came from, so the legend/coverage card can show that
# breakdown honestly instead of lumping "real GPS from someone else's
# session" in with "our own live session" under one generic "GPS asli". ────
SRC_OWN      = "own"       # live from our own mqtt_tap session (/api/nodes)
SRC_MESHNODE = "meshnode"  # map.meshnode.id's public community map report
SRC_CITY     = "city"      # registry city centroid, geocoded — least precise

SRC_COLOR = {SRC_OWN: ACCENT, SRC_MESHNODE: (86, 149, 227), SRC_CITY: ACCENT_DK}
SRC_RADIUS = {SRC_OWN: 9, SRC_MESHNODE: 8, SRC_CITY: 6}
SRC_LABEL = {SRC_OWN: "GPS langsung (RiV-Bot)", SRC_MESHNODE: "map.meshnode.id",
             SRC_CITY: "perkiraan dari kota terdaftar"}
PIN_FILL = SRC_COLOR[SRC_OWN]  # kept for the zoom inset's own-node pin


def font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(f"{FONT_DIR}/{name}", size)


def text_w(draw, s, f):
    return draw.textbbox((0, 0), s, font=f)[2]


def rounded(draw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def stat_card(draw, x, y, w, h, label, value, value_color=TEXT):
    rounded(draw, (x, y, x + w, y + h), 12, fill=SURF, outline=BORDER, width=1)
    f_label = font(15)
    f_value = font(30, bold=True)
    draw.text((x + 20, y + 16), label, font=f_label, fill=FAINT)
    draw.text((x + 20, y + 44), value, font=f_value, fill=value_color)


def _halo_text(d, xy, text, f, fill=MAP_LABEL, halo=MAP_HALO, anchor=None):
    """Text with a soft outline so labels stay legible sitting on top of
    polygons/water rather than a solid label chip — how Maps-style labels
    are usually drawn."""
    x, y = xy
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
        d.text((x + dx, y + dy), text, font=f, fill=halo, anchor=anchor)
    d.text((x, y), text, font=f, fill=fill, anchor=anchor)


def _draw_pin(d, px, py, r=PIN_HEAD_R, fill=PIN_FILL):
    """Classic Maps-style teardrop marker: a circle head tapering to a
    point at the actual coordinate, instead of a plain dot."""
    d.polygon([(px, py), (px - r * 0.78, py - r * 1.55), (px + r * 0.78, py - r * 1.55)],
              fill=fill)
    d.ellipse((px - r, py - r * 2.5, px + r, py - r * 0.5), fill=fill, outline=(255, 255, 255), width=1)
    d.ellipse((px - r * 0.42, py - r * 1.9, px + r * 0.42, py - r * 1.1), fill=(255, 255, 255))


def _draw_coverage_card(sd, cx, cy, own_count, meshnode_count, city_count, unknown_count):
    """Floating white info-card (like a real Maps popup) with a small donut
    chart, in a corner of the map — turns the empty-ocean space into a
    stand-in for the nodes with no location, instead of the caption text
    below the map being the only place that's mentioned at all. Shows all
    four position sources (own live session / map.meshnode.id / city
    estimate / unknown) so it doubles as a "where did this data come from"
    legend, not just a coverage percentage."""
    total = own_count + meshnode_count + city_count + unknown_count
    if total == 0:
        return

    card_w, card_h = 196, 140
    x0, y0 = cx, cy
    x1, y1 = x0 + card_w, y0 + card_h
    d = sd
    d.rounded_rectangle((x0, y0, x1, y1), radius=10, fill=(255, 255, 255),
                         outline=(210, 213, 216), width=1)

    d.text((x0 + 14, y0 + 12), "Sumber Lokasi", font=font(12, bold=True), fill=(40, 40, 40))

    r = 30
    dcx, dcy = x0 + 14 + r, y0 + 32 + r
    start = -90
    for count, color in ((own_count, SRC_COLOR[SRC_OWN]), (meshnode_count, SRC_COLOR[SRC_MESHNODE]),
                          (city_count, SRC_COLOR[SRC_CITY]), (unknown_count, PIN_UNKNOWN)):
        if count <= 0:
            continue
        sweep = 360 * count / total
        d.pieslice((dcx - r, dcy - r, dcx + r, dcy + r), start, start + sweep, fill=color)
        start += sweep
    # punch the donut hole
    hole_r = r * 0.55
    d.ellipse((dcx - hole_r, dcy - hole_r, dcx + hole_r, dcy + hole_r), fill=(255, 255, 255))
    d.text((dcx, dcy), f"{total}", font=font(13, bold=True), fill=(40, 40, 40), anchor="mm")

    rows = [("RiV-Bot", own_count, SRC_COLOR[SRC_OWN]),
            ("meshnode.id", meshnode_count, SRC_COLOR[SRC_MESHNODE]),
            ("Perkiraan kota", city_count, SRC_COLOR[SRC_CITY]),
            ("Tanpa lokasi", unknown_count, PIN_UNKNOWN)]
    ly = y0 + 38
    lx = dcx + r + 14
    for label, count, color in rows:
        d.ellipse((lx, ly + 3, lx + 8, ly + 11), fill=color)
        d.text((lx + 13, ly), f"{label} ({count})", font=font(10), fill=(60, 60, 60))
        ly += 17


def _load_city_coords_cache():
    try:
        with open(_CITY_COORDS_CACHE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_city_coords_cache(cache):
    os.makedirs(os.path.dirname(_CITY_COORDS_CACHE), exist_ok=True)
    with open(_CITY_COORDS_CACHE, "w") as f:
        json.dump(cache, f)


_last_geocode_ts = [0.0]


def _geocode_city(city, cache):
    """(lat, lon) for an Indonesian city name, or None. Disk-cached forever
    (city centroids don't move) — only ever hits Nominatim for a city not
    seen before, and there are only a few dozen distinct cities across the
    whole registry. Nominatim's usage policy caps requests at 1/sec — a
    fresh cache (first run, or a new city added to the registry) was
    hitting several dozen lookups back-to-back and getting 429'd."""
    if city in cache:
        return tuple(cache[city]) if cache[city] else None
    try:
        from geopy.geocoders import Nominatim
        elapsed = time.time() - _last_geocode_ts[0]
        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)
        geolocator = Nominatim(user_agent="rivbot_stat_image/1.0")
        loc = geolocator.geocode(f"{city}, Indonesia", timeout=10)
        _last_geocode_ts[0] = time.time()
        result = (loc.latitude, loc.longitude) if loc else None
    except Exception as e:
        print(f"geocode failed for {city!r}: {e}")
        result = None
    cache[city] = list(result) if result else None
    return result


_MESHNODE_MAP_URL = "https://map.meshnode.id/api/nodes/map"


def _get_meshnode_positions():
    """Real GPS for nodes our own mqtt_tap session hasn't heard fresh
    lat/lon from directly, sourced from map.meshnode.id's public node-map
    API — the community's shared MQTT broker (mqtt.meshnode.id, same one
    RiV-Bot itself listens on) where devices self-publish a Meshtastic
    "map report" containing their GPS position. This is genuine reported
    GPS, not a guess, and covers ~85% of what our own session shows as
    "no location" — some other client on the same broker simply heard that
    node's map report more recently than we did. No API key; public JSON.
    Best-effort: an empty dict on any failure just falls back to the
    existing city-centroid tier, same as before this existed."""
    try:
        raw = json.load(urllib.request.urlopen(_MESHNODE_MAP_URL, timeout=15))
        out = {}
        for meta in raw.values():
            short = (meta.get("shortName") or "").strip().upper()
            lat, lon = meta.get("latitude"), meta.get("longitude")
            # coords are int, scaled by 1e7 (Meshtastic's own wire format)
            if short and lat and lon:
                out[short] = (lat / 1e7, lon / 1e7)
        return out
    except Exception as e:
        print(f"map.meshnode.id fetch failed: {e}")
        return {}


def _fallback_positions(nodes, registry):
    """Three-tier position lookup, each node tagged with SRC_OWN / SRC_MESHNODE
    / SRC_CITY so the map can show — and the legend can honestly label —
    exactly where each pin's coordinates came from. Returns [(node, lat,
    lon, source), ...]."""
    meshnode_positions = _get_meshnode_positions()
    cache = _load_city_coords_cache()
    dirty = False
    out = []
    for n in nodes:
        if n.get("lat") and n.get("lon"):
            out.append((n, n["lat"], n["lon"], SRC_OWN))
            continue
        short = (n.get("short") or "").strip().upper()
        mn_pos = meshnode_positions.get(short)
        if mn_pos:
            out.append((n, mn_pos[0], mn_pos[1], SRC_MESHNODE))
            continue
        entry = registry.get(short)
        city = entry.get("city") if entry else None
        if not city:
            continue
        before = city in cache
        coord = _geocode_city(city, cache)
        if not before:
            dirty = True
        if coord:
            out.append((n, coord[0], coord[1], SRC_CITY))
    if dirty:
        _save_city_coords_cache(cache)
    return out


def _haversine_km(lat1, lon1, lat2, lon2):
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _find_requester_position(requester_short, positions):
    """Looks up the requesting node (by short name/callsign) inside an
    already-computed positions list, so the national map and the zoom inset
    share one _fallback_positions() call instead of geocoding twice."""
    if not requester_short:
        return None
    requester_short = requester_short.strip().upper()
    for n, lat, lon, source in positions:
        if (n.get("short") or "").strip().upper() == requester_short:
            return (n, lat, lon, source)
    return None


NEARBY_RADIUS_KM = 25  # how far counts as "nearby" for the zoom inset's neighbor list
NEARBY_LABEL_MAX = 6   # only label this many pins on the map itself, to avoid clutter
NEARBY_LIST_MAX = 5    # only list this many in the sidebar text


def draw_zoom_inset(d, img, x, y, w, h, requester_short, requester_pos, registry, hw_map, positions):
    """Right-sidebar panel: a tight zoom around whoever sent !stat, reusing
    the same projector/pin-drawing approach as the national map but with a
    city-scale bounding box instead of all of Indonesia. Falls back to a
    plain explainer if we don't know who asked or can't place them."""
    rounded(d, (x, y, x + w, y + h), 12, fill=SURF, outline=BORDER, width=1)
    d.text((x + 20, y + 16), "Lokasi Kamu", font=font(17, bold=True), fill=TEXT)

    if not requester_pos:
        map_x0, map_y0 = x + 16, y + 50
        map_x1, map_y1 = x + w - 16, y + h - 16
        rounded(d, (map_x0, map_y0, map_x1, map_y1), 8, fill=MAP_WATER)
        msg = ("Kirim !stat dari node kamu\nuntuk lihat lokasimu di sini."
               if not requester_short else
               "Node kamu belum punya data\nlokasi (GPS atau kota terdaftar).")
        for i, line in enumerate(msg.split("\n")):
            d.text((map_x0 + 16, map_y0 + 20 + i * 20), line, font=font(13), fill=MAP_LABEL)
        return

    n, lat, lon, source = requester_pos
    short = (n.get("short") or "?").strip()

    # ── find nearby nodes (real distance, not just "inside the same pixel
    # box") so the nearest-node figure and the list are both trustworthy.
    # Skip pairs where BOTH points are city-fallback positions that landed
    # on the exact same geocoded centroid — that's two nodes registered to
    # the same city, not two nodes verified to be near each other, and
    # reporting it as "0.0 km" claims a precision the data doesn't have. A
    # requester-vs-real-GPS comparison (or two DIFFERENT city centroids) is
    # still shown, since that distance is meaningful even if approximate. ──
    nearby = []
    for other_n, olat, olon, osource in positions:
        if other_n is n:
            continue
        same_fallback_city = (source == SRC_CITY and osource == SRC_CITY
                               and abs(olat - lat) < 1e-6 and abs(olon - lon) < 1e-6)
        if same_fallback_city:
            continue
        dist = _haversine_km(lat, lon, olat, olon)
        if dist <= NEARBY_RADIUS_KM:
            nearby.append((other_n, olat, olon, osource, dist))
    nearby.sort(key=lambda t: t[4])
    same_city_count = sum(
        1 for other_n, olat, olon, osource in positions
        if other_n is not n and source == SRC_CITY and osource == SRC_CITY
        and abs(olat - lat) < 1e-6 and abs(olon - lon) < 1e-6
    )

    # Bottom info block needs room for: own node (name/city/coords/hw) +
    # nearest-node line + a short neighbor list + the same-city caveat line.
    info_h = 118 + 20 + min(len(nearby), NEARBY_LIST_MAX) * 17 + (17 if same_city_count else 0)
    map_x0, map_y0 = x + 16, y + 50
    map_x1, map_y1 = x + w - 16, y + h - 16 - info_h
    rounded(d, (map_x0, map_y0, map_x1, map_y1), 8, fill=MAP_WATER)

    # City/reasonable-radius view, not a whole province.
    pad = 0.2  # ~22 km half-width
    box_w, box_h = map_x1 - map_x0, map_y1 - map_y0
    tile_img, project = _render_osm_basemap(box_w, box_h, lon - pad, lon + pad, lat - pad, lat + pad, pad=0.1)
    sub = tile_img if tile_img else Image.new("RGB", (box_w, box_h), MAP_WATER)
    sd = ImageDraw.Draw(sub)
    if not tile_img:
        sd.text((16, 20), "(peta OSM tidak tersedia)", font=font(13), fill=MAP_LABEL)

    px, py = project(lat, lon)

    # Distance rings — at city scale the province polygon rarely shows any
    # actual boundary (the requester is almost never near a province edge),
    # so a fixed-radius ring is what actually gives the reader a sense of
    # scale. 1 deg lat ~= 111 km; measure via project() rather than assuming
    # a flat px/km ratio, since the cos(lat) longitude correction makes the
    # two axes scale slightly differently.
    px_per_km = abs(project(lat + 5 / 111.0, lon)[1] - py) / 5.0
    for radius_km, label in ((5, "5 km"), (15, "15 km")):
        r = radius_km * px_per_km
        sd.ellipse((px - r, py - r, px + r, py + r), outline=(90, 108, 104), width=1)
        _halo_text(sd, (px + r * 0.70, py - r * 0.70 - 12), label, font(11))

    # ── nearby nodes, drawn in a distinct color from the requester's own pin ──
    for other_n, olat, olon, osource, dist in nearby:
        opx, opy = project(olat, olon)
        if not (0 <= opx <= box_w and 0 <= opy <= box_h):
            continue
        _draw_pin(sd, opx, opy, r=6, fill=PIN_OTHER)
    for other_n, olat, olon, osource, dist in nearby[:NEARBY_LABEL_MAX]:
        opx, opy = project(olat, olon)
        if 0 <= opx <= box_w and 0 <= opy <= box_h:
            oshort = (other_n.get("short") or "?").strip()
            _halo_text(sd, (opx + 7, opy - 10), oshort, font(10, bold=True))

    entry = registry.get(short.upper())
    city = entry.get("city") if entry else None
    if city:
        _halo_text(sd, (px + 9, py - 3), city, font(12, bold=True), fill=MAP_LABEL, anchor="lm")

    _draw_pin(sd, px, py, fill=SRC_COLOR[source])
    if tile_img:
        _halo_text(sd, (box_w - 6, box_h - 6), _OSM_ATTRIBUTION, font(9), anchor="rs")
    img.paste(sub, (map_x0, map_y0))

    # ── info block: node name, city, coords, hardware, nearest node ────────
    long_name = (n.get("long") or "").strip()
    hw = _normalize_hw(n.get("hw", "?"), hw_map)

    info_y = map_y1 + 12
    d.text((x + 20, info_y), long_name or short, font=font(15, bold=True), fill=TEXT)
    info_y += 22
    if city:
        d.text((x + 20, info_y), city, font=font(13), fill=MUTED)
        info_y += 19
    d.text((x + 20, info_y), f"{lat:.4f}, {lon:.4f}", font=font(12), fill=MUTED)
    info_y += 19
    d.text((x + 20, info_y), f"{hw} · {SRC_LABEL[source]}", font=font(11), fill=FAINT)
    info_y += 26

    if nearby:
        nearest_n, _, _, _, nearest_dist = nearby[0]
        nearest_short = (nearest_n.get("short") or "?").strip()
        d.text((x + 20, info_y), f"Node terdekat: {nearest_short} ({nearest_dist:.1f} km)",
               font=font(13, bold=True), fill=ACCENT)
        info_y += 22
        for other_n, _, _, _, dist in nearby[:NEARBY_LIST_MAX]:
            oshort = (other_n.get("short") or "?").strip()
            d.text((x + 20, info_y), f"• {oshort} — {dist:.1f} km", font=font(12), fill=MUTED)
            info_y += 17
        extra = len(nearby) - NEARBY_LIST_MAX
        if extra > 0:
            d.text((x + 20, info_y), f"+{extra} node lain dalam {NEARBY_RADIUS_KM} km",
                   font=font(11), fill=FAINT)
            info_y += 17
    else:
        d.text((x + 20, info_y), f"Tidak ada node lain dalam {NEARBY_RADIUS_KM} km",
               font=font(12), fill=FAINT)
        info_y += 17

    if same_city_count:
        # These nodes collapse to the same registered-city point as the
        # requester — real distance unknown, not "0 km" — say so plainly
        # instead of omitting them or implying a precision we don't have.
        d.text((x + 20, info_y), f"+{same_city_count} node di kota sama (jarak tak diketahui)",
               font=font(11), fill=FAINT)


def draw_indonesia_map(img, d, x, y, w, h, nodes, registry, positions):
    rounded(d, (x, y, x + w, y + h), 12, fill=SURF, outline=BORDER, width=1)
    d.text((x + 20, y + 16), "Peta Node", font=font(17, bold=True), fill=TEXT)

    map_x0, map_y0 = x + 16, y + 50
    map_x1, map_y1 = x + w - 16, y + h - 16
    box_w, box_h = map_x1 - map_x0, map_y1 - map_y0

    own_count = sum(1 for _, _, _, s in positions if s == SRC_OWN)
    meshnode_count = sum(1 for _, _, _, s in positions if s == SRC_MESHNODE)
    city_count = sum(1 for _, _, _, s in positions if s == SRC_CITY)

    tile_img, project = _render_osm_basemap(box_w, box_h, 95.0, 141.1, -11.0, 6.1, pad=0.05, axis="width")
    sub = tile_img if tile_img else Image.new("RGB", (box_w, box_h), MAP_WATER)
    sd = ImageDraw.Draw(sub)
    if not tile_img:
        sd.text((16, 20), "(peta OSM tidak tersedia)", font=font(14), fill=MAP_LABEL)

    # ── registered-city labels (only cities that actually have a node) ─────
    # OSM's own tiles already carry real place names at this zoom, so this
    # only labels registry cities that OSM itself might not show (smaller
    # towns), to make clear *why* a pin sits where it does.
    seen_cities = set()
    f_city = font(11, bold=True)
    for n, lat, lon, source in positions:
        if source != SRC_CITY:
            continue
        short = (n.get("short") or "").strip().upper()
        city = (registry.get(short) or {}).get("city")
        if not city or city in seen_cities:
            continue
        px, py = project(lat, lon)
        if 0 <= px <= box_w and 0 <= py <= box_h:
            seen_cities.add(city)
            _halo_text(sd, (px + 8, py - 3), city, f_city, anchor="lm")

    # ── node pins ────────────────────────────────────────────────────────────
    # Color + size both encode the source (own live session brightest/
    # biggest, meshnode.id mid, city-centroid dimmest/smallest) — several
    # nodes sharing one city will visually stack at the same point, that's
    # honest, not a bug: it IS the same point.
    for n, lat, lon, source in positions:
        px, py = project(lat, lon)
        if not (0 <= px <= box_w and 0 <= py <= box_h):
            continue
        _draw_pin(sd, px, py, r=SRC_RADIUS[source], fill=SRC_COLOR[source])

    # Floating coverage card in the top-right corner — that area is open
    # sea for Indonesia's actual shape at this zoom, so it puts the "no
    # location" nodes somewhere on the map instead of only in the caption.
    unknown_count = len(nodes) - own_count - meshnode_count - city_count
    _draw_coverage_card(sd, box_w - 196 - 12, 12, own_count, meshnode_count, city_count, unknown_count)

    if tile_img:
        _halo_text(sd, (box_w - 6, box_h - 6), _OSM_ATTRIBUTION, font(9), anchor="rs")
    img.paste(sub, (map_x0, map_y0))

    # ── legend + honest caption ──────────────────────────────────────────────
    leg_y = map_y0 + 12
    leg_x = map_x0 + 12
    for label, color in ((SRC_LABEL[SRC_OWN], SRC_COLOR[SRC_OWN]),
                         (SRC_LABEL[SRC_MESHNODE], SRC_COLOR[SRC_MESHNODE]),
                         (SRC_LABEL[SRC_CITY], SRC_COLOR[SRC_CITY])):
        d.ellipse((leg_x, leg_y + 1, leg_x + 8, leg_y + 9), fill=color)
        tw = text_w(d, label, font(12))
        _halo_text(d, (leg_x + 14, leg_y - 2), label, font(12))
        leg_x += 14 + tw + 18

    caption = (f"{own_count} node GPS langsung, {meshnode_count} dari map.meshnode.id, "
               f"{city_count} posisi perkiraan (kota terdaftar), {unknown_count} tanpa data lokasi")
    d.text((x + 20, y + h - 30), caption, font=font(13), fill=MUTED)


def _get_imgbb_key():
    try:
        cfg = configparser.ConfigParser()
        cfg.read(_CONFIG_PATH)
        return cfg.get("statImage", "imgbbAPIKey", fallback="").strip() or None
    except Exception as e:
        print(f"config.ini read failed: {e}")
        return None


def upload_to_imgbb(path):
    """Uploads the PNG to imgbb and returns its public URL, or None if no
    key is configured or the upload fails — callers should treat this as
    best-effort and fall back to the plain-text stat reply either way,
    since Meshtastic can't send images directly regardless."""
    key = _get_imgbb_key()
    if not key:
        print("no imgbbAPIKey configured in config.ini's [statImage] section — skipping upload")
        return None
    try:
        import requests
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read())
        resp = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": key, "image": b64, "expiration": 15 * 86400},  # auto-expire in 15 days, matches node_days-ish retention spirit
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["data"]["url"] if data.get("success") else None
    except Exception as e:
        print(f"imgbb upload failed: {e}")
        return None


def main():
    # Optional: short name/callsign of whoever sent !stat, so the sidebar
    # zoom-inset can center on them. Passed as argv[1] by the bot handler;
    # standalone runs (no arg) just show the "send !stat" placeholder.
    requester_short = sys.argv[1] if len(sys.argv) > 1 else None

    nodes = json.load(urllib.request.urlopen("http://localhost:8080/api/nodes", timeout=15))
    import modules.statistik as st
    registry = st._get_registry()

    positions = _fallback_positions(nodes, registry)
    requester_pos = _find_requester_position(requester_short, positions)

    total = len(nodes)
    hw_map = _get_device_hardware()
    hw_counter = collections.Counter(_normalize_hw(n.get("hw", "?"), hw_map) for n in nodes)

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # ── header ──────────────────────────────────────────────────────────────
    now = datetime.now(WIB)
    # DejaVu has no color-emoji glyphs (PIL can't render those anyway without
    # a bitmap-emoji font + extra plumbing) — draw a small accent square
    # instead of an emoji icon, plain text elsewhere.
    d.rounded_rectangle((40, 40, 62, 62), radius=6, fill=ACCENT)
    d.text((72, 36), "RiV-Bot Mesh Statistics", font=font(28, bold=True), fill=TEXT)
    d.text((40, 76), now.strftime("%d %B %Y · %H:%M WIB"), font=font(15), fill=MUTED)

    # ── layout: left content column + right sidebar (zoom inset) ───────────
    main_x = 40
    main_w = W - 80 - SIDEBAR_W - 24
    sidebar_x = main_x + main_w + 24

    # ── top stat row ─────────────────────────────────────────────────────
    card_y = 120
    card_h = 90
    card_w = main_w
    stat_card(d, main_x, card_y, card_w, card_h, "NODE TERDETEKSI", str(total), ACCENT)

    # ── hardware population bar chart (with device icons) ──────────────────
    chart_y = card_y + card_h + 30
    chart_x = main_x
    chart_w = main_w
    top_hw = hw_counter.most_common(10)
    row_h = 48
    chart_h = 40 + row_h * len(top_hw) + 20

    rounded(d, (chart_x, chart_y, chart_x + chart_w, chart_y + chart_h), 12, fill=SURF, outline=BORDER)
    d.text((chart_x + 20, chart_y + 16), "Sebaran Hardware", font=font(17, bold=True), fill=TEXT)

    max_count = max(c for _, c in top_hw) if top_hw else 1
    icon_col_w = _ICON_SIZE + 12
    label_w = 220
    bar_x0 = chart_x + 20 + icon_col_w + label_w
    bar_max_w = chart_w - 40 - icon_col_w - label_w - 60
    f_hw_label = font(14)
    f_hw_count = font(14, bold=True)
    row_y = chart_y + 52
    for hw, count in top_hw:
        icon_y = row_y + (row_h - _ICON_SIZE) // 2 - 4
        # hw is always a resolved slug string now (numeric hwModel values
        # were normalized before counting) — always try for an icon; devices
        # with no specific image fall back to the generic "unknown" one
        # inside _get_device_icon rather than being skipped.
        icon = _get_device_icon(hw, hw_map)
        if icon:
            # Most device SVGs are dark line-art meant for a light page —
            # near-invisible on this dark theme without a light chip behind.
            chip_pad = 4
            rounded(d, (chart_x + 20 - chip_pad, icon_y - chip_pad,
                        chart_x + 20 + _ICON_SIZE + chip_pad, icon_y + _ICON_SIZE + chip_pad),
                    8, fill=(224, 228, 232))
            img.paste(icon, (chart_x + 20, icon_y), icon)
        label = hw if len(hw) <= 24 else hw[:22] + "…"
        d.text((chart_x + 20 + icon_col_w, row_y + 10), label, font=f_hw_label, fill=MUTED)
        bar_w = max(6, int(bar_max_w * count / max_count))
        rounded(d, (bar_x0, row_y + 8, bar_x0 + bar_w, row_y + 30), 4, fill=ACCENT_DK)
        d.text((bar_x0 + bar_w + 10, row_y + 11), str(count), font=f_hw_count, fill=TEXT)
        row_y += row_h

    # ── sidebar: personal zoom inset, spans header through hw chart ────────
    sidebar_y = card_y
    sidebar_h = chart_y + chart_h - card_y
    draw_zoom_inset(d, img, sidebar_x, sidebar_y, SIDEBAR_W, sidebar_h,
                     requester_short, requester_pos, registry, hw_map, positions)

    # ── Indonesia map with node pins (full width, below both columns) ──────
    map_y = chart_y + chart_h + 24
    map_h = 480
    draw_indonesia_map(img, d, main_x, map_y, W - 80, map_h, nodes, registry, positions)

    # ── footer ──────────────────────────────────────────────────────────────
    footer_y = map_y + map_h + 24
    d.text((40, footer_y), "Belum terdaftar? Isi form pendaftaran ID Node —", font=font(14), fill=FAINT)
    d.text((40, footer_y + 22), "cek !stat di bot buat link lengkapnya.", font=font(14), fill=FAINT)

    img = img.crop((0, 0, W, footer_y + 60))
    img.save(OUT_PATH)
    print(f"Saved {OUT_PATH} ({img.width}x{img.height})")

    # Printed as its own line (not mixed into the "Saved ..." line) so a
    # caller like statistik.py can grep stdout for this prefix without
    # parsing the rest of this script's diagnostic output.
    url = upload_to_imgbb(OUT_PATH)
    if url:
        print(f"URL: {url}")


if __name__ == "__main__":
    main()
