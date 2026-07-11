"""
Per-node preference for the bare (no "!") magic-word auto-reply — exact
whole-message match on "Test" or "test" only (the common ham-radio "just
checking my radio works" convention), nothing before or after. See
mesh_bot.py's is_bare_magic_word check.

!senyap opts a node out of ALL of the bot's unsolicited/proactive replies
(this magic-word auto-reply, idle follow-ups, dad jokes) — explicit
!commands the node sends always still get a reply regardless, so !aktif
(opt back in) can never get stuck being silenced along with everything
else.

Small JSON file, same pattern as the other data/*.json caches in this
project — no DB needed for a couple hundred node IDs at most.
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

_PREF_FILE = "/opt/meshing-around/data/magicword_pref.json"

# Exact match only: "Test" and "test", nothing else — "TEST", "test123",
# "let's test this" do NOT match.
MAGIC_WORDS = frozenset(("Test", "test"))

NOTICE_TEMPLATES = [
    "\n(Btw, gue balas otomatis kalau ada yang ketik persis \"Test\" di channel. Keganggu? Ketik !senyap buat matiin. Aktifin lagi kapan aja pakai !aktif. Ketik !cmd buat liat semua fitur lain.)",
    "\n(Ini balesan otomatis krn kamu ketik \"test\" di channel. Ga suka? !senyap buat stop. !aktif kalau mau nyalain lagi nanti. Ada !cmd juga kalau mau liat fitur lainnya.)",
    "\n(Fitur auto-reply ini nyala kalau kamu ketik persis \"Test\". Bisa dimatiin — ketik !senyap. Nanti tinggal !aktif buat nyalain lagi. Ketik !cmd buat liat semua yang bisa gue bantu.)",
]


def _load():
    try:
        if os.path.exists(_PREF_FILE):
            with open(_PREF_FILE) as f:
                data = json.load(f)
            data.setdefault("opted_out", [])
            return data
    except Exception as e:
        logger.warning("MagicWord: pref file load error: %s", e)
    return {"opted_out": []}


def _save(data):
    try:
        os.makedirs(os.path.dirname(_PREF_FILE), exist_ok=True)
        with open(_PREF_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning("MagicWord: pref file save error: %s", e)


def is_opted_out(node_id):
    return str(node_id) in _load().get("opted_out", [])


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
