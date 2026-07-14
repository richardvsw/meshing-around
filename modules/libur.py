"""Nearest upcoming Indonesian public holiday, from the same HOLIDAYS_2026
table used by the greeting scheduler."""
from datetime import date, timedelta

_BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
          "Juli", "Agustus", "September", "Oktober", "November", "Desember"]


def get_libur(message=None):
    from data.greeting_banks import HOLIDAYS_2026

    today = date.today()
    upcoming = []
    for (m, d), name in HOLIDAYS_2026.items():
        try:
            hdate = date(today.year, m, d)
        except ValueError:
            continue
        if hdate >= today:
            upcoming.append((hdate, name))

    if not upcoming:
        return "🎉 Tidak ada libur nasional tersisa tahun ini."

    upcoming.sort(key=lambda x: x[0])
    hdate, name = upcoming[0]
    days_left = (hdate - today).days
    when = f"{hdate.day} {_BULAN[hdate.month - 1]}"

    if days_left == 0:
        rel = "Hari ini! 🎉"
    elif days_left == 1:
        rel = "Besok!"
    else:
        rel = f"{days_left} hari lagi"

    return f"📅 Libur berikutnya\n\n{when}\n{name}\n{rel}"
