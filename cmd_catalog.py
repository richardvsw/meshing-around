"""Pure command catalog for !cmd — shared by mesh_bot.py and rivbot-ui.
No side effects, no radio/network imports. Safe to import from anywhere."""

CMDS = [
    # Utama
    ("!ringkasan",   "Ringkasan harian: gempa, gunung, kurs, libur 📊"),
    ("!ping",          "Bot masih hidup? Cek di sini 📡"),
    # Informasi
    ("!cuaca",         "Cuaca real-time di lokasimu ☀️🌧️"),
    ("!bencana",       "Ringkasan bencana: gempa, gunung, banjir 🚨"),
    ("!berita",        "Headline terkini: Tempo, CNN & BBC Indonesia 📰"),
    ("!libur",         "Libur nasional berikutnya + hitung mundur 📅"),
    # Ekonomi
    ("!hargabbm",      "Harga BBM hari ini per provinsi ⛽ — auto-detect lokasimu!"),
    ("!kursrupiah",    "Kurs Rupiah vs 9 mata uang dunia 💱"),
    # Utilitas
    ("!konversi",    "Konversi satuan: jarak, berat, suhu, dll"),
    ("!jarak",         "Tracking jarak tempuhmu — panggil lagi setelah bergerak 🚗"),
    ("!alarm HH:MM", "Set alarm, bot DM sampai kamu balas"),
    ("!morse",       "Encode/decode kode morse"),
    ("!ketinggian",    "Estimasi ketinggian dari panjang bayangan ⛰️"),
    # Astronomi
    ("!matahari",      "Terbit & terbenam + sisa siang hari ini 🌅"),
    ("!bulan",         "Fase bulan malam ini + countdown purnama 🌙"),
    ("!surya",         "Kondisi matahari & cuaca antariksa ☀️"),
    # Komunitas
    ("!siapa",         "Siapa kamu di mesh? ID, sinyal & lokasi 🧑‍💻"),
    ("!dimana",        "Di mana kamu? Bot balas + link Google Maps 📍"),
    ("!daftar",        "Siapa aja yang terdengar di mesh sekarang? 📡"),
    ("!peringkat",     "Node paling jauh, paling aktif — cek ranking 🏆"),
    ("!pesan",         "Motivasi & salam harian dari bot 💬"),
    # AI & pencarian
    ("!tanya <teks>",  "Tanya AI apa aja, dijawab via DM 🤖"),
    ("!wiki <kata>",   "Cari info di Wikipedia bahasa Indonesia 🔍 (alias: !cari)"),
    # Darurat
    ("!p3k",         "Panduan pertolongan pertama"),
    ("!darurat",     "Nomor kontak darurat nasional (112, SAR, polisi, dll) 🚨"),
    ("!pesawat [nomor]", "Pesawat terdekat, atau cari by nomor penerbangan ✈️"),
    # Lainnya
    ("!lelucon",       "Joke & tebak-tebakan acak 😀"),
    ("!fifa2026",      "Skor & jadwal FIFA 2026 ⚽ — live update tiap 2 menit!"),
]

# Grouped view for the no-arg !cmd reply — (emoji, category-only-for-humans,
# [command names in display order]). Kept separate from CMDS (which stays
# flat for the detail lookup / simulator) so regrouping the help screen
# never risks breaking !cmd <nama>.
CATEGORIES = [
    ("📊", ["ringkasan", "ping"]),
    ("🌤",  ["cuaca", "bencana", "berita", "libur"]),
    ("💰", ["hargabbm", "kursrupiah"]),
    ("🧭", ["konversi", "jarak", "alarm", "morse", "ketinggian"]),
    ("🌌", ["matahari", "bulan", "surya"]),
    ("👥", ["siapa", "dimana", "daftar", "peringkat", "pesan"]),
    ("🤖", ["tanya", "wiki"]),
    ("🏥", ["p3k", "darurat"]),
    ("✈️", ["pesawat"]),
    ("🎉", ["lelucon", "fifa2026"]),
]


# Old command names that now display under a different primary name in
# CMDS, kept resolvable here so "!cmd <old name>" still finds the entry.
_ALIASES = {"cari": "wiki"}


