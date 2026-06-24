import urllib.request
import json
import time
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
_CACHE = {}       # date_str -> (data, fetch_time)
_CACHE_TTL_LIVE = 120    # 2 menit saat ada pertandingan live
_CACHE_TTL_STATIC = 1800  # 30 menit untuk data lama

WIB = timezone(timedelta(hours=7))

_HARI = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
_BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
          "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

_STATUS_MAP = {
    "STATUS_SCHEDULED":   "Belum main",
    "STATUS_IN_PROGRESS": "Sedang main",
    "STATUS_HALFTIME":    "Babak turun",
    "STATUS_FINAL":       "Selesai",
    "STATUS_FULL_TIME":   "Selesai",
    "STATUS_END_PERIOD":  "Akhir babak",
    "STATUS_OVERTIME":    "Perpanjangan",
    "STATUS_SHOOTOUT":    "Adu penalti",
}

_LIVE_STATUSES = {
    "STATUS_IN_PROGRESS", "STATUS_HALFTIME",
    "STATUS_END_PERIOD", "STATUS_OVERTIME", "STATUS_SHOOTOUT",
}
_DONE_STATUSES = {"STATUS_FINAL", "STATUS_FULL_TIME"}


def _fetch_date(date_str):
    """Fetch events for a YYYYMMDD date string, with per-date caching."""
    cached = _CACHE.get(date_str)
    now = time.time()
    if cached:
        data, fetch_time = cached
        # use shorter TTL if any event was live
        has_live = any(
            e.get("status", {}).get("type", {}).get("name") in _LIVE_STATUSES
            for e in data.get("events", [])
        )
        ttl = _CACHE_TTL_LIVE if has_live else _CACHE_TTL_STATIC
        if (now - fetch_time) < ttl:
            return data

    url = f"{_BASE_URL}?dates={date_str}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    r = urllib.request.urlopen(req, timeout=10)
    data = json.loads(r.read())
    _CACHE[date_str] = (data, now)
    return data


def _fmt_wib(dt):
    hari = _HARI[dt.weekday()]
    bln = _BULAN[dt.month - 1]
    return f"{hari} {dt.day:02d} {bln} {dt.hour:02d}:{dt.minute:02d}"


def _format_event(e):
    comps = e.get("competitions", [{}])[0]
    teams = {t["homeAway"]: t for t in comps.get("competitors", [])}
    home = teams.get("home", {})
    away = teams.get("away", {})

    hn = home.get("team", {}).get("abbreviation", "?")
    an = away.get("team", {}).get("abbreviation", "?")
    score_h = home.get("score", "")
    score_a = away.get("score", "")

    status_type = e.get("status", {}).get("type", {})
    status_name = status_type.get("name", "")
    clock = e.get("status", {}).get("displayClock", "")

    dt = datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(WIB)
    jam = _fmt_wib(dt)

    group = comps.get("altGameNote", "").replace("FIFA World Cup, ", "")

    if status_name == "STATUS_SCHEDULED":
        return f"{jam} WIB | {hn} vs {an} | {group}"
    elif status_name in _DONE_STATUSES:
        if home.get("winner"):
            skor = f"**{score_h}**-{score_a}"
        elif away.get("winner"):
            skor = f"{score_h}-**{score_a}**"
        else:
            skor = f"{score_h}-{score_a}"
        return f"{hn} {score_h}-{score_a} {an} | {group}"
    elif status_name in _LIVE_STATUSES:
        label = _STATUS_MAP.get(status_name, "Live")
        return f"🔴 {hn} {score_h}-{score_a} {an} ({clock}) | {group}"
    else:
        label = _STATUS_MAP.get(status_name, status_type.get("description", ""))
        return f"{jam} WIB | {hn} {score_h}-{score_a} {an} [{label}] | {group}"


def get_fifa2026(message):
    now = datetime.now(WIB)
    today_str = now.strftime("%Y%m%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y%m%d")

    try:
        data_today = _fetch_date(today_str)
        data_yesterday = _fetch_date(yesterday_str)
    except Exception as e:
        logger.error("FIFA fetch error: %s", e)
        return "❌ Gagal mengambil data FIFA 2026. Coba lagi nanti."

    all_events = data_yesterday.get("events", []) + data_today.get("events", [])
    if not all_events:
        return "⚽ Tidak ada pertandingan FIFA 2026 dalam 24 jam terakhir."

    tgl = f"{now.day:02d}/{now.month:02d}"
    lines = [f"⚽ FIFA World Cup 2026 — {tgl}"]

    live, done, upcoming = [], [], []
    for e in all_events:
        status_name = e.get("status", {}).get("type", {}).get("name", "")
        if status_name in _LIVE_STATUSES:
            live.append(e)
        elif status_name in _DONE_STATUSES:
            done.append(e)
        else:
            upcoming.append(e)

    if live:
        lines.append("🔴 LIVE:")
        for e in live:
            lines.append("  " + _format_event(e))

    if done:
        lines.append("✅ Hasil:")
        for e in done:
            lines.append("  " + _format_event(e))

    if upcoming:
        lines.append("🕐 Jadwal:")
        for e in upcoming:
            lines.append("  " + _format_event(e))

    lines.append("📡 espn.com")
    return "\n".join(lines)
