"""Roblox Piano Studio Pro — Ultra Sleek, Fast & Clean.

Sistem Autoplayer, Follower & Virtual Piano Studio untuk Roblox Piano:
  - Audio Engine: Synthesizer Grand Piano berlatensi ultra-rendah (<5ms) bawaan Windows.
  - Interactive 61-Key Piano: Tuts piano interaktif yang dapat diklik & menampilkan highlight akord.
  - Smart Musical Rhythm: Auto Player berirama dinamis alami (chords sustain, arpeggios mengalir cepat, jeda bernafas natural seperti PlayPianoSheets).
  - Visual Sheet Display: Format notation tile real-time dengan status benar/salah & auto-scrolling.
  - Performance HUD: Pelacak akurasi, streak/combo counter, metronome & progress durasi.
  - Song Library: Katalog lagu lengkap (Anime, Pop, Klasik, Game) dengan pencarian instan & audio preview.
  - Sheet Tools: Transpose instan (semitone/oktaf), perapih sheet (beautifier), dan simplifikasi akord.
  - Roblox Integration: Deteksi otomatis fokus Roblox, shortcut F6 global & hotkey tahan not '+'.
  - Window Mode: Always on Top (Pin) & Mini-Overlay mode untuk kenyamanan split screen.
"""

import ctypes
import json
import queue
import re
import sys
import threading
import time
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk
    import keyboard
except ImportError as exc:
    print("Gagal memuat modul:", exc)
    sys.exit(1)

from layouts import (
    WHITE_KEYS, BLACK_KEY_GAPS, VALID_KEYS, WHITE_INDEX, BLACK_INDEX,
    sort_keys, key_note_name, get_key_press_info, get_vk_code,
    win_press_vk, win_release_vk, VK_SHIFT, normalize_key
)
from audio_engine import PianoAudioEngine
from sheet_tools import transpose_sheet_text, beautify_sheet, simplify_chords, analyze_sheet_stats
from song_library import SongLibrary, clean_display_title

if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent

CONFIG_PATH = APP_DIR / "config.json"
SONGS_DIR = APP_DIR / "songs"
if not SONGS_DIR.exists() and (APP_DIR / "dist" / "songs").exists():
    SONGS_DIR = APP_DIR / "dist" / "songs"

# ---------------------------------------------------------------------------
# Visual Theme — Premium Sleek Studio Palette
# ---------------------------------------------------------------------------
BG            = "#07090e"    # Midnight Space
PANEL_BG      = "#0d111a"    # Studio Panel Background
CARD_BG       = "#131a26"    # Button / Card Normal
CARD_HOVER    = "#1d273a"    # Button Hover
CARD_ACTIVE   = "#0b1018"    # Button Clicked
CARD_BORDER   = "#232e42"    # Sleek Subdued Border
ACCENT_CYAN   = "#06b6d4"    # Vibrant Cyan Accent
ACCENT_BLUE   = "#38bdf8"    # Sky Blue Accent
ACCENT_PURPLE = "#a855f7"    # Neon Purple Accent
ACCENT_AMBER  = "#f59e0b"    # Golden Amber Accent
ACCENT_ROSE   = "#f43f5e"    # Rose Accent
TEXT_WHITE    = "#f8fafc"    # High-contrast Crisp White
TEXT_MUTED    = "#94a3b8"    # Subdued Gray
TEXT_DIM      = "#64748b"    # Slate Gray

COLOR_UNPRESSED = "#cbd5e1"   # Soft White: belum ditekan
COLOR_CORRECT   = "#10b981"   # Emerald Green: benar
COLOR_WRONG     = "#f43f5e"   # Bright Rose: salah
COLOR_ACTIVE_BG = "#0284c7"   # Kotak Biru not aktif
COLOR_SEP       = "#475569"   # Abu-abu separator (| -)
FONT            = "Segoe UI"


# ---------------------------------------------------------------------------
# Roblox Focus Detection
# ---------------------------------------------------------------------------
def _is_roblox_focused():
    """Return True jika jendela aktif (foreground) adalah Roblox."""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return False
        buf_len = ctypes.windll.user32.GetWindowTextLengthW(hwnd) + 1
        buf = ctypes.create_unicode_buffer(buf_len)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, buf_len)
        return "roblox" in buf.value.lower()
    except Exception:
        return False


# Tracking key buatan kita agar tidak memicu hook follower
_injected_keys: dict = {}
_injected_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Smart Musical Display Tokenizer (Dynamic Rhythm Weights)
# ---------------------------------------------------------------------------
_DISP_TOKEN_RE = re.compile(r'\[[^\]]*\]|\{[^}]*\}|\([^)]*\)|[|.\-~_]+|[^\s|.\-~_\[\](){}]+')


def build_display_tokens(raw_text, rhythm_mode="presisi"):
    """Parse raw sheet text menjadi display rows & playable steps dengan timing presisi PlayPianoSheets."""
    steps = []
    display_rows = []

    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip() and not ln.strip().startswith("#")]

    for line in lines:
        raw_toks = _DISP_TOKEN_RE.findall(line)
        n = len(raw_toks)
        row_tokens = []

        for i, tok in enumerate(raw_toks):
            is_sep = all(c in "|.-~_" for c in tok)
            is_chord = (tok.startswith("[") and tok.endswith("]")) or (tok.startswith("(") and tok.endswith(")"))
            is_fast = (tok.startswith("{") and tok.endswith("}"))

            if is_sep:
                step_idx = len(steps)
                w = float(len(tok))
                steps.append(("r", len(tok), w))
                row_tokens.append({"text": tok, "step_idx": step_idx, "is_sep": True})

            elif is_chord:
                # Bersihkan spasi dan strip tanda hubung di dalam kurung akord (mis. [p-9-d-g])
                inner = tok[1:-1].replace(" ", "")
                keys = frozenset(ch for ch in inner if ch in VALID_KEYS)
                if keys:
                    step_idx = len(steps)
                    w = 1.0
                    steps.append(("n", keys, w))
                    row_tokens.append({"text": tok, "step_idx": step_idx, "is_sep": False})

            elif is_fast:
                # Fast sequence dalam kurung kurawal {abc} (50ms per key)
                inner = tok[1:-1].replace(" ", "")
                keys = [ch for ch in inner if ch in VALID_KEYS]
                if keys:
                    step_idx = len(steps)
                    w = 0.25 * len(keys)
                    steps.append(("n", frozenset(keys), w))
                    row_tokens.append({"text": tok, "step_idx": step_idx, "is_sep": False})

            else:
                # Single notes atau rangkaian tanpa spasi (misal: asdf)
                if len(tok) > 1:
                    # Rangkaian rapat tanpa spasi = urutan cepat (ornamen / run)
                    for ch in tok:
                        if ch in VALID_KEYS:
                            step_idx = len(steps)
                            w = 0.5
                            steps.append(("n", frozenset([ch]), w))
                            row_tokens.append({"text": ch, "step_idx": step_idx, "is_sep": False})
                else:
                    ch = tok
                    if ch in VALID_KEYS:
                        step_idx = len(steps)
                        w = 1.0
                        steps.append(("n", frozenset([ch]), w))
                        row_tokens.append({"text": ch, "step_idx": step_idx, "is_sep": False})

        if row_tokens:
            display_rows.append(row_tokens)

    return display_rows, steps


def _find_active_note_step(steps, current_pos):
    pos = current_pos
    while pos < len(steps):
        if steps[pos][0] == "n":
            return pos
        pos += 1
    return -1


# ---------------------------------------------------------------------------
# UI Helper Functions & Custom Widgets
# ---------------------------------------------------------------------------
def round_rect(cv, x0, y0, x1, y1, r, **kw):
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y0 + r, x0, y0]
    return cv.create_polygon(pts, smooth=True, **kw)


class RoundedButton(tk.Canvas):
    """Tombol Custom Modern & Ringan dengan State Hover/Active/Pulse."""
    def __init__(self, parent, text="", command=None, width=80, height=34,
                 bg_color=CARD_BG, hover_color=CARD_HOVER, active_bg=CARD_ACTIVE,
                 fg_color=TEXT_WHITE, border_color=CARD_BORDER, active_border=None,
                 font=(FONT, 9, "bold"), radius=6, is_active=False, **kwargs):
        super().__init__(parent, width=width, height=height, bg=parent["bg"],
                         highlightthickness=0, bd=0, cursor="hand2", **kwargs)
        self.command = command
        self.text = text
        self.w = width
        self.h = height
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.active_bg = active_bg
        self.fg_color = fg_color
        self.border_color = border_color
        self.active_border = active_border
        self.font = font
        self.radius = radius
        self.is_hovered = False
        self.is_pressed = False
        self.is_active = is_active

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._draw()

    def set_active(self, active, active_border=ACCENT_BLUE):
        self.is_active = active
        if active_border:
            self.active_border = active_border
        self._draw()

    def set_text(self, text, fg_color=None):
        self.text = text
        if fg_color:
            self.fg_color = fg_color
        self._draw()

    def _on_enter(self, _e):
        self.is_hovered = True
        self._draw()

    def _on_leave(self, _e):
        self.is_hovered = False
        self.is_pressed = False
        self._draw()

    def _on_press(self, _e):
        self.is_pressed = True
        self._draw()

    def _on_release(self, event):
        if self.is_pressed:
            self.is_pressed = False
            self._draw()
            if 0 <= event.x <= self.w and 0 <= event.y <= self.h:
                if self.command:
                    self.command()

    def _draw(self):
        self.delete("all")
        bg = self.active_bg if self.is_pressed else (self.hover_color if self.is_hovered else self.bg_color)
        border = self.active_border if (self.is_active and self.active_border) else self.border_color
        border_w = 2 if (self.is_active and self.active_border) else 1
        round_rect(self, 2, 2, self.w - 2, self.h - 2, self.radius, fill=bg, outline=border, width=border_w)
        fg = (self.active_border or self.fg_color) if self.is_active else self.fg_color
        self.create_text(self.w / 2, self.h / 2, text=self.text, font=self.font, fill=fg)