def handle_cmd_pure(message: str) -> str:
    """Same logic as mesh_bot.handle_cmd() but with no radio/network side effects."""
    words = message.strip().split()
    arg = words[1].lstrip("!").lower() if len(words) > 1 else ""
    arg = _ALIASES.get(arg, arg)
    if arg and not arg.isdigit():
        for cmd, desc in CMDS:
            bare = cmd.split()[0].lstrip("!").lower()
            if bare == arg:
                return f"{cmd} — {desc}"
        return f'🤖 Perintah "{arg}" tidak ditemukan. Ketik !cmd untuk lihat daftar.'

    lines = ["📋 Perintah"]
    for emoji, names in CATEGORIES:
        lines.append(f"{emoji} " + " ".join(f"!{n}" for n in names))
    lines.append("")
    lines.append("Detail: !cmd <nama>, misal !cmd cuaca")
    return "\n".join(lines)


def _mock_location():
    """The bot's own fixed lat/lon (set via the map's 'Set Bot Fixed
    Location'). This is what get_node_location() itself falls back to for
    any node without real GPS, so using it here is the same fallback the
    live bot already uses, not a fabrication.

    Deliberately NOT using modules.settings.latitudeValue/longitudeValue:
    that module reads config.ini via a relative path ("config.ini"), which
    resolves fine when the real bot runs with CWD=/opt/meshing-around, but
    silently falls back to a bogus default (San Juan, WA) when imported
    from rivbot-ui's process, which has a different working directory.
    Parsing the same [location] section with an absolute path here avoids
    that trap without needing to touch the process's global CWD."""
    import configparser
    cfg = configparser.ConfigParser()
    cfg.read("/opt/meshing-around/config.ini", encoding="utf-8")
    lat = cfg.getfloat("location", "lat", fallback=48.50)
    lon = cfg.getfloat("location", "lon", fallback=-123.0)
    return lat, lon


# ── Simulatable commands ─────────────────────────────────────────────────
# Commands whose real handler is reachable without importing mesh_bot.py or
# modules/system.py — modules/system.py opens a live TCP connection to
# meshtasticd at IMPORT time (not inside a function), so anything that
# touches it, even transitively for a rate limiter or node-location lookup,
# can't be safely dry-run: importing it from this separate process would
# attempt a second connection and can disrupt the live mesh_bot service
# (single-client TCP). Commands defined *inside* mesh_bot.py itself (not a
# standalone module) hit the same problem just by being imported, even if
# the specific function body is otherwise harmless — so those are
# reimplemented here directly against their underlying data functions
# instead of calling mesh_bot.py's wrapper, using _mock_location() wherever
# the real command would use the caller's GPS.
#
# Still excluded: !ping/!siapa (need hop/SNR/RSSI from a real received
# packet), !daftar/!peringkat (need the live in-memory seenNodes/leaderboard
# state), !jarak (needs a *previous* stored location to diff against —
# meaningless as a single stateless simulator call), !alarm (schedules a
# real future DM — a side effect, not a dry-run), !tanya (LLM call routed
# through the live bot's DM plumbing), !berita (rss.py's api_throttle import
# chain), !matahari/!surya (need the `ephem` package — installed in the
# bot's own venv but out of scope to add here for a solar-position calc).
SIMULATABLE = {
    "fifa2026", "konversi", "kursrupiah", "morse", "p3k", "libur", "gunung",
    "cari", "wiki", "ringkasan", "cuaca", "hargabbm", "dimana", "pesan",
    "lelucon", "joke", "humor", "darurat", "pesawat", "banjir", "bencana",
}


