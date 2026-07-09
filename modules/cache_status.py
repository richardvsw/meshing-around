# -*- coding: utf-8 -*-
"""
Shared last-fetch status tracker for modules with internet-backed caches.

Each cached module (bbm, gempa, kurs, fifa, pesawat, darurat) calls
record_status() right after a live fetch succeeds or fails. Status is
written to a small sidecar JSON file per source under data/cache_status/ so
a separate process (rivbot-ui) can read "last updated" / "is it currently
failing" without needing IPC into the bot's own process — the bot and the
UI are two independent systemd services with no shared memory.
"""
import json
import os
import time
import threading

_STATUS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache_status"
)
_lock = threading.Lock()


_MAX_HISTORY = 5


def record_status(name, ok=True, error=None, extra=None):
    with _lock:
        try:
            # mesh_bot.service runs as 'meshbot', rivbot-ui runs as root — both
            # need write access to this directory, so keep it wide open (it
            # only ever holds small, non-sensitive freshness/status JSON).
            os.makedirs(_STATUS_DIR, exist_ok=True)
            os.chmod(_STATUS_DIR, 0o777)
            path = os.path.join(_STATUS_DIR, f"{name}.json")

            prev = {}
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        prev = json.load(f)
                except Exception:
                    prev = {}

            now = time.time()
            payload = {"last_attempt": now, "ok": ok}
            if ok:
                payload["last_success"] = now
            elif "last_success" in prev:
                payload["last_success"] = prev["last_success"]
            if error:
                payload["error"] = str(error)[:200]
            if extra:
                payload.update(extra)

            # keep a short rolling history of failures for diagnosing a
            # flaky-vs-genuinely-down source, not just the single latest error
            history = prev.get("failure_history", [])
            if not ok:
                history = ([{"ts": now, "error": str(error)[:200] if error else "unknown"}] + history)[:_MAX_HISTORY]
            payload["failure_history"] = history

            with open(path, "w") as f:
                json.dump(payload, f)
            os.chmod(path, 0o666)
        except Exception:
            pass  # status tracking must never break the actual command


def read_all_status():
    if not os.path.isdir(_STATUS_DIR):
        return {}
    out = {}
    for fn in os.listdir(_STATUS_DIR):
        if fn.endswith(".json"):
            try:
                with open(os.path.join(_STATUS_DIR, fn)) as f:
                    out[fn[:-5]] = json.load(f)
            except Exception:
                pass
    return out