# ---------------------------------------------------------------------------
# Interactive 61-Key Virtual Piano Keyboard Component
# ---------------------------------------------------------------------------
class VirtualPianoKeyboardCanvas(tk.Canvas):
    """Keyboard Virtual Piano 61-Key interaktif (clickable + highlight akord + label ganda)."""
    def __init__(self, parent, on_key_click=None, bg="#06080c", **kwargs):
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0, height=72, **kwargs)
        self.on_key_click = on_key_click
        self.active_keys = set()
        self.flashing_keys = {}
        self.label_mode = "key"

        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<Button-1>", self._on_canvas_click)

    def set_active_keys(self, active_keys):
        self.active_keys = set(active_keys or [])
        self.redraw()

    def flash_key(self, key, color=COLOR_CORRECT, duration_ms=250):
        self.flashing_keys[key] = color
        self.redraw()
        def _clear():
            self.flashing_keys.pop(key, None)
            self.redraw()
        self.after(duration_ms, _clear)

    def set_label_mode(self, mode):
        self.label_mode = mode
        self.redraw()

    def _get_key_at_pos(self, x, y):
        w = max(self.winfo_width(), 300)
        h = max(self.winfo_height(), 50)
        num_white = len(WHITE_KEYS)
        pad_x = 10
        usable_w = w - (2 * pad_x)
        kw = usable_w / num_white
        kh_white = h - 6
        kh_black = int(kh_white * 0.62)
        bw = max(6, kw * 0.65)

        if y <= 3 + kh_black:
            for gap, key in BLACK_KEY_GAPS:
                if gap < num_white - 1:
                    x_center = pad_x + (gap + 1) * kw
                    if (x_center - bw / 2) <= x <= (x_center + bw / 2):
                        return key

        if 0 <= y <= 3 + kh_white:
            idx = int((x - pad_x) // kw)
            if 0 <= idx < num_white:
                return WHITE_KEYS[idx]
        return None

    def _on_canvas_click(self, event):
        key = self._get_key_at_pos(event.x, event.y)
        if key and self.on_key_click:
            self.flash_key(key, color=ACCENT_CYAN, duration_ms=180)
            self.on_key_click(key)

    def redraw(self):
        self.delete("all")
        w = max(self.winfo_width(), 300)
        h = max(self.winfo_height(), 50)

        num_white = len(WHITE_KEYS)
        pad_x = 10
        usable_w = w - (2 * pad_x)
        kw = max(8, usable_w / num_white)
        kh_white = h - 6
        kh_black = int(kh_white * 0.62)
        bw = max(5, kw * 0.66)

        # 1. Gambar Tombol Putih
        for i, key in enumerate(WHITE_KEYS):
            x0 = pad_x + i * kw
            x1 = x0 + kw - 1
            y0 = 3
            y1 = y0 + kh_white

            is_act = key in self.active_keys
            is_flash = key in self.flashing_keys

            if is_flash:
                fill_col = self.flashing_keys[key]
                border_col = "#ffffff"
            elif is_act:
                fill_col = ACCENT_CYAN
                border_col = "#7dd3fc"
            else:
                fill_col = "#1a2230"
                border_col = "#2a374a"

            round_rect(self, x0, y0, x1, y1, r=3, fill=fill_col, outline=border_col, width=1)

            note_name = key_note_name(key)
            if note_name.startswith("C") and not "#" in note_name:
                self.create_text(x0 + kw / 2, y1 - 4, text=note_name, font=(FONT, 6, "bold"), fill=ACCENT_AMBER)

            if self.label_mode != "none" and kw >= 12:
                lbl_col = "#ffffff" if (is_act or is_flash) else "#94a3b8"
                font_sz = 7 if kw < 18 else 8

                if self.label_mode == "key":
                    txt = key
                elif self.label_mode == "note":
                    txt = note_name
                elif self.label_mode == "both":
                    txt = f"{key}\n{note_name}"
                else:
                    txt = key

                y_pos = y1 - 16 if self.label_mode == "both" else y1 - 14
                self.create_text(x0 + kw / 2, y_pos, text=txt, font=(FONT, font_sz, "bold"), fill=lbl_col)

        # 2. Gambar Tombol Hitam
        for gap, key in BLACK_KEY_GAPS:
            if gap < num_white - 1:
                x_center = pad_x + (gap + 1) * kw
                x0 = x_center - bw / 2
                x1 = x_center + bw / 2
                y0 = 3
                y1 = y0 + kh_black

                is_act = key in self.active_keys
                is_flash = key in self.flashing_keys

                if is_flash:
                    fill_col = self.flashing_keys[key]
                    border_col = "#ffffff"
                elif is_act:
                    fill_col = ACCENT_PURPLE
                    border_col = "#e9d5ff"
                else:
                    fill_col = "#070a10"
                    border_col = "#1b2535"

                round_rect(self, x0, y0, x1, y1, r=2, fill=fill_col, outline=border_col, width=1)

                if self.label_mode != "none" and bw >= 8:
                    lbl_col = "#ffffff" if (is_act or is_flash) else "#cbd5e1"
                    txt = key if self.label_mode in ("key", "both") else key_note_name(key)
                    self.create_text(x_center, y0 + 10, text=txt, font=(FONT, 7, "bold"), fill=lbl_col)


# ---------------------------------------------------------------------------
# Visual Sheet Canvas — Modern, Clean & High Performance
# ---------------------------------------------------------------------------
class VisualSheetCanvas(tk.Canvas):
    """Menampilkan sheet interaktif persis format teks dengan active row banner & glowing token."""
    ROW_H  = 54
    PAD_X  = 16
    CHAR_W = 12
    MIN_W  = 34
    GAP    = 8

    def __init__(self, parent, bg="#06080c", **kwargs):
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0, **kwargs)
        self.display_rows = []
        self.active_step_idx = -1
        self.step_status = {}
        self.total_steps = 0
        self.song_title = ""
        self._last_draw_key = None
        self.bind("<Configure>", lambda _e: self.redraw(force=True))

    def set_data(self, display_rows, active_step_idx=-1, step_status=None, total_steps=0, song_title=""):
        self.display_rows = display_rows
        self.active_step_idx = active_step_idx
        self.step_status = step_status or {}
        self.total_steps = total_steps
        self.song_title = song_title
        self.redraw(force=True)

    def _token_w(self, text):
        return max(self.MIN_W, len(text) * self.CHAR_W + 18)

    def redraw(self, force=False):
        draw_key = (id(self.display_rows), self.active_step_idx, len(self.step_status),
                     self.winfo_width(), self.winfo_height(), self.song_title)
        if not force and draw_key == self._last_draw_key:
            return
        self._last_draw_key = draw_key

        self.delete("all")
        w = max(self.winfo_width(), 300)
        h = max(self.winfo_height(), 200)

        # Top Progress Bar
        if self.total_steps > 0 and self.active_step_idx >= 0:
            pct = min(1.0, max(0.0, (self.active_step_idx + 1) / self.total_steps))
            self.create_rectangle(0, 0, w, 4, fill="#131b26", width=0)
            if pct > 0:
                self.create_rectangle(0, 0, w * pct, 4, fill=ACCENT_CYAN, width=0)

        if not self.display_rows:
            self.create_text(
                w / 2, h / 2 - 12,
                text="Pilih lagu di Library (Katalog Lagu) atau paste sheet baru.",
                font=(FONT, 12, "bold"), fill=TEXT_MUTED, justify="center"
            )
            self.create_text(
                w / 2, h / 2 + 18,
                text="Klik tombol 'Library' di header atas untuk membuka puluhan lagu populer.",
                font=(FONT, 9), fill=TEXT_DIM, justify="center"
            )
            return

        # Cari baris aktif
        active_row_idx = 0
        for ri, row in enumerate(self.display_rows):
            for tok in row:
                if not tok["is_sep"] and tok["step_idx"] == self.active_step_idx:
                    active_row_idx = ri
                    break
            else:
                continue
            break

        start_y = h / 2 - active_row_idx * self.ROW_H - self.ROW_H / 2

        # Active Row Banner Highlight
        active_y_center = start_y + active_row_idx * self.ROW_H
        round_rect(self, 8, active_y_center - 23, w - 8, active_y_center + 23, r=8,
                   fill="#0e1624", outline="#1c2a3f", width=1)

        # Garis pembagi grid yang halus
        num_lines = int(h / self.ROW_H) + 3
        for i in range(-1, num_lines + 2):
            y_line = start_y + (i - 0.5) * self.ROW_H
            self.create_line(0, y_line, w, y_line, fill="#101520", width=1)

        # Gambar Tokens
        for ri, row in enumerate(self.display_rows):
            y_center = start_y + ri * self.ROW_H

            if y_center + self.ROW_H < 0 or y_center - self.ROW_H > h:
                continue

            total_w = sum(self._token_w(tok["text"]) for tok in row) + self.GAP * (len(row) - 1)
            x = (w - total_w) / 2 if total_w + 2 * self.PAD_X <= w else self.PAD_X

            for tok in row:
                tw = self._token_w(tok["text"])
                x_center = x + tw / 2
                x += tw + self.GAP

                step_idx = tok["step_idx"]
                if tok["is_sep"]:
                    self.create_text(x_center, y_center, text=tok["text"],
                                     font=("Consolas", 13, "bold"), fill=COLOR_SEP)
                    continue

                if step_idx == self.active_step_idx:
                    round_rect(self, x_center - tw / 2, y_center - 20,
                               x_center + tw / 2, y_center + 20, 6,
                               fill=COLOR_ACTIVE_BG, outline=ACCENT_CYAN, width=2)
                    self.create_text(x_center, y_center, text=tok["text"],
                                     font=("Consolas", 14, "bold"), fill="#ffffff")
                elif step_idx is not None and step_idx < self.active_step_idx:
                    status = self.step_status.get(step_idx, "correct")
                    color = COLOR_CORRECT if status == "correct" else COLOR_WRONG
                    self.create_text(x_center, y_center, text=tok["text"],
                                     font=("Consolas", 13, "bold"), fill=color)
                else:
                    self.create_text(x_center, y_center, text=tok["text"],
                                     font=("Consolas", 13, "bold"), fill=COLOR_UNPRESSED)


