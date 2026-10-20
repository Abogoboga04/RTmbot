# MASTER PLAN IMPLEMENTASI: UNIFIED SOCIAL MEDIA CHECKER (YOUTUBE & TIKTOK) & PERBAIKAN PARTY GAMES

## 1. Ringkasan Proyek & Standar Kualitas Kode

Dokumen ini merupakan master plan implementasi untuk menyatukan pemantau otomatis **YouTube dan TikTok** ke dalam satu cog terpadu (`cogs/social_checker.py`), menerapkan sistem konfigurasi fleksibel setara `cogs/notif.py`, serta memperbaiki bug command `!balapan` di `cogs/party_games.py`.

### Standar Kebersihan Kode (Zero Comment Bloat Policy):
Sesuai permintaan pengguna, seluruh kode baru dan perbaikan akan ditulis dengan prinsip kebersihan mutlak:
1. **Tanpa Komentar Bertele-tele:** Menghilangkan narasi alur, catatan hardcode, nomor langkah (`# Step 1`, `# Step 2`), dan banner pemisah berulang (`# =================`).
2. **Tanpa Emoji Dekoratif di Kode:** Tidak ada emoji dalam komentar kode Python.
3. **Self-Documenting Code:** Struktur fungsi, nama variabel, dan penanganan logika dibuat jelas dan modular sehingga kode dapat dipahami secara langsung tanpa perlu tumpukan komentar yang mengotori file.

---

## 2. Perbaikan Bug `!balapan` (`TavernPartyGames`)

### Akar Masalah
Pada `cogs/party_games.py` baris 2146 dan 2407, perintah `!balapan` memanggil method helper `self._get_current_bets_text(race_state['bets'], race_state['horses'])` yang belum didefinisikan di dalam kelas `TavernPartyGames`, memicu runtime error `AttributeError`.

### Rencana Solusi
Menambahkan method helper `_get_current_bets_text` pada kelas `TavernPartyGames` di `cogs/party_games.py` dengan format kode bersih tanpa komentar berlebihan:
```python
def _get_current_bets_text(self, bets: dict, horses: list) -> str:
    if not bets:
        return "- Belum ada taruhan.\n"
    horse_map = {h['id']: h['name'] for h in horses}
    lines = []
    for user_id_str, bet_info in bets.items():
        h_name = horse_map.get(bet_info['horse_id'], f"Kuda #{bet_info['horse_id']}")
        lines.append(f"• <@{user_id_str}>: **{bet_info['amount']:,} RSWN** pada **{h_name}** (#{bet_info['horse_id']})")
    return "\n".join(lines) + "\n"
```

---

## 3. Arsitektur Terpadu: `cogs/social_checker.py` (`SocialChecker`)

Penyatuan pemantauan YouTube dan TikTok ke dalam satu file cog yang rapi dan terorganisir:
- **Nama File Cog:** `cogs/social_checker.py`
- **Nama Kelas:** `SocialChecker(commands.Cog)`
- **Dukungan Perintah Hybrid (Slash & Prefix):** Menggunakan `@commands.hybrid_group` untuk YouTube (`/yt` & `!yt`), TikTok (`/tt` & `!tt`), dan Checker Global (`/checker` & `!checker`).
- **Owner-Only Test Guard:** Seluruh perintah diproteksi dengan `@commands.is_owner()` selama masa pengetesan.
- **Penyimpanan MongoDB Terpusat:** Konfigurasi dan riwayat cache tersimpan permanen di database `reSwan` (koleksi `social_checker_config` dan `social_checker_cache`).

---

## 4. Skema Database MongoDB Terpusat (`reSwan`)

### Koleksi: `social_checker_config`
```json
{
  "_id": "social_checker_config",
  "data": {
    "check_interval_seconds": 30,
    "targets": [
      {
        "id": "target_uuid",
        "platform": "youtube", // "youtube" | "tiktok"
        "identifier": "UCrEj4d2ynysNsYttTYROXEg", // Channel ID YouTube atau Username TikTok
        "display_name": "Luthfi Halimawan",
        "target_guild_id": 1234567890,
        "target_channel_id": 1417636236356485141,
        "mention_role": "@everyone",
        "message_mode": "ai", // "ai" | "default" | "custom"
        "custom_template": "{mention} Ada konten baru dari {creator}!\n{judul}\n{url}",
        "enabled": true,
        "added_at": "2026-10-20T18:30:00Z"
      }
    ]
  }
}
```

### Koleksi: `social_checker_cache`
```json
{
  "_id": "social_checker_cache",
  "data": {
    "posted_ids": ["0ZR1PPQHp98", "7698275878328978740"]
  }
}
```

---

## 5. Mesin Deteksi Konten Real-time

### A. YouTube Native Engine
- **Triple-Layer Scanning:**
  1. Universal User Uploads Playlist (`UU...`)
  2. Direct Canonical Live Detection (`/channel/{id}/live`) dengan pembacaan tag `<link rel="canonical">` (kebal dari rekomendasi sidebar)
  3. Atom RSS Feed
- **Strict Channel Ownership Guard:** Memverifikasi `channelId` asli dari video untuk menolak video rekomendasi streamer lain.

