"""Indonesian volcano (gunung api) activity status, scraped from PVMBG's
MAGMA Indonesia site (magma.esdm.go.id) — there is no public JSON API, only
a server-rendered HTML dashboard, so this parses that HTML with BeautifulSoup."""
import difflib
import logging
import math
import time
import urllib.request

import bs4

logger = logging.getLogger(__name__)

# Coordinates for the commonly-monitored volcanoes (PVMBG's regular Level I-IV
# list). There's no coordinate field on the list page, and fetching every
# volcano's detail page live (up to ~45) to get one would be far too slow for
# a single mesh reply — this static table covers what actually shows up in
# practice; anything not listed here is simply left out of "!gunung dekat"
# rather than triggering a live fetch.
_COORDS = {
    "anak krakatau": (-6.102, 105.423), "awu": (3.67, 125.447),
    "lewotobi laki-laki": (-8.542, 122.775), "lewotobi perempuan": (-8.358, 122.640),
    "merapi": (-7.542, 110.442), "semeru": (-8.108, 112.922),
    "banda api": (-4.525, 129.871), "bromo": (-7.942, 112.95),
    "bur ni telong": (4.767, 96.817), "dempo": (-4.03, 103.13),
    "dukono": (1.693, 127.894), "ibu": (1.488, 127.63),
    "karangetang": (2.781, 125.407), "kerinci": (-1.697, 101.264),
    "marapi": (-0.381, 100.473), "gamalama": (0.8, 127.325),
    "gamkonora": (1.38, 127.53), "ile lewotolok": (-8.272, 123.505),
    "kelud": (-7.93, 112.308), "raung": (-8.125, 114.042),
    "rinjani": (-8.42, 116.47), "sangeang api": (-8.183, 119.067),
    "sinabung": (3.17, 98.392), "slamet": (-7.242, 109.208),
    "soputan": (1.108, 124.737), "tangkuban perahu": (-6.77, 107.6),
    "gede": (-6.789, 106.98), "salak": (-6.72, 106.73),
    "papandayan": (-7.32, 107.73), "guntur": (-7.14, 107.83),
    "sundoro": (-7.3, 109.992), "sumbing": (-7.383, 110.07),
    "ijen": (-8.058, 114.242), "agung": (-8.343, 115.508),
    "batur": (-8.242, 115.375), "peut sague": (4.917, 96.33),
    "iya": (-8.9, 121.65), "egon": (-8.677, 122.45),
    "inielika": (-8.786, 121.202), "lokon": (1.358, 124.792),
    "colo": (-0.169, 121.608), "krakatau": (-6.102, 105.423),
}


def _haversine(lat1, lon1, lat2, lon2):
    R    = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    a    = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
            + math.cos(phi1) * math.cos(phi2)
            * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

_HEADERS  = {"User-Agent": "Mozilla/5.0"}
_LIST_URL = "https://magma.esdm.go.id/v1/gunung-api/tingkat-aktivitas"

_LEVEL_ORDER = {
    "Level IV (Awas)":    4,
    "Level III (Siaga)":  3,
    "Level II (Waspada)": 2,
    "Level I (Normal)":   1,
}
_LEVEL_SHORT = {4: "AWAS (IV)", 3: "SIAGA (III)", 2: "WASPADA (II)", 1: "NORMAL (I)"}
_LEVEL_ICON  = {4: "🟥", 3: "🟧", 2: "🟨", 1: "🟩"}

_MATCH_THRESHOLD = 0.8

_list_cache = {"data": None, "ts": 0}
_LIST_TTL   = 1800  # 30 minutes

_detail_cache = {}  # link -> (dict, ts)
_DETAIL_TTL   = 1800


def _fetch(url):
    req = urllib.request.Request(url, headers=_HEADERS)
    return urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="replace")


