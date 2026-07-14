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
    "hipotermia": (
        "🥶 Hipotermia\n"
        "1. Pindah ke tempat kering & terlindung angin\n"
        "2. Lepas pakaian basah, ganti kering\n"
        "3. Selimuti termasuk kepala, kontak kulit-ke-kulit jika perlu\n"
        "4. Beri minuman hangat manis jika sadar (jangan alkohol/kafein)\n"
        "5. JANGAN pijat/gosok anggota tubuh yg dingin\n"
        "⚠️ RS jika: menggigil berhenti tiba-tiba, bicara ngawur, kesadaran turun"
    ),
    "dehidrasi": (
        "💧 Dehidrasi\n"
        "1. Istirahat di tempat teduh\n"
        "2. Minum sedikit-sedikit tapi sering (oralit jika ada)\n"
        "3. Longgarkan pakaian, kipasi\n"
        "4. Hindari aktivitas berat sampai pulih\n"
        "⚠️ RS jika: tidak bisa minum, pusing berat, urin sangat gelap/tidak keluar"
    ),
    "kram": (
        "🦵 Kram Otot\n"
        "1. Hentikan aktivitas, istirahat\n"
        "2. Regangkan otot yg kram perlahan\n"
        "3. Pijat lembut area kram\n"
        "4. Minum air/elektrolit\n"
        "5. Kompres hangat jika masih tegang setelah kram reda"
    ),
    "sengatan": (
        "🐝 Sengatan Serangga/Tawon\n"
        "1. Cabut sengat dgn kuku/kartu (jangan pinset, bisa memeras racun)\n"
        "2. Cuci area dgn sabun & air\n"
        "3. Kompres dingin utk kurangi bengkak\n"
        "4. Pantau reaksi alergi (lihat !p3k alergi)\n"
        "⚠️ 118 jika: bengkak menyebar cepat, sesak napas, sengatan di mulut/leher"
    ),
    "alergi": (
        "🤧 Reaksi Alergi / Anafilaksis\n"
        "1. Jauhkan dari pemicu (makanan/serangga/obat)\n"
        "2. Jika ada epinefrin auto-injector: gunakan segera\n"
        "3. Baringkan, angkat kaki (jika tidak sesak)\n"
        "4. Longgarkan pakaian\n"
        "⚠️ 118 SEGERA jika: bengkak wajah/tenggorokan, sesak napas, pusing berat — ini darurat"
    ),
    "kejang": (
        "🧠 Kejang\n"
        "1. Jauhkan benda berbahaya di sekitar korban\n"
        "2. JANGAN tahan gerakan atau masukkan apapun ke mulut\n"
        "3. Miringkan tubuh setelah kejang mereda\n"
        "4. Longgarkan pakaian di leher\n"
        "5. Catat durasi kejang\n"
        "⚠️ 118 jika: kejang >5 menit, berulang, atau korban tidak sadar setelahnya"
    ),
    "keseleo": (
        "🦶 Keseleo/Terkilir\n"
        "1. R.I.C.E: Rest, Ice, Compress, Elevate\n"
        "2. Istirahatkan sendi, jangan dipaksa gerak\n"
        "3. Kompres es 15–20 mnt tiap 2–3 jam (hari pertama)\n"
        "4. Balut dgn perban elastis, jangan terlalu kencang\n"
        "5. Tinggikan area cedera\n"
        "⚠️ RS jika: tidak bisa menahan beban, bengkak parah, bentuk tidak normal"
    ),
    "lecet": (
        "🩹 Lecet/Lepuh (Blister)\n"
        "1. JANGAN pecahkan lepuh yg masih utuh\n"
        "2. Tutup dgn plester khusus lepuh/kasa\n"
        "3. Jika pecah sendiri: bersihkan, oles antiseptik, tutup\n"
        "4. Ganti alas kaki/kaos kaki yg pas\n"
        "5. Kurangi gesekan dgn plester pencegah di area rawan\n"
        "⚠️ RS jika: tanda infeksi (merah, bengkak, nanah, demam)"
    ),
    "kepala": (
        "🤕 Cedera Kepala\n"
        "1. Baringkan, jangan gerakkan leher berlebihan\n"
        "2. Kompres es di area benjol/luka\n"
        "3. Pantau kesadaran, ingatan, & ukuran pupil mata\n"
        "4. Jangan beri makan/minum jika muntah/bingung\n"
        "⚠️ 118 SEGERA jika: pingsan, muntah berulang, bingung, pupil tidak sama besar, kejang"
    ),
    "mimisan": (
        "👃 Mimisan\n"
        "1. Duduk, condongkan badan sedikit ke depan\n"
        "2. Pencet cuping hidung 10–15 mnt tanpa dilepas\n"
        "3. Bernapas lewat mulut\n"
        "4. JANGAN dongakkan kepala ke belakang\n"
        "5. Kompres dingin di pangkal hidung\n"
        "⚠️ RS jika: tidak berhenti >20 mnt, akibat benturan keras, sering berulang"
    ),
    "kelilipan": (
        "👁️ Kelilipan (Benda Asing di Mata)\n"
        "1. JANGAN mengucek mata\n"
        "2. Cuci mata dgn air bersih mengalir\n"
        "3. Kedipkan mata berulang di air bersih\n"
        "4. Tarik kelopak atas ke bawah utk keluarkan kotoran\n"
        "⚠️ RS jika: benda tertancap, nyeri hebat, penglihatan kabur setelah dibilas"
    ),
    "lintah": (
        "🩸 Gigitan Lintah\n"
        "1. JANGAN tarik paksa — bisa tertinggal di kulit\n"
        "2. Beri garam/air garam di lintah agar lepas\n"
        "3. Setelah lepas, bersihkan luka & tekan jika berdarah\n"
        "4. Oleskan antiseptik\n"
        "⚠️ RS jika: darah tidak berhenti >30 mnt atau tanda infeksi"
    ),
    "kalajengking": (
        "🦂 Gigitan/Sengatan Kalajengking\n"
        "1. Tenangkan korban, minimalisir gerak\n"
        "2. Kompres dingin di area sengatan\n"
        "3. Bersihkan luka dgn air & sabun\n"
        "4. Pantau reaksi alergi/sistemik\n"
        "⚠️ RS SEGERA jika: anak kecil, nyeri hebat menyebar, kesemutan wajah/mulut, sesak"
    ),
    "radangdingin": (
        "🧊 Radang Dingin (Frostbite)\n"
        "1. Pindah ke tempat hangat & kering\n"
        "2. Lepas pakaian/aksesoris basah/ketat\n"
        "3. Hangatkan bertahap dgn air hangat (bukan panas), JANGAN gosok\n"
        "4. JANGAN pecahkan lepuh yg muncul\n"
        "5. Jaga area terkena tetap terangkat\n"
        "⚠️ RS jika: kulit putih/keras/mati rasa, tidak membaik setelah dihangatkan"
    ),
    "heatstroke": (
        "🥵 Sengatan Panas (Heat Stroke)\n"
        "1. Pindah ke tempat teduh/sejuk segera\n"
        "2. Lepas pakaian berlebih\n"
        "3. Kompres/siram air dingin di leher, ketiak, selangkangan\n"
        "4. Kipasi terus menerus\n"
        "5. JANGAN beri minum jika kesadaran menurun\n"
        "⚠️ 118 SEGERA jika: suhu tubuh sangat tinggi, bingung, kejang, tidak sadar — darurat!"
    ),
    "hipoglikemia": (
        "🍬 Hipoglikemia (Gula Darah Rendah)\n"
        "1. Kenali tanda: lemas, gemetar, keringat dingin, bingung\n"
        "2. Jika sadar: beri gula/permen/minuman manis segera\n"
        "3. Tunggu 15 mnt, ulangi jika belum membaik\n"
        "4. Jangan beri makan/minum jika tidak sadar — risiko tersedak\n"
        "⚠️ 118 jika: tidak sadar, kejang, atau tidak membaik setelah diberi gula"
    ),
    "nyeridada": (
        "❤️‍🩹 Nyeri Dada (Serangan Jantung)\n"
        "1. Dudukkan korban senyaman mungkin\n"
        "2. Hubungi 118 SEGERA\n"
        "3. Longgarkan pakaian\n"
        "4. Jika sadar & tidak alergi aspirin: kunyah 1 aspirin\n"
        "5. Pantau kesadaran & napas terus menerus\n"
        "⚠️ Jika tidak sadar & tidak bernapas normal: mulai CPR (!p3k cpr)"
    ),
    "stroke": (
        "🧠 Stroke (Kenali F.A.S.T)\n"
        "F — Face: wajah mencong sebelah?\n"
        "A — Arms: satu lengan lemah/tidak bisa diangkat?\n"
        "S — Speech: bicara pelo/tidak jelas?\n"
        "T — Time: SEGERA hubungi 118, catat waktu gejala mulai\n"
        "Baringkan, miringkan jika muntah, JANGAN beri makan/minum\n"
        "⚠️ Setiap menit penting — jangan tunda ke RS"
    ),
    "tomcat": (
        "🐛 Dermatitis Tomcat (Kumbang Rove)\n"
        "1. JANGAN pukul/gencet serangga di kulit — racunnya iritatif\n"
        "2. Tiup/singkirkan perlahan tanpa memencet\n"
        "3. Cuci area terkena dgn sabun & air mengalir\n"
        "4. Jangan garuk — bisa menyebar\n"
        "5. Oleskan salep kortikosteroid ringan jika ada\n"
        "⚠️ RS jika: luka melepuh luas, nyeri hebat, infeksi"
    ),
}

