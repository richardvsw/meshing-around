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
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/opt/meshing-around")

WIB = timezone(timedelta(hours=7))
CACHE_FILE = "/opt/meshing-around/data/longfast_hourly_summary.json"
FEED_URL = "http://localhost:8080/api/channels/LongFast/messages"
MIN_MESSAGES = 3    # skip the LLM call if LongFast has been too quiet to summarize meaningfully
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


def main():
    now = datetime.now(WIB)
    # "22:00" means the hour that ENDED at 22:00, i.e. the 21:00–22:00
    # window — the top of the current hour is the boundary, not the start
    # of an in-progress window.
    hour_end = now.replace(minute=0, second=0, microsecond=0)
    hour_start = hour_end - timedelta(hours=1)
    date_label = hour_end.strftime("%Y-%m-%d")
    hour_label = hour_end.strftime("%H:%M")
    range_label = f"{hour_start.strftime('%H:%M')}–{hour_label}"

    history = _load_history()
    if any((h.get("date"), h.get("hour_label")) == (date_label, hour_label) for h in history):
        print(f"{hour_label} already summarized, skipping")
        return

    try:
        since_ts = int(hour_start.timestamp())
        with urllib.request.urlopen(f"{FEED_URL}?since={since_ts}", timeout=15) as r:
            data = json.load(r)
    except Exception as e:
        print(f"fetch error: {e}")
        return

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
    _write_cache(history, {
        "date": date_label, "hour_label": hour_label, "range_label": range_label,
        "summary": summary, "message_count": len(msgs), "generated_at": int(time.time()),
    })
    print(f"Wrote summary for {range_label}: {len(msgs)} messages")


if __name__ == "__main__":
    main()
