"""
Per-node preference for the bare "Test"/"test" magic-word auto-reply
(see mesh_bot.py's is_bare_test_ping check). !diamtest opts a node out,
!aktiftest opts back in. Also tracks which nodes have already been shown
the one-time "you can turn this off" notice, so it's not repeated on
every single ping.

Small JSON file, same pattern as the other data/*.json caches in this
project — no DB needed for a couple hundred node IDs at most.
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

_PREF_FILE = "/opt/meshing-around/data/magicword_pref.json"

NOTICE_TEMPLATES = [
    "\n(Btw, gue balas kalau ada yang ketik persis \"Test\" di channel. Keganggu? Ketik !diamtest buat matiin. Aktifin lagi kapan aja pakai !aktiftest.)",
    "\n(Ini balesan otomatis krn kamu ngetik \"test\" di channel. Ga suka? !diamtest buat stop. !aktiftest kalau mau nyalain lagi nanti.)",
    "\n(Fitur auto-reply utk kata \"Test\" ini bisa dimatiin kalau ganggu — ketik !diamtest. Nanti tinggal !aktiftest buat nyalain lagi.)",
]


def _load():
    try:
        if os.path.exists(_PREF_FILE):
            with open(_PREF_FILE) as f:
                data = json.load(f)
            data.setdefault("opted_out", [])
            data.setdefault("notified", [])
            return data
    except Exception as e:
        logger.warning("MagicWord: pref file load error: %s", e)
    return {"opted_out": [], "notified": []}


def _save(data):
    try:
        os.makedirs(os.path.dirname(_PREF_FILE), exist_ok=True)
        with open(_PREF_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning("MagicWord: pref file save error: %s", e)


def is_opted_out(node_id):
    return str(node_id) in _load().get("opted_out", [])


def was_notified(node_id):
    return str(node_id) in _load().get("notified", [])


def mark_notified(node_id):
    data = _load()
    nid = str(node_id)
    if nid not in data["notified"]:
        data["notified"].append(nid)
        _save(data)


def opt_out(node_id):
    data = _load()
    nid = str(node_id)
    if nid not in data["opted_out"]:
        data["opted_out"].append(nid)
        _save(data)


def opt_in(node_id):
    data = _load()
    nid = str(node_id)
    if nid in data["opted_out"]:
        data["opted_out"].remove(nid)
        _save(data)