_ALIASES = {
    "lukab": "bakar", "lukabakar": "bakar",
    "patah tulang": "patah",
    "heimlich": "tersedak",
    "cardiac": "cpr", "jantung": "cpr",
    "racun": "keracunan",
    "hipotermi": "hipotermia", "kedinginan": "hipotermia",
    "haus": "dehidrasi", "dehidrasi berat": "dehidrasi",
    "kram otot": "kram",
    "tawon": "sengatan", "lebah": "sengatan", "digigit serangga": "sengatan",
    "anafilaksis": "alergi", "alergi berat": "alergi",
    "ayan": "kejang", "epilepsi": "kejang",
    "terkilir": "keseleo",
    "lepuh": "lecet", "melepuh": "lecet",
    "gegar otak": "kepala", "benturan kepala": "kepala",
    "hidung berdarah": "mimisan",
    "kelilipen": "kelilipan", "kemasukan benda": "kelilipan",
    "pacet": "lintah",
    "kalajengking gigit": "kalajengking", "scorpion": "kalajengking",
    "frostbite": "radangdingin", "kaki beku": "radangdingin",
    "kepanasan": "heatstroke", "sengatan panas": "heatstroke",
    "gula darah rendah": "hipoglikemia", "lemas gula": "hipoglikemia",
    "serangan jantung": "nyeridada", "sakit jantung": "nyeridada",
    "gejala stroke": "stroke", "fast": "stroke",
    "tomcat gigit": "tomcat", "kumbang rove": "tomcat", "semut kayap": "tomcat",
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
