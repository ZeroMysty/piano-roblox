"""Manajer Perpustakaan Lagu (Song Library) untuk Roblox Piano Studio.

Menyediakan pencarian instan, filter kategori (Anime, Pop, Klasik, Game, OST),
perhitungan kesulitan, tagging, dan penanda lagu favorit.
"""

from pathlib import Path
import re
from sheet_tools import analyze_sheet_stats

# Aturan tagging otomatis berdasarkan kata kunci judul/nama file
CATEGORY_RULES = {
    "Anime & Game": [
        "titan", "aot", "doraemon", "kamado", "undertale", "hopes_and_dreams",
        "shop", "michishirube", "ghibli", "erika", "blue"
    ],
    "Cinema & OST": [
        "interstellar", "married_life", "up", "ost", "experience", "theme"
    ],
    "Klasik": [
        "canon", "beethoven", "virus", "pachelbel", "fur elise", "mozart", "bach", "chopin"
    ],
    "Pop & Hits": [
        "losing us", "raissa", "love_story", "sampai_jadi_debu", "no_suprises",
        "radiohead", "karaoke", "debussy", "taylor", "golden hour"
    ],
}


def clean_display_title(filename: str) -> str:
    """Format nama file menjadi judul lagu yang rapi dan elegan."""
    stem = Path(filename).stem
    if stem.lower().endswith(".mid"):
        stem = stem[:-4]
    
    # Bersihkan pola teks umum
    stem = re.sub(r"[-_]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem.title()


class SongLibrary:
    def __init__(self, songs_dir: Path, favorites: list = None):
        self.songs_dir = Path(songs_dir)
        self.favorites = set(favorites or [])
        self.catalog = []
        self.reload()

    def reload(self):
        """Memindai ulang folder songs/ dan mengindeks seluruh lagu."""
        self.catalog = []
        if not self.songs_dir.exists():
            return

        for f in sorted(self.songs_dir.glob("*.txt")):
            if f.stat().st_size == 0:
                continue

            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            if not content.strip():
                continue

            # Ekstrak metadata dari komentar header jika ada
            title = clean_display_title(f.name)
            artist = "Roblox Piano"
            bpm = 100

            for line in content.splitlines()[:5]:
                line_str = line.strip()
                if line_str.startswith("#"):
                    if "BPM:" in line_str:
                        m = re.search(r"BPM:\s*~?(\d+)", line_str, re.IGNORECASE)
                        if m:
                            bpm = int(m.group(1))
                    if "Sheet Roblox Piano:" in line_str:
                        raw_t = line_str.replace("# Sheet Roblox Piano:", "").strip()
                        raw_t = re.sub(r"\(BPM:[^)]*\)", "", raw_t)
                        raw_t = re.sub(r"\[Transpose:[^\]]*\]", "", raw_t).strip()
                        if raw_t:
                            title = clean_display_title(raw_t)

            # Hitung statistik
            stats = analyze_sheet_stats(content, bpm=bpm)

            # Tentukan kategori
            lower_name = f.name.lower() + " " + title.lower()
            categories = []
            for cat, keywords in CATEGORY_RULES.items():
                if any(kw in lower_name for kw in keywords):
                    categories.append(cat)

            if not categories:
                categories.append("Pop & Hits" if stats["difficulty_level"] <= 2 else "Klasik")

            if stats["difficulty_level"] <= 2:
                categories.append("Pemula")

            is_fav = f.name in self.favorites

            self.catalog.append({
                "filename": f.name,
                "path": str(f),
                "title": title,
                "artist": artist,
                "bpm": bpm,
                "categories": categories,
                "stats": stats,
                "is_fav": is_fav,
                "content": content,
            })

    def filter(self, query="", category="Semua", favorites_only=False):
        """Menyaring katalog berdasarkan kata kunci, kategori, atau status favorit."""
        q = (query or "").lower().strip()
        results = []

        for item in self.catalog:
            if favorites_only and not item["is_fav"]:
                continue

            if category and category != "Semua":
                if category == "Favorit":
                    if not item["is_fav"]:
                        continue
                elif category not in item["categories"]:
                    continue

            if q:
                match_title = q in item["title"].lower()
                match_fn = q in item["filename"].lower()
                match_cat = any(q in c.lower() for c in item["categories"])
                if not (match_title or match_fn or match_cat):
                    continue

            results.append(item)

        return results

    def toggle_favorite(self, filename: str) -> bool:
        """Toggle status bintang favorit untuk sebuah lagu."""
        if filename in self.favorites:
            self.favorites.remove(filename)
            new_state = False
        else:
            self.favorites.add(filename)
            new_state = True

        for item in self.catalog:
            if item["filename"] == filename:
                item["is_fav"] = new_state
                break

        return new_state
