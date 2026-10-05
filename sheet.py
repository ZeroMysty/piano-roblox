"""Parser format teks sheet piano (gaya playpianosheets / virtualpiano.net).

Semantik yang didukung:
  a s d f             -> tiap huruf = satu nada (tombol ditekan bergantian)
  asdf                -> nada cepat berurutan -> tetap dipecah per huruf
  [asdf] / [a s d f]  -> akord: semua tombol ditekan bersamaan (konvensi Roblox)
  (d f)               -> tahan: diperlakukan sebagai akord
  |  atau  -          -> jeda / istirahat (tidak perlu ditekan)
  baris kosong        -> jeda panjang
  baris diawali '#'   -> komentar / judul (diabaikan)

Hasil: list step, masing-masing:
  ("n", frozenset(tombol))   satu nada / akord
  ("r", jumlah_jeda)         istirahat

Tombol yang bukan bagian layout diabaikan (biar app tidak macet).
"""

import re

from layouts import VALID_KEYS

# 1) [..] atau (..) tetap satu token
# 2) "|" atau "-" (satu atau lebih, boleh menempel di huruf: "as|df" / "s--s")
# 3) token lain (huruf, simbol)
_TOKEN_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)|\|+|-+|[^\s|\-]+")
_BLANK_LINE_RE = re.compile(r"\n[ \t]*\n+", re.MULTILINE)
_SEPARATOR_CHARS = set("-.")


def parse_sheet(text):
    steps = []
    rest = 0

    def flush_rest():
        nonlocal rest
        if rest:
            steps.append(("r", rest))
            rest = 0

    def add_note(chars):
        # Simpan hanya tombol yang ada di layout.
        keys = frozenset(ch for ch in chars if ch in VALID_KEYS)
        if keys:
            steps.append(("n", keys))

    # Baris komentar / judul (# ...) diabaikan.
    text = "\n".join(ln for ln in text.splitlines()
                     if not ln.strip().startswith("#"))
    # Baris kosong = jeda panjang.
    text = _BLANK_LINE_RE.sub(" | ", text)

    for tok in _TOKEN_RE.findall(text):
        if tok.startswith("|"):
            rest += len(tok)
            continue
        if set(tok) <= _SEPARATOR_CHARS:
            rest += len(tok)
            continue
        flush_rest()

        if tok.startswith("[") and tok.endswith("]"):
            inner = tok[1:-1]
            parts = inner.split()
            if not parts:
                continue
            add_note(parts if len(parts) > 1 else parts[0])
        elif tok.startswith("(") and tok.endswith(")"):
            parts = tok[1:-1].split()
            if parts:
                add_note(parts if len(parts) > 1 else parts[0])
        else:
            # Tanpa kurung = huruf-huruf ditekan satu per satu.
            for ch in tok:
                if ch in VALID_KEYS:
                    steps.append(("n", frozenset(ch)))

    flush_rest()
    return steps


def count_notes(steps):
    return sum(len(s[1]) for s in steps if s[0] == "n")
