"""Flagship dashboard command — one compact snapshot combining gempa,
gunung, kurs, libur, and a rolling LongFast chat-activity summary. Built
only from modules that expose clean structured data (raw JSON / parsed
lists), not modules whose only public function returns pre-formatted
reply text — parsing formatted text a second time is fragile and breaks
silently if that module's wording changes. Weather (!cuaca) and fuel
prices (!hargabbm) are skipped for that reason: mesh_bot.py's
handle_wxc() and modules/bbm.py's get_bbm_prices() only return final
display text, no structured data to pull a single number from safely."""
import json
import logging
import re
import time

logger = logging.getLogger(__name__)

_LONGFAST_SUMMARY_CACHE = "/opt/meshing-around/data/longfast_hourly_summary.json"
_LONGFAST_SUMMARY_MAX_AGE = 3600  # if the hourly refresh timer stalls, stop showing stale chat


def get_ringkasan(message=None, message_from_id=None, deviceID=None):
    lines = ["📊 Ringkasan Hari Ini", ""]

    # ── Gempa ──────────────────────────────────────────────────────────────
    try:
        from modules.gempa import _fetch as _fetch_gempa, _URL_LATEST
        g = _fetch_gempa(_URL_LATEST).get("Infogempa", {}).get("gempa", {})
        if g:
            # BMKG's Wilayah field is a full sentence, e.g. "Pusat gempa
            # berada di laut 82 km tenggara Kota Sukabumi" — truncating that
            # at 35 chars for a one-line summary used to cut it right after
            # "laut" ("...at sea..."), which reads alarming out of context.
            # Strip the boilerplate preamble and just keep the location.
            wilayah = g.get("Wilayah", "?")
            wilayah = re.sub(r'^Pusat gempa berada di (laut|darat)\s*', '', wilayah)
            if len(wilayah) > 35:
                wilayah = wilayah[:35].rsplit(" ", 1)[0] + "..."
            lines.append(f"🌎 Gempa M{g.get('Magnitude','?')} {wilayah}")
    except Exception as e:
        logger.debug("ringkasan gempa error: %s", e)

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
        logger.debug("ringkasan gunung error: %s", e)

    # ── Kurs ───────────────────────────────────────────────────────────────
    try:
        from modules.kurs import _fetch as _fetch_kurs
        data = _fetch_kurs()
        rates = data.get("rates", {})
        idr_per_usd = rates.get("IDR")
        if idr_per_usd:
            lines.append(f"💵 USD Rp{idr_per_usd:,.0f}")
    except Exception as e:
        logger.debug("ringkasan kurs error: %s", e)

    # ── Libur ──────────────────────────────────────────────────────────────
    try:
        from modules.libur import get_libur
        libur_text = get_libur()
        # get_libur() returns a multi-line block; compress to one line
        parts = [p for p in libur_text.split("\n") if p.strip()]
        if len(parts) >= 3:
            when, name, rel = parts[-3], parts[-2], parts[-1]
            lines.append(f"📅 {rel} ke {when} ({name})")
    except Exception as e:
        logger.debug("ringkasan libur error: %s", e)

    # ── Obrolan LongFast ──────────────────────────────────────────────────
    # Pre-cached by scripts/summarize_longfast.py (systemd timer, every 15
    # min) rather than calling the LLM live here — keeps !ringkasan fast
    # and avoids re-summarizing the same hour's chat on every request.
    try:
        with open(_LONGFAST_SUMMARY_CACHE) as f:
            history = json.load(f).get("history", [])
        c = history[0] if history else None
        age = time.time() - c.get("generated_at", 0) if c else None
        if c and c.get("summary") and age < _LONGFAST_SUMMARY_MAX_AGE:
            lines.append(f"💬 Obrolan LongFast sejak jam {c['hour_label']}: {c['summary']}")
            lines.append("   Yuk gabung ngobrol! 👋")
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug("ringkasan longfast summary error: %s", e)

    if len(lines) <= 2:
        return "❌ Gagal mengambil data ringkasan. Coba lagi nanti."

    lines.append("")
    lines.append("Detail: !gempa !gunung !kursrupiah !libur")
    return "\n".join(lines)
