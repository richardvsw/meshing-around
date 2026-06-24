"""
!alarm <HH:MM>   — set alarm at specific time (WIB)
!alarm <Nm>      — alarm in N minutes
!alarm off       — cancel active alarm
"""
import json
import os
import re
import threading
import time
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))
_ALARM_FILE = "/opt/meshing-around/data/alarms.json"

# node_id -> {"target_ts": float, "label": str, "acked": bool, "timer": Thread}
_alarms = {}
_lock = threading.Lock()
_send_fn = None  # set by register_send()


def register_send(fn):
    """Call this from mesh_bot.py at startup: alarm.register_send(send_message)"""
    global _send_fn
    _send_fn = fn
    _load_alarms()


def _load_alarms():
    if not os.path.exists(_ALARM_FILE):
        return
    try:
        with open(_ALARM_FILE) as f:
            saved = json.load(f)
        now = time.time()
        for node_id, entry in saved.items():
            ts = entry.get("target_ts", 0)
            if ts > now:
                _schedule_alarm(node_id, ts, entry.get("label", ""))
    except Exception as e:
        logger.error("alarm: load error: %s", e)


def _save_alarms():
    os.makedirs(os.path.dirname(_ALARM_FILE), exist_ok=True)
    try:
        data = {}
        with _lock:
            for node_id, entry in _alarms.items():
                data[node_id] = {
                    "target_ts": entry["target_ts"],
                    "label": entry["label"],
                }
        with open(_ALARM_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.error("alarm: save error: %s", e)


def _ring(node_id):
    """Called by timer thread: send DM every 60s until acked."""
    while True:
        with _lock:
            entry = _alarms.get(node_id)
            if not entry or entry.get("acked"):
                break
        msg = f"⏰ ALARM! {entry['label']}\nBalas pesan apapun untuk mematikan alarm."
        if _send_fn:
            try:
                _send_fn(msg, node_id)
            except Exception as e:
                logger.error("alarm: send error: %s", e)
        time.sleep(60)


def _schedule_alarm(node_id, target_ts, label):
    delay = max(0, target_ts - time.time())

    def _fire():
        time.sleep(delay)
        with _lock:
            if node_id not in _alarms:
                return
            _alarms[node_id]["acked"] = False
        _ring(node_id)

    t = threading.Thread(target=_fire, daemon=True)
    t.start()
    with _lock:
        _alarms[node_id] = {
            "target_ts": target_ts,
            "label": label,
            "acked": False,
            "timer": t,
        }


def ack_alarm(node_id):
    """Call from mesh_bot.py when ANY message arrives from node_id."""
    with _lock:
        if node_id in _alarms:
            _alarms[node_id]["acked"] = True
            del _alarms[node_id]
            _save_alarms()


def get_alarm(message, message_from_id=None):
    if not message_from_id:
        return "❌ Alarm hanya bisa diatur via DM (node ID tidak diketahui)."

    args = message.strip().split(None, 1)
    param = args[1].strip() if len(args) > 1 else ""

    if not param or param.lower() == "help":
        return (
            "⏰ Alarm — cara pakai:\n"
            "  !alarm 07:30   → alarm jam 07:30 WIB\n"
            "  !alarm 30m     → alarm 30 menit lagi\n"
            "  !alarm off     → batalkan alarm"
        )

    if param.lower() == "off":
        ack_alarm(message_from_id)
        return "✅ Alarm dibatalkan."

    now = datetime.now(WIB)
    target_ts = None
    label = ""

    # "30m" format
    m = re.fullmatch(r"(\d+)m", param.lower())
    if m:
        minutes = int(m.group(1))
        if minutes < 1 or minutes > 1440:
            return "❌ Durasi harus antara 1–1440 menit."
        target_ts = time.time() + minutes * 60
        t = datetime.fromtimestamp(target_ts, tz=WIB)
        label = f"set {minutes} menit lagi ({t.strftime('%H:%M')} WIB)"

    # "HH:MM" format
    if not target_ts:
        m2 = re.fullmatch(r"(\d{1,2}):(\d{2})", param)
        if m2:
            h, mn = int(m2.group(1)), int(m2.group(2))
            if h > 23 or mn > 59:
                return "❌ Format waktu tidak valid (00:00–23:59)."
            target = now.replace(hour=h, minute=mn, second=0, microsecond=0)
            if target <= now:
                target = target + timedelta(days=1)
            target_ts = target.timestamp()
            label = f"{h:02d}:{mn:02d} WIB"

    if not target_ts:
        return "❌ Format tidak dikenali. Coba: !alarm 07:30 atau !alarm 30m"

    # Cancel any existing alarm for this node
    ack_alarm(message_from_id)
    _schedule_alarm(message_from_id, target_ts, label)
    _save_alarms()

    dt = datetime.fromtimestamp(target_ts, tz=WIB)
    mnt = int((target_ts - time.time()) / 60)
    return f"✅ Alarm diset: {label}\n⏱ ~{mnt} menit lagi ({dt.strftime('%H:%M')} WIB)\nBalas pesan apapun untuk mematikan."
