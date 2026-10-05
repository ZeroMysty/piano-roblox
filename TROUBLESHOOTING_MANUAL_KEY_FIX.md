# 🎹 Panduan Perbaikan: Manual Key Detection Tidak Terdeteksi

## 🐛 Masalah yang Dilaporkan
**"Saat aku main manual key yang aku tekan tidak terdeteksi di app jadi notnya tidak bergeser"**

Terjemahan: Ketika bermain dalam mode manual/follower, tombol yang ditekan tidak terdeteksi oleh aplikasi, sehingga nada tidak maju ke not berikutnya.

---

## 🔍 Root Causes yang Ditemukan

### Issue #1: Shift Key Detection yang Rapuh
**Masalah:** Ketika Shift+angka ditekan (seperti Shift+1 untuk "!"), deteksi shift key bisa gagal karena:
- Keyboard library Windows tidak selalu melaporkan event Shift terlebih dahulu
- Event modifiers dari library bisa tidak konsisten
- Timing issue antara shift press dan key press

**Dampak:** Semua tombol hitam (!, @, $, %, ^, *, () tidak terdeteksi atau terdeteksi dengan delay

### Issue #2: Fallback Detection yang Terbatas  
**Masalah:** Jika keyboard event parsing gagal pada pass pertama, tidak ada fallback yang robust
- Hanya cek sederhana dengan `len(e.name) == 1`
- Tidak handle symbols yang dilaporkan langsung oleh library
- Tidak cek terhadap VALID_KEYS secara eksplisit

**Dampak:** Edge cases menghasilkan key yang tidak dikenali

### Issue #3: Modifiers Parsing yang Inkonsisten
**Masalah:** Deteksi modifiers dari keyboard library bisa berbeda-beda:
```python
# Old code (tidak robust)
shift_held = self._shift or "shift" in (e.modifiers or ())
```

Seharusnya:
```python
# Better code
shift_held = self._shift or any(
    "shift" in mod for mod in (getattr(e, "modifiers", []) or [])
)
```

---

## ✅ Solusi yang Diterapkan

### Perbaikan #1: Improved Keyboard Event Parsing
File baru: `_parse_keyboard_event()` di app_fixed.py

```python
def _parse_keyboard_event(e):
    """
    Parse keyboard event dengan lebih robust.
    Return (normalized_key, is_shift_event).
    
    Menangani edge cases:
    - Symbol keys yang dilaporkan langsung (!, @, $, %, ^, *, ()
    - Shift+number combinations
    - Different keyboard library behaviors on Windows
    """
    name = (e.name or "").lower().strip()
    
    # 1. Deteksi Shift key
    if "shift" in name:
        return None, True
    
    # 2. Fallback 1: Cek apakah sudah dalam VALID_KEYS (case-sensitive)
    if e.name in VALID_KEYS:
        return e.name, False
    
    # 3. Fallback 2: Lowercase untuk letters
    if name in VALID_KEYS:
        return name, False
    
    # 4. Fallback 3: Normalize dengan shift detection
    modifiers = getattr(e, "modifiers", []) or []
    shift_held = "shift" in modifiers or "left shift" in modifiers or "right shift" in modifiers
    
    if len(name) == 1:
        normalized = normalize_key(name, shift_held)
        if normalized:
            return normalized, False
    
    return None, False
```

### Perbaikan #2: Enhanced Hook Callback
Diperbarui hook callback di `_install_hook()`:

```python
if e.event_type == "down":
    # === IMPROVED KEY DETECTION ===
    # 1. Check if shift key
    if "shift" in name:
        self._shift = True
        return
    
    # 2. Check if injected key
    with _injected_lock:
        if _injected_keys.get(e.name, 0) > 0:
            _injected_keys[e.name] -= 1
            return
    
    # 3. Parse event dengan robust fallback
    key, is_shift_event = _parse_keyboard_event(e)
    if is_shift_event:
        self._shift = True
        return
    
    # 4. Use self._shift tracking as fallback
    if not key:
        shift_held = self._shift or "shift" in (getattr(e, "modifiers", []) or [])
        key = normalize_key(e.name, shift_held)
    
    # 5. Final fallback untuk single char
    if not key and len(e.name) == 1 and e.name in VALID_KEYS:
        key = e.name
    
    # 6. Queue the key
    if key:
        self._q.put(key)
```

---

## 🚀 Cara Menggunakan Fix

### Opsi A: Ganti file app.py (Rekomendasi)
```bash
# Backup file lama
copy app.py app.py.backup

# Gunakan file baru
copy app_fixed.py app.py
```

### Opsi B: Merge Manual
Jika kamu memiliki custom changes di app.py lama, merge changes dari app_fixed.py ke app.py lama:
1. Cari fungsi `_install_hook()` di app.py
2. Ganti seluruh fungsi dengan versi baru dari app_fixed.py
3. Tambahkan fungsi baru `_parse_keyboard_event()` sebelum class `PianoApp`

---

## 🧪 Testing Checklist

Setelah menerapkan fix, test dengan:

### Test 1: Tombol Putih (Normal Keys)
- [ ] Tekan '1', '2', '3', dst tanpa Shift
- [ ] Cek apakah app mengenali key press
- [ ] Not di visual sheet harus berpindah ke hijau (correct)

### Test 2: Tombol Hitam (Shift+Number)
- [ ] Tekan Shift+1 (harusnya tombol !)
- [ ] Tekan Shift+2 (harusnya tombol @)
- [ ] Tekan Shift+4 (harusnya tombol $)
- [ ] Dst untuk black keys lainnya
- [ ] Visual sheet harus mengenali key press

### Test 3: Huruf dengan Shift
- [ ] Tekan 'q' (white key)
- [ ] Tekan Shift+q = 'Q' (black key)
- [ ] Keduanya harus terdeteksi di visual sheet

### Test 4: Sequencing
- [ ] Paste sheet sederhana: "1 2 3 4"
- [ ] Tekan Play (atau tekan + key untuk auto-start in Follower Mode)
- [ ] Tekan keys sesuai urutan
- [ ] Check: warna berubah hijau ketika correct
- [ ] Not harus berpindah otomatis ke berikutnya

### Test 5: Roblox Integration
- [ ] Buka Roblox piano mini game
- [ ] Pastikan window Roblox aktif (badge berubah ke [ROBLOX FOCUSED])
- [ ] Test manual key press di Roblox
- [ ] App visual sheet harus menyinkron dengan Roblox

---

## 📋 Checklist Sebelum Bermain

Pastikan ini sudah benar sebelum test manual keys:

- [ ] **Mode Benar**: Pastikan mode adalah **"Follower Mode"** (bukan Auto Player)
  - Lihat button di dock area bawah
  - Seharusnya tulisannya "Follower Mode"

- [ ] **Playback Dimulai**: Tekan tombol **"Play"** sebelum mulai tekan keys
  - Button Play harus berubah jadi "Playing"
  - Status badge di atas harus menunjukkan state aktif

- [ ] **Sheet Ter-load**: Paste atau load sheet lagu di tab "Edit Sheet"
  - Sheet harus valid dengan valid piano keys
  - Visual Sheet harus menampilkan not di tengah layar (kotak biru)

- [ ] **Roblox Aktif**: Window Roblox harus aktif di foreground
  - Badge di atas sebelah kiri harus berubah hijau: "[ROBLOX FOCUSED]"
  - Jika badge kuning, click window Roblox untuk fokus

---

## 🎯 Expected Behavior Setelah Fix

### Follower Mode (Manual Key Detection)
1. **Play sheet**: Tekan Play button
2. **Current note highlighted**: Kotak biru menunjukkan not yang aktif
3. **Press key**: User tekan tombol piano (1, 2, 3, !, @, dll)
4. **Key detected**: Key muncul di visual sheet dengan warna:
   - ✅ **Hijau**: Key correct, lanjut ke not berikutnya
   - ❌ **Merah**: Key salah, tidak lanjut
5. **Auto-advance**: Untuk rest markers (- |), auto-advance setelah delay
6. **End**: Semua not selesai, state menjadi "finished"

### Example:
```
Sheet: 1 2 3 ! @ 4 5

Scenario:
User press: [1] ✅ Green - advance to 2
User press: [2] ✅ Green - advance to 3
User press: [3] ✅ Green - advance to !
User press: [Shift+1] ✅ Green - advance to @
User press: [Shift+2] ✅ Green - advance to 4
...
```

---

## 🔧 Advanced Troubleshooting

### Jika masih tidak terdeteksi:

#### Step 1: Check Mode
```
Pastikan:
☐ Button toggle menunjukkan "Follower Mode" (bukan "Auto Player")
☐ Playback state adalah "playing" (button Play terlihat active)
```

#### Step 2: Check Window Focus
```
Pastikan:
☐ Badge di top-left berubah HIJAU: "[ROBLOX FOCUSED]"
☐ Jika badge KUNING: click window Roblox untuk refocus
```

#### Step 3: Debug Keyboard Hook
Tambahkan ini di `on_key()` untuk debug:

```python
def on_key(self, key):
    print(f"[DEBUG] on_key called: key={key}, auto_mode={self.auto_mode}, state={self.state}")
    
    if self.auto_mode or self.state != "playing":
        print(f"[DEBUG] Ignored: auto_mode={self.auto_mode}, state={self.state}")
        return
    
    steps = self.current_steps
    if not steps or self.current_pos >= len(steps):
        print(f"[DEBUG] No steps: steps={len(steps)}, pos={self.current_pos}")
        return
    
    step = steps[self.current_pos]
    print(f"[DEBUG] Current step: type={step[0]}, keys={step[1]}")
    
    if step[0] == "r":
        print(f"[DEBUG] Step is rest, ignoring")
        return

    keys = step[1]
    if key in keys:
        print(f"[DEBUG] KEY MATCH! {key} in {keys}")
        # ... rest of code
    else:
        print(f"[DEBUG] KEY MISMATCH! {key} not in {keys}")
        # ... rest of code
```

Jalankan app dan lihat console output untuk debug info.

#### Step 4: Check Keyboard Library
Pastikan keyboard library terinstall:
```bash
pip list | find "keyboard"
# Seharusnya muncul: keyboard>=0.13.5

# Jika tidak ada:
pip install --upgrade keyboard
```

#### Step 5: Run as Administrator
Keyboard hook pada Windows kadang memerlukan admin privileges:
1. Klik kanan app shortcut
2. Pilih "Run as Administrator"
3. Test kembali

---

## 📝 Version History

### v2.0 (Fixed)
- ✅ Improved keyboard event parsing dengan multiple fallbacks
- ✅ Better shift key detection logic
- ✅ Enhanced modifiers parsing dari keyboard library
- ✅ Better error handling dalam hook callback

### v1.0 (Original)
- ❌ Manual key detection gagal pada edge cases
- ❌ Shift key handling tidak robust
- ❌ Limited fallback untuk symbol keys

---

## 💬 Notes

- Fix ini fokus pada **key press detection**, bukan Roblox integration
- Jika Roblox masih tidak merespons keys, issue mungkin pada side Roblox
- Test di sandbox dulu sebelum main di actual Roblox game
- Report any remaining issues dengan include console output dari debug mode

Good luck! 🎮🎵