def _fetch_list():
    now = time.time()
    if _list_cache["data"] and now - _list_cache["ts"] < _LIST_TTL:
        return _list_cache["data"]

    html = _fetch(_LIST_URL)
    soup = bs4.BeautifulSoup(html, "html.parser")

    volcanoes = []
    cur_level_label = None
    for tr in soup.select("table tr"):
        level_a = tr.select_one("td a.tx-inverse")
        if level_a:
            cur_level_label = level_a.get_text(strip=True)
            continue
        tds = tr.find_all("td")
        if not tds:
            continue
        link_el = tds[0].find("a")
        if not link_el or not cur_level_label:
            continue
        name_region = tds[0].get_text(separator="|", strip=True).split("|")[0]
        if " - " in name_region:
            name, region = name_region.rsplit(" - ", 1)
        else:
            name, region = name_region, ""
        volcanoes.append({
            "name": name.strip(),
            "region": region.strip(),
            "level": _LEVEL_ORDER.get(cur_level_label, 0),
            "link": link_el.get("href"),
        })

    if volcanoes:
        _list_cache["data"] = volcanoes
        _list_cache["ts"] = now
    return volcanoes


def _fetch_detail(link):
    now = time.time()
    cached = _detail_cache.get(link)
    if cached and now - cached[1] < _DETAIL_TTL:
        return cached[0]

    html = _fetch(link)
    soup = bs4.BeautifulSoup(html, "html.parser")

    badge = soup.select_one(".badge")
    status = badge.get_text(strip=True) if badge else "?"
    title = soup.select_one("h5.card-title")
    period = "?"
    if title:
        # title looks like "Merapi, Selasa - 07 Juli 2026, periode 00:00-24:00 WIB"
        # — keep just the date, drop the volcano name/day-name/period-window noise
        raw = title.get_text(strip=True)
        parts = raw.split(",")
        if len(parts) >= 2 and " - " in parts[1]:
            period = parts[1].split(" - ", 1)[1].strip()
        else:
            period = raw

    sections = {}
    for h6 in soup.select("h6.slim-card-title"):
        p = h6.find_next_sibling("p")
        if p:
            sections[h6.get_text(strip=True)] = p.get_text(strip=True)

    detail = {
        "status": status,
        "period": period,
        "aktivitas": sections.get("Keterangan Lainnya") or sections.get("Pengamatan Visual", ""),
        "rekomendasi": sections.get("Rekomendasi", ""),
    }
    _detail_cache[link] = (detail, now)
    return detail


def _best_ratio(query, name):
    q = query.lower().strip()
    n = name.lower().strip()
    best = difflib.SequenceMatcher(None, q, n).ratio()
    for word in n.split():
        best = max(best, difflib.SequenceMatcher(None, q, word).ratio())
    return best


def _trim(text, limit=180):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "..."


