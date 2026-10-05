
"""Layout keyboard untuk piano Roblox.

Layout default = layout klasik Roblox Piano / Virtual Piano "MAX":

  Tombol PUTIH (tekan biasa):
      1 2 3 4 5 6 7 8 9 0 q w e r t y u i o p a s d f g h j k l z x c v b n m

  Tombol HITAM (tekan sambil menahan Shift):
      ! @ $ % ^ * (   Q W E T Y I O P   S D G H J L   Z C V B

Setiap tombol hitam berada di atas celah antara dua tombol putih di
sekitarnya (persis seperti keyboard piano asli).
"""

import ctypes

# ---------------------------------------------------------------------------
# Data layout
# ---------------------------------------------------------------------------

# Tombol putih, dari kiri ke kanan (nada: C D E F G A B berulang).
WHITE_KEYS = list("1234567890qwertyuiopasdfghjklzxcvbnm")

# Tombol hitam: (index tombol putih SEBELUM celah, karakter tombol).
# Contoh: ("!", 0) artinya tombol ! berada di antara tombol putih ke-0 ("1")
# dan ke-1 ("2").
BLACK_KEY_GAPS = [
    (0, "!"), (1, "@"), (3, "$"), (4, "%"), (5, "^"), (7, "*"), (8, "("),
    (10, "Q"), (11, "W"), (12, "E"), (14, "T"), (15, "Y"),
    (17, "I"), (18, "O"), (19, "P"),
    (21, "S"), (22, "D"), (24, "G"), (25, "H"), (26, "J"), (28, "L"),
    (29, "Z"), (31, "C"), (32, "V"), (33, "B"),
]

VALID_KEYS = set(WHITE_KEYS) | {k for _, k in BLACK_KEY_GAPS}

WHITE_INDEX = {k: i for i, k in enumerate(WHITE_KEYS)}
BLACK_INDEX = {k: gap for gap, k in BLACK_KEY_GAPS}

# Urutan tampilan di layar (tombol hitam di tengah celahnya).
_ORDER = {}
for _i, _k in enumerate(WHITE_KEYS):
    _ORDER[_k] = 2 * _i
for _gap, _k in BLACK_KEY_GAPS:
    _ORDER[_k] = 2 * _gap + 1


def sort_keys(keys):
    """Urutkan kumpulan tombol seperti posisi di piano (kiri -> kanan)."""
    return sorted(keys, key=lambda k: _ORDER.get(k, 9999))


# ---------------------------------------------------------------------------
# Nama nada
# ---------------------------------------------------------------------------

NOTE_NAMES = ["C", "D", "E", "F", "G", "A", "B"]
# Setengah-nada dalam satu oktaf untuk nada putih.
SEMIS = [0, 2, 4, 5, 7, 9, 11]


def note_name_for_white(idx, base_octave=3):
    return f"{NOTE_NAMES[idx % 7]}{base_octave + idx // 7}"


def note_name_for_black(gap, base_octave=3):
    return f"{NOTE_NAMES[gap % 7]}#{base_octave + gap // 7}"


def key_note_name(key, base_octave=3):
    """Nama nada untuk sebuah tombol, mis. '1' -> 'C3', '!' -> 'C#3'."""
    if key in WHITE_INDEX:
        return note_name_for_white(WHITE_INDEX[key], base_octave)
    if key in BLACK_INDEX:
        return note_name_for_black(BLACK_INDEX[key], base_octave)
    return key


# ---------------------------------------------------------------------------
# Mapping pitch MIDI <-> tombol (untuk import file MIDI)
# ---------------------------------------------------------------------------

def build_pitch_map(base_midi=48):
    """Buat mapping {pitch MIDI: tombol}.  base_midi = nada '1' (default C3)."""
    m = {}
    for i, k in enumerate(WHITE_KEYS):
        m[base_midi + (i // 7) * 12 + SEMIS[i % 7]] = k
    for gap, k in BLACK_KEY_GAPS:
        m[base_midi + (gap // 7) * 12 + SEMIS[gap % 7] + 1] = k
    return m


# ---------------------------------------------------------------------------
# Normalisasi kejadian keyboard (Shift -> tombol hitam)
# ---------------------------------------------------------------------------

# Hanya tombol hitam yang benar-benar ada di layout (celah E-F dan B-C
# tidak punya tombol hitam: Shift+3/#, Shift+7/&, Shift+0/) bukan kunci piano).
SHIFT_NUM = {"1": "!", "2": "@", "4": "$", "5": "%", "6": "^", "8": "*", "9": "("}
SHIFT_ALL = {"1": "!", "2": "@", "3": "#", "4": "$", "5": "%", "6": "^", "7": "&", "8": "*", "9": "(", "0": ")"}
SYMBOL_TO_BASE = {v: k for k, v in SHIFT_ALL.items()}


def get_key_press_info(ch):
    """Mengembalikan (base_key, is_shifted) untuk sebuah karakter not piano.

    Contoh:
    - '1' -> ('1', False)
    - '!' -> ('1', True)
    - 'q' -> ('q', False)
    - 'Q' -> ('q', True)
    """
    if ch in SYMBOL_TO_BASE:
        return SYMBOL_TO_BASE[ch], True
    if ch.isupper():
        return ch.lower(), True
    return ch, False


VK_SHIFT = 0x10
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", _KEYBDINPUT),
        ("mi", _MOUSEINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("union", _INPUT_UNION),
    ]


def get_vk_code(base_char):
    """Mengembalikan Virtual Key code Windows untuk karakter dasar piano."""
    if "0" <= base_char <= "9":
        return ord(base_char)
    if "a" <= base_char <= "z":
        return ord(base_char.upper())
    if "A" <= base_char <= "Z":
        return ord(base_char)
    return None


def win_press_vk(vk):
    """Menekan Virtual Key menggunakan Windows keybd_event API (VirtualKey + ScanCode untuk Roblox)."""
    try:
        sc = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
        ctypes.windll.user32.keybd_event(vk, sc, 0, 0)
    except Exception:
        pass


def win_release_vk(vk):
    """Melepas Virtual Key menggunakan Windows keybd_event API (VirtualKey + ScanCode untuk Roblox)."""
    try:
        sc = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
        ctypes.windll.user32.keybd_event(vk, sc, 2, 0)
    except Exception:
        pass



def caps_lock_on():
    try:
        return bool(ctypes.windll.user32.GetKeyState(0x14) & 1)
    except Exception:
        return False


def normalize_key(name, shift_held):
    """Ubah nama tombol dari hook menjadi tombol piano yang bisa dicocokkan.

    - 'a'        -> 'a'
    - shift+'a'  -> 'A'   (tombol hitam)
    - '1'        -> '1'
    - shift+'1'  -> '!'
    - simbol yang sudah berupa tombol piano ('!', 'Q', ...) -> diteruskan.
    - selain itu -> None (bukan tombol piano).
    """
    if len(name) != 1:
        return None
    ch = name
    if ch.isdigit():
        if shift_held:
            # Hanya angka yang punya tombol hitam di layout (mis. Shift+1 = !).
            return SHIFT_NUM.get(ch)
        return ch
    if ch.isalpha():
        upper = shift_held ^ caps_lock_on()
        return ch.upper() if upper else ch.lower()
    if ch in VALID_KEYS:
        return ch
    return None
