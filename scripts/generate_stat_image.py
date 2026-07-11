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
_ICON_DIR = "/opt/meshing-around/data/device_icons"
_ICON_SIZE = 34


def _get_device_hardware():
    """Returns {hwModelSlug: [image_filenames]}. Disk-cached 7d."""
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
        mapping = {d["hwModelSlug"]: d.get("images") or [] for d in raw if d.get("hwModelSlug")}
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
            return {}


def _get_device_icon(slug, hw_map):
    """Returns a PIL Image (RGBA, _ICON_SIZE square) for this hwModelSlug, or
    None if there's no image for it (private/custom hardware, or the API
    just doesn't have one — several real devices genuinely have none)."""
    images = hw_map.get(slug) or []
    if not images:
        return None

    os.makedirs(_ICON_DIR, exist_ok=True)
    # Render at 4x then downscale in PIL (LANCZOS) rather than trusting
    # rsvg-convert's own scaling — crisper small icons.
    render_size = _ICON_SIZE * 4
    png_path = f"{_ICON_DIR}/{slug}.png"
    if not os.path.exists(png_path):
        svg_url = f"https://flasher.meshtastic.org/img/devices/{images[0]}"
        svg_path = f"{_ICON_DIR}/{slug}.svg"
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

W, H = 900, 1180


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


def main():
    nodes = json.load(urllib.request.urlopen("http://localhost:8080/api/nodes", timeout=15))
    import modules.statistik as st
    registry = st._get_registry()

    total = len(nodes)
    hw_counter = collections.Counter(n.get("hw", "?") for n in nodes)
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

    # ── top stat row: 3 cards ──────────────────────────────────────────────
    card_y = 120
    card_h = 90
    gap = 16
    card_w = (W - 80 - gap * 2) // 3
    stat_card(d, 40, card_y, card_w, card_h, "NODE TERDETEKSI", str(total), ACCENT)
    stat_card(d, 40 + card_w + gap, card_y, card_w, card_h, "NODE TERDAFTAR", f"{matched}/{total}", ACCENT)
    stat_card(d, 40 + (card_w + gap) * 2, card_y, card_w, card_h, "% TERDAFTAR", f"{pct}%",
              ACCENT if pct >= 50 else (227, 179, 65))

    # ── hardware population bar chart (with device icons) ──────────────────
    hw_map = _get_device_hardware()
    chart_y = card_y + card_h + 30
    chart_x = 40
    chart_w = W - 80
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
        icon = _get_device_icon(hw, hw_map) if isinstance(hw, str) else None
        if icon:
            # Most device SVGs are dark line-art meant for a light page —
            # near-invisible on this dark theme without a light chip behind.
            chip_pad = 4
            rounded(d, (chart_x + 20 - chip_pad, icon_y - chip_pad,
                        chart_x + 20 + _ICON_SIZE + chip_pad, icon_y + _ICON_SIZE + chip_pad),
                    8, fill=(224, 228, 232))
            img.paste(icon, (chart_x + 20, icon_y), icon)
        label = hw if isinstance(hw, str) else f"hwModel {hw}"
        label = label if len(label) <= 24 else label[:22] + "…"
        d.text((chart_x + 20 + icon_col_w, row_y + 10), label, font=f_hw_label, fill=MUTED)
        bar_w = max(6, int(bar_max_w * count / max_count))
        rounded(d, (bar_x0, row_y + 8, bar_x0 + bar_w, row_y + 30), 4, fill=ACCENT_DK)
        d.text((bar_x0 + bar_w + 10, row_y + 11), str(count), font=f_hw_count, fill=TEXT)
        row_y += row_h

    # ── footer ──────────────────────────────────────────────────────────────
    footer_y = chart_y + chart_h + 24
    d.text((40, footer_y), "Belum terdaftar? Isi form pendaftaran ID Node —", font=font(14), fill=FAINT)
    d.text((40, footer_y + 22), "cek !stat di bot buat link lengkapnya.", font=font(14), fill=FAINT)

    img = img.crop((0, 0, W, footer_y + 60))
    img.save(OUT_PATH)
    print(f"Saved {OUT_PATH} ({img.width}x{img.height})")


if __name__ == "__main__":
    main()