def simulate_command(text: str):
    """Returns (ok, reply_or_error) for a dry-run of a supported command.
    Only commands in SIMULATABLE are attempted; see the comment above for why
    the rest are excluded."""
    word = text.strip().split()[0].lstrip("!").lower() if text.strip() else ""

    if word == "cmd":
        return True, handle_cmd_pure(text)

    if word not in SIMULATABLE:
        return False, (
            f'Simulator doesn\'t support "!{word}" — either it needs live '
            f'radio/node data (position, signal, hop info) that only exists on '
            f'a real received packet, or its module has a dependency that isn\'t '
            f'installed in this process, so it can\'t be dry-run safely from here. '
            f'Supported: !cmd, '
            + ", ".join(f"!{w}" for w in sorted(SIMULATABLE))
        )

    try:
        if word == "fifa2026":
            from modules.fifa import get_fifa2026
            return True, get_fifa2026(text)
        if word == "konversi":
            from modules.konversi import get_konversi
            return True, get_konversi(text)
        if word == "kursrupiah":
            from modules.kurs import get_kurs_rupiah
            return True, get_kurs_rupiah(text)
        if word == "morse":
            from modules.morse import get_morse
            return True, get_morse(text)
        if word == "p3k":
            from modules.p3k import get_p3k
            return True, get_p3k(text)
        if word == "darurat":
            from modules.darurat import get_darurat
            lat, lon = _mock_location()
            return True, get_darurat(text, lat, lon, gps_available=True)
        if word == "pesawat":
            from modules.pesawat import get_pesawat
            lat, lon = _mock_location()
            return True, get_pesawat(text, lat, lon, gps_available=True)
        if word == "banjir":
            from modules.banjir import get_banjir
            lat, lon = _mock_location()
            return True, get_banjir(text, lat, lon, gps_available=True)
        if word == "bencana":
            from modules.bencana import get_bencana
            return True, get_bencana(text)
        if word == "libur":
            from modules.libur import get_libur
            return True, get_libur(text)
        if word == "gunung":
            from modules.gunung import get_gunung
            return True, get_gunung(text)
        if word in ("cari", "wiki"):
            from modules.wiki import get_wikipedia_summary
            parts = text.strip().split(None, 1)
            query = parts[1].strip() if len(parts) > 1 else ""
            if not query:
                return True, "Ketik kata yang mau dicari. Contoh: !cari gunung krakatau"
            return True, get_wikipedia_summary(query)
        if word == "ringkasan":
            from modules.ringkasan import get_ringkasan
            return True, get_ringkasan(text)

        if word == "cuaca":
            from modules.wx_meteo import get_wx_meteo
            lat, lon = _mock_location()
            return True, get_wx_meteo(str(lat), str(lon))

        if word == "hargabbm":
            from modules.bbm import get_bbm_prices
            parts = text.strip().split(None, 1)
            if len(parts) > 1 and parts[1].strip():
                # explicit province — bbm.py's own code path never touches
                # modules.system for this case, so just call it directly
                return True, get_bbm_prices(text)
            # no province given — reverse-geocode the bot's mock location to
            # a province ourselves (same approach bbm.py's own auto-detect
            # takes, minus the get_node_location() call it would need)
            from geopy.geocoders import Nominatim
            lat, lon = _mock_location()
            geolocator = Nominatim(user_agent="meshbot_bbm_sim/1.0")
            geo = geolocator.reverse(f"{lat},{lon}", language="id", timeout=10)
            addr = geo.raw.get("address", {}) if geo else {}
            state = addr.get("state", "")
            if not state:
                return True, "❌ Tidak bisa deteksi provinsi dari lokasi bot. Coba: !hargabbm jawa barat"
            return True, get_bbm_prices(f"!hargabbm {state}")

        if word == "dimana":
            from geopy.geocoders import Nominatim
            import maidenhead as mh
            lat, lon = _mock_location()
            geolocator = Nominatim(user_agent="mesh-bot-sim")
            loc = geolocator.reverse(f"{lat}, {lon}")
            addr = loc.raw.get("address", {}) if loc else {}
            parts = []
            road = addr.get("road") or addr.get("pedestrian") or addr.get("footway", "")
            village = addr.get("village") or addr.get("suburb") or addr.get("neighbourhood", "")
            city = addr.get("city") or addr.get("town") or addr.get("regency", "")
            county = addr.get("county", "")
            state = addr.get("state", "")
            if road:    parts.append(road)
            if village: parts.append(village)
            if city:    parts.append(city)
            elif county: parts.append(county)
            if state:   parts.append(state)
            area = ", ".join(filter(None, parts)) or (loc.address if loc else "?")
            grid = mh.to_maiden(float(lat), float(lon))
            gmaps = f"https://maps.google.com/?q={lat},{lon}"
            return True, f"📍 {area}\n🌐 Grid: {grid}\n🗺️ {gmaps}"

        if word == "pesan":
            import importlib.util
            from datetime import datetime, timezone, timedelta
            wib = datetime.now(timezone(timedelta(hours=7)))
            hour, doy = wib.hour, wib.timetuple().tm_yday
            if 5 <= hour < 11:    salam, bank_key = "Selamat pagi", "MOTIVASI_PAGI"
            elif 11 <= hour < 15: salam, bank_key = "Selamat siang", "MOTIVASI_SIANG"
            elif 15 <= hour < 18: salam, bank_key = "Selamat sore", "MOTIVASI_SORE"
            else:                 salam, bank_key = "Selamat malam", "MOTIVASI_MALAM"
            spec = importlib.util.spec_from_file_location(
                "greeting_banks", "/opt/meshing-around/data/greeting_banks.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            bank = getattr(mod, bank_key, [])
            daily_msg = bank[doy % len(bank)] if bank else "(pesan default)"
            return True, f"{salam}! {daily_msg}"

        if word in ("lelucon", "joke", "humor"):
            from modules.games.joke import tell_joke
            return True, tell_joke()
    except Exception as e:
        return False, f"Simulated command raised an error: {e}"

    return False, "Unhandled command"
