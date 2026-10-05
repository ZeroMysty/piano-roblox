"""Tes cepat: jalankan  python selftest.py
Menguji parser sheet, mapping layout, normalisasi tombol, dan import MIDI.
"""

import os
import tempfile

import mido

from layouts import (build_pitch_map, normalize_key, key_note_name, sort_keys,
                     VALID_KEYS, get_key_press_info)
from sheet import parse_sheet, count_notes
from midi_import import midi_to_steps

FAIL = []


def check(name, cond, detail=""):
    status = "OK " if cond else "FAIL"
    print(f"[{status}] {name} {detail}")
    if not cond:
        FAIL.append(name)


# ---- Parser
steps = parse_sheet("s s h h j j h | g g f f d d s")
check("parse spasi -> 14 nada + 1 jeda", len(steps) == 15 and steps[0][0] == "n"
      and steps[7] == ("r", 1))

steps = parse_sheet("[asdf] [a s d f] asdf")
check("akord [asdf]", steps[0] == ("n", frozenset("asdf")))
check("akord [a s d f] (spasi) juga akord", steps[1] == ("n", frozenset("asdf")))
check("urutan asdf dipecah", [s[1] for s in steps[2:6]] ==
      [frozenset(c) for c in "asdf"])

steps = parse_sheet("[9 $ e] [e T u]")
check("akord dengan huruf besar", steps[0] == ("n", frozenset("9$e")))

steps = parse_sheet("as|df ||  q")
check("jeda gabung + ||", [s for s in steps if s[0] == "r"] == [("r", 1), ("r", 2)])

steps = parse_sheet("a--b")
check("jeda -- di antara nada", steps == [("n", frozenset("a")), ("r", 2), ("n", frozenset("b"))])

steps = parse_sheet("s---")
check("jeda --- setelah nada", steps == [("n", frozenset("s")), ("r", 3)])

steps = parse_sheet("# Judul Lagu\n# komentar juga\ns s h h")
check("baris # diabaikan", len(steps) == 4 and steps[0][1] == frozenset("s"))

steps = parse_sheet("p| s| [qpf4]|||\n[w5]| |[ywoa]| s| [oed6]|||")
check("sheet 2 tangan (format user)", steps[:3] ==
      [("n", frozenset("p")), ("r", 1), ("n", frozenset("s"))]
      and ("n", frozenset("qpf4")) in steps
      and ("r", 3) in steps)

# ---- Layout
p2k = build_pitch_map(48)
check("MIDI C3=48 -> '1'", p2k.get(48) == "1")
check("MIDI C#3=49 -> '!'", p2k.get(49) == "!")
check("MIDI D3=50 -> '2'", p2k.get(50) == "2")
check("MIDI C4=60 -> '8'", p2k.get(60) == "8")
check("MIDI E4=64 -> '0'", p2k.get(64) == "0")
check("MIDI F#4=66 -> 'Q'", p2k.get(66) == "Q")
check("MIDI F#3=54 -> '$'", p2k.get(54) == "$")

check("nama nada 1 = C3", key_note_name("1") == "C3")
check("nama nada ! = C#3", key_note_name("!") == "C#3")
check("sort_keys urutkan seperti piano", sort_keys(list("9$eT")) == ["$", "9", "e", "T"])

# ---- Normalisasi tombol & Info Penekanan (Base Key + Shift)
check("normal a -> a", normalize_key("a", False) == "a")
check("shift+a -> A", normalize_key("a", True) == "A")
check("shift+1 -> !", normalize_key("1", True) == "!")
check("1 -> 1", normalize_key("1", False) == "1")
check("shift+3 -> None (bukan tombol hitam)", normalize_key("3", True) is None)
check("shift+7 -> None", normalize_key("7", True) is None)
check("shift+0 -> None", normalize_key("0", True) is None)
check("karakter langsung diteruskan", normalize_key("!", False) == "!")
check("bukan tombol piano -> None", normalize_key("space", False) is None)