# ---------------------------------------------------------------------------
# Modal Dialog: Song Library
# ---------------------------------------------------------------------------
class SongLibraryModal(tk.Toplevel):
    """Dialog browser lagu canggih dengan pencarian instan, kategori, info kesulitan & audio preview."""
    def __init__(self, parent, library: SongLibrary, audio_engine: PianoAudioEngine, on_load_song):
        super().__init__(parent)
        self.library = library
        self.audio = audio_engine
        self.on_load_song = on_load_song
        self.current_preview_thread = None
        self.is_previewing = False

        self.title("Katalog Lagu Studio — Roblox Piano")
        self.configure(bg=PANEL_BG)
        self.geometry("780x520")
        self.minsize(680, 440)
        self.transient(parent)
        self.grab_set()

        x = parent.winfo_x() + (parent.winfo_width() - 780) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 520) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self.current_cat = "Semua"
        self.selected_item = None

        self._build_ui()
        self._refresh_list()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        header = tk.Frame(self, bg=PANEL_BG)
        header.pack(fill="x", padx=18, pady=(14, 8))

        tk.Label(header, text="Koleksi Sheet Lagu Piano", bg=PANEL_BG, fg=TEXT_WHITE,
                 font=(FONT, 13, "bold")).pack(side="left")
        tk.Label(header, text="Pilih lagu untuk langsung dimainkan atau dengarkan cuplikan audio.",
                 bg=PANEL_BG, fg=TEXT_DIM, font=(FONT, 9)).pack(side="left", padx=(10, 0))

        # Search Bar
        search_box = tk.Frame(self, bg=PANEL_BG)
        search_box.pack(fill="x", padx=18, pady=(0, 8))

        tk.Label(search_box, text="Cari:", bg=PANEL_BG, fg=TEXT_MUTED, font=(FONT, 9, "bold")).pack(side="left", padx=(0, 6))
        self.entry_search = tk.Entry(search_box, font=(FONT, 10), bg=CARD_BG, fg=TEXT_WHITE,
                                     insertbackground=TEXT_WHITE, bd=0, highlightthickness=1,
                                     highlightcolor=ACCENT_CYAN, highlightbackground=CARD_BORDER)
        self.entry_search.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 6))
        self.entry_search.bind("<KeyRelease>", lambda _e: self._refresh_list())

        RoundedButton(search_box, text="Clear", command=self._clear_search, width=60, height=28, font=(FONT, 8))\
            .pack(side="left", padx=2)

        # Categories
        cat_frame = tk.Frame(self, bg=PANEL_BG)
        cat_frame.pack(fill="x", padx=18, pady=(0, 10))

        self.cat_buttons = {}
        categories = ["Semua", "Favorit", "Anime & Game", "Cinema & OST", "Klasik", "Pop & Hits", "Pemula"]
        for cat in categories:
            btn = RoundedButton(cat_frame, text=cat, command=lambda c=cat: self._set_category(c),
                                width=max(60, len(cat) * 9 + 18), height=28, font=(FONT, 8, "bold"),
                                is_active=(cat == "Semua"))
            btn.pack(side="left", padx=2)
            self.cat_buttons[cat] = btn

        # Main Split Content
        main_content = tk.Frame(self, bg=PANEL_BG)
        main_content.pack(fill="both", expand=True, padx=18, pady=(0, 10))

        # Left Column: Song List
        left_frame = tk.Frame(main_content, bg=CARD_BORDER, bd=1)
        left_frame.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(left_frame)
        scrollbar.pack(side="right", fill="y")

        self.listbox = tk.Listbox(left_frame, bg=CARD_BG, fg=TEXT_WHITE, font=(FONT, 10),
                                  selectbackground=ACCENT_BLUE, selectforeground="#ffffff",
                                  bd=0, highlightthickness=0, yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", self._on_select_song)
        self.listbox.bind("<Double-Button-1>", lambda _e: self._load_current_selection())

        # Right Column: Details Card
        self.right_card = tk.Frame(main_content, bg=CARD_BG, bd=1, relief="solid", width=340)
        self.right_card.pack(side="right", fill="both", padx=(10, 0))
        self.right_card.pack_propagate(False)

        self._build_details_card()

        # Bottom Bar
        dock = tk.Frame(self, bg=PANEL_BG)
        dock.pack(fill="x", padx=18, pady=(4, 14))

        RoundedButton(dock, text="Buka Folder Songs", command=self._open_folder, width=140, height=32, font=(FONT, 9))\
            .pack(side="left", padx=3)
        RoundedButton(dock, text="Tutup", command=self._on_close, width=70, height=32, font=(FONT, 9))\
            .pack(side="right", padx=3)

    def _build_details_card(self):
        pad = tk.Frame(self.right_card, bg=CARD_BG)
        pad.pack(fill="both", expand=True, padx=14, pady=12)

        self.lbl_det_title = tk.Label(pad, text="Pilih Lagu", bg=CARD_BG, fg=TEXT_WHITE,
                                      font=(FONT, 12, "bold"), wraplength=310, justify="left")
        self.lbl_det_title.pack(anchor="w")

        self.lbl_det_stars = tk.Label(pad, text="", bg=CARD_BG, fg=ACCENT_AMBER, font=(FONT, 10, "bold"))
        self.lbl_det_stars.pack(anchor="w", pady=(2, 6))

        self.stats_frame = tk.Frame(pad, bg=CARD_BG)
        self.stats_frame.pack(fill="x", pady=4)

        self.lbl_stat_bpm = tk.Label(self.stats_frame, text="BPM: -", bg=CARD_BG, fg=TEXT_MUTED, font=(FONT, 8))
        self.lbl_stat_bpm.grid(row=0, column=0, sticky="w", padx=(0, 14), pady=2)

        self.lbl_stat_notes = tk.Label(self.stats_frame, text="Total Not: -", bg=CARD_BG, fg=TEXT_MUTED, font=(FONT, 8))
        self.lbl_stat_notes.grid(row=0, column=1, sticky="w", pady=2)

        self.lbl_stat_chords = tk.Label(self.stats_frame, text="Akord: -", bg=CARD_BG, fg=TEXT_MUTED, font=(FONT, 8))
        self.lbl_stat_chords.grid(row=1, column=0, sticky="w", padx=(0, 14), pady=2)

        self.lbl_stat_dur = tk.Label(self.stats_frame, text="Durasi: -", bg=CARD_BG, fg=TEXT_MUTED, font=(FONT, 8))
        self.lbl_stat_dur.grid(row=1, column=1, sticky="w", pady=2)

        tk.Label(pad, text="Preview Notasi:", bg=CARD_BG, fg=TEXT_DIM, font=(FONT, 8, "bold")).pack(anchor="w", pady=(8, 2))
        self.txt_preview = tk.Text(pad, bg="#0a0e16", fg=TEXT_WHITE, font=("Consolas", 9),
                                   bd=0, height=7, wrap="word", highlightthickness=1,
                                   highlightbackground=CARD_BORDER)
        self.txt_preview.pack(fill="x", pady=(0, 10))

        btn_box = tk.Frame(pad, bg=CARD_BG)
        btn_box.pack(fill="x", side="bottom")

        self.btn_load_now = RoundedButton(btn_box, text="Mainkan", command=self._load_current_selection,
                                          width=90, height=32, fg_color=COLOR_CORRECT, font=(FONT, 9, "bold"))
        self.btn_load_now.pack(side="left", padx=2)

        self.btn_preview_audio = RoundedButton(btn_box, text="Dengarkan", command=self._toggle_audio_preview,
                                               width=95, height=32, fg_color=ACCENT_CYAN, font=(FONT, 9, "bold"))
        self.btn_preview_audio.pack(side="left", padx=2)

        self.btn_fav_toggle = RoundedButton(btn_box, text="Fav", command=self._toggle_fav_selected,
                                            width=50, height=32, fg_color=ACCENT_AMBER, font=(FONT, 9, "bold"))
        self.btn_fav_toggle.pack(side="left", padx=2)

    def _clear_search(self):
        self.entry_search.delete(0, "end")
        self._refresh_list()

    def _set_category(self, cat):
        self.current_cat = cat
        for c, btn in self.cat_buttons.items():
            btn.set_active(c == cat)
        self._refresh_list()

    def _refresh_list(self):
        q = self.entry_search.get().strip()
        items = self.library.filter(query=q, category=self.current_cat)
        self.filtered_items = items

        self.listbox.delete(0, "end")
        for item in items:
            fav_star = "[*] " if item["is_fav"] else "    "
            stars = item["stats"]["difficulty_stars"]
            bpm = item["bpm"]
            self.listbox.insert("end", f"{fav_star}{item['title']}  •  ~{bpm} BPM  {stars}")

        if items:
            self.listbox.selection_set(0)
            self._on_select_song()
        else:
            self.selected_item = None
            self.lbl_det_title.configure(text="Tidak Ada Lagu Cocok")
            self.lbl_det_stars.configure(text="")
            self.txt_preview.delete("1.0", "end")

    def _on_select_song(self, _e=None):
        sel = self.listbox.curselection()
        if not sel or sel[0] >= len(self.filtered_items):
            return
        item = self.filtered_items[sel[0]]
        self.selected_item = item

        st = item["stats"]
        self.lbl_det_title.configure(text=item["title"])
        self.lbl_det_stars.configure(text=f"{st['difficulty_stars']} ({st['difficulty_name']})", fg=st["difficulty_color"])
        self.lbl_stat_bpm.configure(text=f"BPM: ~{item['bpm']}")
        self.lbl_stat_notes.configure(text=f"Total Not: {st['total_notes']}")
        self.lbl_stat_chords.configure(text=f"Akord: {st['total_chords']}")
        self.lbl_stat_dur.configure(text=f"Durasi: ~{st['duration_str']}")

        self.txt_preview.delete("1.0", "end")
        snippet = "\n".join(item["content"].splitlines()[:15])
        self.txt_preview.insert("1.0", snippet)

        fav_label = "Unfav" if item["is_fav"] else "Fav"
        self.btn_fav_toggle.set_text(fav_label)

    def _toggle_fav_selected(self):
        if not self.selected_item:
            return
        fn = self.selected_item["filename"]
        new_fav = self.library.toggle_favorite(fn)
        self.btn_fav_toggle.set_text("Unfav" if new_fav else "Fav")
        self._refresh_list()

    def _toggle_audio_preview(self):
        if self.is_previewing:
            self.is_previewing = False
            self.btn_preview_audio.set_text("Dengarkan", fg_color=ACCENT_CYAN)
            if self.audio:
                self.audio.stop_all()
            return

        if not self.selected_item:
            return

        self.is_previewing = True
        self.btn_preview_audio.set_text("Stop", fg_color=ACCENT_ROSE)

        content = self.selected_item["content"]
        bpm = self.selected_item["bpm"]

        t = self.selected_item.get("transpose", 0)
        if self.audio:
            self.audio.set_transpose(t)

        def _preview_worker():
            _, steps = build_display_tokens(content, rhythm_mode="presisi")
            base_delay = 60.0 / max(30, bpm)
            for step in steps[:28]:
                if not self.is_previewing:
                    break
                w = step[2] if len(step) > 2 else 1.0
                step_dur = max(0.04, base_delay * w)

                if step[0] == "n":
                    keys = list(step[1])
                    if self.audio and self.audio.is_enabled():
                        self.audio.play_chord(keys, velocity=95)
                time.sleep(step_dur)

            self.is_previewing = False
            try:
                self.after(0, lambda: self.btn_preview_audio.set_text("Dengarkan", fg_color=ACCENT_CYAN))
            except Exception:
                pass

        threading.Thread(target=_preview_worker, daemon=True).start()

    def _load_current_selection(self):
        if not self.selected_item:
            return
        self.is_previewing = False
        if self.audio:
            self.audio.stop_all()
        self.on_load_song(self.selected_item["content"], self.selected_item["bpm"],
                          self.selected_item["title"], self.selected_item.get("transpose", 0))
        self.destroy()

    def _open_folder(self):
        import os
        os.startfile(str(self.library.songs_dir))

    def _on_close(self):
        self.is_previewing = False
        if self.audio:
            self.audio.stop_all()
        self.destroy()


# ---------------------------------------------------------------------------
# Modal Dialog: Sheet Tools
# ---------------------------------------------------------------------------
class SheetToolsModal(tk.Toplevel):
    """Dialog utilitas lengkap: Transpose real-time, beautify format, & simplifikasi akord."""
    def __init__(self, parent, current_text, on_apply_sheet):
        super().__init__(parent)
        self.raw_text = current_text
        self.on_apply_sheet = on_apply_sheet
        self.current_transpose = 0

        self.title("Sheet Tools & Transpose")
        self.configure(bg=PANEL_BG)
        self.geometry("640x480")
        self.minsize(540, 400)
        self.transient(parent)
        self.grab_set()

        x = parent.winfo_x() + (parent.winfo_width() - 640) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 480) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self._build_ui()

    def _build_ui(self):
        header = tk.Frame(self, bg=PANEL_BG)
        header.pack(fill="x", padx=16, pady=(12, 6))

        tk.Label(header, text="Alat Bantu Sheet Piano", bg=PANEL_BG, fg=TEXT_WHITE,
                 font=(FONT, 12, "bold")).pack(side="left")

        # Transpose
        tr_card = tk.Frame(self, bg=CARD_BG, bd=1, relief="solid")
        tr_card.pack(fill="x", padx=16, pady=6)

        tk.Label(tr_card, text="TRANSPOSE NADA (SEMITONE / OKTAF)", bg=CARD_BG, fg=TEXT_DIM,
                 font=(FONT, 8, "bold")).pack(anchor="w", padx=12, pady=(8, 4))

        tr_row = tk.Frame(tr_card, bg=CARD_BG)
        tr_row.pack(fill="x", padx=12, pady=(0, 8))

        RoundedButton(tr_row, text="-12", command=lambda: self._shift_transpose(-12), width=40, height=28, font=(FONT, 8)).pack(side="left", padx=2)
        RoundedButton(tr_row, text="-3", command=lambda: self._shift_transpose(-3), width=35, height=28, font=(FONT, 8)).pack(side="left", padx=2)
        RoundedButton(tr_row, text="-1", command=lambda: self._shift_transpose(-1), width=35, height=28, font=(FONT, 8)).pack(side="left", padx=2)

        self.lbl_tr_val = tk.Label(tr_row, text="Transpose: 0 semitone", bg=CARD_BG, fg=TEXT_WHITE,
                                   font=(FONT, 9, "bold"), width=22)
        self.lbl_tr_val.pack(side="left", padx=4)

        RoundedButton(tr_row, text="+1", command=lambda: self._shift_transpose(1), width=35, height=28, font=(FONT, 8)).pack(side="left", padx=2)
        RoundedButton(tr_row, text="+3", command=lambda: self._shift_transpose(3), width=35, height=28, font=(FONT, 8)).pack(side="left", padx=2)
        RoundedButton(tr_row, text="+12", command=lambda: self._shift_transpose(12), width=40, height=28, font=(FONT, 8)).pack(side="left", padx=2)

        RoundedButton(tr_row, text="Reset", command=lambda: self._set_transpose(0), width=50, height=28, font=(FONT, 8))\
            .pack(side="left", padx=(10, 2))

        # Format & Simplification
        tools_row = tk.Frame(self, bg=PANEL_BG)
        tools_row.pack(fill="x", padx=16, pady=4)

        RoundedButton(tools_row, text="Rapikan Format (Beautify)", command=self._do_beautify,
                      width=180, height=30, fg_color=ACCENT_BLUE, font=(FONT, 8, "bold")).pack(side="left", padx=(0, 4))
        RoundedButton(tools_row, text="Sederhanakan Akord (Max 2 Nada)", command=self._do_simplify,
                      width=210, height=30, fg_color=ACCENT_PURPLE, font=(FONT, 8, "bold")).pack(side="left", padx=4)

        tk.Label(self, text="Preview Hasil Pengeditan:", bg=PANEL_BG, fg=TEXT_MUTED, font=(FONT, 8, "bold"))\
            .pack(anchor="w", padx=16, pady=(8, 2))

        self.txt_result = scrolledtext.ScrolledText(self, bg=CARD_BG, fg=TEXT_WHITE,
                                                    insertbackground=TEXT_WHITE, font=("Consolas", 10),
                                                    bd=0, highlightthickness=1, highlightbackground=CARD_BORDER)
        self.txt_result.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        self.txt_result.insert("1.0", self.raw_text)

        dock = tk.Frame(self, bg=PANEL_BG)
        dock.pack(fill="x", padx=16, pady=(0, 12))

        RoundedButton(dock, text="Terapkan ke Sheet", command=self._apply_and_close,
                      width=140, height=34, fg_color=COLOR_CORRECT, font=(FONT, 9, "bold")).pack(side="left", padx=2)
        RoundedButton(dock, text="Batal", command=self.destroy, width=70, height=34, font=(FONT, 9)).pack(side="right", padx=2)

    def _shift_transpose(self, delta):
        self._set_transpose(self.current_transpose + delta)

    def _set_transpose(self, val):
        self.current_transpose = max(-36, min(36, val))
        self.lbl_tr_val.configure(text=f"Transpose: {self.current_transpose:+d} semitone")
        transposed = transpose_sheet_text(self.raw_text, self.current_transpose)
        self.txt_result.delete("1.0", "end")
        self.txt_result.insert("1.0", transposed)

    def _do_beautify(self):
        current = self.txt_result.get("1.0", "end")
        beautified = beautify_sheet(current)
        self.txt_result.delete("1.0", "end")
        self.txt_result.insert("1.0", beautified)

    def _do_simplify(self):
        current = self.txt_result.get("1.0", "end")
        simplified = simplify_chords(current, max_keys=2)
        self.txt_result.delete("1.0", "end")
        self.txt_result.insert("1.0", simplified)

    def _apply_and_close(self):
        final_text = self.txt_result.get("1.0", "end").strip()
        self.on_apply_sheet(final_text)
        self.destroy()


