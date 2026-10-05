"""Audio Engine untuk Roblox Piano Studio.

Menyediakan output audio piano akustik real-time berlatensi ultra-rendah (<5ms)
menggunakan Windows Multimedia API (winmm.dll) dan General MIDI Synthesizer bawaan.
Tanpa memerlukan instalasi dependensi pihak ketiga atau file soundfont tambahan.
"""

import ctypes
import threading
import time
from layouts import build_pitch_map, VALID_KEYS

# MIDI constants
NOTE_ON = 0x90
NOTE_OFF = 0x80
CONTROL_CHANGE = 0xB0
ALL_NOTES_OFF = 123
ALL_SOUND_OFF = 120
PROGRAM_CHANGE = 0xC0


class PianoAudioEngine:
    """Mesin suara piano MIDI Windows dengan polyphony tinggi & note-off scheduler."""

    def __init__(self, base_midi=48):
        self.winmm = None
        self.hmidi = ctypes.c_void_p()
        self.available = False
        self.enabled = True
        self.volume = 0.85  # 0.0 sampai 1.0
        self.base_midi = base_midi
        self._lock = threading.Lock()

        # Build reverse key-to-pitch map
        p2k = build_pitch_map(base_midi)
        self.k2p = {k: p for p, k in p2k.items()}

        self._init_midi()

    def _init_midi(self):
        try:
            self.winmm = ctypes.windll.winmm
            # Open default MIDI output device (-1)
            res = self.winmm.midiOutOpen(ctypes.byref(self.hmidi), -1, 0, 0, 0)
            if res == 0:
                self.available = True
                # Set program 0 (Acoustic Grand Piano) on channel 0
                self.winmm.midiOutShortMsg(self.hmidi, PROGRAM_CHANGE | (0 << 8))
            else:
                self.available = False
        except Exception:
            self.available = False

    def set_enabled(self, enabled: bool):
        """Aktifkan atau matikan suara app."""
        self.enabled = bool(enabled)
        if not self.enabled:
            self.stop_all()

    def set_volume(self, volume: float):
        """Atur volume (0.0 sampai 1.0)."""
        self.volume = max(0.0, min(1.0, float(volume)))

    def is_enabled(self) -> bool:
        return self.enabled and self.available

    def play_key(self, key: str, velocity=95, duration=0.6):
        """Memainkan satu tuts piano berdasarkan karakter (misal '1', 'q', '!', 'Q')."""
        if not self.enabled or not self.available:
            return
        pitch = self.k2p.get(key)
        if pitch is not None:
            self._send_note(pitch, velocity, duration)

    def play_chord(self, keys, velocity=95, duration=0.8):
        """Memainkan beberapa nada sekaligus (akord)."""
        if not self.enabled or not self.available or not keys:
            return
        pitches = [self.k2p[k] for k in keys if k in self.k2p]
        if not pitches:
            return
        adj_vel = int(max(1, min(127, velocity * self.volume)))
        with self._lock:
            for p in pitches:
                msg = NOTE_ON | (p << 8) | (adj_vel << 16)
                self.winmm.midiOutShortMsg(self.hmidi, msg)

        def _release():
            time.sleep(duration)
            with self._lock:
                for p in pitches:
                    msg = NOTE_OFF | (p << 8) | (0 << 16)
                    self.winmm.midiOutShortMsg(self.hmidi, msg)

        threading.Thread(target=_release, daemon=True).start()

    def _send_note(self, pitch: int, velocity=95, duration=0.6):
        adj_vel = int(max(1, min(127, velocity * self.volume)))
        with self._lock:
            msg = NOTE_ON | (pitch << 8) | (adj_vel << 16)
            self.winmm.midiOutShortMsg(self.hmidi, msg)

        def _release():
            time.sleep(duration)
            with self._lock:
                msg = NOTE_OFF | (pitch << 8) | (0 << 16)
                self.winmm.midiOutShortMsg(self.hmidi, msg)

        threading.Thread(target=_release, daemon=True).start()

    def play_metronome(self, accent=False):
        """Bunyi metronome klik/woodblock pada channel perkusi MIDI 9."""
        if not self.enabled or not self.available:
            return
        # Percussion pitch: 76 = High Wood Block, 77 = Low Wood Block (atau 37 = Side Stick)
        pitch = 76 if accent else 77
        vel = int(110 * self.volume) if accent else int(85 * self.volume)
        with self._lock:
            # Channel 9 is 0x09 -> status 0x99 for Note On
            msg = 0x99 | (pitch << 8) | (vel << 16)
            self.winmm.midiOutShortMsg(self.hmidi, msg)

        def _off():
            time.sleep(0.08)
            with self._lock:
                msg = 0x89 | (pitch << 8) | (0 << 16)
                self.winmm.midiOutShortMsg(self.hmidi, msg)

        threading.Thread(target=_off, daemon=True).start()

    def stop_all(self):
        """Hentikan semua nada yang sedang berdering."""
        if not self.available or not self.hmidi:
            return
        with self._lock:
            try:
                # All sound off (CC 120) & All notes off (CC 123)
                self.winmm.midiOutShortMsg(self.hmidi, CONTROL_CHANGE | (ALL_SOUND_OFF << 8))
                self.winmm.midiOutShortMsg(self.hmidi, CONTROL_CHANGE | (ALL_NOTES_OFF << 8))
            except Exception:
                pass

    def close(self):
        """Tutup handle MIDI saat aplikasi ditutup."""
        self.stop_all()
        if self.available and self.hmidi:
            try:
                self.winmm.midiOutClose(self.hmidi)
            except Exception:
                pass
            self.hmidi = None
            self.available = False