def get_gunung(message, message_from_id=None, deviceID=None):
    """Dispatch: '!gunung' -> top 5 summary, '!gunung aktif' -> level>=2,
    '!gunung awas' -> level 4 only, '!gunung dekat' -> nearest to caller,
    '!gunung <nama>' -> fuzzy detail lookup."""
    parts = message.strip().split(None, 1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    try:
        volcanoes = _fetch_list()
    except Exception as e:
        logger.error("gunung fetch error: %s", e)
        return "❌ Gagal mengambil data PVMBG. Coba lagi nanti."

    if not volcanoes:
        return "❌ Data gunung api tidak tersedia saat ini."

    if not arg:
        return _summary(volcanoes)

    low = arg.lower()
    if low == "aktif":
        return _filtered(volcanoes, lambda v: v["level"] >= 2, "Gunung Aktif (Level II+)")
    if low == "awas":
        return _filtered(volcanoes, lambda v: v["level"] == 4, "Gunung Level AWAS (IV)")
    if low == "dekat":
        return _nearest(volcanoes, message_from_id, deviceID)

    return _detail(volcanoes, arg)


def _nearest(volcanoes, message_from_id, deviceID):
    if not message_from_id or not deviceID:
        return "🤔 Lokasi tidak diketahui. Fitur ini butuh posisi node kamu."
    try:
        from modules.system import get_node_location
        loc = get_node_location(message_from_id, deviceID)
        user_lat, user_lon = loc[0], loc[1]
    except Exception as e:
        logger.debug("gunung dekat location error: %s", e)
        return "🤔 Gagal membaca lokasi node kamu. Pastikan GPS aktif."

    ranked = []
    for v in volcanoes:
        coord = _COORDS.get(v["name"].lower())
        if not coord:
            continue
        dist = _haversine(user_lat, user_lon, coord[0], coord[1])
        ranked.append((dist, v))
    if not ranked:
        return "❌ Koordinat gunung tidak tersedia untuk dihitung."

    ranked.sort(key=lambda x: x[0])
    lines = ["🌋 Gunung Terdekat", ""]
    for dist, v in ranked[:5]:
        icon = _LEVEL_ICON.get(v["level"], "⬜")
        lines.append(f"{icon} {v['name']} ({v['region']}, {dist:.0f} km) - {_LEVEL_SHORT.get(v['level'], '?')}")
    return "\n".join(lines)


def _summary(volcanoes):
    top = sorted(volcanoes, key=lambda v: (-v["level"], v["name"]))[:5]
    lines = ["🔥 Status Gunung (Top 5)", ""]
    for i, v in enumerate(top, 1):
        icon = _LEVEL_ICON.get(v["level"], "⬜")
        lines.append(f"{icon}{i}. {v['name']} ({v['region']}) - {_LEVEL_SHORT.get(v['level'], '?')}")
    lines.append("")
    lines.append("!gunung <nama> untuk detail")
    return "\n".join(lines)


def _filtered(volcanoes, pred, title):
    matches = sorted((v for v in volcanoes if pred(v)), key=lambda v: (-v["level"], v["name"]))
    if not matches:
        return f"{title}: tidak ada saat ini. 👍"
    lines = [f"🔥 {title}", ""]
    for v in matches[:10]:
        icon = _LEVEL_ICON.get(v["level"], "⬜")
        lines.append(f"{icon} {v['name']} ({v['region']}) - {_LEVEL_SHORT.get(v['level'], '?')}")
    if len(matches) > 10:
        lines.append(f"...dan {len(matches) - 10} lainnya")
    return "\n".join(lines)


def _detail(volcanoes, query):
    scored = [(v, _best_ratio(query, v["name"])) for v in volcanoes]
    matches = sorted((v for v, r in scored if r >= _MATCH_THRESHOLD),
                      key=lambda v: (-v["level"], v["name"]))
    if not matches:
        return f'🤔 Gunung "{query}" tidak ditemukan. Ketik !gunung untuk lihat daftar teratas.'

    blocks = []
    for v in matches[:3]:
        try:
            d = _fetch_detail(v["link"])
        except Exception as e:
            logger.debug("gunung detail error for %s: %s", v["name"], e)
            blocks.append(f"{v['name']} ({v['region']})\nStatus: {_LEVEL_SHORT.get(v['level'], '?')}\n(detail gagal dimuat)")
            continue
        icon = _LEVEL_ICON.get(v["level"], "⬜")
        lines = [v["name"]]
        if v["region"]:
            lines.append(f"📍 {v['region']}")
        coord = _COORDS.get(v["name"].lower())
        if coord:
            lines.append(f"🗺️ {coord[0]:.3f}, {coord[1]:.3f}")
        lines += [
            f"Status: {icon} {_LEVEL_SHORT.get(v['level'], d['status'])}",
            f"Update: {d['period']}",
        ]
        if d["aktivitas"]:
            lines.append(f"\nAktivitas:\n{_trim(d['aktivitas'])}")
        if d["rekomendasi"]:
            lines.append(f"\nRekomendasi:\n{_trim(d['rekomendasi'])}")
        blocks.append("\n".join(lines))

    if len(matches) > 3:
        blocks.append(f"...dan {len(matches) - 3} gunung lain juga cocok, coba nama lebih spesifik.")

    return "\n\n---\n\n".join(blocks)
