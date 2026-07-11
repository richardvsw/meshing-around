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
import collections
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/opt/meshing-around")

from PIL import Image, ImageDraw, ImageFont

WIB = timezone(timedelta(hours=7))
FONT_DIR = "/usr/share/fonts/truetype/dejavu"
OUT_PATH = "/opt/meshing-around/data/stat_snapshot.png"

_DEVICE_HW_URL = "https://api.meshtastic.org/resource/deviceHardware"
_DEVICE_HW_CACHE = "/opt/meshing-around/data/device_hardware.json"
_DEVICE_HW_TTL = 7 * 86400  # this list changes rarely — new hardware releases, not daily

# Real Indonesia province boundaries (public domain, BAKOSURTANAL-sourced via
# github.com/superpikar/indonesia-geojson) — fetched once, vendored locally.
# NOT regenerated from a live URL on every run: this is static geography,
# no reason to refetch it.
_GEOJSON_PATH = "/opt/meshing-around/data/indonesia_provinces.geojson"

# City name -> (lat, lon), geocoded once via Nominatim (same free/no-key
# service !hargabbm and !dimana already use elsewhere in this project) and
# cached indefinitely — city centroids don't move.
_CITY_COORDS_CACHE = "/opt/meshing-around/data/city_coords.json"
_ICON_DIR = "/opt/meshing-around/data/device_icons"
_ICON_SIZE = 34


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

# ── map palette — "night mode Maps" (like Google/Apple Maps' dark theme):
# dark navy sea, a slightly lighter dark land tone, muted border lines,
# light labels with a dark halo — tinted to the dashboard's own teal so it
# sits naturally in the dark dashboard instead of a bright light-mode panel. ─
MAP_WATER  = (12, 20, 27)     # deep navy sea
MAP_LAND   = (26, 38, 43)     # muted dark teal-green land, distinct from sea
MAP_BORDER = (52, 70, 68)     # province boundary lines
MAP_LABEL  = (205, 216, 212)  # light label text
MAP_HALO   = (8, 13, 17)      # dark halo for legibility over polygons/water
PIN_FILL   = ACCENT
PIN_OTHER  = (227, 179, 65)   # nearby-node pins (distinct from the requester's own ACCENT pin)
PIN_HEAD_R = 9  # teardrop head radius, px


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


def _load_provinces():
    try:
        with open(_GEOJSON_PATH) as f:
            return json.load(f).get("features", [])
    except Exception as e:
        print(f"provinces geojson load failed: {e}")
        return []


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


def _province_centroid(feat, project):
    """Rough polygon centroid (vertex average of the exterior ring, not
    area-weighted) — good enough to place a label roughly inside a
    province at this map scale, no need for a real centroid algorithm."""
    geom = feat.get("geometry", {})
    polys = geom.get("coordinates", [])
    if geom.get("type") == "Polygon":
        polys = [polys]
    # Label on the largest ring (by vertex count) if a province is a
    # multi-polygon (e.g. archipelagos) — avoids labeling a tiny outlying
    # island instead of the main landmass.
    ring = max((poly[0] for poly in polys if poly), key=len, default=None)
    if not ring:
        return None
    xs, ys = [], []
    for lon, lat in ring:
        x, y = project(lat, lon)
        xs.append(x)
        ys.append(y)
    return sum(xs) / len(xs), sum(ys) / len(ys)


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


def _fallback_positions(nodes, registry):
    """For nodes with no live GPS but a registered short name that has a
    city on file, approximate their position as that city's centroid.
    Returns [(node, lat, lon, is_approx), ...] — is_approx distinguishes
    these from real GPS fixes so the map can render them differently
    (smaller/dimmer, not claiming precision the data doesn't have)."""
    cache = _load_city_coords_cache()
    dirty = False
    out = []
    for n in nodes:
        if n.get("lat") and n.get("lon"):
            out.append((n, n["lat"], n["lon"], False))
            continue
        short = (n.get("short") or "").strip().upper()
        entry = registry.get(short)
        city = entry.get("city") if entry else None
        if not city:
            continue
        before = city in cache
        coord = _geocode_city(city, cache)
        if not before:
            dirty = True
        if coord:
            out.append((n, coord[0], coord[1], True))
    if dirty:
        _save_city_coords_cache(cache)
    return out


