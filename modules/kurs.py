import urllib.request
import json
import time
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_API_URL = "https://open.er-api.com/v6/latest/USD"
_CACHE = None
_CACHE_TIME = 0
_CACHE_TTL = 3600  # 1 jam

WIB = timezone(timedelta(hours=7))

_HARI = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
_BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
          "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

_CURRENCIES = [
    ("USD", "Dolar AS"),
    ("EUR", "Euro"),
    ("SGD", "Dolar SG"),
    ("MYR", "Ringgit"),
    ("JPY", "Yen (100)"),
    ("SAR", "Riyal Saudi"),
    ("GBP", "Poundsterling"),
    ("AUD", "Dolar AU"),
    ("CNY", "Yuan"),
]


def _fmt_wib(dt):
    hari = _HARI[dt.weekday()]
    bln = _BULAN[dt.month - 1]
    return f"{hari} {dt.day:02d} {bln} {dt.year}"


def _fetch():
    global _CACHE, _CACHE_TIME
    now = time.time()
    if _CACHE and (now - _CACHE_TIME) < _CACHE_TTL:
        return _CACHE
    req = urllib.request.Request(_API_URL, headers={"User-Agent": "Mozilla/5.0"})
    r = urllib.request.urlopen(req, timeout=10)
    data = json.loads(r.read())
    _CACHE = data
    _CACHE_TIME = now
    return data


def get_kurs_rupiah(message):
    try:
        data = _fetch()
    except Exception as e:
        logger.error("Kurs fetch error: %s", e)
        return "❌ Gagal mengambil data kurs. Coba lagi nanti."

    rates_vs_usd = data.get("rates", {})
    idr_per_usd = rates_vs_usd.get("IDR", 1)

    # parse update time from API (Unix timestamp or string)
    ts = data.get("time_last_update_unix")
    if ts:
        dt = datetime.fromtimestamp(ts, tz=WIB)
        tgl = _fmt_wib(dt)
    else:
        tgl = _fmt_wib(datetime.now(WIB))

    lines = [f"💱 Kurs Rupiah ({tgl} WIB)"]
    for code, label in _CURRENCIES:
        if code not in rates_vs_usd:
            continue
        rate_vs_usd = rates_vs_usd[code]
        idr_per_unit = idr_per_usd / rate_vs_usd
        if code == "JPY":
            display = f"Rp {idr_per_unit * 100:,.0f}"
        else:
            display = f"Rp {idr_per_unit:,.0f}"
        lines.append(f"{code} ({label}): {display}")

    lines.append("📡 open.er-api.com")
    return "\n".join(lines)
