"""
!survival           — daftar topik bertahan hidup di alam bebas
!survival <topik>   — panduan bertahan hidup untuk topik tersebut

Fokus wilderness survival (air, api, tempat berlindung, sinyal, navigasi) —
bukan P3K medis (lihat !p3k) atau data bencana real-time (lihat !bencana).
"""

_TOPICS = {
    "air": (
        "💧 Cari & Murnikan Air\n"
        "1. Cari air mengalir (sungai/mata air), hindari air tergenang\n"
        "2. Rebus 1 menit (3 menit jika >2000 mdpl) sebelum diminum\n"
        "3. Tanpa alat masak: jemur di botol bening 6 jam terik matahari (SODIS), atau pakai tablet/tetes klorin\n"
        "4. Saring air keruh dulu pakai kain/pasir/arang sebelum dimurnikan\n"
        "5. Tampung embun pagi atau air hujan — biasanya lebih aman langsung\n"
        "⚠️ Jangan minum air dekat pemukiman/ternak di hulu tanpa dimurnikan dulu"
    ),
    "api": (
        "🔥 Membuat Api\n"
        "1. Butuh 3 hal: bahan bakar kering, oksigen, sumber panas\n"
        "2. Kumpulkan 3 lapis: sarang pemantik (rumput/serat kering), ranting kecil, kayu besar\n"
        "3. Ranting kering yg patah dgn suara \"krek\" = kering, yg menekuk = masih basah\n"
        "4. Susun piramida kecil dulu, besarkan bertahap setelah menyala\n"
        "5. Tanpa korek: batu api+baja, atau lensa kamera/kacamata saat terik\n"
        "6. Lindungi dari angin & hujan dgn penahan angin sederhana\n"
        "⚠️ JANGAN nyalakan di lahan gambut/rumput kering musim kemarau — risiko karhutla"
    ),
    "tempat": (
        "🏕️ Tempat Berlindung\n"
        "1. Prioritas: lindungi dari hujan, angin, & dinginnya tanah — bukan dari hewan\n"
        "2. Pilih tanah datar & tinggi, JAUHI lembah/aliran sungai kering (rawan banjir bandang)\n"
        "3. Hindari di bawah pohon mati/dahan rapuh\n"
        "4. Alasi tanah dgn daun/ranting kering — kontak langsung ke tanah bikin cepat hipotermia\n"
        "5. Bivak sederhana: ponco/terpal + tali, miringkan biar air hujan mengalir turun\n"
        "6. Di hutan tropis: naikkan alas sedikit dari tanah, waspada serangga & ular"
    ),
    "sinyal": (
        "🆘 Sinyal Minta Tolong\n"
        "1. Aturan 3 = kode darurat internasional: 3 peluit, 3 nyala api, atau 3 tanda apa pun\n"
        "2. Api unggun 3 titik segitiga di area terbuka (jika aman)\n"
        "3. Asap tebal siang hari: taruh ranting hijau/basah di atas api menyala\n"
        "4. Pantulkan cermin/benda mengkilap ke arah pesawat/helikopter\n"
        "5. Buat tanda X atau SOS besar dari batu/kayu di tanah lapang, kontras dgn warna tanah\n"
        "6. Kibarkan kain warna cerah/mencolok\n"
        "📻 Kode Morse SOS: !morse"
    ),
    "navigasi": (
        "🧭 Navigasi Tanpa GPS/Kompas\n"
        "1. Metode bayangan: tancapkan tongkat tegak, tandai ujung bayangan, tunggu 15 mnt, tandai lagi — garis tanda 1→2 = barat→timur kasar\n"
        "2. Matahari terbit dari timur, terbenam di barat (kasar, bisa geser musiman)\n"
        "3. Ikuti aliran air turun ke hilir — biasanya mengarah ke pemukiman/laut\n"
        "4. Tandai jejak (ikat kain/goresan pohon) biar tidak muter di area yang sama\n"
        "5. Malam cerah: gunakan bintang paling terang sbg titik acuan arah, jangan jalan random\n"
        "⚠️ Kalau tersesat & lelah: LEBIH baik diam di tempat terbuka & beri sinyal drpd terus jalan"
    ),
}

_ALIASES = {
    "minum": "air", "sumber air": "air", "murnikan air": "air", "air minum": "air",
    "bakar": "api", "membuat api": "api", "korek": "api", "unggun": "api",
    "shelter": "tempat", "berlindung": "tempat", "bivak": "tempat", "tenda darurat": "tempat",
    "isyarat": "sinyal", "sos": "sinyal", "minta tolong": "sinyal", "cari perhatian": "sinyal",
    "arah": "navigasi", "kompas": "navigasi", "orientasi": "navigasi", "tersesat": "navigasi",
}


def get_survival(message):
    parts = message.strip().split(None, 1)
    query = parts[1].strip().lower() if len(parts) > 1 else ""

    if not query:
        topic_list = ", ".join(sorted(_TOPICS.keys()))
        return (
            "🏕️ Survival — Bertahan Hidup di Alam\n"
            f"Topik: {topic_list}\n"
            "Ketik: !survival <topik>\n"
            "Contoh: !survival air\n"
            "(P3K medis: !p3k · Info bencana: !bencana)"
        )

    key = _ALIASES.get(query, query)
    if key in _TOPICS:
        return _TOPICS[key]

    for k in _TOPICS:
        if k.startswith(query):
            return _TOPICS[k]

    topic_list = ", ".join(sorted(_TOPICS.keys()))
    return f"❌ Topik '{query}' tidak ditemukan.\nTopik tersedia: {topic_list}"