def _make_projector(lon_min, lon_max, lat_min, lat_max, px_x0, px_y0, px_x1, px_y1, pad=0.04):
    """Equirectangular lat/lon -> pixel, fit-within (preserves aspect ratio,
    letterboxed within the box) rather than stretch-to-fill — otherwise
    Indonesia's real shape gets visibly distorted. `pad` adds a geo margin
    so coastline provinces don't touch the panel edge."""
    lon_span = lon_max - lon_min
    lat_span = lat_max - lat_min
    lon_min -= lon_span * pad
    lon_max += lon_span * pad
    lat_min -= lat_span * pad
    lat_max += lat_span * pad
    lon_span = lon_max - lon_min
    lat_span = lat_max - lat_min

    # cos(mean latitude) correction — near the equator this is close to 1,
    # but Indonesia spans far enough south (to -11°) that skipping it would
    # visibly stretch the map east-west.
    import math
    mean_lat_rad = math.radians((lat_min + lat_max) / 2)
    geo_w = lon_span * math.cos(mean_lat_rad)
    geo_h = lat_span

    box_w, box_h = px_x1 - px_x0, px_y1 - px_y0
    scale = min(box_w / geo_w, box_h / geo_h)
    used_w, used_h = geo_w * scale, geo_h * scale
    off_x = px_x0 + (box_w - used_w) / 2
    off_y = px_y0 + (box_h - used_h) / 2

    def project(lat, lon):
        x = off_x + (lon - lon_min) * math.cos(mean_lat_rad) * scale
        y = off_y + (lat_max - lat) * scale  # image y grows downward, lat grows upward
        return x, y

    return project


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
    for n, lat, lon, is_approx in positions:
        if (n.get("short") or "").strip().upper() == requester_short:
            return (n, lat, lon, is_approx)
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

    n, lat, lon, is_approx = requester_pos
    short = (n.get("short") or "?").strip()

    # ── find nearby nodes (real distance, not just "inside the same pixel
    # box") so the nearest-node figure and the list are both trustworthy ──
    nearby = []
    for other_n, olat, olon, oapprox in positions:
        if other_n is n:
            continue
        dist = _haversine_km(lat, lon, olat, olon)
        if dist <= NEARBY_RADIUS_KM:
            nearby.append((other_n, olat, olon, oapprox, dist))
    nearby.sort(key=lambda t: t[4])

    # Bottom info block needs room for: own node (name/city/coords/hw) +
    # nearest-node line + a short neighbor list — taller than a plain tag.
    info_h = 118 + 20 + min(len(nearby), NEARBY_LIST_MAX) * 17
    map_x0, map_y0 = x + 16, y + 50
    map_x1, map_y1 = x + w - 16, y + h - 16 - info_h
    rounded(d, (map_x0, map_y0, map_x1, map_y1), 8, fill=MAP_WATER)

    features = _load_provinces()
    # City/reasonable-radius view, not a whole province — the vendored
    # geometry has no city-level detail anyway, so at this scale the
    # province polygon mostly just tints the background; the km rings
    # below are what actually convey scale.
    pad = 0.2  # ~22 km half-width
    box_w, box_h = map_x1 - map_x0, map_y1 - map_y0
    # Province polygons at this tight zoom extend far past the panel in
    # pixel space (national-scale geometry projected at a much larger local
    # scale) — draw.polygon has no clip region, so drawing straight onto
    # the main canvas bled into the header/cards above. Render onto a
    # panel-sized sub-image instead, then paste that in — the sub-image's
    # own edges do the clipping for free.
    sub = Image.new("RGB", (box_w, box_h), MAP_WATER)
    sd = ImageDraw.Draw(sub)
    project = _make_projector(lon - pad, lon + pad, lat - pad, lat + pad,
                               0, 0, box_w, box_h, pad=0.1)

    for feat in features:
        geom = feat.get("geometry", {})
        gtype = geom.get("type")
        polys = geom.get("coordinates", [])
        if gtype == "Polygon":
            polys = [polys]
        for poly in polys:
            if not poly:
                continue
            ring = poly[0]
            pts = [project(plat, plon) for plon, plat in ring]
            if len(pts) >= 3:
                sd.polygon(pts, fill=MAP_LAND, outline=MAP_BORDER, width=2)

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
    for other_n, olat, olon, oapprox, dist in nearby:
        opx, opy = project(olat, olon)
        if not (0 <= opx <= box_w and 0 <= opy <= box_h):
            continue
        _draw_pin(sd, opx, opy, r=6, fill=PIN_OTHER)
    for other_n, olat, olon, oapprox, dist in nearby[:NEARBY_LABEL_MAX]:
        opx, opy = project(olat, olon)
        if 0 <= opx <= box_w and 0 <= opy <= box_h:
            oshort = (other_n.get("short") or "?").strip()
            _halo_text(sd, (opx + 7, opy - 10), oshort, font(10, bold=True))

    entry = registry.get(short.upper())
    city = entry.get("city") if entry else None
    if city:
        _halo_text(sd, (px + 9, py - 3), city, font(12, bold=True), fill=MAP_LABEL, anchor="lm")

    _draw_pin(sd, px, py, fill=PIN_FILL)
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
    d.text((x + 20, info_y), hw, font=font(12), fill=FAINT)
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
    else:
        d.text((x + 20, info_y), f"Tidak ada node lain dalam {NEARBY_RADIUS_KM} km",
               font=font(12), fill=FAINT)


