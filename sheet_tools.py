"""Koleksi alat bantu pemrosesan & pengeditan sheet piano.

Fitur:
1. Transpose Sheet: Menaikkan/menurunkan nada sheet teks secara akurat (+1, -1, +12, -12).
2. Format & Rapikan Sheet: Merapikan sheet hasil copy-paste internet jadi rapi & estetik.
3. Simplifikasi Akord: Membatasi chord menjadi 2-3 nada (bass + melodi) untuk keyboard non-antighosting.
4. Analisis Lagu: Menghitung jumlah nada, akord, BPM perkiraan, durasi, dan tingkat kesulitan (1-5 bintang).
"""

import re
from layouts import build_pitch_map, sort_keys, VALID_KEYS, BLACK_KEY_GAPS

_TOKEN_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)|[|.\-~_]+|[^\s|.\-~_\[\]()]+")


def get_key_maps(base_midi=48):
    """Mengembalikan (pitch_to_key, key_to_pitch)."""
    p2k = build_pitch_map(base_midi)
    k2p = {k: p for p, k in p2k.items()}
    return p2k, k2p


def transpose_key(key, delta_semitones, p2k, k2p):
    """Transpose sebuah karakter tuts dengan delta semitone."""
    if key not in k2p:
        return key
    orig_pitch = k2p[key]
    new_pitch = orig_pitch + delta_semitones
    # Jika dalam jangkauan 61 key
    if new_pitch in p2k:
        return p2k[new_pitch]
    # Jika lewat batas atas atau bawah, coba wrap oktaf jika memungkinkan
    if delta_semitones > 0:
        while new_pitch > 108:
            new_pitch -= 12
    else:
        while new_pitch < 48:
            new_pitch += 12
    return p2k.get(new_pitch, key)


def transpose_sheet_text(raw_text, delta_semitones, base_midi=48):
    """Transpose seluruh teks sheet, mempertahankan komentar, baris baru, kurung, dan jeda."""
    if delta_semitones == 0:
        return raw_text

    p2k, k2p = get_key_maps(base_midi)
    output_lines = []

    for line in raw_text.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            # Update header jika ada keterangan transpose
            if trimmed.startswith("#") and "Transpose:" in trimmed:
                sub_tr = re.sub(r"\[Transpose:\s*[+-]?\d+\]", f"[Transpose: {delta_semitones:+d}]", trimmed)
                output_lines.append(sub_tr)
            else:
                output_lines.append(line)
            continue

        def _replace_token(m):
            tok = m.group(0)
            if all(c in "|.-~_" for c in tok):
                return tok
            if tok.startswith("[") and tok.endswith("]"):
                inner = tok[1:-1]
                parts = inner.split() if " " in inner else list(inner)
                new_parts = []
                for ch in parts:
                    if ch in k2p:
                        new_parts.append(transpose_key(ch, delta_semitones, p2k, k2p))
                    else:
                        new_parts.append(ch)
                sorted_parts = sort_keys(new_parts)
                sep = " " if " " in inner else ""
                return f"[{sep.join(sorted_parts)}]"
            elif tok.startswith("(") and tok.endswith(")"):
                inner = tok[1:-1]
                parts = inner.split() if " " in inner else list(inner)
                new_parts = [transpose_key(ch, delta_semitones, p2k, k2p) if ch in k2p else ch for ch in parts]
                sep = " " if " " in inner else ""
                return f"({sep.join(new_parts)})"
            else:
                new_tok = ""
                for ch in tok:
                    new_tok += transpose_key(ch, delta_semitones, p2k, k2p) if ch in k2p else ch
                return new_tok

        new_line = _TOKEN_RE.sub(_replace_token, line)
        output_lines.append(new_line)

    return "\n".join(output_lines)


