#!/usr/bin/env python3
"""Hourly-rolling LongFast chat summary, feeding !ringkasan's 'obrolan'
section (see modules/ringkasan.py).

Run via a systemd timer every 15 minutes (see summarize-longfast.timer).
Always summarizes from the top of the CURRENT hour to now, so the cached
summary is naturally labeled "sejak jam HH:00" and resets each time the
hour changes — no separate reset logic needed, the window start just
recomputes every run.

Reads the transcript from rivbot-ui's existing /api/channels/LongFast/
messages endpoint (mqtt_tap.py already decrypts and logs all LongFast
channel traffic there, not just bot interactions) rather than opening a
second connection to meshtasticd — same reasoning cmd_catalog.py's
simulator uses for staying out of mesh_bot's single-client TCP connection.
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/opt/meshing-around")

WIB = timezone(timedelta(hours=7))
CACHE_FILE = "/opt/meshing-around/data/longfast_hourly_summary.json"
FEED_URL = "http://localhost:8080/api/channels/LongFast/messages"
MIN_MESSAGES = 3  # skip the LLM call if LongFast has been too quiet to summarize meaningfully


def _write_cache(hour_label, summary, message_count):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump({
            "hour_label": hour_label,
            "summary": summary,
            "message_count": message_count,
            "generated_at": int(time.time()),
        }, f)


def main():
    now = datetime.now(WIB)
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    hour_start_ts = int(hour_start.timestamp())
    hour_label = hour_start.strftime("%H:%M")

    try:
        with urllib.request.urlopen(f"{FEED_URL}?since={hour_start_ts}", timeout=15) as r:
            data = json.load(r)
    except Exception as e:
        print(f"fetch error: {e}")
        return

    # Only count messages FROM other nodes — skip the bot's own broadcasts
    # so the summary reflects what the community said, not the bot's MOTD.
    msgs = [m for m in data.get("messages", []) if m.get("direction") == "in"]

    if len(msgs) < MIN_MESSAGES:
        _write_cache(hour_label, None, len(msgs))
        print(f"Too quiet ({len(msgs)} msgs since {hour_label}) — wrote empty cache")
        return

    transcript = "\n".join(f"{m['from_name']}: {m['text']}" for m in msgs)
    if len(transcript) > 6000:
        transcript = transcript[-6000:]  # keep the most recent if it's a very chatty hour

    from modules.llm import send_openwebui_query
    prompt = (
        "Ringkas obrolan grup mesh radio LongFast di bawah ini. Balas HANYA "
        "dengan 2 kalimat ringkasan santai bahasa Indonesia, langsung ke inti "
        "— TANPA kalimat pembuka seperti 'berikut ringkasannya', tanpa judul, "
        "tanpa daftar. Sebutkan topik utama yang dibahas dan (kalau jelas "
        "terlihat) node mana yang paling aktif — sebut nama node saja, JANGAN "
        "kutip isi obrolan kata demi kata. Jangan mengarang topik yang tidak "
        "ada, dan jangan berkomentar kalau kamu tidak yakin soal sesuatu — "
        "cukup lewati bagian itu.\n\n"
        f"{transcript}"
    )
    summary = send_openwebui_query(prompt, max_tokens=150)
    _write_cache(hour_label, summary, len(msgs))
    print(f"Wrote summary for {hour_label}: {len(msgs)} messages")


if __name__ == "__main__":
    main()
