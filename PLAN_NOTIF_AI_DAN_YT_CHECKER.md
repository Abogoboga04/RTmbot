# MASTER PLAN: UNIFIED SOCIAL MEDIA CHECKER (YOUTUBE & TIKTOK) & BUGFIX BALAPAN

## 1. Ringkasan & Tujuan Arsitektur

Dokumen ini merupakan satu-satunya master plan resmi yang menyatukan seluruh sistem pemantauan media sosial otomatis ke dalam satu arsitektur terpadu (**YouTube & TikTok**), menyelaraskan fleksibilitas konfigurasi setara dengan `cogs/notif.py`, serta memperbaiki bug command `!balapan` pada `cogs/party_games.py`.

### Prinsip Utama Desain:
1. **Satu Cog Terpadu & Profesional:** Penyatuan engine YouTube dan TikTok ke dalam `cogs/social_checker.py` dengan kelas `SocialChecker(commands.Cog)`.
2. **Hybrid Commands (Slash & Prefix):** Seluruh perintah dapat diakses menggunakan prefix (`!yt`, `!tt`, `!checker`) maupun Slash Command (`/yt`, `/tt`, `/checker`).
3. **Owner-Only Test Guard:** Seluruh perintah diproteksi dengan `@commands.is_owner()` selama masa pengujian.
4. **Konfigurasi Penuh (Setara `cogs/notif.py`):**
   - Fleksibilitas target channel: Bisa mengatur target ke `#channel` mana saja atau server mana saja dari mana pun perintah dijalankan.
   - 3 Mode Pesan: Bawaan (Default), Pesan Kustom (Custom Template), atau Serahkan ke AI (Full AI Copywriting).
   - Kustomisasi mention: `@everyone`, role tertentu, atau tanpa mention (`none`).
   - Toggle aktif/nonaktif per akun tanpa menghapus data.
5. **Penyimpanan Permanen di MongoDB:** Menggunakan koleksi `social_checker_config` dan `social_checker_cache` pada database `reSwan`.
6. **Zero Slop / Clean Code:** Kode murni, ringkas, profesional, dan bebas dari komentar hardcode atau banner hiasan bertele-tele.

---

## 2. Perbaikan Bug `!balapan` (`TavernPartyGames`)

### Akar Masalah
Pada `cogs/party_games.py` baris 2146 dan 2407, perintah `!balapan` memanggil `self._get_current_bets_text(race_state['bets'], race_state['horses'])` yang belum didefinisikan di dalam kelas `TavernPartyGames`, memicu `AttributeError`.

### Rencana Solusi
Menambahkan method helper `_get_current_bets_text` pada kelas `TavernPartyGames`:
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

## 3. Skema Database MongoDB Terpusat (`reSwan`)

### Koleksi: `social_checker_config`
```json
{
  "_id": "social_checker_config",
  "data": {
    "check_interval_seconds": 30,
    "targets": [
      {
        "id": "target_uuid_atau_channel_id",
        "platform": "youtube", // "youtube" | "tiktok"
        "identifier": "UCrEj4d2ynysNsYttTYROXEg", // Channel ID / TikTok Username
        "display_name": "Luthfi Halimawan",
        "target_guild_id": 1234567890,
        "target_channel_id": 1417636236356485141,
        "mention_role": "@everyone",
        "message_mode": "ai", // "default" | "custom" | "ai"
        "custom_template": "{mention} Ada video baru dari {creator}!\n{judul}\n{url}",
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

## 4. Mesin Deteksi Konten & Format Notifikasi V2

### A. YouTube Native Engine
- **Triple-Layer Content Detection:**
  1. Universal User Uploads Playlist (`UU...`)
  2. Direct Canonical Live Detection (`/channel/{id}/live`) dengan pembacaan tag `<link rel="canonical">` (kebal 100% dari rekomendasi sidebar)
  3. Atom RSS Feed
- **Strict Channel Ownership Guard:** Memverifikasi `channelId` dari halaman watch agar video rekomendasi dari channel lain langsung ditolak.

### B. TikTok Native Engine
- **`yt_dlp` Asynchronous Engine:**
  - Menjalankan pemindaian profil target (`https://www.tiktok.com/@{username}`) via `asyncio.to_thread`.
  - 100% kebal Slardar WAF TikTok, kecepatan tinggi (~3 detik), menghasilkan Video ID, Caption, Uploader Name, Thumbnail Cover, dan Upload Timestamp.