# ---------------------------------------------------------------------------
# Main Application Class — Studio Pro
# ---------------------------------------------------------------------------
class PianoApp:
    def __init__(self):
        self.cfg = self._load_config()
        self.active_slot = 1
        self.slots = {
            i: {"text": "", "steps": [], "display_rows": [], "pos": 0, "status": {}}
            for i in (1, 2, 3)
        }

        self.state = "ready"        # ready | playing | paused | finished
        self.bpm = int(self.cfg.get("bpm", 180))  # Default 180 BPM untuk PlayPianoSheets
        self.speed_multiplier = float(self.cfg.get("speed_multiplier", 1.0))
        self.rest_delay = round(60.0 / max(1, self.bpm * self.speed_multiplier), 4)
        self.auto_mode = bool(self.cfg.get("auto_mode", True))      # Default: Auto Player aktif langsung
        self.transpose = int(self.cfg.get("transpose", 0))
        self.sustain = bool(self.cfg.get("sustain", True))
        self.rhythm_mode = self.cfg.get("rhythm_mode", "presisi")
        self.auto_target = self.cfg.get("auto_target", "roblox")  # "roblox" (ketik game) | "app" (preview suara)
        self.loop_mode = bool(self.cfg.get("loop_mode", False))
        self.metronome_active = False
        self.is_pinned = bool(self.cfg.get("pinned", False))
        self.last_auto_time = 0.0
        self.last_rest_time = 0.0
        self.last_metro_time = 0.0
        self.right_view_mode = "visual"
        self.key_hold_ms = int(self.cfg.get("key_hold_ms", 45))
        self._q = queue.Queue()
        self._shift = False
        self._hook_cb = None
        self._manual_plus_held = False
        self._manual_plus_keys = []
        self._manual_plus_shifted = False
        self._plus_held = False
        self._plus_pressed = False
        self._f6_pressed = False

        self.combo = 0
        self.max_combo = 0
        self.correct_count = 0
        self.wrong_count = 0

        # Audio Engine Initialisation
        self.audio = PianoAudioEngine()
        audio_enabled = self.cfg.get("audio_enabled", True)
        self.audio.set_enabled(audio_enabled)
        self.audio.set_volume(float(self.cfg.get("volume", 0.90)))
        self.audio.set_transpose(self.transpose)
        self.audio.set_sustain(self.sustain)

        # Song Library Initialisation
        favs = self.cfg.get("favorites", [])
        self.song_library = SongLibrary(SONGS_DIR, favorites=favs)

        self.recording = False
        self.recorded_keys = []
        self.record_start_time = 0.0

        self._build_ui()
        self._load_initial_sheet()
        self._install_hook()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(16, self._tick)

    # ---------------------------------------------------------------- UI Layout
    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("Roblox Piano Studio Pro — Follower & Autoplayer")
        self.root.configure(bg=BG)

        try:
            self.root.geometry(self.cfg.get("geometry", "960x650"))
        except tk.TclError:
            self.root.geometry("960x650")
        self.root.minsize(820, 520)

        if self.is_pinned:
            self.root.attributes("-topmost", True)

        main_box = tk.Frame(self.root, bg=PANEL_BG, bd=1, relief="solid")
        main_box.pack(fill="both", expand=True, padx=8, pady=8)

        # --- Top Header ---
        header = tk.Frame(main_box, bg=PANEL_BG, height=44)
        header.pack(fill="x", padx=12, pady=(10, 4))

        tk.Label(header, text="ROBLOX PIANO STUDIO", bg=PANEL_BG, fg=TEXT_WHITE,
                 font=(FONT, 12, "bold")).pack(side="left", padx=(4, 6))

        # Status Focus Roblox Badge (Clickable to switch Auto Target)
        self.lbl_focus_badge = tk.Label(header, text="[FOKUS KE ROBLOX]", bg="#2a2410", fg="#f59e0b",
                                        font=(FONT, 8, "bold"), padx=8, pady=3, cursor="hand2")
        self.lbl_focus_badge.pack(side="left", padx=4)
        self.lbl_focus_badge.bind("<Button-1>", lambda _e: self._toggle_auto_target())

        # Slot Selector Presets (1, 2, 3)
        tk.Label(header, text="Slot:", bg=PANEL_BG, fg=TEXT_DIM, font=(FONT, 9)).pack(side="left", padx=(10, 4))
        self.btn_slot1 = RoundedButton(header, text="1", command=lambda: self._switch_slot(1), width=28, height=28, is_active=True)
        self.btn_slot1.pack(side="left", padx=1)
        self.btn_slot2 = RoundedButton(header, text="2", command=lambda: self._switch_slot(2), width=28, height=28)
        self.btn_slot2.pack(side="left", padx=1)
        self.btn_slot3 = RoundedButton(header, text="3", command=lambda: self._switch_slot(3), width=28, height=28)
        self.btn_slot3.pack(side="left", padx=1)

        # Song Library Button
        RoundedButton(header, text="Library", command=self._open_library_modal, width=70, height=28,
                      font=(FONT, 8, "bold"), fg_color=ACCENT_CYAN).pack(side="left", padx=(8, 2))

        # Pin / Always on Top Toggle
        self.btn_pin = RoundedButton(header, text="Pin" if not self.is_pinned else "Pinned",
                                     command=self._toggle_pinned, width=55, height=28, font=(FONT, 8),
                                     is_active=self.is_pinned, active_border=ACCENT_AMBER)
        self.btn_pin.pack(side="left", padx=2)

        # View Mode Switcher
        self.btn_view_vis = RoundedButton(header, text="Visual Sheet", command=lambda: self._set_view_mode("visual"),
                                          width=100, height=28, is_active=True, font=(FONT, 9, "bold"))
        self.btn_view_vis.pack(side="right", padx=2)
        self.btn_view_edit = RoundedButton(header, text="Edit Sheet", command=lambda: self._set_view_mode("editor"),
                                           width=90, height=28, font=(FONT, 9, "bold"))
        self.btn_view_edit.pack(side="right", padx=2)

        # --- Performance & Practice HUD Sub-Bar ---
        hud_bar = tk.Frame(main_box, bg="#0a0e16", height=32, bd=1, relief="solid")
        hud_bar.pack(fill="x", padx=12, pady=(0, 4))

        self.lbl_hud_song = tk.Label(hud_bar, text="Lagu: (Belum Dimuat)", bg="#0a0e16", fg=ACCENT_BLUE,
                                     font=(FONT, 8, "bold"))
        self.lbl_hud_song.pack(side="left", padx=(10, 12))

        self.lbl_hud_progress = tk.Label(hud_bar, text="Not: 0 / 0 (0%)", bg="#0a0e16", fg=TEXT_MUTED, font=(FONT, 8))
        self.lbl_hud_progress.pack(side="left", padx=6)

        self.lbl_hud_accuracy = tk.Label(hud_bar, text="Akurasi: 100%", bg="#0a0e16", fg=COLOR_CORRECT, font=(FONT, 8, "bold"))
        self.lbl_hud_accuracy.pack(side="left", padx=6)

        self.lbl_hud_streak = tk.Label(hud_bar, text="Combo: 0", bg="#0a0e16", fg=ACCENT_AMBER, font=(FONT, 8, "bold"))
        self.lbl_hud_streak.pack(side="left", padx=6)

        RoundedButton(hud_bar, text="|<<", command=self._restart_position, width=32, height=22, font=(FONT, 7)).pack(side="right", padx=2)
        RoundedButton(hud_bar, text="<< 5", command=lambda: self._jump_steps(-5), width=42, height=22, font=(FONT, 7)).pack(side="right", padx=2)
        RoundedButton(hud_bar, text="5 >>", command=lambda: self._jump_steps(5), width=42, height=22, font=(FONT, 7)).pack(side="right", padx=2)

        self.btn_loop = RoundedButton(hud_bar, text="Loop", command=self._toggle_loop, width=45, height=22, font=(FONT, 7),
                                      is_active=self.loop_mode, active_border=ACCENT_CYAN)
        self.btn_loop.pack(side="right", padx=2)

        self.btn_metro = RoundedButton(hud_bar, text="Metro", command=self._toggle_metronome, width=50, height=22, font=(FONT, 7),
                                       is_active=self.metronome_active, active_border=ACCENT_AMBER)
        self.btn_metro.pack(side="right", padx=(2, 8))

        # --- Center Display ---
        display_frame = tk.Frame(main_box, bg="#06080c", bd=1, relief="solid")
        display_frame.pack(fill="both", expand=True, padx=12, pady=2)

        self.visual_canvas = VisualSheetCanvas(display_frame, bg="#06080c")
        self.visual_canvas.pack(fill="both", expand=True)

        self.editor_frame = tk.Frame(display_frame, bg="#0d1117")
        self.sheet_text = scrolledtext.ScrolledText(
            self.editor_frame, bg="#0d1117", fg=TEXT_WHITE,
            insertbackground=TEXT_WHITE, font=("Consolas", 11), bd=0,
            highlightthickness=0, wrap="word")
        self.sheet_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.sheet_text.insert("1.0", "Paste sheet lagu di sini...")
        self.sheet_text.bind("<KeyRelease>", self._on_sheet_text_change)
        self.sheet_text.bind("<FocusIn>", self._on_sheet_text_focus)

        # --- Interactive Virtual Piano Keyboard (61 Keys) ---
        piano_box = tk.Frame(main_box, bg="#06080c", bd=1, relief="solid", height=76)
        piano_box.pack(fill="x", padx=12, pady=(2, 4))
        piano_box.pack_propagate(False)

        label_bar = tk.Frame(piano_box, bg="#06080c")
        label_bar.pack(fill="x", padx=8, pady=(1, 0))

        tk.Label(label_bar, text="Virtual Piano (Clickable):", bg="#06080c", fg=TEXT_DIM, font=(FONT, 7, "bold")).pack(side="left")
        self.btn_label_toggle = RoundedButton(label_bar, text="Label: Key", command=self._cycle_label_mode,
                                              width=70, height=18, font=(FONT, 7))
        self.btn_label_toggle.pack(side="right")

        self.keyboard_canvas = VirtualPianoKeyboardCanvas(piano_box, on_key_click=self._on_piano_key_click, bg="#06080c")
        self.keyboard_canvas.pack(fill="both", expand=True)

        # --- Bottom Control Dock ---
        dock = tk.Frame(main_box, bg=PANEL_BG, height=48)
        dock.pack(fill="x", padx=12, pady=(4, 8))

        # Playback Controls
        play_title = "AutoPlay" if self.auto_mode else "Latihan"
        play_color = ACCENT_PURPLE if self.auto_mode else COLOR_CORRECT
        self.btn_play = RoundedButton(dock, text=play_title, command=self._toggle_play, width=72, height=36,
                                      font=(FONT, 9, "bold"), fg_color=play_color)
        self.btn_play.pack(side="left", padx=2)
        self.btn_stop = RoundedButton(dock, text="Stop", command=self._stop, width=52, height=36, font=(FONT, 9, "bold"))
        self.btn_stop.pack(side="left", padx=2)

        # Mode Switch (Follower vs Auto Player)
        mode_text = "Auto Player" if self.auto_mode else "Follower Mode"
        mode_color = ACCENT_CYAN if self.auto_mode else TEXT_WHITE
        self.btn_mode_toggle = RoundedButton(dock, text=mode_text, command=self._toggle_auto_mode,
                                             width=98, height=36, font=(FONT, 8, "bold"), fg_color=mode_color)
        self.btn_mode_toggle.pack(side="left", padx=2)

        # Transpose Controls (TRANS: -3 / + / Reset)
        tk.Frame(dock, bg=CARD_BORDER, width=1, height=24).pack(side="left", padx=2)
        RoundedButton(dock, text="-", command=lambda: self._change_transpose(-1), width=22, height=32, font=(FONT, 10, "bold")).pack(side="left", padx=1)
        tr_text = f"TRANS: {self.transpose:+d}" if self.transpose != 0 else "TRANS: 0"
        tr_color = ACCENT_PURPLE if self.transpose != 0 else TEXT_MUTED
        self.btn_trans_val = RoundedButton(dock, text=tr_text, command=lambda: self._change_transpose(0, reset=True),
                                           width=70, height=32, font=(FONT, 8, "bold"), fg_color=tr_color)
        self.btn_trans_val.pack(side="left", padx=1)
        RoundedButton(dock, text="+", command=lambda: self._change_transpose(1), width=22, height=32, font=(FONT, 10, "bold")).pack(side="left", padx=1)

        # Sustain Pedal Toggle
        tk.Frame(dock, bg=CARD_BORDER, width=1, height=24).pack(side="left", padx=2)
        sustain_title = "Sustain: ON" if self.sustain else "Sustain: OFF"
        sustain_color = ACCENT_CYAN if self.sustain else TEXT_MUTED
        self.btn_sustain = RoundedButton(dock, text=sustain_title, command=self._toggle_sustain,
                                         width=80, height=36, font=(FONT, 8, "bold"), fg_color=sustain_color)
        self.btn_sustain.pack(side="left", padx=2)

        # Target Auto Player Switcher (Roblox vs App Suara)
        target_title = "Auto: Roblox" if self.auto_target == "roblox" else "Auto: App Suara"
        target_color = COLOR_CORRECT if self.auto_target == "roblox" else ACCENT_CYAN
        self.btn_auto_target = RoundedButton(dock, text=target_title, command=self._toggle_auto_target,
                                             width=90, height=36, font=(FONT, 8, "bold"), fg_color=target_color)
        self.btn_auto_target.pack(side="left", padx=2)

        # Speed Multipliers (0.5x, 0.75x, 1x, 1.25x, 1.5x)
        tk.Frame(dock, bg=CARD_BORDER, width=1, height=24).pack(side="left", padx=2)
        self.speed_buttons = {}
        for spd in (0.5, 0.75, 1.0, 1.25, 1.5):
            lbl = f"{spd}x" if spd != 1.0 else "1.0x"
            btn = RoundedButton(dock, text=lbl, command=lambda s=spd: self._set_speed(s),
                                width=34, height=30, font=(FONT, 8, "bold"), is_active=(spd == self.speed_multiplier))
            btn.pack(side="left", padx=1)
            self.speed_buttons[spd] = btn

        # BPM Control
        tk.Frame(dock, bg=CARD_BORDER, width=1, height=24).pack(side="left", padx=2)
        RoundedButton(dock, text="-", command=lambda: self._change_bpm(-5), width=22, height=32, font=(FONT, 10, "bold")).pack(side="left", padx=1)
        self.btn_bpm_val = RoundedButton(dock, text=f"BPM: {self.bpm}", command=self._edit_bpm, width=74, height=32, font=(FONT, 8, "bold"))
        self.btn_bpm_val.pack(side="left", padx=1)
        RoundedButton(dock, text="+", command=lambda: self._change_bpm(5), width=22, height=32, font=(FONT, 10, "bold")).pack(side="left", padx=1)

        # Audio Sound Toggle
        tk.Frame(dock, bg=CARD_BORDER, width=1, height=24).pack(side="left", padx=2)
        audio_lbl = "Suara: ON" if self.audio.is_enabled() else "Suara: OFF"
        audio_fg = ACCENT_CYAN if self.audio.is_enabled() else TEXT_MUTED
        self.btn_audio = RoundedButton(dock, text=audio_lbl, command=self._toggle_audio,
                                       width=76, height=36, font=(FONT, 8, "bold"), fg_color=audio_fg)
        self.btn_audio.pack(side="left", padx=2)

        # Right Actions
        RoundedButton(dock, text="Clear", command=self._clear_sheet_box, width=50, height=36, font=(FONT, 9))\
            .pack(side="right", padx=1)
        RoundedButton(dock, text="Paste", command=self._quick_paste, width=52, height=36, font=(FONT, 9, "bold"))\
            .pack(side="right", padx=1)
        RoundedButton(dock, text="Tools", command=self._open_tools_modal, width=56, height=36,
                       font=(FONT, 9, "bold"), fg_color=ACCENT_PURPLE).pack(side="right", padx=1)
        RoundedButton(dock, text="Import / AI", command=self._open_import_choice_dialog, width=86, height=36,
                       font=(FONT, 8, "bold"), fg_color=ACCENT_CYAN).pack(side="right", padx=1)

        self._set_view_mode("visual")

    # ---------------------------------------------------------------- Initial Loader
    def _load_initial_sheet(self):
        sample_path = SONGS_DIR / "wet_hands.txt"
        if not sample_path.exists():
            sample_path = SONGS_DIR / "canon_in_d.txt"
        if sample_path.exists():
            try:
                txt = sample_path.read_text(encoding="utf-8", errors="replace")
                self.sheet_text.delete("1.0", "end")
                self.sheet_text.insert("1.0", txt)
                self.lbl_hud_song.configure(text=f"Lagu: {clean_display_title(sample_path.name)}")

                for line in txt.splitlines()[:5]:
                    line_str = line.strip()
                    if "BPM:" in line_str:
                        m = re.search(r"BPM:\s*~?(\d+)", line_str, re.IGNORECASE)
                        if m:
                            self.bpm = int(m.group(1))
                            self.rest_delay = round(60.0 / max(1, self.bpm * self.speed_multiplier), 4)
                            self.btn_bpm_val.set_text(f"BPM: {self.bpm}")
                    if "Transpose:" in line_str:
                        m = re.search(r"Transpose:\s*([+-]?\d+)", line_str, re.IGNORECASE)
                        if m:
                            self._set_transpose(int(m.group(1)))
            except Exception:
                pass
        self._parse_active_sheet()
        self._update_visual_canvas()

    # ---------------------------------------------------------------- View Controls
    def _set_view_mode(self, mode):
        self.right_view_mode = mode
        self.btn_view_vis.set_active(mode == "visual")
        self.btn_view_edit.set_active(mode == "editor")
        if mode == "visual":
            self.editor_frame.pack_forget()
            self.visual_canvas.pack(fill="both", expand=True)
            self._update_visual_canvas()
        else:
            self.visual_canvas.pack_forget()
            self.editor_frame.pack(fill="both", expand=True)

    def _cycle_label_mode(self):
        modes = ["key", "note", "both", "none"]
        curr_idx = modes.index(self.keyboard_canvas.label_mode) if self.keyboard_canvas.label_mode in modes else 0
        new_mode = modes[(curr_idx + 1) % len(modes)]
        self.keyboard_canvas.set_label_mode(new_mode)
        labels = {"key": "Label: Key", "note": "Label: Nada", "both": "Label: Ganda", "none": "Label: Polos"}
        self.btn_label_toggle.set_text(labels.get(new_mode, "Label"))

    def _toggle_pinned(self):
        self.is_pinned = not self.is_pinned
        self.root.attributes("-topmost", self.is_pinned)
        self.btn_pin.set_text("Pinned" if self.is_pinned else "Pin")
        self.btn_pin.set_active(self.is_pinned, active_border=ACCENT_AMBER)

    def _change_transpose(self, delta, reset=False):
        if reset:
            self.transpose = 0
        else:
            self.transpose = max(-36, min(36, self.transpose + delta))
        self._update_transpose_ui()

    def _set_transpose(self, val):
        self.transpose = max(-36, min(36, int(val)))
        self._update_transpose_ui()

    def _update_transpose_ui(self):
        self.audio.set_transpose(self.transpose)
        if hasattr(self, "btn_trans_val"):
            t_text = f"TRANS: {self.transpose:+d}" if self.transpose != 0 else "TRANS: 0"
            t_color = ACCENT_PURPLE if self.transpose != 0 else TEXT_MUTED
            self.btn_trans_val.set_text(t_text, fg_color=t_color)
        self.cfg["transpose"] = self.transpose

    def _toggle_sustain(self):
        self.sustain = not self.sustain
        self.audio.set_sustain(self.sustain)
        if hasattr(self, "btn_sustain"):
            s_text = "Sustain: ON" if self.sustain else "Sustain: OFF"
            s_color = ACCENT_CYAN if self.sustain else TEXT_MUTED
            self.btn_sustain.set_text(s_text, fg_color=s_color)
        self.cfg["sustain"] = self.sustain

    def _toggle_auto_target(self):
        self.auto_target = "app" if self.auto_target == "roblox" else "roblox"
        target_title = "Auto: Roblox" if self.auto_target == "roblox" else "Auto: App Suara"
        target_color = COLOR_CORRECT if self.auto_target == "roblox" else ACCENT_CYAN
        self.btn_auto_target.set_text(target_title, fg_color=target_color)

    def _update_visual_canvas(self):
        steps = self.current_steps
        active_note_idx = _find_active_note_step(steps, self.current_pos)
        active_keys = set()
        if steps and 0 <= active_note_idx < len(steps):
            step = steps[active_note_idx]
            if step[0] == "n":
                active_keys = set(step[1])

        total = len(steps)
        curr = max(0, self.current_pos)
        pct = int(min(1.0, curr / max(1, total)) * 100)
        self.lbl_hud_progress.configure(text=f"Not: {curr} / {total} ({pct}%)")

        total_hits = self.correct_count + self.wrong_count
        acc = round((self.correct_count / total_hits * 100), 1) if total_hits > 0 else 100.0
        self.lbl_hud_accuracy.configure(text=f"Akurasi: {acc}%")
        self.lbl_hud_streak.configure(text=f"Combo: {self.combo}")

        self.visual_canvas.set_data(
            self.current_display_rows,
            active_step_idx=active_note_idx,
            step_status=self.current_step_status,
            total_steps=total
        )
        if hasattr(self, "keyboard_canvas"):
            self.keyboard_canvas.set_active_keys(active_keys)

    # ---------------------------------------------------------------- Slots & Editor
    def _switch_slot(self, slot_num):
        self._release_manual_plus()
        self.slots[self.active_slot]["text"] = self.sheet_text.get("1.0", "end").strip()
        self.slots[self.active_slot]["pos"] = self.current_pos

        self.active_slot = slot_num
        self.btn_slot1.set_active(slot_num == 1)
        self.btn_slot2.set_active(slot_num == 2)
        self.btn_slot3.set_active(slot_num == 3)

        slot_data = self.slots[slot_num]
        txt = slot_data["text"] if slot_data["text"] else "Paste sheet lagu di sini..."
        self.sheet_text.delete("1.0", "end")
        self.sheet_text.insert("1.0", txt)

        self._parse_active_sheet()
        self.current_pos = slot_data["pos"]
        self._update_visual_canvas()

    def _open_library_modal(self):
        SongLibraryModal(self.root, self.song_library, self.audio, on_load_song=self._load_song_from_library)

    def _load_song_from_library(self, sheet_text, bpm, title, transpose=0):
        self.sheet_text.delete("1.0", "end")
        self.sheet_text.insert("1.0", sheet_text)
        self.bpm = max(20, min(1000, bpm))
        self.rest_delay = round(60.0 / max(1, self.bpm * self.speed_multiplier), 4)
        self.btn_bpm_val.set_text(f"BPM: {self.bpm}")
        self.lbl_hud_song.configure(text=f"Lagu: {title[:32]}")
        self._set_transpose(transpose)

        self._parse_active_sheet()
        self.current_pos = 0
        self.combo = 0
        self.correct_count = 0
        self.wrong_count = 0
        self.slots[self.active_slot]["status"] = {}
        self._set_view_mode("visual")
        self._update_visual_canvas()

    def _open_tools_modal(self):
        current_text = self.sheet_text.get("1.0", "end").strip()
        if not current_text or current_text == "Paste sheet lagu di sini...":
            messagebox.showinfo("Sheet Kosong", "Silakan muat atau ketik sheet terlebih dahulu.", parent=self.root)
            return

        def _apply_edited(new_text):
            self.sheet_text.delete("1.0", "end")
            self.sheet_text.insert("1.0", new_text)
            self._parse_active_sheet()
            self._update_visual_canvas()

        SheetToolsModal(self.root, current_text, on_apply_sheet=_apply_edited)

    @property
    def current_pos(self):
        return self.slots[self.active_slot]["pos"]

    @current_pos.setter
    def current_pos(self, val):
        self.slots[self.active_slot]["pos"] = val

    @property
    def current_steps(self):
        return self.slots[self.active_slot]["steps"]

    @property
    def current_display_rows(self):
        return self.slots[self.active_slot]["display_rows"]

    @property
    def current_step_status(self):
        return self.slots[self.active_slot]["status"]

    def _on_sheet_text_focus(self, _e=None):
        if self.sheet_text.get("1.0", "end").strip() == "Paste sheet lagu di sini...":
            self.sheet_text.delete("1.0", "end")

    def _on_sheet_text_change(self, _e=None):
        self._parse_active_sheet()
        self._update_visual_canvas()

    def _parse_active_sheet(self):
        raw = self.sheet_text.get("1.0", "end")
        if not raw.strip() or raw.strip() == "Paste sheet lagu di sini...":
            self.slots[self.active_slot].update(steps=[], display_rows=[], status={})
            return
        display_rows, steps = build_display_tokens(raw, rhythm_mode=self.rhythm_mode)
        self.slots[self.active_slot]["steps"] = steps
        self.slots[self.active_slot]["display_rows"] = display_rows
        if self.current_pos >= len(steps):
            self.current_pos = 0

    def _clear_sheet_box(self):
        self.sheet_text.delete("1.0", "end")
        self.slots[self.active_slot].update(text="", steps=[], display_rows=[], status={}, pos=0)
        self.lbl_hud_song.configure(text="Lagu: (Kosong)")
        self.combo = 0
        self.correct_count = 0
        self.wrong_count = 0
        self._update_visual_canvas()

    def _quick_paste(self):
        try:
            clip = self.root.clipboard_get()
            if clip:
                self.sheet_text.delete("1.0", "end")
                self.sheet_text.insert("1.0", clip)
                self.lbl_hud_song.configure(text="Lagu: Custom Paste")
                self._parse_active_sheet()
                self.current_pos = 0
                self.combo = 0
                self.correct_count = 0
                self.wrong_count = 0
                self._set_view_mode("visual")
                self._update_visual_canvas()
        except Exception:
            pass

    # ---------------------------------------------------------------- Import / AI Dialog
    def _open_import_choice_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Import / Konversi Lagu")
        win.configure(bg=PANEL_BG)
        win.geometry("420x290")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        x = self.root.winfo_x() + (self.root.winfo_width() - 420) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 290) // 2
        win.geometry(f"+{max(0, x)}+{max(0, y)}")

        tk.Label(win, text="Import / Konversi Lagu", bg=PANEL_BG, fg=TEXT_WHITE,
                 font=(FONT, 12, "bold")).pack(pady=(16, 2))
        tk.Label(win, text="Pilih metode import lagu ke Sheet Roblox Piano:",
                 bg=PANEL_BG, fg=TEXT_DIM, font=(FONT, 8)).pack(pady=(0, 14))

        def choose_midi():
            win.destroy()
            self._open_midi_dialog()

        def choose_audio():
            win.destroy()
            self._open_audio_dialog()

        card1 = tk.Frame(win, bg=CARD_BG, bd=1, relief="solid", cursor="hand2")
        card1.pack(fill="x", padx=20, pady=(0, 10))
        c1_top = tk.Frame(card1, bg=CARD_BG)
        c1_top.pack(fill="x", padx=12, pady=(10, 2))
        tk.Label(c1_top, text="🎹  Import File MIDI (.mid, .midi)", bg=CARD_BG, fg="#a78bfa",
                 font=(FONT, 10, "bold")).pack(side="left")
        tk.Label(card1, text="Buka file MIDI langsung. Cepat & instan dengan analisis nada serta auto-transpose.",
                 bg=CARD_BG, fg=TEXT_DIM, font=(FONT, 8), wraplength=360, justify="left").pack(anchor="w", padx=12, pady=(0, 10))

        card2 = tk.Frame(win, bg=CARD_BG, bd=1, relief="solid", cursor="hand2")
        card2.pack(fill="x", padx=20, pady=(0, 14))
        c2_top = tk.Frame(card2, bg=CARD_BG)
        c2_top.pack(fill="x", padx=12, pady=(10, 2))
        tk.Label(c2_top, text="🎙️  Konversi MP3 / Audio ke MIDI (AI)", bg=CARD_BG, fg=ACCENT_CYAN,
                 font=(FONT, 10, "bold")).pack(side="left")
        tk.Label(card2, text="Transkripsi audio (.mp3, .wav, .m4a) menjadi MIDI & Sheet via ByteDance Solo Piano AI.",
                 bg=CARD_BG, fg=TEXT_DIM, font=(FONT, 8), wraplength=360, justify="left").pack(anchor="w", padx=12, pady=(0, 10))

        def bind_card(card, cmd):
            card.bind("<Button-1>", lambda _e: cmd())
            for ch in card.winfo_children():
                ch.bind("<Button-1>", lambda _e: cmd())

        bind_card(card1, choose_midi)
        bind_card(card2, choose_audio)
        RoundedButton(win, text="Batal", command=win.destroy, width=70, height=30, font=(FONT, 9)).pack(pady=(0, 8))

    def _open_midi_dialog(self):
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Buka File MIDI (.mid, .midi)",
            filetypes=[("File MIDI", "*.mid *.midi"), ("Semua File", "*.*")]
        )
        if not path:
            return

        try:
            from midi_import import analyze_midi, get_transpose_stats, midi_to_sheet_text
            analysis = analyze_midi(path)
        except Exception as err:
            messagebox.showerror("Gagal Membaca MIDI", f"Error saat membaca file MIDI:\n{err}", parent=self.root)
            return

        total_notes = analysis["total_notes"]
        if total_notes == 0:
            messagebox.showwarning("File MIDI Kosong", "File MIDI tidak memiliki event nada piano (note_on).", parent=self.root)
            return

        events = analysis["events"]
        duration_sec = analysis["duration"]
        dur_mins = int(duration_sec // 60)
        dur_secs = int(duration_sec % 60)
        dur_str = f"{dur_mins}m {dur_secs:02d}s" if dur_mins > 0 else f"{dur_secs}s"
        bpm_detected = analysis["bpm"]
        optimal_t = analysis["optimal_transpose"]

        win = tk.Toplevel(self.root)
        win.title("Import File MIDI")
        win.configure(bg=PANEL_BG)
        win.geometry("450x380")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        x = self.root.winfo_x() + (self.root.winfo_width() - 450) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 380) // 2
        win.geometry(f"+{max(0, x)}+{max(0, y)}")

        tk.Label(win, text="Import MIDI ke Sheet Roblox", bg=PANEL_BG, fg="#a78bfa",
                 font=(FONT, 11, "bold")).pack(pady=(12, 4))
        tk.Label(win, text=f"File: {Path(path).name[:45]}", bg=PANEL_BG, fg=TEXT_WHITE,
                 font=(FONT, 9, "bold")).pack()
        tk.Label(win, text=f"Durasi: {dur_str}  |  Total Not: {total_notes}  |  Tempo: ~{bpm_detected} BPM",
                 bg=PANEL_BG, fg=TEXT_DIM, font=(FONT, 8)).pack(pady=(2, 8))

        tr_card = tk.Frame(win, bg=CARD_BG, bd=1, relief="solid")
        tr_card.pack(fill="x", padx=16, pady=(0, 8))

        tk.Label(tr_card, text="PENGATURAN TRANSPOSE NADA", bg=CARD_BG, fg=TEXT_DIM,
                 font=(FONT, 8, "bold")).pack(anchor="w", padx=10, pady=(8, 4))

        tr_row = tk.Frame(tr_card, bg=CARD_BG)
        tr_row.pack(fill="x", padx=10, pady=(0, 6))

        current_transpose = [optimal_t]
        lbl_tr_val = tk.Label(tr_row, text=f"Transpose: {optimal_t:+d} semitone", bg=CARD_BG,
                              fg=TEXT_WHITE, font=(FONT, 9, "bold"), width=22)

        lbl_coverage = tk.Label(tr_card, text="", bg=CARD_BG, font=(FONT, 8, "bold"))
        lbl_coverage.pack(anchor="w", padx=10, pady=(0, 8))

        def update_tr_ui():
            t = current_transpose[0]
            lbl_tr_val.configure(text=f"Transpose: {t:+d} semitone")
            playable, skipped, pct = get_transpose_stats(events, t)
            color = COLOR_CORRECT if pct >= 95 else ("#f59e0b" if pct >= 75 else COLOR_WRONG)
            lbl_coverage.configure(
                text=f"{pct}% not cocok Roblox ({playable}/{total_notes} not, {skipped} di-skip)",
                fg=color
            )

        def change_t(delta):
            current_transpose[0] = max(-36, min(36, current_transpose[0] + delta))
            update_tr_ui()

        RoundedButton(tr_row, text="-12", command=lambda: change_t(-12), width=36, height=28, font=(FONT, 8)).pack(side="left", padx=2)
        RoundedButton(tr_row, text="-1", command=lambda: change_t(-1), width=30, height=28, font=(FONT, 8)).pack(side="left", padx=2)
        lbl_tr_val.pack(side="left", padx=4)
        RoundedButton(tr_row, text="+1", command=lambda: change_t(1), width=30, height=28, font=(FONT, 8)).pack(side="left", padx=2)
        RoundedButton(tr_row, text="+12", command=lambda: change_t(12), width=36, height=28, font=(FONT, 8)).pack(side="left", padx=2)

        update_tr_ui()

        opt_frame = tk.Frame(win, bg=PANEL_BG)
        opt_frame.pack(fill="x", padx=18, pady=(0, 8))

        var_set_bpm = tk.BooleanVar(value=True)
        tk.Checkbutton(opt_frame, text=f"Terapkan BPM lagu ini ke App ({bpm_detected} BPM)",
                       variable=var_set_bpm, bg=PANEL_BG, fg=TEXT_WHITE,
                       selectcolor=CARD_BG, font=(FONT, 8)).pack(anchor="w")

        btn_row = tk.Frame(win, bg=PANEL_BG)
        btn_row.pack(pady=(4, 10))

        def do_import():
            chosen_t = current_transpose[0]
            sheet_text = midi_to_sheet_text(path, transpose=chosen_t)

            if var_set_bpm.get() and bpm_detected > 0:
                self.bpm = max(1, min(1000, bpm_detected))
                self.rest_delay = round(60.0 / max(1, self.bpm * self.speed_multiplier), 4)
                self.btn_bpm_val.set_text(f"BPM: {self.bpm}")

            self.sheet_text.delete("1.0", "end")
            self.sheet_text.insert("1.0", sheet_text)
            self.lbl_hud_song.configure(text=f"Lagu: {clean_display_title(Path(path).name)}")
            self._parse_active_sheet()
            self.current_pos = 0
            self.combo = 0
            self._set_view_mode("visual")
            self._update_visual_canvas()
            win.destroy()

        RoundedButton(btn_row, text="Import ke Piano", command=do_import, width=130, height=34,
                      font=(FONT, 9, "bold"), fg_color="#8b5cf6").pack(side="left", padx=6)
        RoundedButton(btn_row, text="Batal", command=win.destroy, width=70, height=34, font=(FONT, 9)).pack(side="left", padx=6)

    def _open_audio_dialog(self):
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Buka File Audio Piano (.mp3, .wav, .flac, .ogg, .m4a)",
            filetypes=[("File Audio Piano", "*.mp3 *.wav *.flac *.ogg *.m4a"), ("Semua File", "*.*")]
        )
        if not path:
            return

        win = tk.Toplevel(self.root)
        win.title("ByteDance AI Audio Transcription")
        win.configure(bg=PANEL_BG)
        win.geometry("400x260")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        x = self.root.winfo_x() + (self.root.winfo_width() - 400) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 260) // 2
        win.geometry(f"+{max(0, x)}+{max(0, y)}")

        tk.Label(win, text="ByteDance Solo Piano AI", bg=PANEL_BG, fg=ACCENT_BLUE, font=(FONT, 11, "bold")).pack(pady=(14, 4))
        tk.Label(win, text=f"File: {Path(path).name[:45]}", bg=PANEL_BG, fg=TEXT_DIM, font=(FONT, 8)).pack()

        token_frame = tk.Frame(win, bg=PANEL_BG)
        token_frame.pack(fill="x", padx=20, pady=(10, 0))
        tk.Label(token_frame, text="HuggingFace Token (opsional):", bg=PANEL_BG, fg=TEXT_DIM, font=(FONT, 8)).pack(anchor="w")
        entry_token = tk.Entry(token_frame, font=(FONT, 9), bg=CARD_BG, fg=TEXT_WHITE,
                               insertbackground=TEXT_WHITE, bd=0, highlightthickness=1, show="*")
        entry_token.pack(fill="x", ipady=4, pady=(2, 0))

        lbl_status = tk.Label(win, text="", bg=PANEL_BG, fg=TEXT_WHITE, font=(FONT, 9), wraplength=360)
        lbl_status.pack(pady=(8, 0))

        btn_row = tk.Frame(win, bg=PANEL_BG)
        btn_row.pack(pady=8)

        def set_status(msg):
            def _update():
                if win.winfo_exists():
                    lbl_status.configure(text=msg)
            self.root.after(0, _update)

        def worker(hf_token):
            try:
                from audio_transcriber import transcribe_audio_to_midi, midi_to_sheet_text
                midi_path = transcribe_audio_to_midi(
                    path, output_dir=SONGS_DIR, status_callback=set_status, hf_token=hf_token or None
                )
                set_status("Mengonversi MIDI ke Sheet Roblox...")
                sheet_text = midi_to_sheet_text(midi_path)

                def apply_success():
                    if win.winfo_exists():
                        win.destroy()
                    self.sheet_text.delete("1.0", "end")
                    self.sheet_text.insert("1.0", sheet_text)
                    self.lbl_hud_song.configure(text=f"Lagu: {clean_display_title(Path(path).stem)}")
                    self._parse_active_sheet()
                    self.current_pos = 0
                    self.combo = 0
                    self._set_view_mode("visual")
                    self._update_visual_canvas()

                self.root.after(0, apply_success)
            except Exception as err:
                def apply_error():
                    if win.winfo_exists():
                        lbl_status.configure(text=f"Gagal: {str(err)[:120]}", fg=COLOR_WRONG)
                self.root.after(0, apply_error)

        def start_transcribe():
            hf_token = entry_token.get().strip()
            btn_start.pack_forget()
            btn_cancel.pack_forget()
            lbl_status.configure(text="Menghubungkan ke AI...")
            threading.Thread(target=worker, args=(hf_token,), daemon=True).start()

        btn_start = RoundedButton(btn_row, text="Mulai Transkripsi", command=start_transcribe,
                                  width=130, height=34, font=(FONT, 9, "bold"), fg_color=ACCENT_CYAN)
        btn_start.pack(side="left", padx=6)
        btn_cancel = RoundedButton(btn_row, text="Batal", command=win.destroy, width=70, height=34, font=(FONT, 9))
        btn_cancel.pack(side="left", padx=6)

    # ---------------------------------------------------------------- Navigation & HUD Controls
    def _restart_position(self):
        self._release_manual_plus()
        self.current_pos = 0
        self.combo = 0
        self.slots[self.active_slot]["status"] = {}
        self._update_visual_canvas()

    def _jump_steps(self, delta):
        self._release_manual_plus()
        steps = self.current_steps
        if not steps:
            return
        new_pos = max(0, min(len(steps) - 1, self.current_pos + delta))
        self.current_pos = new_pos
        self._update_visual_canvas()

    def _toggle_loop(self):
        self.loop_mode = not self.loop_mode
        self.btn_loop.set_active(self.loop_mode, active_border=ACCENT_CYAN)

    def _toggle_metronome(self):
        self.metronome_active = not self.metronome_active
        self.btn_metro.set_active(self.metronome_active, active_border=ACCENT_AMBER)
        self.last_metro_time = time.time()

    def _set_speed(self, multiplier):
        self.speed_multiplier = float(multiplier)
        self.rest_delay = round(60.0 / max(1, self.bpm * self.speed_multiplier), 4)
        for s, btn in self.speed_buttons.items():
            btn.set_active(s == self.speed_multiplier)

    def _toggle_audio(self):
        new_state = not self.audio.is_enabled()
        self.audio.set_enabled(new_state)
        lbl = "Suara: ON" if new_state else "Suara: OFF"
        fg = ACCENT_CYAN if new_state else TEXT_MUTED
        self.btn_audio.set_text(lbl, fg_color=fg)

    def _on_piano_key_click(self, key):
        if self.audio.is_enabled():
            self.audio.play_key(key, velocity=95, duration=0.6)

        if _is_roblox_focused():
            base, is_shifted = get_key_press_info(key)
            vk = get_vk_code(base)
            if vk:
                def _do_send():
                    try:
                        if is_shifted:
                            win_press_vk(VK_SHIFT)
                        win_press_vk(vk)
                        time.sleep(0.035)
                        win_release_vk(vk)
                        if is_shifted:
                            win_release_vk(VK_SHIFT)
                    except Exception:
                        pass
                threading.Thread(target=_do_send, daemon=True).start()

        if not self.auto_mode and self.state == "playing":
            self.on_key(key)

    # ---------------------------------------------------------------- Playback Core
    def _release_manual_plus(self):
        self._plus_held = False
        if getattr(self, "_manual_plus_held", False):
            self._manual_plus_held = False
            for k in getattr(self, "_manual_plus_keys", []):
                try:
                    vk = get_vk_code(k)
                    if vk:
                        win_release_vk(vk)
                except Exception:
                    pass
            if getattr(self, "_manual_plus_shifted", False):
                try:
                    win_release_vk(VK_SHIFT)
                except Exception:
                    pass
            self._manual_plus_keys = []
            self._manual_plus_shifted = False

    def _toggle_play(self):
        if not self.current_steps:
            return
        if self.state == "playing":
            self._pause()
        else:
            if self.state == "finished":
                self.current_pos = 0
                self.combo = 0
                self.slots[self.active_slot]["status"] = {}
            self.state = "playing"
            self.last_rest_time = time.time()
            self.last_metro_time = time.time()
            self.btn_play.set_text("Pause", fg_color="#f43f5e")
            self._update_visual_canvas()
            if self.auto_mode:
                self._start_auto_worker_if_needed()

    def _pause(self):
        self._release_manual_plus()
        if self.state == "playing":
            self.state = "paused"
            play_title = "AutoPlay" if self.auto_mode else "Latihan"
            play_color = ACCENT_PURPLE if self.auto_mode else COLOR_CORRECT
            self.btn_play.set_text(play_title, fg_color=play_color)
            self._update_visual_canvas()

    def _stop(self):
        self._release_manual_plus()
        self.state = "ready"
        self.current_pos = 0
        self.combo = 0
        self.slots[self.active_slot]["status"] = {}
        play_title = "AutoPlay" if self.auto_mode else "Latihan"
        play_color = ACCENT_PURPLE if self.auto_mode else COLOR_CORRECT
        self.btn_play.set_text(play_title, fg_color=play_color)
        if self.audio:
            self.audio.stop_all()
        self._update_visual_canvas()

    def _change_bpm(self, delta):
        self.bpm = max(1, min(1000, self.bpm + delta))
        self.rest_delay = round(60.0 / max(1, self.bpm * self.speed_multiplier), 4)
        self.btn_bpm_val.set_text(f"BPM: {self.bpm}")

    def _edit_bpm(self):
        win = tk.Toplevel(self.root)
        win.title("Set BPM")
        win.configure(bg=PANEL_BG)
        win.geometry("220x130")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        x = self.root.winfo_x() + (self.root.winfo_width() - 220) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 130) // 2
        win.geometry(f"+{max(0, x)}+{max(0, y)}")

        tk.Label(win, text="Ketik BPM (20 - 1000):", bg=PANEL_BG, fg=TEXT_WHITE, font=(FONT, 9)).pack(pady=(12, 4))
        entry = tk.Entry(win, font=(FONT, 14, "bold"), justify="center", bg=CARD_BG, fg=TEXT_WHITE,
                         insertbackground=TEXT_WHITE, bd=0, highlightthickness=1, width=10)
        entry.pack(padx=20, ipady=3)
        entry.insert(0, str(self.bpm))
        entry.select_range(0, "end")
        entry.focus_set()

        def apply(_e=None):
            raw = entry.get().strip()
            if raw.isdigit() and 20 <= int(raw) <= 1000:
                self.bpm = int(raw)
                self.rest_delay = round(60.0 / max(1, self.bpm * self.speed_multiplier), 4)
                self.btn_bpm_val.set_text(f"BPM: {self.bpm}")
                win.destroy()

        entry.bind("<Return>", apply)
        btn_row = tk.Frame(win, bg=PANEL_BG)
        btn_row.pack(pady=10)
        RoundedButton(btn_row, text="OK", command=apply, width=70, height=28, fg_color=ACCENT_CYAN).pack(side="left", padx=4)
        RoundedButton(btn_row, text="Batal", command=win.destroy, width=70, height=28).pack(side="left", padx=4)

    def _toggle_auto_mode(self):
        self._release_manual_plus()
        self.auto_mode = not self.auto_mode
        if self.auto_mode:
            self.btn_mode_toggle.set_text("Auto Player", fg_color=ACCENT_CYAN)
            self.btn_mode_toggle.set_active(True, active_border=ACCENT_CYAN)
            if self.state != "playing":
                self.btn_play.set_text("AutoPlay", fg_color=ACCENT_PURPLE)
            self._start_auto_worker_if_needed()
        else:
            self.btn_mode_toggle.set_text("Follower Mode", fg_color=TEXT_WHITE)
            self.btn_mode_toggle.set_active(False)
            if self.state != "playing":
                self.btn_play.set_text("Latihan", fg_color=COLOR_CORRECT)

    def _start_auto_worker_if_needed(self):
        if self.auto_mode and self.state == "playing":
            if not getattr(self, "_auto_worker_running", False):
                self._auto_worker_running = True
                threading.Thread(target=self._auto_play_worker, daemon=True).start()

    def _send_keys_sync(self, chars):
        """Kirim notasi keyboard ke Roblox secara sekuensial dan presisi."""
        if not chars:
            return

        shifted_bases = []
        unshifted_bases = []
        for ch in chars:
            base, is_shifted = get_key_press_info(ch)
            if is_shifted:
                shifted_bases.append(base)
            else:
                unshifted_bases.append(base)

        all_bases = shifted_bases + unshifted_bases
        with _injected_lock:
            for ch in chars:
                _injected_keys[ch] = _injected_keys.get(ch, 0) + 1
                _injected_keys[ch.lower()] = _injected_keys.get(ch.lower(), 0) + 1
            for b in all_bases:
                _injected_keys[b] = _injected_keys.get(b, 0) + 1
                _injected_keys[b.lower()] = _injected_keys.get(b.lower(), 0) + 1

        hold_time = min(0.040, max(0.020, self.key_hold_ms / 1000.0))
        inter_key = 0.005

        try:
            if shifted_bases and unshifted_bases:
                win_press_vk(VK_SHIFT)
                time.sleep(inter_key)
                for b in shifted_bases:
                    vk = get_vk_code(b)
                    if vk:
                        win_press_vk(vk)
                time.sleep(hold_time)
                for b in reversed(shifted_bases):
                    vk = get_vk_code(b)
                    if vk:
                        win_release_vk(vk)
                time.sleep(inter_key)
                win_release_vk(VK_SHIFT)
                time.sleep(inter_key)

                for b in unshifted_bases:
                    vk = get_vk_code(b)
                    if vk:
                        win_press_vk(vk)
                time.sleep(hold_time)
                for b in reversed(unshifted_bases):
                    vk = get_vk_code(b)
                    if vk:
                        win_release_vk(vk)

            elif shifted_bases:
                win_press_vk(VK_SHIFT)
                time.sleep(inter_key)
                for b in shifted_bases:
                    vk = get_vk_code(b)
                    if vk:
                        win_press_vk(vk)
                time.sleep(hold_time)
                for b in reversed(shifted_bases):
                    vk = get_vk_code(b)
                    if vk:
                        win_release_vk(vk)
                time.sleep(inter_key)
                win_release_vk(VK_SHIFT)

            elif unshifted_bases:
                for b in unshifted_bases:
                    vk = get_vk_code(b)
                    if vk:
                        win_press_vk(vk)
                time.sleep(hold_time)
                for b in reversed(unshifted_bases):
                    vk = get_vk_code(b)
                    if vk:
                        win_release_vk(vk)
        except Exception:
            pass
        finally:
            try:
                win_release_vk(VK_SHIFT)
                for b in all_bases:
                    vk = get_vk_code(b)
                    if vk:
                        win_release_vk(vk)
            except Exception:
                pass

    def _auto_play_worker(self):
        """Worker thread sekuensial yang memutar sheet di Auto Mode dengan ritme musikal alami."""
        try:
            while self.state == "playing" and self.auto_mode:
                steps = self.current_steps
                if not steps or self.current_pos >= len(steps):
                    if self.loop_mode:
                        self.current_pos = 0
                        self.slots[self.active_slot]["status"] = {}
                    else:
                        self.state = "finished"
                        self.root.after(0, self._after_advance)
                        break

                # Jika target adalah Roblox, tunggu sampai Roblox fokus tanpa melewati not
                if self.auto_target == "roblox":
                    while not _is_roblox_focused() and self.state == "playing" and self.auto_mode:
                        time.sleep(0.04)

                    if self.state != "playing" or not self.auto_mode:
                        break

                pos = self.current_pos
                step = steps[pos]
                start_t = time.time()

                # Ambil bobot ritme musikal (weight)
                step_weight = step[2] if len(step) > 2 else 1.0
                step_dur = max(0.035, self.rest_delay * step_weight)

                if step[0] == "r":
                    end_t = start_t + step_dur
                    while time.time() < end_t and self.state == "playing" and self.auto_mode:
                        time.sleep(min(0.015, max(0.001, end_t - time.time())))
                elif step[0] == "n":
                    chars = list(step[1])

                    # Mainkan audio dengan resonansi sustain alami
                    if self.audio.is_enabled():
                        self.audio.play_chord(chars, velocity=95)

                    # Kirim ketukan ke Roblox jika target Roblox & jendela fokus
                    if self.auto_target == "roblox" and _is_roblox_focused():
                        self._send_keys_sync(chars)

                    # Nyalakan tuts piano virtual secara sinkron di UI thread
                    if hasattr(self, "keyboard_canvas"):
                        def _flash(ch_list=chars):
                            for ch in ch_list:
                                self.keyboard_canvas.flash_key(ch, color=COLOR_CORRECT, duration_ms=180)
                        self.root.after(0, _flash)

                    spent = time.time() - start_t
                    remaining = step_dur - spent
                    if remaining > 0.002:
                        end_t = time.time() + remaining
                        while time.time() < end_t and self.state == "playing" and self.auto_mode:
                            time.sleep(min(0.015, max(0.001, end_t - time.time())))

                if self.state != "playing" or not self.auto_mode:
                    break

                self.current_step_status[pos] = "correct"
                self.current_pos = pos + 1

                def _ui_update(p=self.current_pos):
                    if p >= len(self.current_steps):
                        if self.loop_mode:
                            self.current_pos = 0
                            self.slots[self.active_slot]["status"] = {}
                        else:
                            self.state = "finished"
                            play_title = "AutoPlay" if self.auto_mode else "Latihan"
                            play_color = ACCENT_PURPLE if self.auto_mode else COLOR_CORRECT
                            self.btn_play.set_text(play_title, fg_color=play_color)
                    self._update_visual_canvas()

                self.root.after(0, _ui_update)
        finally:
            self._auto_worker_running = False

    def _after_advance(self):
        steps = self.current_steps
        if steps and self.current_pos >= len(steps):
            if self.loop_mode:
                self.current_pos = 0
                self.slots[self.active_slot]["status"] = {}
            else:
                self.state = "finished"
                play_title = "AutoPlay" if self.auto_mode else "Latihan"
                play_color = ACCENT_PURPLE if self.auto_mode else COLOR_CORRECT
                self.btn_play.set_text(play_title, fg_color=play_color)
        self._update_visual_canvas()

    def _tick(self):
        try:
            self._tick_body()
        except Exception:
            pass
        try:
            self.root.after(16, self._tick)
        except tk.TclError:
            pass

    def _handle_f6(self):
        self._handle_play_toggle()

    def _handle_play_toggle(self):
        """Mulai atau jeda AutoPlay secara otomatis, mulus, dan bebas patah-patah."""
        if not _is_roblox_focused():
            try:
                if self.root.focus_get() == getattr(self, "sheet_text", None):
                    return
            except Exception:
                pass

        if not self.current_steps:
            self._parse_active_sheet()

        if not self.current_steps:
            return

        if not self.auto_mode:
            self.auto_mode = True
            self.btn_mode_toggle.set_text("Auto Player", fg_color=ACCENT_CYAN)
            self.btn_mode_toggle.set_active(True, active_border=ACCENT_CYAN)
            if self.state != "playing":
                self._toggle_play()
        else:
            if self.state == "playing":
                self._pause()
            else:
                self._toggle_play()

    def _tick_body(self):
        roblox_ok = _is_roblox_focused()
        if getattr(self, "_last_rf", None) != roblox_ok:
            self._last_rf = roblox_ok
            if roblox_ok:
                self.lbl_focus_badge.configure(text="[ROBLOX FOCUSED]", bg="#102a1d", fg=COLOR_CORRECT)
            else:
                self.lbl_focus_badge.configure(text="[FOKUS KE ROBLOX]", bg="#2a2410", fg="#f59e0b")

        try:
            while True:
                item = self._q.get_nowait()
                if isinstance(item, tuple):
                    cmd = item[1]
                    if cmd in ("f6", "plus_toggle"):
                        self._handle_play_toggle()
                elif isinstance(item, str):
                    self.on_key(item)
        except queue.Empty:
            pass

        now = time.time()
        steps = self.current_steps

        if self.metronome_active and self.state == "playing":
            beat_delay = 60.0 / max(20, self.bpm * self.speed_multiplier)
            if now - self.last_metro_time >= beat_delay:
                self.last_metro_time = now
                if self.audio and self.audio.is_enabled():
                    self.audio.play_metronome(accent=False)

        # Follower Mode Rest Advance Loop
        # HANYA berjalan jika mode manual (Follower Mode) dan TIDAK ada worker otomatis yang sedang aktif
        if not self.auto_mode and not getattr(self, "_auto_worker_running", False) and self.state == "playing" and steps and self.current_pos < len(steps):
            step = steps[self.current_pos]
            if step[0] == "r":
                step_weight = step[2] if len(step) > 2 else 1.0
                delay = max(0.04, self.rest_delay * step_weight)
                if now - self.last_rest_time >= delay:
                    self.last_rest_time = now
                    self.current_pos += 1
                    self._after_advance()

    def _install_hook(self):
        def cb(e):
            try:
                name = (e.name or "").lower()
                sc = getattr(e, "scan_code", None)
                vk = getattr(e, "vk", None)

                # Hotkey F6
                if name == "f6" or sc == 64 or vk == 117:
                    if e.event_type == "down":
                        if not getattr(self, "_f6_pressed", False):
                            self._f6_pressed = True
                            self._q.put(("cmd", "f6"))
                    elif e.event_type == "up":
                        self._f6_pressed = False
                    return

                # Hotkey '+' / '=' / Numpad '+'
                if name in ("+", "plus", "numpad +", "=") or "+" in name or sc in (13, 78) or vk in (187, 107):
                    if e.event_type == "down":
                        if not getattr(self, "_plus_pressed", False):
                            self._plus_pressed = True
                            self._q.put(("cmd", "plus_toggle"))
                    elif e.event_type == "up":
                        self._plus_pressed = False
                    return

                if e.event_type == "down":
                    if "shift" in name:
                        self._shift = True
                        return
                    with _injected_lock:
                        if _injected_keys.get(e.name, 0) > 0:
                            _injected_keys[e.name] -= 1
                            return
                        if _injected_keys.get(name, 0) > 0:
                            _injected_keys[name] -= 1
                            return
                    shift_held = self._shift or "shift" in (e.modifiers or ())
                    key = normalize_key(e.name, shift_held)
                    if not key and len(e.name) == 1:
                        key = e.name
                    if key:
                        self._q.put(key)
                elif e.event_type == "up" and "shift" in name:
                    self._shift = False
            except Exception:
                pass

        self._hook_cb = cb
        keyboard.hook(cb)

    def on_key(self, key):
        if self.audio.is_enabled():
            self.audio.play_key(key, velocity=95, duration=0.5)

        if self.recording:
            elapsed = time.time() - self.record_start_time
            self.recorded_keys.append((elapsed, key))

        # Jika Auto Player aktif atau worker sedang berjalan, abaikan input manual agar tidak terjadi race condition
        if self.auto_mode or self.state != "playing" or getattr(self, "_auto_worker_running", False):
            return
        steps = self.current_steps
        if not steps or self.current_pos >= len(steps):
            return

        step = steps[self.current_pos]
        if step[0] == "r":
            self._update_visual_canvas()
            return

        keys = step[1]
        if key in keys:
            self.current_step_status[self.current_pos] = "correct"
            self.combo += 1
            self.correct_count += 1
            self.last_rest_time = time.time()
            if hasattr(self, "keyboard_canvas"):
                self.keyboard_canvas.flash_key(key, color=COLOR_CORRECT, duration_ms=200)
            self.current_pos += 1
            self._after_advance()
        else:
            self.current_step_status[self.current_pos] = "wrong"
            self.combo = 0
            self.wrong_count += 1
            if hasattr(self, "keyboard_canvas"):
                self.keyboard_canvas.flash_key(key, color=COLOR_WRONG, duration_ms=250)
            self._update_visual_canvas()

    def _on_close(self):
        self._release_manual_plus()
        try:
            keyboard.unhook(self._hook_cb)
        except Exception:
            pass
        if self.audio:
            self.audio.close()
        try:
            self.cfg["geometry"] = self.root.geometry()
            self.cfg["bpm"] = self.bpm
            self.cfg["speed_multiplier"] = self.speed_multiplier
            self.cfg["transpose"] = self.transpose
            self.cfg["sustain"] = self.sustain
            self.cfg["loop_mode"] = self.loop_mode
            self.cfg["pinned"] = self.is_pinned
            self.cfg["audio_enabled"] = self.audio.is_enabled()
            self.cfg["rhythm_mode"] = self.rhythm_mode
            self.cfg["auto_target"] = self.auto_target
            self.cfg["favorites"] = list(self.song_library.favorites)
            CONFIG_PATH.write_text(json.dumps(self.cfg, indent=2), encoding="utf-8")
        except Exception:
            pass
        self.root.destroy()

    def _load_config(self):
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}


def _enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def main():
    _enable_dpi_awareness()
    app = PianoApp()
    app.root.mainloop()


if __name__ == "__main__":
    main()
