"""
!p3k            — daftar topik P3K
!p3k <topik>   — panduan pertolongan pertama untuk topik tersebut
"""

_TOPICS = {
    "luka": (
        "🩹 Luka Terbuka\n"
        "1. Tekan luka dgn kain bersih 5–10 mnt\n"
        "2. Bilas dgn air mengalir\n"
        "3. Oleskan antiseptik (povidone iodine)\n"
        "4. Tutup dgn perban bersih\n"
        "5. Ganti perban tiap hari\n"
        "⚠️ RS jika: luka dalam/lebar/tidak berhenti berdarah"
    ),
    "bakar": (
        "🔥 Luka Bakar\n"
        "1. Siram air dingin mengalir 10–20 mnt\n"
        "2. JANGAN pakai es, pasta gigi, atau mentega\n"
        "3. Lepas cincin/jam tangan sebelum bengkak\n"
        "4. Tutup longgar dgn kain bersih\n"
        "⚠️ RS jika: > telapak tangan, di wajah/tangan/kaki, melepuh besar"
    ),
    "tersedak": (
        "😮 Tersedak (Heimlich)\n"
        "Dewasa:\n"
        "1. Berdiri di belakang korban\n"
        "2. Kepalkan tangan di atas pusar, di bawah tulang dada\n"
        "3. Tangan lain melingkupi\n"
        "4. Hentakkan ke dalam-atas dengan cepat, ulangi\n"
        "Bayi <1th: 5 tepukan punggung + 5 tekan dada"
    ),
    "pingsan": (
        "😵 Pingsan\n"
        "1. Baringkan, angkat kaki 30cm\n"
        "2. Longgarkan pakaian ketat\n"
        "3. Pastikan napas lancar\n"
        "4. Jangan beri minum saat tidak sadar\n"
        "5. Kipasi / pindah ke tempat teduh\n"
        "⚠️ RS jika: tidak sadar >2 mnt atau ada riwayat jantung"
    ),
    "patah": (
        "🦴 Patah Tulang\n"
        "1. JANGAN paksakan tulang ke posisi semula\n"
        "2. Imobilisasi dgn bidai (kayu/majalah) + perban\n"
        "3. Kompres es (bungkus kain) maks 20 mnt\n"
        "4. Tinggikan anggota tubuh yg patah\n"
        "⚠️ Segera RS — jangan tunda"
    ),
    "gigitan": (
        "🐍 Gigitan Ular/Hewan\n"
        "Ular:\n"
        "1. Tenangkan korban, minimalisir gerak\n"
        "2. Lepas perhiasan di sekitar gigitan\n"
        "3. JANGAN isap racun atau tourniquet\n"
        "4. Segera ke RS dengan antivenom\n"
        "Anjing rabies: cuci luka 15 mnt dgn sabun, RS segera"
    ),
    "sesak": (
        "🫁 Sesak Napas\n"
        "1. Dudukkan tegak / condong ke depan\n"
        "2. Longgarkan pakaian\n"
        "3. Buka jendela / area terbuka\n"
        "4. Jika ada inhaler: gunakan\n"
        "⚠️ 118 jika: bibir biru, tidak bisa bicara, tidak membaik"
    ),
    "cpr": (
        "❤️ CPR (Henti Jantung)\n"
        "1. Pastikan aman, periksa respons + napas\n"
        "2. Hubungi 118\n"
        "3. Posisi tangan di tengah dada\n"
        "4. Tekan keras 5–6cm, 100–120x/mnt\n"
        "5. 30 kompresi : 2 napas bantuan\n"
        "6. Lanjutkan sampai ambulans tiba"
    ),
    "keracunan": (
        "☠️ Keracunan\n"
        "Ditelan:\n"
        "1. JANGAN paksa muntah\n"
        "2. Simpan kemasan racun\n"
        "3. Segera 119 / RS\n"
        "Kulit/mata: bilas air bersih 15–20 mnt\n"
        "Gas: evakuasi ke udara segar, 118 jika tidak sadar"
    ),
    "tenggelam": (
        "🌊 Hampir Tenggelam\n"
        "1. Keluarkan dari air — jaga kepala\n"
        "2. Panggil bantuan 118\n"
        "3. Jika tidak bernapas: mulai CPR\n"
        "4. Jaga hangat (hipotermia)\n"
        "⚠️ Semua korban hampir tenggelam harus ke RS meski tampak baik"
    ),
}

_ALIASES = {
    "lukab": "bakar", "lukabakar": "bakar",
    "patah tulang": "patah",
    "heimlich": "tersedak",
    "cardiac": "cpr", "jantung": "cpr",
    "racun": "keracunan",
}


def get_p3k(message):
    parts = message.strip().split(None, 1)
    query = parts[1].strip().lower() if len(parts) > 1 else ""

    if not query:
        topic_list = ", ".join(sorted(_TOPICS.keys()))
        return (
            "🏥 P3K — Pertolongan Pertama\n"
            f"Topik: {topic_list}\n"
            "Ketik: !p3k <topik>\n"
            "Contoh: !p3k luka"
        )

    key = _ALIASES.get(query, query)
    if key in _TOPICS:
        return _TOPICS[key]

    # fuzzy: find first topic that starts with query
    for k in _TOPICS:
        if k.startswith(query):
            return _TOPICS[k]

    topic_list = ", ".join(sorted(_TOPICS.keys()))
    return f"❌ Topik '{query}' tidak ditemukan.\nTopik tersedia: {topic_list}"
