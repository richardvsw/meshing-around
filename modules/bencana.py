# -*- coding: utf-8 -*-
"""
!bencana — ringkasan bencana: gempa, gunung, dan banjir dalam satu balasan.
!gempa, !gunung, !banjir masih berfungsi penuh (bisa dipanggil langsung),
cuma disembunyikan dari !cmd supaya daftar perintah gak terlalu panjang —
!bencana adalah entry point utama untuk info bencana.

Same "structured data only, no re-parsing formatted text" principle as
ringkasan.py, except for the banjir section — get_banjir()'s underlying
Open-Meteo flood call has no separate structured accessor (same reasoning
ringkasan.py's docstring gives for skipping !cuaca/!hargabbm), so this
does the same one-line "compress formatted text" extraction ringkasan.py
already does for !libur.
"""
import logging

logger = logging.getLogger(__name__)


def get_bencana(message=None, message_from_id=None, deviceID=None):
    lines = ["🚨 Ringkasan Bencana", ""]

    # ── Gempa ──────────────────────────────────────────────────────────────
    try:
        from modules.gempa import _fetch as _fetch_gempa, _URL_LATEST
        g = _fetch_gempa(_URL_LATEST).get("Infogempa", {}).get("gempa", {})
        if g:
            wilayah = g.get("Wilayah", "?")
            if len(wilayah) > 35:
                wilayah = wilayah[:35].rsplit(" ", 1)[0] + "..."
            lines.append(f"🌎 Gempa M{g.get('Magnitude','?')} {wilayah}")
    except Exception as e:
        logger.debug("bencana gempa error: %s", e)

    # ── Gunung ─────────────────────────────────────────────────────────────
    try:
        from modules.gunung import _fetch_list
        volcanoes = _fetch_list()
        if volcanoes:
            max_level = max(v["level"] for v in volcanoes)
            if max_level >= 2:
                label = {4: "AWAS", 3: "SIAGA", 2: "WASPADA"}[max_level]
                count = sum(1 for v in volcanoes if v["level"] == max_level)
                lines.append(f"🌋 {count} gunung {label}")
    except Exception as e:
        logger.debug("bencana gunung error: %s", e)

    # ── Banjir (needs GPS) ────────────────────────────────────────────────
    try:
        if message_from_id is not None:
            from modules.system import get_node_location
            import modules.settings as my_settings
            loc = get_node_location(message_from_id, deviceID)
            if not (loc[0] == my_settings.latitudeValue and loc[1] == my_settings.longitudeValue):
                from modules.banjir import get_banjir
                banjir_text = get_banjir(None, loc[0], loc[1], gps_available=True)
                for line in banjir_text.split("\n"):
                    if line.startswith("Hari ini:"):
                        lines.append(f"🌊 Debit sungai {line.replace('Hari ini: ', '')}")
                        break
    except Exception as e:
        logger.debug("bencana banjir error: %s", e)

    if len(lines) <= 2:
        return "❌ Gagal mengambil data bencana. Coba lagi nanti."

    lines.append("")
    lines.append("Detail: !gempa !gunung !banjir")
    return "\n".join(lines)
