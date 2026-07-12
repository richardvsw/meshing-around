#!/usr/bin/env python3
"""Hourly LongFast message volume + channel-congestion snapshot, feeding
the Stats page's "Kesehatan Mesh" chart.

Run via a systemd timer every 15 minutes (see longfast-congestion.timer),
same self-guard pattern as summarize_longfast.py: each COMPLETED hour is
only ever recorded once — an entry labeled "22:00" covers the full
21:00-22:00 window.

message_count is a real count over that hour (from rivbot-ui's own
/api/channels/LongFast/messages, same source summarize_longfast.py uses).
chutil/airutiltx are NOT a true hourly average — map.meshnode.id's API is
a live snapshot with no history endpoint, so these are a single sample
taken whenever this script happens to run, averaged across whichever of
our own nodes reported one at that instant. Good enough to eyeball
"was the channel busy around the same time messages spiked", not a
rigorous engineering measurement — labelled as a sample in the UI, not
an average.
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/opt/meshing-around")

WIB = timezone(timedelta(hours=7))
CACHE_FILE = "/opt/meshing-around/data/longfast_congestion_history.json"
FEED_URL = "http://localhost:8080/api/channels/LongFast/messages"
NODES_URL = "http://localhost:8080/api/nodes"
MESHNODE_URL = "https://map.meshnode.id/api/nodes/map"
# Same reasoning as summarize_longfast.py's MAX_HISTORY — a hard ceiling
# only, actual retention is handled by rivbot-ui's Retention page pruning
# this file by age alongside the other longfast_days-governed data.
MAX_HISTORY = 24 * 35


def _load_history():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f).get("history", [])
    except Exception:
        return []


def _write_cache(history, entry):
    key = (entry["date"], entry["hour_label"])
    history = [h for h in history if (h.get("date"), h.get("hour_label")) != key]
    history.insert(0, entry)
    history = history[:MAX_HISTORY]

    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump({"history": history}, f)


def _congestion_sample():
    """Averages chUtil/airUtilTx across our own known nodes, using
    whichever of them map.meshnode.id currently has a fresh metrics report
    for. Returns (avg_chutil, avg_airutiltx, sample_size) — any of these
    can be None if nothing was available this tick."""
    try:
        our_nodes = json.load(urllib.request.urlopen(NODES_URL, timeout=15))
        our_shorts = {(n.get("short") or "").strip().upper() for n in our_nodes}
        mn = json.load(urllib.request.urlopen(MESHNODE_URL, timeout=15))
    except Exception as e:
        print(f"congestion sample fetch failed: {e}")
        return None, None, 0

    chutils, airutils = [], []
    for meta in mn.values():
        short = (meta.get("shortName") or "").strip().upper()
        if short not in our_shorts:
            continue
        cu, au = meta.get("chUtil"), meta.get("airUtilTx")
        if cu is not None:
            chutils.append(cu)
        if au is not None:
            airutils.append(au)

    avg_cu = round(sum(chutils) / len(chutils), 2) if chutils else None
    avg_au = round(sum(airutils) / len(airutils), 2) if airutils else None
    return avg_cu, avg_au, max(len(chutils), len(airutils))


def main():
    now = datetime.now(WIB)
    hour_end = now.replace(minute=0, second=0, microsecond=0)
    hour_start = hour_end - timedelta(hours=1)
    date_label = hour_end.strftime("%Y-%m-%d")
    hour_label = hour_end.strftime("%H:%M")

    history = _load_history()
    if any((h.get("date"), h.get("hour_label")) == (date_label, hour_label) for h in history):
        print(f"{hour_label} already recorded, skipping")
        return

    try:
        since_ts = int(hour_start.timestamp())
        with urllib.request.urlopen(f"{FEED_URL}?since={since_ts}", timeout=15) as r:
            data = json.load(r)
    except Exception as e:
        print(f"message feed fetch failed: {e}")
        return

    until_ts = int(hour_end.timestamp())
    msg_count = sum(1 for m in data.get("messages", [])
                     if m.get("direction") == "in" and m.get("ts", 0) < until_ts)

    avg_chutil, avg_airutiltx, sample_size = _congestion_sample()

    _write_cache(history, {
        "date": date_label, "hour_label": hour_label,
        "message_count": msg_count,
        "avg_chutil": avg_chutil, "avg_airutiltx": avg_airutiltx, "sample_size": sample_size,
        "generated_at": int(time.time()),
    })
    print(f"Recorded {hour_label}: {msg_count} messages, chUtil~{avg_chutil} "
          f"(n={sample_size})")


if __name__ == "__main__":
    main()