def draw_indonesia_map(img, d, x, y, w, h, nodes, registry, positions):
    rounded(d, (x, y, x + w, y + h), 12, fill=SURF, outline=BORDER, width=1)
    d.text((x + 20, y + 16), "Peta Node", font=font(17, bold=True), fill=TEXT)

    map_x0, map_y0 = x + 16, y + 50
    map_x1, map_y1 = x + w - 16, y + h - 16
    rounded(d, (map_x0, map_y0, map_x1, map_y1), 8, fill=MAP_WATER)

    features = _load_provinces()
    gps_count = sum(1 for _, _, _, approx in positions if not approx)
    approx_count = sum(1 for _, _, _, approx in positions if approx)

    if not features:
        d.text((map_x0 + 20, map_y0 + 20), "(peta tidak tersedia)", font=font(14), fill=FAINT)
        return

    project = _make_projector(95.0, 141.1, -11.0, 6.1, map_x0, map_y0, map_x1, map_y1)

    # ── province polygons (exterior rings only — this dataset has no holes
    # worth rendering for an infographic at this scale) + name labels ──────
    f_province = font(11)
    for feat in features:
        geom = feat.get("geometry", {})
        gtype = geom.get("type")
        polys = geom.get("coordinates", [])
        if gtype == "Polygon":
            polys = [polys]
        for poly in polys:
            if not poly:
                continue
            ring = poly[0]  # exterior ring
            pts = [project(lat, lon) for lon, lat in ring]
            if len(pts) >= 3:
                d.polygon(pts, fill=MAP_LAND, outline=MAP_BORDER, width=2)

        name = feat.get("properties", {}).get("Propinsi")
        centroid = _province_centroid(feat, project)
        if name and centroid and map_x0 < centroid[0] < map_x1 and map_y0 < centroid[1] < map_y1:
            _halo_text(d, centroid, name.title(), f_province, anchor="mm")

    # ── registered-city labels (only cities that actually have a node) ─────
    seen_cities = set()
    f_city = font(11, bold=True)
    for n, lat, lon, is_approx in positions:
        if not is_approx:
            continue
        short = (n.get("short") or "").strip().upper()
        city = (registry.get(short) or {}).get("city")
        if not city or city in seen_cities:
            continue
        px, py = project(lat, lon)
        if map_x0 <= px <= map_x1 and map_y0 <= py <= map_y1:
            seen_cities.add(city)
            _halo_text(d, (px + 8, py - 3), city, f_city, anchor="lm")

    # ── node pins ────────────────────────────────────────────────────────────
    # Approximate (city-centroid) positions render as a smaller pin than
    # real GPS fixes, and several nodes sharing one city will visually stack
    # at the same point — that's honest, not a bug: it IS the same point.
    for n, lat, lon, is_approx in positions:
        px, py = project(lat, lon)
        if not (map_x0 <= px <= map_x1 and map_y0 <= py <= map_y1):
            continue
        r = 6 if is_approx else 9
        _draw_pin(d, px, py, r=r, fill=ACCENT_DK if is_approx else PIN_FILL)

    # ── legend + honest caption ──────────────────────────────────────────────
    leg_y = map_y0 + 12
    d.ellipse((map_x0 + 12, leg_y, map_x0 + 20, leg_y + 8), fill=PIN_FILL)
    _halo_text(d, (map_x0 + 26, leg_y - 3), "GPS asli", font(12))
    d.ellipse((map_x0 + 100, leg_y + 1, map_x0 + 106, leg_y + 7), fill=ACCENT_DK)
    _halo_text(d, (map_x0 + 112, leg_y - 3), "perkiraan dari kota terdaftar", font(12))

    caption = (f"{gps_count} node dgn GPS asli, {approx_count} dgn posisi perkiraan "
               f"(dari kota terdaftar), {len(nodes) - gps_count - approx_count} tanpa data lokasi")
    d.text((x + 20, y + h - 30), caption, font=font(13), fill=MUTED)


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
    matched = 0
    for n in nodes:
        short = (n.get("short") or "").strip().upper()
        if short in registry:
            matched += 1
    pct = round(matched / total * 100) if total else 0

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

    # ── top stat row: 3 cards ──────────────────────────────────────────────
    card_y = 120
    card_h = 90
    gap = 16
    card_w = (main_w - gap * 2) // 3
    stat_card(d, main_x, card_y, card_w, card_h, "NODE TERDETEKSI", str(total), ACCENT)
    stat_card(d, main_x + card_w + gap, card_y, card_w, card_h, "NODE TERDAFTAR", f"{matched}/{total}", ACCENT)
    stat_card(d, main_x + (card_w + gap) * 2, card_y, card_w, card_h, "% TERDAFTAR", f"{pct}%",
              ACCENT if pct >= 50 else (227, 179, 65))

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


if __name__ == "__main__":
    main()