check("press info '1' -> ('1', False)", get_key_press_info("1") == ("1", False))
check("press info '!' -> ('1', True)", get_key_press_info("!") == ("1", True))
check("press info 'q' -> ('q', False)", get_key_press_info("q") == ("q", False))
check("press info 'Q' -> ('q', True)", get_key_press_info("Q") == ("q", True))
check("press info '$' -> ('4', True)", get_key_press_info("$") == ("4", True))


# ---- MIDI
with tempfile.TemporaryDirectory() as tmp:
    mid_path = os.path.join(tmp, "t.mid")
    mid = mido.MidiFile()
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000))
    tr.append(mido.Message("note_on", note=60, velocity=100, time=0))
    tr.append(mido.Message("note_on", note=64, velocity=100, time=0))    # akord C4+E4
    tr.append(mido.Message("note_on", note=62, velocity=100, time=480))  # lalu D4
    tr.append(mido.Message("note_off", note=60, velocity=0, time=480))
    tr.append(mido.Message("note_off", note=64, velocity=0, time=0))
    tr.append(mido.Message("note_off", note=62, velocity=0, time=480))
    mid.save(mid_path)

    steps, skipped, total = midi_to_steps(mid_path, 0)
    check("MIDI akord C4+E4 -> {'8','0'}", steps and steps[0] == ("n", frozenset("80")))
    check("MIDI nada D4 -> {'9'}", len(steps) >= 2 and steps[1] == ("n", frozenset("9")))
    check("MIDI tidak ada yang di-skip", skipped == 0 and total == 3)

    # transpose: naikkan 2 semitone -> C4 jadi D4 ('9'), E4 jadi F#4 ('Q').
    steps2, _, _ = midi_to_steps(mid_path, 2)
    check("MIDI transpose +2", steps2 and steps2[0] == ("n", frozenset("9Q")))

    # analyze_midi test
    from midi_import import analyze_midi, get_transpose_stats, midi_to_sheet_text
    info = analyze_midi(mid_path)
    check("analyze_midi total_notes == 3", info["total_notes"] == 3)
    check("analyze_midi bpm == 120", info["bpm"] == 120)
    check("analyze_midi optimal_transpose == 0", info["optimal_transpose"] == 0)
    check("analyze_midi best_coverage_pct == 100.0", info["best_coverage_pct"] == 100.0)

    playable, skipped, pct = get_transpose_stats(info["events"], 0)
    check("get_transpose_stats 100%", playable == 3 and skipped == 0 and pct == 100.0)

    # Audio Transcriber & midi_import MIDI-to-sheet test
    sheet_text = midi_to_sheet_text(mid_path)
    check("midi_to_sheet_text terkonversi", "[80]" in sheet_text or "[08]" in sheet_text and "9" in sheet_text)


# ---- Lagu bawaan
songs_dir = os.path.join(os.path.dirname(__file__), "songs")
if not os.path.exists(songs_dir) and os.path.exists(os.path.join(os.path.dirname(__file__), "dist", "songs")):
    songs_dir = os.path.join(os.path.dirname(__file__), "dist", "songs")
n = 0
all_valid = True
if os.path.exists(songs_dir):
    for fn in sorted(os.listdir(songs_dir)):
        if fn.endswith(".txt"):
            with open(os.path.join(songs_dir, fn), encoding="utf-8") as f:
                s = parse_sheet(f.read())
            check(f"song {fn} terbaca", len(s) > 0, f"({len(s)} step, {count_notes(s)} nada)")
            for st in s:
                if st[0] == "n" and not st[1] <= VALID_KEYS:
                    all_valid = False
            n += 1
check("semua tombol lagu bawaan valid", all_valid)
check("minimal 5 lagu bawaan", n >= 5)

print()
if FAIL:
    print(f"{len(FAIL)} TES GAGAL: {FAIL}")
    raise SystemExit(1)
print("Semua tes lolos")
