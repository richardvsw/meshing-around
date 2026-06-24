"""
!morse <teks>       — teks ke kode morse
!morse decode <...> — kode morse ke teks (titik/dash dipisah spasi, kata dipisah '/')
"""

_ENCODE = {
    'A': '.-',   'B': '-...', 'C': '-.-.', 'D': '-..',
    'E': '.',    'F': '..-.', 'G': '--.',  'H': '....',
    'I': '..',   'J': '.---', 'K': '-.-',  'L': '.-..',
    'M': '--',   'N': '-.',   'O': '---',  'P': '.--.',
    'Q': '--.-', 'R': '.-.',  'S': '...',  'T': '-',
    'U': '..-',  'V': '...-', 'W': '.--',  'X': '-..-',
    'Y': '-.--', 'Z': '--..',
    '0': '-----', '1': '.----', '2': '..---', '3': '...--',
    '4': '....-', '5': '.....', '6': '-....', '7': '--...',
    '8': '---..', '9': '----.',
    '.': '.-.-.-', ',': '--..--', '?': '..--..', "'": '.----.',
    '!': '-.-.--', '/': '-..-.', '(': '-.--.',  ')': '-.--.-',
    '&': '.-...', ':': '---...', ';': '-.-.-.', '=': '-...-',
    '+': '.-.-.', '-': '-....-', '_': '..--.-', '"': '.-..-.',
    '$': '...-..-', '@': '.--.-.', ' ': '/',
}

_DECODE = {v: k for k, v in _ENCODE.items() if k != ' '}
_DECODE['/'] = ' '


def _to_morse(text):
    result = []
    for ch in text.upper():
        if ch in _ENCODE:
            result.append(_ENCODE[ch])
        elif ch == ' ':
            result.append('/')
        # skip unknown chars
    # join: letters separated by space, words (/) keep as-is
    # merge consecutive '/' back
    out = []
    for token in result:
        if token == '/':
            if out and out[-1] != '/':
                out.append('/')
        else:
            out.append(token)
    return ' '.join(out).replace(' / ', ' / ')


def _from_morse(code):
    words = code.strip().split('/')
    result = []
    for word in words:
        chars = []
        for symbol in word.strip().split():
            if symbol in _DECODE:
                chars.append(_DECODE[symbol])
            else:
                chars.append(f'[{symbol}]')
        result.append(''.join(chars))
    return ' '.join(result)


def get_morse(message):
    parts = message.strip().split(None, 1)
    args = parts[1].strip() if len(parts) > 1 else ""

    if not args:
        return (
            "📡 Morse Code\n"
            "  !morse <teks>         → ke morse\n"
            "  !morse decode <kode>  → ke teks\n"
            "Contoh:\n"
            "  !morse SOS\n"
            "  !morse decode ... --- ..."
        )

    if args.lower().startswith("decode "):
        code = args[7:].strip()
        if not code:
            return "❌ Masukkan kode morse setelah 'decode'."
        text = _from_morse(code)
        return f"📡 Morse → Teks:\n{text}"

    # encode
    morse = _to_morse(args)
    if not morse:
        return "❌ Tidak ada karakter yang bisa dikonversi."

    # chunk if too long
    if len(morse) > 200:
        morse = morse[:197] + "..."

    return f"📡 Teks → Morse:\n{morse}"
