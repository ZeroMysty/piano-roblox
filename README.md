# 🎹 Roblox Piano Studio Pro

Aplikasi desktop profesional untuk **bantu bermain dan menguasai piano di Roblox** — dirancang dengan visual modern, performa tinggi, dan fitur lengkap yang mampu menyaingi dan melengkapi platform web seperti **playpianosheet.com** dan **virtualpiano.net**.

Aplikasi ini mendeteksi tekanan tombol keyboard secara **GLOBAL**, sehingga tetap sinkron meski jendela game Roblox sedang aktif di foreground (sempurna untuk split-screen atau dual-monitor).

---

## ✨ Fitur Unggulan

### 🔊 1. Mesin Audio Piano Akustik Real-Time (<5ms Latency)
- **Built-in Windows MIDI Synthesizer**: Suara Grand Piano akustik jernih tanpa perlu install soundfont atau library berat pihak ketiga.
- Suara berbunyi saat latihan (Follower Mode), preview lagu, maupun saat mengklik tuts piano virtual.
- Tombol **Suara: ON / OFF** untuk mematikan suara aplikasi jika ingin hanya mendengarkan suara dari dalam game Roblox.

### 🎹 2. Virtual Piano 61-Tuts Interaktif (Clickable)
- Tuts piano realistis 61 nada (C3 hingga C8) yang dapat **diklik langsung dengan mouse**.
- Visual highlight nada aktif (akord bersinar cyan/ungu), efek kilau hijau saat not ditekan benar, dan merah saat salah.
- **Mode Label Fleksibel**:
  - `Label: Key` (1 2 3... q w e... a s d... dengan simbol Shift ! @ $...)
  - `Label: Nada` (C3, D3, E3, F3... C#3, D#3...)
  - `Label: Ganda` (Menampilkan tombol keyboard dan nama nada sekaligus)
  - `Label: Polos` (Tampilan tuts bersih tanpa tulisan)
- Penanda oktaf C emas (C3, C4 / Middle C, C5, C6, C7).

### 📚 3. Katalog Lagu Lengkap (Song Library)
- Dilengkapi **25+ lagu hits siap main** (Interstellar, Golden Hour, Fur Elise, Canon in D, AOT, Demon Slayer, Raissa Anggiani, Yiruma, Spirited Away, dll).
- **Pencarian instan** berdasarkan judul, artis, atau kategori.
- **Filter Kategori**: Anime & Game, Cinema & OST, Klasik, Pop & Hits, Pemula, dan ⭐ Favorit.
- **Audio Preview**: Dengarkan cuplikan audio lagu sebelum dimainkan.
- Indikator tingkat kesulitan bintang (★☆☆☆☆ s.d. ★★★★★), perkiraan durasi, dan total not.

### 🛠️ 4. Sheet Tools & Transpose
- **Transpose Instan**: Geser nada sheet teks (+1 / -1 semitone, +12 / -12 oktaf) dengan 1 klik.
- **Format & Rapikan Sheet (Beautifier)**: Merapikan sheet hasil copy-paste internet yang berantakan menjadi baris-baris beraturan dan rapi.
- **Simplifikasi Akord**: Opsi menyederhanakan akord tebal (4-5 jari) menjadi 2 nada (bass + melodi) untuk mengatasi keyboard tanpa anti-ghosting.

### 📊 5. Performance HUD & Practice Tracker
- **Akurasi Real-Time (%)** dan pelacak **Streak / Combo 🔥**.
- Indikator kemajuan notasi (`Not: 42 / 380 (11%)`).
- **Navigasi Cepat**: Mulai ulang (`|<<`), Mundur 5 langkah (`<< 5`), Lewati 5 langkah (`5 >>`).
- **Mode Loop (🔁)**: Mengulang lagu secara otomatis dari awal setelah selesai.
- **Audio Metronome (⏱)**: Bunyi ketukan tempo sinkron dengan BPM untuk melatih ritme bermain.
- **Speed Multiplier**: Pilihan kecepatan `0.5x`, `0.75x`, `1.0x`, `1.25x`, `1.5x`.

### ⚡ 6. Roblox Gaming Tools
- 📌 **Pin (Always on Top)**: Menjaga jendela aplikasi selalu mengambang di atas game Roblox.
- ⚡ **Shortcut Global F6 (Auto Player)**: Tekan F6 di mana saja untuk toggle Auto Player otomatis mengetik ke Roblox.
- ➕ **Tombol Manual `+`**: Tekan dan tahan tombol `+` untuk menahan not aktif di Roblox dengan durasi presisi.
- 🎵 **Import MIDI Langsung**: Analisis durasi, BPM, dan kalkulator transpose otomatis.
- 🪄 **Transkripsi Audio AI**: Konversi audio `.mp3`, `.wav`, `.m4a` menjadi MIDI & Sheet via ByteDance Solo Piano AI.

---

## 📦 Persyaratan & Instalasi

Pastikan menggunakan **Python 3.10+** dan sistem operasi **Windows**.

```bash
pip install -r requirements.txt
```

---

## ▶️ Menjalankan Aplikasi

Jalankan langsung dengan klik dua kali `Jalankan Aplikasi.bat` atau via terminal:

```bash
python app.py
```

---

## 🎮 Cara Pakai

1. Buka aplikasi dan klik tombol **Library** untuk memilih lagu (atau gunakan tombol **Paste** jika memiliki sheet sendiri).
2. Klik **▶ Play**.
3. Arahkan kursor dan klik jendela **Roblox** (badge fokus akan berubah menjadi hijau `[ROBLOX FOCUSED]`).
4. Mainkan piano di keyboard kamu:
   - Tombol yang benar → not maju berwarna hijau + kombo bertambah.
   - Tombol salah → ditandai merah.
   - Tanda jeda `|` atau `-` → otomatis lewat sesuai tempo BPM.
5. Ingin santai mendengarkan bot bermain? Tekan tombol **Follower Mode** untuk berpindah ke **Auto Player** (atau tekan tombol **F6** kapan saja).

---

## 🎹 Layout Keyboard Roblox (Virtual Piano MAX)

```
Tombol PUTIH :  1 2 3 4 5 6 7 8 9 0 q w e r t y u i o p a s d f g h j k l z x c v b n m
Tombol HITAM :   ! @   $ % ^   * (   Q W   E T Y   I O P   S D   G H J   L   Z C   V B
```

- Nada putih: tekan tuts langsung (misal: `a`, `s`, `d`).
- Nada hitam: tekan **Shift + tuts** (misal: `Shift+1` = `!`, `Shift+s` = `S`).

---

## 🧪 Pengujian Unit

Jalankan skrip tes mandiri untuk memverifikasi seluruh komponen:

```bash
python selftest.py
```
