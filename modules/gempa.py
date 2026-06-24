import urllib.request
import json
import time
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))

_HARI = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
_BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
          "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

_URL_LATEST = "https://data.bmkg.go.id/DataMKG/TEWS/autogempa.json"
_URL_RECENT = "https://data.bmkg.go.id/DataMKG/TEWS/gempaterkini.json"

_CACHE = {}
_CACHE_TTL = 120  # 2 minutes


def _fmt_wib(dt):
    hari = _HARI[dt.weekday()]
    bln = _BULAN[dt.month - 1]
    return f"{hari} {dt.day:02d} {bln} {dt.year} {dt.hour:02d}:{dt.minute:02d}"


def _fetch(url):
    now = time.time()
    if url in _CACHE:
        data, ts = _CACHE[url]
        if now - ts < _CACHE_TTL:
            return data
    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.88.1"})
    r = urllib.request.urlopen(req, timeout=10)
    data = json.loads(r.read())
    _CACHE[url] = (data, now)
    return data


def _parse_bmkg_time(tgl, jam):
    """Parse BMKG date/time strings like '24-Jun-25' and '01:23:45 WIB'."""
    try:
        jam_clean = jam.replace(" WIB", "").replace(" WITA", "").replace(" WIT", "").strip()
        dt_str = f"{tgl} {jam_clean}"
        dt = datetime.strptime(dt_str, "%d-%b-%y %H:%M:%S")
        return dt.replace(tzinfo=WIB)
    except Exception:
        return None


def _shake_emoji(mag):
    m = float(mag)
    if m >= 7.0:
        return "🔴"
    elif m >= 6.0:
        return "🟠"
    elif m >= 5.0:
        return "🟡"
    else:
        return "🟢"


def get_gempa(message):
    try:
        latest_data = _fetch(_URL_LATEST)
    except Exception as e:
        logger.error("BMKG fetch error: %s", e)
        return "❌ Gagal mengambil data BMKG. Coba lagi nanti."

    g = latest_data.get("Infogempa", {}).get("gempa", {})
    if not g:
        return "❌ Data gempa tidak tersedia."

    mag = g.get("Magnitude", "?")
    kedalaman = g.get("Kedalaman", "?")
    wilayah = g.get("Wilayah", "?")
    potensi = g.get("Potensi", "")
    dirasakan = g.get("Dirasakan", "")
    tgl = g.get("Tanggal", "")
    jam = g.get("Jam", "")
    koordinat = g.get("Coordinates", "")
    lintang = g.get("Lintang", "")
    bujur = g.get("Bujur", "")

    dt = _parse_bmkg_time(tgl, jam)
    waktu_str = _fmt_wib(dt) + " WIB" if dt else f"{tgl} {jam}"

    icon = _shake_emoji(mag)

    lines = [f"🌍 Gempa Terakhir — BMKG"]
    lines.append(f"{icon} M{mag} — {wilayah}")
    lines.append(f"⏱ {waktu_str}")
    lines.append(f"📍 {lintang}, {bujur} | Kedalaman: {kedalaman}")
    if dirasakan:
        lines.append(f"💬 Dirasakan: {dirasakan}")
    if potensi:
        lines.append(f"⚠️ {potensi}")
    lines.append("📡 bmkg.go.id")

    return "\n".join(lines)
