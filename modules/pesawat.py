# -*- coding: utf-8 -*-
"""
!pesawat            — pesawat terdekat dari lokasimu (radius ~80km)
!pesawat <nomor>     — cari pesawat spesifik by callsign/nomor penerbangan

Data live dari OpenSky Network (state vectors, gratis tanpa auth). Dibatasi
ke wilayah Indonesia + sekitarnya (bukan global) — lingkup regional cukup
untuk kebutuhan mesh network ini dan jauh lebih ringan per-request.
"""
import math
import time

try:
    import requests
except ImportError:
    requests = None

from modules.log import logger

_STATES_URL = "https://opensky-network.org/api/states/all"
_HEADERS = {"User-Agent": "RiV-Bot-Meshtastic/1.0 (Indonesian mesh network flight lookup)"}

# Indonesia + immediate neighbors — covers virtually all domestic and
# regional inbound/outbound traffic without pulling a full global payload.
_REGION_BBOX = {"lamin": -15, "lamax": 10, "lomin": 90, "lomax": 145}

_SEARCH_RADIUS_KM = 80
_CACHE_TTL_SECONDS = 20  # shares one fetch across near-simultaneous queries

_OPERATOR_PREFIXES = {
    "GIA": "Garuda Indonesia", "LNI": "Lion Air", "BTK": "Batik Air",
    "CTV": "Citilink", "SJY": "Sriwijaya Air", "AWQ": "AirAsia Indonesia",
    "IWW": "Wings Air", "SCO": "Nam Air", "TGW": "Trigana Air",
    "AXM": "AirAsia", "SIA": "Singapore Airlines", "MAS": "Malaysia Airlines",
    "CPA": "Cathay Pacific", "QFA": "Qantas", "UAE": "Emirates",
}

_cache = {"ts": 0, "states": None}


def _fetch_region_states():
    now = time.time()
    if _cache["states"] is not None and (now - _cache["ts"]) < _CACHE_TTL_SECONDS:
        return _cache["states"]

    from modules.cache_status import record_status
    try:
        resp = requests.get(_STATES_URL, params=_REGION_BBOX, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        states = resp.json().get("states") or []
        _cache["states"] = states
        _cache["ts"] = now
        record_status("pesawat", ok=True, extra={"aircraft_count": len(states)})
        return states
    except Exception as e:
        record_status("pesawat", ok=False, error=e)
        raise


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlambda)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _compass_id(deg):
    # arrow + full Indonesian word — a bare abbreviation (e.g. "TL") isn't
    # obviously a direction to someone unfamiliar with the convention.
    dirs = [
        "⬆️ Utara", "↗️ Timur Laut", "➡️ Timur", "↘️ Tenggara",
        "⬇️ Selatan", "↙️ Barat Daya", "⬅️ Barat", "↖️ Barat Laut",
    ]
    return dirs[round(deg / 45) % 8]


def _operator_name(callsign):
    prefix = callsign[:3].upper()
    return _OPERATOR_PREFIXES.get(prefix)


def _format_state(state, lat=None, lon=None):
    callsign = (state[1] or "").strip() or "(tanpa callsign)"
    slon, slat = state[5], state[6]
    alt_m = state[7] or state[13]
    velocity_ms = state[9]
    heading = state[10]

    op = _operator_name(callsign)
    label = f"{callsign} ({op})" if op else callsign

    parts = [f"🛫 {label}"]
    details = []
    if alt_m is not None:
        details.append(f"{alt_m:,.0f}m".replace(",", "."))
    if velocity_ms is not None:
        details.append(f"{velocity_ms * 3.6:.0f} km/h")
    if heading is not None:
        details.append(f"{heading:.0f}° ({_compass_id(heading)})")
    if details:
        parts.append(" | ".join(details))

    if lat is not None and lon is not None and slat is not None and slon is not None:
        dist = _haversine_km(lat, lon, slat, slon)
        brg = _bearing_deg(lat, lon, slat, slon)
        parts.append(f"~{dist:.0f} km {_compass_id(brg)} dari kamu")

    return "\n".join(parts)


def _nearest_flights(lat, lon):
    states = _fetch_region_states()
    candidates = []
    for s in states:
        if s[6] is None or s[5] is None or s[8]:  # no position, or on_ground
            continue
        dist = _haversine_km(lat, lon, s[6], s[5])
        if dist <= _SEARCH_RADIUS_KM:
            candidates.append((dist, s))
    candidates.sort(key=lambda x: x[0])
    return [s for _, s in candidates[:3]]


def _find_by_callsign(query):
    states = _fetch_region_states()
    q = query.strip().upper()
    for s in states:
        callsign = (s[1] or "").strip().upper()
        if callsign == q or callsign.startswith(q):
            return s
    return None


def get_pesawat(message=None, lat=None, lon=None, gps_available=True):
    if requests is None:
        return "✈️ Fitur pesawat lagi gak tersedia (dependency belum siap)."

    words = (message or "").strip().split(None, 1)
    query = words[1].strip() if len(words) > 1 else ""

    try:
        if query:
            state = _find_by_callsign(query)
            if not state:
                return f'✈️ Pesawat "{query}" gak kedeteksi saat ini.'
            return _format_state(state, lat, lon)

        if lat is None or lon is None:
            return "✈️ Lokasi kamu ga ketahuan — coba lagi nanti atau sebutkan nomor penerbangan: !pesawat <nomor>"
        if not gps_available:
            return "📍 GPS kamu belum aktif — nyalakan GPS di node lalu !pesawat lagi, atau sebutkan nomor penerbangan: !pesawat <nomor>"

        flights = _nearest_flights(lat, lon)
        if not flights:
            return f"✈️ Gak ada pesawat kedeteksi dlm radius {_SEARCH_RADIUS_KM}km saat ini."
        return f"✈️ Pesawat Terdekat (radius {_SEARCH_RADIUS_KM}km)\n" + "\n".join(
            _format_state(s, lat, lon) for s in flights
        )
    except Exception as e:
        logger.warning(f"System: pesawat lookup failed: {e}")
        return "✈️ Gagal ambil data pesawat, coba lagi bentar lagi ya."
