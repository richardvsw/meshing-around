import urllib.request
import json
import math
import time
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))

_HARI   = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
_BULAN  = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
           "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

_URL_LATEST = "https://data.bmkg.go.id/DataMKG/TEWS/autogempa.json"
_URL_RECENT = "https://data.bmkg.go.id/DataMKG/TEWS/gempaterkini.json"

_CACHE     = {}
_CACHE_TTL = 120  # 2 minutes


def _fmt_wib(dt):
    hari = _HARI[dt.weekday()]
    bln  = _BULAN[dt.month - 1]
    return f"{hari} {dt.day:02d} {bln} {dt.year} {dt.hour:02d}:{dt.minute:02d}"


def _fetch(url):
    now = time.time()
    if url in _CACHE:
        data, ts = _CACHE[url]
        if now - ts < _CACHE_TTL:
            return data
    req  = urllib.request.Request(url, headers={"User-Agent": "curl/7.88.1"})
    r    = urllib.request.urlopen(req, timeout=10)
    data = json.loads(r.read())
    _CACHE[url] = (data, now)
    return data


def _parse_bmkg_time(tgl, jam):
    try:
        jam_clean = jam.replace(" WIB", "").replace(" WITA", "").replace(" WIT", "").strip()
        dt = datetime.strptime(f"{tgl} {jam_clean}", "%d-%b-%y %H:%M:%S")
        return dt.replace(tzinfo=WIB)
    except Exception:
        return None


def _shake_emoji(mag):
    m = float(mag)
    if m >= 7.0: return "🔴"
    if m >= 6.0: return "🟠"
    if m >= 5.0: return "🟡"
    return "🟢"


def _haversine(lat1, lon1, lat2, lon2):
    R    = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    a    = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
            + math.cos(phi1) * math.cos(phi2)
            * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing_label(lat1, lon1, lat2, lon2):
    angle = math.degrees(math.atan2(lon2 - lon1, lat2 - lat1)) % 360
    dirs  = ["U", "TL", "T", "TG", "S", "BD", "B", "BL"]
    return dirs[round(angle / 45) % 8]


def get_gempa(message, message_from_id=None, deviceID=None, settings=None):
    try:
        latest_data = _fetch(_URL_LATEST)
    except Exception as e:
        logger.error("BMKG fetch error: %s", e)
        return "❌ Gagal mengambil data BMKG. Coba lagi nanti."

    g = latest_data.get("Infogempa", {}).get("gempa", {})
    if not g:
        return "❌ Data gempa tidak tersedia."

    mag       = g.get("Magnitude", "?")
    kedalaman = g.get("Kedalaman", "?")
    wilayah   = g.get("Wilayah", "?")
    potensi   = g.get("Potensi", "")
    dirasakan = g.get("Dirasakan", "")
    tgl       = g.get("Tanggal", "")
    jam       = g.get("Jam", "")
    lintang   = g.get("Lintang", "")
    bujur     = g.get("Bujur", "")
    koordinat = g.get("Coordinates", "")  # "lat,lon"

    dt        = _parse_bmkg_time(tgl, jam)
    waktu_str = _fmt_wib(dt) + " WIB" if dt else f"{tgl} {jam}"
    icon      = _shake_emoji(mag)

    lines = [
        f"🌍 Gempa Terakhir — BMKG",
        f"{icon} M{mag} — {wilayah}",
        f"⏱ {waktu_str}",
        f"📍 {lintang}, {bujur} | Kedalaman: {kedalaman}",
    ]
    if dirasakan:
        lines.append(f"💬 Dirasakan: {dirasakan}")
    if potensi:
        lines.append(f"⚠️ {potensi}")

    # ── Distance from caller ───────────────────────────────────────────────
    if message_from_id and deviceID and settings and koordinat:
        try:
            from modules.system import get_node_location
            loc      = get_node_location(message_from_id, deviceID)
            user_lat = loc[0]
            user_lon = loc[1]
            # detect fallback (no real GPS): position equals bot's configured position
            if not (user_lat == settings.latitudeValue and user_lon == settings.longitudeValue):
                parts   = koordinat.split(",")
                epi_lat = float(parts[0].strip())
                epi_lon = float(parts[1].strip())
                dist_km = _haversine(user_lat, user_lon, epi_lat, epi_lon)
                arah    = _bearing_label(user_lat, user_lon, epi_lat, epi_lon)
                lines.append(f"📏 Dari lokasimu: ~{dist_km:.0f} km arah {arah}")
        except Exception as ex:
            logger.debug("gempa distance error: %s", ex)

    lines.append("📡 bmkg.go.id")
    return "\n".join(lines)
