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

# Exact match only: "Test"/"test" and the Indonesian spelling "Tes"/"tes",
# nothing else — "TEST", "test123", "let's test this" do NOT match.
MAGIC_WORDS = frozenset(("Test", "test", "Tes", "tes"))

# Short on purpose — this used to be a 3-chunk essay explaining the whole
# mechanism, which is both annoying over LoRa and unclear to anyone who
# doesn't already know what "!senyap"/"!aktif"/"!cmd" mean. Just: this was
# automatic, here's how to stop/restart it, here's where to see everything
# else.
NOTICE_TEMPLATES = [
    "\n💡 Balesan otomatis. Matiin: !senyap, nyalain: !aktif. Fitur lain: !cmd",
    "\n💡 Ini auto-reply. Stop: !senyap, nyalain lagi: !aktif. Liat fitur: !cmd",
    "\n💡 Otomatis nih. !senyap = stop, !aktif = nyalain lagi. !cmd = fitur lainnya",
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
