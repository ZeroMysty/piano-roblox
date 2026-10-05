"""Import & Konversi file MIDI -> Sheet Roblox Piano / Steps Autoplayer.

Mendukung analisis MIDI otomatis, auto-detect transpose terbaik untuk range
keyboard Roblox, dan konversi langsung ke teks sheet format Roblox Virtual Piano.
"""

from pathlib import Path
import mido

from layouts import build_pitch_map, sort_keys

CHORD_WINDOW = 0.05       # 50 ms chord tolerance
PAUSE_THRESHOLD = 0.4    # detik jeda sebelum menambahkan '|'


def analyze_midi(path, base_midi=48):
    """Menganalisis file MIDI untuk mendapatkan info nada, durasi, tempo, dan transpose optimal.

    Args:
        path: Path ke file MIDI.
        base_midi: Pitch MIDI untuk nada terendah '1' (default 48 = C3).

    Returns:
        dict: {
            'total_notes': int,
            'duration': float,
            'bpm': int,
            'tempo': int,
            'optimal_transpose': int,
            'best_coverage_pct': float,
            'events': list of (abs_time, pitch),
        }
    """
    mid = mido.MidiFile(path)
    p2k_base = build_pitch_map(base_midi)

    abs_time = 0.0
    events = []
    tempo = 500000  # default 120 bpm (500,000 microseconds per beat)

    for msg in mid:
        abs_time += msg.time
        if msg.type == "set_tempo":
            tempo = msg.tempo
        elif msg.type == "note_on" and msg.velocity > 0 and getattr(msg, "channel", 0) != 9:
            events.append((abs_time, msg.note))

    total_notes = len(events)
    bpm = int(round(mido.tempo2bpm(tempo))) if tempo else 120
    duration = abs_time

    best_transpose = 0
    best_playable = 0

    if total_notes > 0:
        # Prioritaskan transpose 0 jika coverage sudah maksimal
        t0_playable = sum(1 for _, pitch in events if pitch in p2k_base)
        best_playable = t0_playable
        best_transpose = 0

        # Cari semitone dari -36 sampai +36
        for t in range(-36, 37):
            playable = sum(1 for _, pitch in events if (pitch + t) in p2k_base)
            if playable > best_playable:
                best_playable = playable
                best_transpose = t

    coverage_pct = (best_playable / total_notes * 100) if total_notes > 0 else 0.0

    return {
        "total_notes": total_notes,
        "duration": duration,
        "bpm": bpm,
        "tempo": tempo,
        "optimal_transpose": best_transpose,
        "best_coverage_pct": round(coverage_pct, 1),
        "events": events,
    }


def get_transpose_stats(events, transpose, base_midi=48):
    """Menghitung jumlah nada valid dan skip untuk nilai transpose tertentu."""
    p2k = build_pitch_map(base_midi)
    playable = sum(1 for _, pitch in events if (pitch + transpose) in p2k)
    total = len(events)
    skipped = total - playable
    pct = (playable / total * 100) if total > 0 else 0.0
    return playable, skipped, round(pct, 1)


def midi_to_sheet_text(midi_path, transpose=0, base_midi=48, chord_window=CHORD_WINDOW,
                       pause_threshold=PAUSE_THRESHOLD, source_note=None):
    """Konversi file MIDI menjadi teks sheet format Roblox Piano ([chord] a s d f |)."""
    mid = mido.MidiFile(midi_path)
    p2k = build_pitch_map(base_midi)

    events = []
    abs_time = 0.0
    tempo = 500000
    for msg in mid:
        abs_time += msg.time
        if msg.type == "set_tempo":
            tempo = msg.tempo
        elif msg.type == "note_on" and msg.velocity > 0 and getattr(msg, "channel", 0) != 9:
            key = p2k.get(msg.note + transpose)
            if key is not None:
                events.append((abs_time, key))

    if not events:
        return "# Tidak ada nada piano yang terdeteksi dalam range keyboard Roblox."

    # Kelompokkan not yang berdekatan menjadi akord
    groups = []
    curr_t, curr_keys = events[0]
    curr_keys = [events[0][1]]

    for t, key in events[1:]:
        if t - curr_t < chord_window:
            if key not in curr_keys:
                curr_keys.append(key)
        else:
            groups.append((curr_t, list(curr_keys)))
            curr_t = t
            curr_keys = [key]
    groups.append((curr_t, list(curr_keys)))

    if not groups:
        return "# Tidak ada nada yang cocok dengan range layout keyboard Roblox."

    lines = []
    current_line = []
    tokens_in_line = 0
    last_t = groups[0][0]

    for t, keys in groups:
        gap = t - last_t
        if gap >= pause_threshold and current_line:
            current_line.append("|")
            tokens_in_line += 1

        if len(keys) == 1:
            token = keys[0]
        else:
            ordered_keys = sort_keys(keys)
            token = f"[{''.join(ordered_keys)}]"

        current_line.append(token)
        tokens_in_line += 1
        last_t = t

        if tokens_in_line >= 12:
            lines.append(" ".join(current_line))
            current_line = []
            tokens_in_line = 0

    if current_line:
        lines.append(" ".join(current_line))

    song_title = Path(midi_path).stem.replace("_transcribed", "")
    bpm_info = f" (BPM: ~{int(round(mido.tempo2bpm(tempo)))})" if tempo else ""
    transpose_info = f" [Transpose: {transpose:+d}]" if transpose != 0 else ""
    note_info = f"\n# {source_note}" if source_note else ""
    header = f"# Sheet Roblox Piano: {song_title}{bpm_info}{transpose_info}{note_info}\n\n"
    return header + "\n".join(lines)


def midi_to_steps(path, transpose=0, base_midi=48):
    """Baca file MIDI -> (steps, jumlah_nada_di_skip, total_nada)."""
    mid = mido.MidiFile(path)
    p2k = build_pitch_map(base_midi)

    events = []
    abs_time = 0.0
    for msg in mid:
        abs_time += msg.time
        if msg.type == "note_on" and msg.velocity > 0 and getattr(msg, "channel", 0) != 9:
            events.append((abs_time, msg.note))

    if not events:
        return [], 0, 0

    steps = []
    group = []
    group_t = events[0][0]
    skipped = 0

    for t, pitch in events:
        key = p2k.get(pitch + transpose)
        if key is None:
            skipped += 1
            continue
        if t - group_t < CHORD_WINDOW:
            group.append(key)
        else:
            steps.append(("n", frozenset(group)))
            group = [key]
            group_t = t

    if group:
        steps.append(("n", frozenset(group)))

    return steps, skipped, len(events)