- **Timestamp Freshness Guard:** Memverifikasi timestamp unggahan (< 6 jam) agar arsip lama tidak dispam saat akun pertama kali ditambahkan.

### C. Sistem Format Pesan (3 Mode Fleksibel)
1. **Mode AI (Default Rekomendasi):** Gemini AI menyusun copywriting santai dan kontekstual sesuai judul video atau caption TikTok.
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

## 5. Kumpulan Perintah Hybrid Lengkap (Prefix & Slash - Owner Only)

Semua perintah diproteksi dengan `@commands.is_owner()`.

### A. Perintah YouTube (`!yt` atau `/yt`)
- `add <identifier> [target_channel]`: Daftarkan channel YouTube (bisa link, handle `@username`, atau UC ID). Target channel opsional (default ke channel saat ini).
- `remove <identifier>`: Hapus channel YouTube dari pemantauan.
- `setchannel <identifier> <target_channel>`: Ubah target channel pengiriman.
- `setmention <identifier> <role>`: Ubah sebutan (@everyone, @role, atau none).
- `setmode <identifier> <mode> [custom_text]`: Atur mode pesan (`ai`, `default`, atau `custom`).
- `toggle <identifier>`: Aktifkan/nonaktifkan pemantauan channel.
- `list`: Tampilkan daftar seluruh channel YouTube yang dipantau beserta konfigurasinya.
- `test <url>`: Uji coba langsung pengiriman kartu V2 untuk link YouTube tertentu.
- `check`: Paksa pengecekan pembaruan YouTube seketika.

### B. Perintah TikTok (`!tt` atau `/tt`)
- `add <username> [target_channel]`: Daftarkan akun TikTok. Target channel opsional (default ke channel saat ini).
- `remove <username>`: Hapus akun TikTok dari pemantauan.
- `setchannel <username> <target_channel>`: Ubah target channel pengiriman.
- `setmention <username> <role>`: Ubah sebutan (@everyone, @role, atau none).
- `setmode <username> <mode> [custom_text]`: Atur mode pesan (`ai`, `default`, atau `custom`).
- `toggle <username>`: Aktifkan/nonaktifkan pemantauan akun TikTok.
- `list`: Tampilkan daftar seluruh akun TikTok yang dipantau beserta konfigurasinya.
- `test <url>`: Uji coba langsung pengiriman kartu V2 untuk link video TikTok tertentu.
- `check`: Paksa pengecekan pembaruan TikTok seketika.

### C. Perintah Global Checker (`!checker` atau `/checker`)
- `list`: Ringkasan gabungan seluruh channel YouTube & TikTok yang aktif.
- `check`: Pengecekan manual serentak seluruh platform.
- `interval <detik>`: Ubah kecepatan background loop polling secara dinamis.
- `cache`: Periksa riwayat ID video yang tersimpan di cache.
- `resetcache`: Kosongkan cache untuk pengujian ulang.

---

## 6. Checklist Pelaksanaan

- [ ] Menunggu Masukan & Persetujuan Pengguna ("ACC") untuk Master Plan Baru
- [ ] Terapkan fungsi `_get_current_bets_text` di `cogs/party_games.py`
- [ ] Implementasikan `cogs/social_checker.py` (`SocialChecker`) menggantikan `cogs/yt_checker_test.py`
- [ ] Terapkan integrasi database MongoDB (`social_checker_config` & `social_checker_cache`)
- [ ] Validasi syntax dengan `py_compile` (0 error)
- [ ] Git commit dan push ke remote `abogoboga main`
