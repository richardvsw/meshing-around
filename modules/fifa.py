import urllib.request
import json
import time
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
_CACHE = {}
_CACHE_TTL_LIVE = 120
_CACHE_TTL_STATIC = 1800

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


def _flag(iso2):
    """Convert ISO 3166-1 alpha-2 code to flag emoji."""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso2.upper())


# ESPN abbr -> (display name, ISO 3166-1 alpha-2)
_TEAMS = {
    "ALG": ("Aljazair",        "DZ"),
    "ARG": ("Argentina",       "AR"),
    "AUS": ("Australia",       "AU"),
    "AUT": ("Austria",         "AT"),
    "BEL": ("Belgia",          "BE"),
    "BIH": ("Bosnia-Herz.",    "BA"),
    "BRA": ("Brasil",          "BR"),
    "CAN": ("Kanada",          "CA"),
    "CIV": ("Pantai Gading",   "CI"),
    "COD": ("Kongo DR",        "CD"),
    "COL": ("Kolombia",        "CO"),
    "CPV": ("Tanjung Verde",   "CV"),
    "CRO": ("Kroasia",         "HR"),
    "CUW": ("Curaçao",         "CW"),
    "CZE": ("Ceko",            "CZ"),
    "ECU": ("Ekuador",         "EC"),
    "EGY": ("Mesir",           "EG"),
    "ENG": ("Inggris",         "GB"),
    "ESP": ("Spanyol",         "ES"),
    "FRA": ("Prancis",         "FR"),
    "GER": ("Jerman",          "DE"),
    "GHA": ("Ghana",           "GH"),
    "HAI": ("Haiti",           "HT"),
    "IRN": ("Iran",            "IR"),
    "IRQ": ("Irak",            "IQ"),
    "JOR": ("Jordania",        "JO"),
    "JPN": ("Jepang",          "JP"),
    "KOR": ("Korea Selatan",   "KR"),
    "KSA": ("Arab Saudi",      "SA"),
    "MAR": ("Maroko",          "MA"),
    "MEX": ("Meksiko",         "MX"),
    "NED": ("Belanda",         "NL"),
    "NOR": ("Norwegia",        "NO"),
    "NZL": ("Selandia Baru",   "NZ"),
    "PAN": ("Panama",          "PA"),
    "PAR": ("Paraguay",        "PY"),
    "POR": ("Portugal",        "PT"),
    "QAT": ("Qatar",           "QA"),
    "RSA": ("Afrika Selatan",  "ZA"),
    "SCO": ("Skotlandia",      "GB"),
    "SEN": ("Senegal",         "SN"),
    "SUI": ("Swiss",           "CH"),
    "SWE": ("Swedia",          "SE"),
    "TUN": ("Tunisia",         "TN"),
    "TUR": ("Türkiye",         "TR"),
    "URU": ("Uruguay",         "UY"),
    "USA": ("Amerika Serikat", "US"),
    "UZB": ("Uzbekistan",      "UZ"),
}


def _team_label(abbr):
    """Return 'FLAG Nama' for a team abbreviation."""
    if abbr in _TEAMS:
        name, iso2 = _TEAMS[abbr]
        return f"{_flag(iso2)} {name}"
    return abbr


def _fetch_date(date_str):
    cached = _CACHE.get(date_str)
    now = time.time()
    if cached:
        data, fetch_time = cached
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


def _get_teams(comps):
    teams = {t["homeAway"]: t for t in comps.get("competitors", [])}
    return teams.get("home", {}), teams.get("away", {})


def _format_event(e):
    comps = e.get("competitions", [{}])[0]
    home, away = _get_teams(comps)

    ha = home.get("team", {}).get("abbreviation", "?")
    aa = away.get("team", {}).get("abbreviation", "?")
    hl = _team_label(ha)
    al = _team_label(aa)
    score_h = home.get("score", "")
    score_a = away.get("score", "")

    status_type = e.get("status", {}).get("type", {})
    status_name = status_type.get("name", "")
    clock = e.get("status", {}).get("displayClock", "")

    dt = datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(WIB)
    jam = _fmt_wib(dt)
    group = comps.get("altGameNote", "").replace("FIFA World Cup, ", "")

    if status_name == "STATUS_SCHEDULED":
        return f"{jam} WIB | {hl} vs {al} ({group})"
    elif status_name in _DONE_STATUSES:
        return f"{hl} {score_h}–{score_a} {al}  ({group})"
    elif status_name in _LIVE_STATUSES:
        label = _STATUS_MAP.get(status_name, "Live")
        return f"🔴 {hl} {score_h}–{score_a} {al} [{clock}]  ({group})"
    else:
        label = _STATUS_MAP.get(status_name, status_type.get("description", ""))
        return f"{jam} WIB | {hl} {score_h}–{score_a} {al} [{label}]  ({group})"


def _yesterday_summary(events):
    """One-line summary of yesterday's results."""
    done = [e for e in events
            if e.get("status", {}).get("type", {}).get("name") in _DONE_STATUSES]
    if not done:
        return None

    lines = ["📋 Hasil kemarin:"]
    for e in done:
        comps = e.get("competitions", [{}])[0]
        home, away = _get_teams(comps)
        ha = home.get("team", {}).get("abbreviation", "?")
        aa = away.get("team", {}).get("abbreviation", "?")
        score_h = home.get("score", "")
        score_a = away.get("score", "")
        group = comps.get("altGameNote", "").replace("FIFA World Cup, ", "")
        hl = _team_label(ha)
        al = _team_label(aa)
        lines.append(f"  {hl} {score_h}–{score_a} {al}  ({group})")
    return "\n".join(lines)


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

    today_events = data_today.get("events", [])
    yesterday_events = data_yesterday.get("events", [])

    tgl = f"{now.day:02d}/{now.month:02d}"
    sections = [f"⚽ FIFA World Cup 2026 — {tgl}"]

    # Yesterday summary
    summary = _yesterday_summary(yesterday_events)
    if summary:
        sections.append(summary)

    # Today: categorise
    live, done, upcoming = [], [], []
    for e in today_events:
        sn = e.get("status", {}).get("type", {}).get("name", "")
        if sn in _LIVE_STATUSES:
            live.append(e)
        elif sn in _DONE_STATUSES:
            done.append(e)
        else:
            upcoming.append(e)

    if live:
        sections.append("🔴 LIVE:")
        for e in live:
            sections.append("  " + _format_event(e))

    if done:
        sections.append("✅ Selesai hari ini:")
        for e in done:
            sections.append("  " + _format_event(e))

    if upcoming:
        sections.append("🕐 Jadwal hari ini:")
        for e in upcoming:
            sections.append("  " + _format_event(e))

    if not (live or done or upcoming):
        sections.append("Tidak ada pertandingan hari ini.")

    sections.append("📡 espn.com")
    return "\n".join(sections)