def beautify_sheet(raw_text, tokens_per_line=10):
    """Membersihkan format sheet yang berantakan dari web menjadi rapi dan teratur."""
    lines = raw_text.splitlines()
    header_lines = []
    tokens = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            header_lines.append(stripped)
            continue
        if not stripped:
            if tokens and tokens[-1] != "|":
                tokens.append("|")
            continue

        for tok in _TOKEN_RE.findall(stripped):
            if all(c in "|.-~_" for c in tok):
                tokens.append("|" * min(3, len(tok)))
            elif tok.startswith("[") and tok.endswith("]"):
                inner = tok[1:-1].replace(" ", "")
                valid_chars = [c for c in inner if c in VALID_KEYS]
                if valid_chars:
                    ordered = sort_keys(valid_chars)
                    tokens.append(f"[{''.join(ordered)}]")
            elif tok.startswith("(") and tok.endswith(")"):
                inner = tok[1:-1].replace(" ", "")
                valid_chars = [c for c in inner if c in VALID_KEYS]
                if valid_chars:
                    ordered = sort_keys(valid_chars)
                    tokens.append(f"[{''.join(ordered)}]")
            else:
                for ch in tok:
                    if ch in VALID_KEYS:
                        tokens.append(ch)

    if not tokens:
        return raw_text

    formatted_rows = []
    curr_row = []
    count = 0

    for tok in tokens:
        curr_row.append(tok)
        count += 1
        if count >= tokens_per_line or (tok.startswith("|") and count >= 6):
            formatted_rows.append(" ".join(curr_row))
            curr_row = []
            count = 0

    if curr_row:
        formatted_rows.append(" ".join(curr_row))

    result = ""
    if header_lines:
        result += "\n".join(header_lines) + "\n\n"
    result += "\n".join(formatted_rows)
    return result


def simplify_chords(raw_text, max_keys=2):
    """Menyederhanakan akord tebal menjadi akord ringan (bass + nada tertinggi)."""
    def _simplify_token(m):
        tok = m.group(0)
        if tok.startswith("[") and tok.endswith("]"):
            inner = tok[1:-1].replace(" ", "")
            valid = [c for c in inner if c in VALID_KEYS]
            if len(valid) <= max_keys:
                return tok
            ordered = sort_keys(valid)
            # Ambil nada terendah (bass) dan tertinggi (melodi)
            if max_keys == 1:
                chosen = [ordered[-1]]
            elif max_keys == 2:
                chosen = [ordered[0], ordered[-1]]
            else:
                chosen = [ordered[0]] + ordered[-(max_keys - 1):]
            return f"[{''.join(chosen)}]"
        return tok

    return _TOKEN_RE.sub(_simplify_token, raw_text)


def analyze_sheet_stats(raw_text, bpm=100):
    """Menganalisis statistik sheet: jumlah nada, akord, durasi, kesulitan."""
    total_notes = 0
    total_chords = 0
    total_rests = 0
    black_key_notes = 0
    black_keys_set = {k for _, k in BLACK_KEY_GAPS}

    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for tok in _TOKEN_RE.findall(stripped):
            if all(c in "|.-~_" for c in tok):
                total_rests += len(tok)
            elif (tok.startswith("[") and tok.endswith("]")) or (tok.startswith("(") and tok.endswith(")")):
                inner = tok[1:-1].replace(" ", "")
                valid = [c for c in inner if c in VALID_KEYS]
                if valid:
                    total_chords += 1
                    total_notes += len(valid)
                    black_key_notes += sum(1 for c in valid if c in black_keys_set)
            else:
                for ch in tok:
                    if ch in VALID_KEYS:
                        total_notes += 1
                        if ch in black_keys_set:
                            black_key_notes += 1

    total_steps = total_notes + total_rests
    sec_per_beat = 60.0 / max(20, bpm)
    est_duration_sec = total_steps * sec_per_beat

    # Rating kesulitan 1-5 bintang
    # Faktor: perbandingan nada hitam (Shift), densitas akord, kecepatan
    shift_ratio = (black_key_notes / max(1, total_notes))
    chord_ratio = (total_chords / max(1, (total_notes - total_chords + 1)))

    score = 1
    if total_notes > 150:
        score += 1
    if shift_ratio > 0.15:
        score += 1
    if chord_ratio > 0.25:
        score += 1
    if total_notes > 800 or (shift_ratio > 0.35 and chord_ratio > 0.4):
        score += 1

    score = min(5, max(1, score))
    difficulty_labels = {
        1: ("Pemula", "★☆☆☆☆", "#10b981"),
        2: ("Mudah", "★★☆☆☆", "#38bdf8"),
        3: ("Sedang", "★★★☆☆", "#f59e0b"),
        4: ("Sulit", "★★★★☆", "#ec4899"),
        5: ("Mahir", "★★★★★", "#a855f7"),
    }
    diff_name, diff_stars, diff_color = difficulty_labels[score]

    mins = int(est_duration_sec // 60)
    secs = int(est_duration_sec % 60)
    duration_str = f"{mins}:{secs:02d}"

    return {
        "total_notes": total_notes,
        "total_chords": total_chords,
        "total_rests": total_rests,
        "black_key_notes": black_key_notes,
        "duration_sec": est_duration_sec,
        "duration_str": duration_str,
        "difficulty_level": score,
        "difficulty_name": diff_name,
        "difficulty_stars": diff_stars,
        "difficulty_color": diff_color,
    }
