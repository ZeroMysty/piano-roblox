"""Audio to MIDI & Roblox Sheet Transcription module.

Uses ByteDance Solo Piano Audio-to-MIDI Transcription AI via Hugging Face API
(asigalov61/ByteDance-Solo-Piano-Audio-to-MIDI-Transcription).
"""

import os
import shutil
from pathlib import Path
import mido

from gradio_client import Client, handle_file
from layouts import build_pitch_map

HF_SPACE_ID = "asigalov61/ByteDance-Solo-Piano-Audio-to-MIDI-Transcription"
CHORD_WINDOW = 0.05  # 50 ms chord tolerance
PAUSE_THRESHOLD = 0.4  # seconds pause before adding '|'


def transcribe_audio_to_midi(audio_path, output_dir=None, status_callback=None, hf_token=None):
    """Kirim file audio ke ByteDance Solo Piano AI Hugging Face Space.

    Args:
        audio_path: Path ke file audio.
        output_dir: Direktori output MIDI (opsional).
        status_callback: Fungsi callback(msg) untuk update status.
        hf_token: Hugging Face token (str) untuk bypass ZeroGPU quota limit.

    Returns:
        midi_path (str): Path ke file MIDI terdownload.
    """
    audio_path = str(Path(audio_path).resolve())
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"File audio tidak ditemukan: {audio_path}")

    if status_callback:
        status_callback("Menghubungkan ke ByteDance AI (Hugging Face)...")

    if hf_token:
        client = Client(HF_SPACE_ID, token=hf_token)
    else:
        client = Client(HF_SPACE_ID)

    if status_callback:
        status_callback("Memproses audio & melakukan transkripsi AI...")

    result = client.predict(
        input_file=handle_file(audio_path),
        api_name="/TranscribePianoAudio"
    )

    # Result structure:
    # (output_midi_title, output_midi_summary, output_midi_file, output_midi_audio, output_midi_score_plot)
    midi_file_info = result[2]
    temp_midi_path = None
    if isinstance(midi_file_info, dict):
        temp_midi_path = midi_file_info.get("path")
    elif isinstance(midi_file_info, str):
        temp_midi_path = midi_file_info

    if not temp_midi_path or not os.path.exists(temp_midi_path):
        raise RuntimeError("Gagal mendapatkan file MIDI dari hasil transkripsi AI.")

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = Path(audio_path).stem + "_transcribed.mid"
        dest_path = output_dir / filename
        shutil.copy(temp_midi_path, dest_path)
        return str(dest_path)

    return temp_midi_path


from midi_import import midi_to_sheet_text as _midi_to_sheet_text


def midi_to_sheet_text(midi_path, transpose=0, base_midi=48):
    """Konversi file MIDI menjadi teks sheet format Roblox Piano."""
    return _midi_to_sheet_text(
        midi_path,
        transpose=transpose,
        base_midi=base_midi,
        source_note="Transkripsi oleh ByteDance Solo Piano AI"
    )

