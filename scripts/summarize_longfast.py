#!/usr/bin/env python3
"""Hourly LongFast chat summary, feeding !ringkasan's 'obrolan' section
(see modules/ringkasan.py) and the Stats page's LongFast history card.

Run via a systemd timer every 15 minutes (see summarize-longfast.timer),
but each COMPLETED hour is only ever summarized once: an entry labeled
"22:00" covers the full 21:00–22:00 window (message range), generated
shortly after 22:00 ticks over. The 15-min cadence is just how often we
check "has the hour that just ended been summarized yet" — not how often
a given hour gets re-summarized.

Reads the transcript from rivbot-ui's existing /api/channels/LongFast/
messages endpoint (mqtt_tap.py already decrypts and logs all LongFast
channel traffic there, not just bot interactions) rather than opening a
second connection to meshtasticd — same reasoning cmd_catalog.py's
simulator uses for staying out of mesh_bot's single-client TCP connection.
"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/opt/meshing-around")

WIB = timezone(timedelta(hours=7))
CACHE_FILE = "/opt/meshing-around/data/longfast_hourly_summary.json"
FEED_URL = "http://localhost:8080/api/channels/LongFast/messages"
MIN_MESSAGES = 3    # skip the LLM call if LongFast has been too quiet to summarize meaningfully
MIN_FOR_ACTIVE_NODE = 6   # below this, "most active node" is noise — one extra message wins it
GREETING_RATIO_FOR_DIGEST = 0.7   # this fraction of messages being bare greetings -> skip the LLM, one-liner instead
GREETING_RE = re.compile(r"^(selamat\s+)?(pagi|siang|sore|malam)\b", re.IGNORECASE)
# modules.llm.send_openwebui_query's own generic failure message (timeout,
# connection error, or rate-limit) — indistinguishable from a real reply
# by type, so it has to be matched by exact string to avoid caching it as
# if it were an actual summary.
_LLM_ERROR_SENTINEL = "⛔️ Aduh, gagal konek ke AI-nya bro. Coba lagi bentar!"
# Hard safety ceiling only — actual retention is the user-configurable
# longfast_days setting on rivbot-ui's Retention page (routes/retention.py
# there prunes this file by age). This just stops unbounded growth if that
# pruning ever fails to run; ~35 days of hourly entries is comfortably
# above any sane retention setting.
MAX_HISTORY = 24 * 35


def _load_history():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f).get("history", [])
    except Exception:
        return []


def _write_cache(history, entry):
    # Replace any existing entry for this (date, hour_label) rather than
    # appending a duplicate — shouldn't normally happen since main() skips
    # already-summarized hours, but keeps this function safe to call twice.
    key = (entry["date"], entry["hour_label"])
    history = [h for h in history if (h.get("date"), h.get("hour_label")) != key]
    history.insert(0, entry)
    history = history[:MAX_HISTORY]

    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump({"history": history}, f)


def _is_bare_greeting(text):
    stripped = text.strip()
    # Prefix match alone false-positives on real messages that happen to
    # open with a greeting word ("Pagi ini saya mau tanya soal antena...")
    # — require the whole message to be short too, so it's actually just
    # the greeting, not a real message that starts with one.
    return bool(GREETING_RE.match(stripped)) and len(stripped.split()) <= 4


def process_hour(hour_end, history, force=False):
    """Summarizes the hour ENDING at hour_end (so hour_end=22:00 covers
    21:00-22:00), writes/overwrites its entry in history, and returns the
    updated history list. force=True re-summarizes even if this hour
    already has an entry — used by the CLI --redo-since backfill mode;
    the normal timer-triggered run never needs it, since it only ever
    processes the hour that just completed."""
    hour_start = hour_end - timedelta(hours=1)
    date_label = hour_end.strftime("%Y-%m-%d")
    hour_label = hour_end.strftime("%H:%M")
    range_label = f"{hour_start.strftime('%H:%M')}–{hour_label}"

    if not force and any((h.get("date"), h.get("hour_label")) == (date_label, hour_label) for h in history):
        print(f"{hour_label} already summarized, skipping")
        return history

    try:
        since_ts = int(hour_start.timestamp())
        with urllib.request.urlopen(f"{FEED_URL}?since={since_ts}", timeout=15) as r:
            data = json.load(r)
    except Exception as e:
        print(f"fetch error: {e}")
        return history

    until_ts = int(hour_end.timestamp())
    # Only count messages FROM other nodes (skip the bot's own broadcasts)
    # and strictly within this completed hour — the feed endpoint only
    # takes a lower bound, so the upper bound is filtered here.
    msgs = [m for m in data.get("messages", [])
            if m.get("direction") == "in" and m.get("ts", 0) < until_ts]

    if len(msgs) < MIN_MESSAGES:
        _write_cache(history, {
            "date": date_label, "hour_label": hour_label, "range_label": range_label,
            "summary": None, "message_count": len(msgs), "generated_at": int(time.time()),
        })
        print(f"Too quiet ({len(msgs)} msgs, {range_label}) — wrote empty cache")
        return _load_history()

    # Bare-greeting hours ("Pagi", "Selamat pagi", "Malam semua"...) are the
    # single most common pattern on this channel — sending each one through
    # the LLM for a full write-up produced near-identical "topik utama:
    # salam pagi" summaries hour after hour. When most of the hour is just
    # greetings, skip the LLM entirely and record a one-line digest —
    # cheaper, and it stops burying genuinely different hours under
    # repetitive noise in the !ringkasan/Stats feed.
    greeting_count = sum(1 for m in msgs if _is_bare_greeting(m["text"]))
    if greeting_count / len(msgs) >= GREETING_RATIO_FOR_DIGEST:
        summary = f"Obrolan santai, sebagian besar salam-salaman ({greeting_count}/{len(msgs)} pesan)."
        _write_cache(history, {
            "date": date_label, "hour_label": hour_label, "range_label": range_label,
            "summary": summary, "message_count": len(msgs), "generated_at": int(time.time()),
        })
        print(f"Wrote greeting digest for {range_label}: {len(msgs)} messages ({greeting_count} greetings)")
        return _load_history()

    transcript = "\n".join(f"{m['from_name']}: {m['text']}" for m in msgs)
    if len(transcript) > 6000:
        transcript = transcript[-6000:]  # keep the most recent if it's a very chatty hour

    # Previous hour's summary, so the LLM can say "masih lanjut soal X"
    # instead of re-describing the same conversation as if it were new.
    # In backfill mode (force=True, iterating hours in order), the caller
    # always passes the already-updated history from the previous
    # iteration, so history[0] is genuinely the hour right before this one
    # even when regenerating everything from scratch.
    prev_summary = history[0].get("summary") if history else None

    active_node_instruction = (
        "Sebutkan juga node mana yang paling aktif — sebut nama node saja."
        if len(msgs) >= MIN_FOR_ACTIVE_NODE else
        "JANGAN sebutkan node mana yang paling aktif — pesannya terlalu "
        "sedikit untuk itu bermakna."
    )
    continuity_instruction = (
        f'Ringkasan jam sebelumnya: "{prev_summary}". Kalau topik obrolan jam '
        "ini masih sama/lanjutan, boleh singgung itu masih berlanjut, TAPI "
        "tetap sebutkan fakta/kejadian BARU jam ini kalau ada — jangan cuma "
        "mengulang kalimat jam sebelumnya. Kalau topiknya beda, jelaskan "
        "topik barunya seperti biasa."
        if prev_summary else ""
    )

    from modules.llm import send_openwebui_query
    prompt = (
        "Ringkas obrolan grup mesh radio LongFast di bawah ini untuk warga "
        "yang tidak sempat baca chat-nya. Balas HANYA dengan 2-3 kalimat "
        "ringkasan dalam SATU baris (jangan pakai baris baru), langsung ke "
        "inti — TANPA kalimat pembuka seperti 'berikut ringkasannya', tanpa "
        "judul, tanpa daftar.\n"
        "BAHASA: Indonesia MURNI dari awal sampai akhir. JANGAN selipkan "
        "kata Inggris sama sekali (termasuk kata sambung kayak 'still', "
        "'also', 'meanwhile') — pakai padanan Indonesia-nya.\n"
        "ISI: cari KEJADIAN atau FAKTA nyata yang benar-benar terjadi di "
        "obrolan — node yang baru online lagi setelah lama offline, gateway/"
        "MQTT yang mati lalu diperbaiki (sebut siapa yang benerin kalau "
        "disebut), hasil pengukuran/tes, nama komponen atau perangkat, "
        "lokasi, rencana atau ide yang dibahas. Tulis fakta itu, JANGAN "
        "diringkas jadi kategori umum seperti 'pengujian koneksi' atau "
        "'diskusi teknis' kalau faktanya lebih spesifik dari itu — itu "
        "kegunaan utama ringkasan ini.\n"
        "KALAU ISINYA TIPIS: kalau obrolan cuma 'test'/'masuk'/sapaan tanpa "
        "kejadian atau detail nyata, JANGAN mengarang deskripsi yang "
        "terdengar teknis — cukup bilang apa adanya (mis. \"Beberapa node "
        "saling tes koneksi, tidak ada topik lain.\").\n"
        f"{active_node_instruction} "
        "JANGAN kutip isi obrolan kata demi kata — parafrasekan, tapi tetap "
        "sebutkan detail konkretnya. Jangan mengarang fakta yang tidak ada "
        "di obrolan, dan jangan berkomentar kalau kamu tidak yakin soal "
        f"sesuatu — cukup lewati bagian itu. {continuity_instruction}\n\n"
        f"{transcript}"
    )
    # send_openwebui_query returns this exact string on ANY failure
    # (timeout, connection error, or a rate-limit 429) — treated the same
    # as a real reply otherwise, this string was getting cached as if it
    # were an actual summary. Retry with backoff a couple times (a 429
    # usually clears within a few seconds), then give up and store no
    # summary rather than a fake one.
    summary = None
    for attempt in range(3):
        result = send_openwebui_query(prompt, max_tokens=220)
        if result and result != _LLM_ERROR_SENTINEL:
            summary = result
            break
        if attempt < 2:
            time.sleep(5)
    if summary:
        summary = " ".join(summary.split())  # collapse any stray newlines/whitespace the model added
    else:
        print(f"LLM failed for {range_label} after retries — storing no summary")
    _write_cache(history, {
        "date": date_label, "hour_label": hour_label, "range_label": range_label,
        "summary": summary, "message_count": len(msgs), "generated_at": int(time.time()),
    })
    print(f"Wrote summary for {range_label}: {len(msgs)} messages")
    return _load_history()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--redo-since":
        # One-off backfill/rework mode: re-summarize every completed hour
        # from the given point through now with the current prompt logic,
        # overwriting whatever's cached — e.g. after a prompt rework, to
        # bring old entries up to the new format instead of leaving them
        # stale until they age out. Not run by the timer.
        start = datetime.strptime(sys.argv[2], "%Y-%m-%d %H:%M").replace(tzinfo=WIB)
        now = datetime.now(WIB)
        # First window is (start, start+1h] — e.g. start=00:00 means the
        # first hour covered is the 00:00-01:00 window (hour_end=01:00),
        # not the 23:00-00:00 window from the day before.
        hour_end = start.replace(minute=0, second=0, microsecond=0)
        while hour_end <= start:
            hour_end += timedelta(hours=1)
        history = _load_history()
        while hour_end <= now.replace(minute=0, second=0, microsecond=0):
            history = process_hour(hour_end, history, force=True)
            hour_end += timedelta(hours=1)
            # Back-to-back LLM calls with no gap tripped the API's rate
            # limit partway through a backfill run — a few seconds between
            # hours keeps it under that ceiling. Only matters here; the
            # normal timer-triggered run only ever does one call per tick.
            time.sleep(4)
        return

    now = datetime.now(WIB)
    # "22:00" means the hour that ENDED at 22:00, i.e. the 21:00–22:00
    # window — the top of the current hour is the boundary, not the start
    # of an in-progress window.
    hour_end = now.replace(minute=0, second=0, microsecond=0)
    history = _load_history()
    process_hour(hour_end, history)


if __name__ == "__main__":
    main()
