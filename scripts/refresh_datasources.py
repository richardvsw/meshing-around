#!/usr/bin/env python3
"""Periodic refresh for the "Live Data Sources" shown on rivbot-ui's
Overview page (Gempa/BMKG, Kurs Rupiah, FIFA 2026, Harga BBM). Until this
existed, each cache only ever updated when a user happened to run the
matching bot command (!gempa, !kursrupiah, ...) or someone clicked the
manual refresh icon in the UI — with light usage that left them showing
"last success 4d ago" even though the underlying source was fine, nobody
had just asked recently.

Run via a systemd timer (see refresh-datasources.timer). Pesawat
(OpenSky) is deliberately not included here — routes/emergency.py already
notes it self-refreshes on a 20s TTL, no periodic trigger needed.

Each refresh is independent and best-effort: one source failing (rate
limit, upstream outage) doesn't block the others, and modules.cache_status
(read by rivbot-ui's /api/datasources/status) is exactly the same sidecar
each module already writes on a manual refresh — this script doesn't touch
that bookkeeping directly, it just calls the same refresh() functions the
UI's "↻" button calls.
"""
import sys

sys.path.insert(0, "/opt/meshing-around")

REFRESHERS = [
    ("gempa", "modules.gempa", "refresh"),
    ("kurs", "modules.kurs", "refresh"),
    ("fifa2026", "modules.fifa", "refresh"),
    ("hargabbm", "modules.bbm", "fetch_and_refresh"),
]


def main():
    for name, module_path, func_name in REFRESHERS:
        try:
            module = __import__(module_path, fromlist=[func_name])
            getattr(module, func_name)()
            print(f"{name}: refreshed")
        except Exception as e:
            print(f"{name}: refresh failed — {e}")


if __name__ == "__main__":
    main()
