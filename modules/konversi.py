"""
!konversi <nilai> <dari> <ke>
!konversi 100 km mil
!konversi 72 kg lbs
!konversi 37 c f
!konversi 1 liter galon
"""
import re

# unit aliases -> canonical
_ALIASES = {
    # length
    "km": "km", "kilometer": "km", "kilometres": "km",
    "mil": "mil", "mile": "mil", "miles": "mil", "mi": "mil",
    "m": "m", "meter": "m", "metre": "m", "meters": "m",
    "cm": "cm", "centimeter": "cm",
    "ft": "ft", "kaki": "ft", "feet": "ft", "foot": "ft",
    "in": "in", "inci": "in", "inch": "in", "inches": "in",
    # weight
    "kg": "kg", "kilogram": "kg",
    "lbs": "lbs", "lb": "lbs", "pound": "lbs", "pounds": "lbs",
    "g": "g", "gram": "g",
    "oz": "oz", "ounce": "oz",
    # temperature
    "c": "c", "celsius": "c", "°c": "c",
    "f": "f", "fahrenheit": "f", "°f": "f",
    "k": "k", "kelvin": "k",
    # volume
    "liter": "l", "litre": "l", "l": "l",
    "ml": "ml", "mililiter": "ml",
    "galon": "gal", "gallon": "gal", "gal": "gal",
    "fl oz": "floz", "floz": "floz",
    # speed
    "kmh": "kmh", "km/h": "kmh", "kph": "kmh",
    "mph": "mph", "knot": "knot", "knots": "knot", "kt": "knot",
    "ms": "ms", "m/s": "ms",
    # data
    "kb": "kb", "mb": "mb", "gb": "gb", "tb": "tb",
    "kib": "kib", "mib": "mib", "gib": "gib", "tib": "tib",
}

# conversion functions: (from, to) -> fn(value)
def _cv(frm, to, val):
    key = (frm, to)
    # length (base: meters)
    _to_m = {"km": 1000, "mil": 1609.344, "m": 1, "cm": 0.01, "ft": 0.3048, "in": 0.0254}
    if frm in _to_m and to in _to_m:
        return val * _to_m[frm] / _to_m[to]
    # weight (base: grams)
    _to_g = {"kg": 1000, "lbs": 453.592, "g": 1, "oz": 28.3495}
    if frm in _to_g and to in _to_g:
        return val * _to_g[frm] / _to_g[to]
    # temperature
    if frm == "c" and to == "f": return val * 9/5 + 32
    if frm == "f" and to == "c": return (val - 32) * 5/9
    if frm == "c" and to == "k": return val + 273.15
    if frm == "k" and to == "c": return val - 273.15
    if frm == "f" and to == "k": return (val - 32) * 5/9 + 273.15
    if frm == "k" and to == "f": return (val - 273.15) * 9/5 + 32
    # volume (base: ml)
    _to_ml = {"l": 1000, "ml": 1, "gal": 3785.41, "floz": 29.5735}
    if frm in _to_ml and to in _to_ml:
        return val * _to_ml[frm] / _to_ml[to]
    # speed (base: km/h)
    _to_kmh = {"kmh": 1, "mph": 1.60934, "knot": 1.852, "ms": 3.6}
    if frm in _to_kmh and to in _to_kmh:
        return val * _to_kmh[frm] / _to_kmh[to]
    # data (base: bytes)
    _to_b = {
        "kb": 1000, "mb": 1e6, "gb": 1e9, "tb": 1e12,
        "kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4,
    }
    if frm in _to_b and to in _to_b:
        return val * _to_b[frm] / _to_b[to]
    return None


def _fmt(val):
    if abs(val) >= 1000:
        return f"{val:,.3f}".rstrip("0").rstrip(".")
    elif abs(val) >= 1:
        return f"{val:.4f}".rstrip("0").rstrip(".")
    else:
        return f"{val:.6f}".rstrip("0").rstrip(".")


def get_konversi(message):
    parts = message.strip().split(None, 1)
    args_str = parts[1].strip() if len(parts) > 1 else ""

    if not args_str:
        return (
            "📐 Konversi Satuan\n"
            "Cara: !konversi <nilai> <dari> <ke>\n"
            "Contoh:\n"
            "  !konversi 100 km mil\n"
            "  !konversi 80 kg lbs\n"
            "  !konversi 37 c f\n"
            "  !konversi 2 liter galon\n"
            "  !konversi 120 kmh mph\n"
            "  !konversi 1 gb mb"
        )

    # parse: number + two unit tokens
    m = re.match(r"([\d.,]+)\s+(\S+)\s+(\S+)", args_str)
    if not m:
        return "❌ Format: !konversi <nilai> <dari> <ke>\nContoh: !konversi 100 km mil"

    try:
        val = float(m.group(1).replace(",", "."))
    except ValueError:
        return "❌ Nilai tidak valid."

    frm_raw = m.group(2).lower()
    to_raw = m.group(3).lower()

    frm = _ALIASES.get(frm_raw)
    to = _ALIASES.get(to_raw)

    if not frm:
        return f"❌ Satuan '{m.group(2)}' tidak dikenali."
    if not to:
        return f"❌ Satuan '{m.group(3)}' tidak dikenali."
    if frm == to:
        return f"✅ {_fmt(val)} {m.group(2)} = {_fmt(val)} {m.group(3)} (sama)"

    result = _cv(frm, to, val)
    if result is None:
        return f"❌ Tidak bisa konversi {m.group(2)} → {m.group(3)} (beda kategori)."

    return f"✅ {_fmt(val)} {m.group(2)} = {_fmt(result)} {m.group(3)}"