### B. TikTok Native Engine
- **`yt_dlp` Asynchronous Engine:**
  - Pemindaian profil target (`https://www.tiktok.com/@{username}`) via `asyncio.to_thread`.
  - 100% kebal Slardar WAF TikTok, kecepatan tinggi (~3 detik), menghasilkan Video ID, Caption, Uploader Name, Thumbnail, dan Upload Timestamp.
- **Timestamp Freshness Guard:** Memverifikasi timestamp unggahan (< 6 jam) agar video arsip lama tidak dikirim saat akun baru ditambahkan.

### C. Sistem Format Pesan (3 Mode Fleksibel Setara `cogs/notif.py`)
1. **Mode AI (Default):** Gemini AI menyusun copywriting santai dan kontekstual sesuai judul video atau caption TikTok.
2. **Mode Default (Bawaan):** Menggunakan template bawaan standar:
   - YouTube Video: `@everyone Video baru dari **{creator}** nih!`
   - YouTube Live: `@everyone **{creator}** lagi live streaming nih!`
   - TikTok Video: `@everyone Video TikTok baru dari **{creator}** nih!`
3. **Mode Custom:** Pengguna dapat menyusun pesan sendiri menggunakan placeholder:
   - `{creator}`: Nama pembuat konten
   - `{judul}`: Judul video / caption
   - `{url}`: Link video YouTube / TikTok
   - `{mention}`: Role mention yang dikonfigurasi

### D. Tampilan Discord V2 Card (1 Pesan Tunggal)
- Menggunakan `send_v2_message(..., content=mention_content)`:
  - Mention dan teks pengantar disisipkan sebagai Text Display (Type 10) di baris teratas kartu.
  - Judul Markdown H1 yang dapat diklik langsung.
  - Subtitle berisi cuplikan deskripsi/caption dan link.
  - Gambar cover/thumbnail resolusi tinggi.
  - Tombol URL (Style 5): `"Tonton Video"`, `"Tonton Live"`, atau `"Tonton di TikTok"`.

---

## 6. Kumpulan Perintah Hybrid Lengkap (Prefix & Slash - Owner Only)

Semua perintah diproteksi dengan `@commands.is_owner()`.

### A. Perintah YouTube (`!yt` atau `/yt`)
- `add <identifier> [target_channel]`: Daftarkan channel YouTube. Target channel opsional (default ke channel saat ini).
- `remove <identifier>`: Hapus channel YouTube dari pemantauan.
- `setchannel <identifier> <target_channel>`: Ubah target channel pengiriman dari mana saja.
- `setmention <identifier> <role>`: Ubah sebutan (@everyone, @role, atau none).
- `setmode <identifier> <mode> [custom_text]`: Atur mode pesan (`ai`, `default`, atau `custom`).
- `toggle <identifier>`: Aktifkan/nonaktifkan pemantauan channel.
- `list`: Tampilkan daftar seluruh channel YouTube yang dipantau beserta konfigurasinya.
- `test <url>`: Uji coba langsung pengiriman kartu V2 untuk link YouTube tertentu.
- `check`: Paksa pengecekan pembaruan YouTube seketika.

### B. Perintah TikTok (`!tt` atau `/tt`)
- `add <username> [target_channel]`: Daftarkan akun TikTok. Target channel opsional (default ke channel saat ini).
- `remove <username>`: Hapus akun TikTok dari pemantauan.
- `setchannel <username> <target_channel>`: Ubah target channel pengiriman dari mana saja.
- `setmention <username> <role>`: Ubah sebutan (@everyone, @role, atau none).
- `setmode <username> <mode> [custom_text]`: Atur mode pesan (`ai`, `default`, atau `custom`).
- `toggle <username>`: Aktifkan/nonaktifkan pemantauan akun TikTok.
- `list`: Tampilkan daftar seluruh akun TikTok yang dipantau beserta konfigurasinya.
- `test <url>`: Uji coba langsung pengiriman kartu V2 untuk link video TikTok tertentu.
- `check`: Paksa pengecekan pembaruan TikTok seketika.

### C. Perintah Global Checker (`!checker` atau `/checker`)
- `list`: Ringkasan gabungan seluruh target YouTube & TikTok yang aktif.
- `check`: Pengecekan manual serentak seluruh platform.
- `interval <detik>`: Ubah kecepatan background loop polling secara dinamis.
- `cache`: Periksa riwayat ID video yang tersimpan di cache.
- `resetcache`: Kosongkan cache untuk pengujian ulang.

---

## 7. Checklist Pelaksanaan

- [ ] Menunggu Masukan & Persetujuan Pengguna ("ACC") untuk Rencana Implementasi
- [ ] Terapkan fungsi `_get_current_bets_text` di `cogs/party_games.py` dengan gaya kode bersih
- [ ] Buat cog baru `cogs/social_checker.py` (`SocialChecker`) dengan kode bersih tanpa comment bloat
- [ ] Terapkan integrasi database MongoDB (`social_checker_config` & `social_checker_cache`)
- [ ] Validasi syntax dengan `py_compile` (0 error)
- [ ] Git commit dan push ke remote `abogoboga main`
