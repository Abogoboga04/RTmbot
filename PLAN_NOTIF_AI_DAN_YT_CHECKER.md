# DOKUMEN MASTER PLAN: RESTRUKTURISASI COPYWRITING AI & PENGEMBANGAN FITUR NATIVE YOUTUBE CHECKER (REVISI V2)

> **Status Dokumen:** Rencana Final (Revisi Berdasarkan Masukan Pengguna)  
> **Target Repositori:** `rtmbot` (`cogs/notif.py` & `cogs/yt_checker_test.py`)  
> **Prinsip Utama:** Sederhana diatur, ringkas digunakan, fleksibel tanpa batasan kaku, dan terisolasi aman untuk pengujian mandiri.

---

## DAFTAR ISI
1. [Rangkuman Revisi Masukan Pengguna](#1-rangkuman-revisi-masukan-pengguna)
2. [Analisis Lengkap Fitur & Alur `cogs/notif.py` Saat Ini](#2-analisis-lengkap-fitur--alur-cogsnotifpy-saat-ini)
3. [Diagnosa Copywriting AI & Solusi Alami (Tanpa Batasan Kaku)](#3-diagnosa-copywriting-ai--solusi-alami-tanpa-batasan-kaku)
4. [Rencana Arsitektur Standalone YouTube Native Checker (`cogs/yt_checker_test.py`)](#4-rencana-arsitektur-standalone-youtube-native-checker-cogsyt_checker_testpy)
5. [Mekanisme Deteksi Mandiri: YouTube RSS Atom Engine (Zero Quota)](#5-mekanisme-deteksi-mandiri-youtube-rss-atom-engine-zero-quota)
6. [Klasifikasi Tiga Jenis Konten: Upload vs Live vs Premiere](#6-klasifikasi-tiga-jenis-konten-upload-vs-live-vs-premiere)
7. [Skema Data Bersih & Fleksibel (Tanpa Hardcoded Channel)](#7-skema-data-bersih--fleksibel-tanpa-hardcoded-channel)
8. [Command Pengujian Simpel & Praktis (Sesuai Karakter Bot RTM)](#8-command-pengujian-simpel--praktis-sesuai-karakter-bot-rtm)
9. [Matriks Perbandingan Sistem](#9-matriks-perbandingan-sistem)
10. [Roadmap Eksekusi Bertahap & Validasi](#10-roadmap-eksekusi-bertahap--validasi)

---

## 1. RANGKUMAN REVISI MASUKAN PENGGUNA

Berdasarkan tinjauan dan arahan pengguna pada draf sebelumnya, telah dilakukan 3 penyesuaian fundamental:

| Poin Masukan Pengguna | Penyesuaian pada Rencana Ini |
|---|---|
| **1. Batasan Kata Kaku Ditiadakan:** *"jangan ada batasan karena bisa mengganggu fungsi yang sudah ada"* | Menghapus seluruh daftar larangan kata (*negative constraints*). Fokus utama adalah **mengoper judul & topik video** ke AI agar gaya bahasanya mengalir bebas, luwes, dan nyambung secara alami dengan isi video tanpa mengekang kreativitas AI. |
| **2. Channel Pengujian Mandiri:** *"jangan langsung set channel yang ada karena mau test sendiri di channel sendiri, bukan nunggu orang live"* | Konfigurasi awal dimulai **bersih (kosong)** tanpa memuat channel produksi orang lain. Pengguna bisa langsung memasukkan channel YouTube sendiri atau link video/live apa saja untuk diuji coba langsung di channel Discord pribadi. |
| **3. Command Simpel & Tidak Berbelit-belit:** *"command nya panjang banget, gak simple, gak sesuai tema bot yang simple mudah diatur dan kompleks"* | Seluruh command disederhanakan total menjadi command pendek nan elegan (gaya bawaan RTM): `!yttest <url>`, `!ytadd <url>`, `!ytcheck`, `!ytlist`, `!ytdel`, dan `!ytclear`. Cukup 1 baris tanpa perlu ribet mengetik ID channel Discord manual. |

---

## 2. ANALISIS LENGKAP FITUR & ALUR `cogs/notif.py` SAAT INI

Sebelum membuat modul baru, berikut adalah pemetaan lengkap mengenai apa saja yang bisa dan biasa dilakukan oleh [cogs/notif.py](file:///c:/Users/Administrator/Downloads/rtmbot/cogs/notif.py):

```
[Sumber Luar: Bot Lain / Webhook] 
               │
               ▼ (Kirim link ke #channel-sumber)
┌────────────────────────────────────────────────────────────────────────┐
│                        COGS/NOTIF.PY (ContentRadar)                    │
│                                                                        │
│ 1. Listener on_message: Memantau pesan masuk di channel sumber terdaftar│
│ 2. Deteksi URL Multi-Platform via Regex:                               │
│    - YouTube: Video (/watch, /shorts, youtu.be), Live (/live), Premiere│
│    - TikTok: Video (@user/video), Live (@user/live, vt.tiktok)         │
│    - Instagram: Post/Reels (/p/, /reel/), Live (/live)                 │
│ 3. Deduplikasi Cache: Mencegah spam kirim ulang (max 1.000 ID video)   │
│ 4. Ekstraksi Metadata:                                                 │
│    - pytubefix (Client WEB)                                            │
│    - yt_dlp fallback                                                   │
│    - YouTube oEmbed API & Scraper HTML Description                     │
│ 5. Hype Generator: Memanggil Gemini API (_generate_jarkasih_hype)      │
│ 6. Render UI:                                                          │
│    - Discord V2 Card resmi dengan thumbnail HD & action button         │
│    - Fallback ke Embed interaktif dengan warna kustom                  │
│ 7. Menu Pengaturan Interaktif (!config, !addpath, !removepath)         │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
                   [Target Channel: #pengumuman]
```

### Kapabilitas Utama yang Dimiliki `cogs/notif.py`:
- **Penerusan Otomatis (Relay):** Mengambil pesan link dari channel A dan mempublikasikan versi cantiknya di channel B.
- **Dukungan 7 Format Konten:** YouTube Upload, YouTube Live, YouTube Premiere, TikTok Video, TikTok Live, Instagram Post, Instagram Live.
- **Kustomisasi Lewat UI Discord:** Admin server dapat mengatur template pesan (`{judul}`, `{channel}`, `{url}`, `{ai_hype}`), warna embed hex, warna tombol, dan toggle thumbnail melalui menu dropdown `!config`.
- **Hybrid Storage:** Tersimpan di file lokal `data/notif.json` dan otomatis sinkron ke koleksi database MongoDB `reSwan.notif_config`.

---

## 3. DIAGNOSA COPYWRITING AI & SOLUSI ALAMI (TANPA BATASAN KAKU)

### Akar Masalah yang Terjadi
Pada kode [cogs/notif.py:1032-1034](file:///c:/Users/Administrator/Downloads/rtmbot/cogs/notif.py#L1032-L1034):
```python
# Judul video BERHASIL diambil:
youtube_title, youtube_description, youtube_thumbnail, video_url, youtube_channel = await asyncio.to_thread(_extract_youtube_info, link_for_send)

# Tapi fungsi hype dipanggil TANPA mengirim judul dan deskripsinya:
ai_hype_text = await self._generate_jarkasih_hype(link_type, channel_name=youtube_channel)
```
1. **AI Buta Judul Video:** Gemini tidak tahu apakah videonya tentang jalan-jalan pagi santai, komedi mabar, tutorial, atau siaran berita.
2. **Persona yang Terlalu Memaksa:** Prompt lama mewajibkan AI menyisipkan slang Barat/Jaksel (*dope, guarantee, relate*), yang membuatnya terdengar kaku dan tidak cocok dengan video yang bernuansa santai atau keluarga.

### Solusi Pembenahan (Bebas Mengalir & Alami)
1. **Kirim Data Lengkap:** Kirimkan `video_title` dan intisari `video_desc` ke fungsi `_generate_jarkasih_hype()`.
2. **Hilangkan Batasan Kata yang Kaku:** Tidak perlu ada daftar larangan kata yang ribet. Cukup beri instruksi konteks yang jelas:
   - *"Tugas lu: bikin kalimat pengumuman/sapaan yang santai, asik, dan nyambung dengan judul video '{video_title}' dari channel '{channel_name}'."*
   - *"Sesuaikan gayanya dengan isi kontennya: kalau santai ya santai, kalau seru ya seru, kalau lagi live ajak warga server buat nonton bareng."*
   - Biarkan AI menyusun kalimatnya dengan luwes tanpa dibatasi aturan negatif yang bisa mengganggu fungsi teks.

---

## 4. RENCANA ARSITEKTUR STANDALONE YOUTUBE NATIVE CHECKER (`cogs/yt_checker_test.py`)

Modul ini dibuat sebagai **file cog terpisah yang 100% mandiri**, tidak bergantung pada bot luar apa pun, dan siap diuji coba langsung di server pengguna.

```
┌────────────────────────────────────────────────────────────────────────┐
│             cogs/yt_checker_test.py (YouTubeNativeCheckerTest)         │
│                                                                        │
│  [Loop Otomatis atau Trigger Manual via !ytcheck / !yttest]            │
│        │                                                               │
│        ▼                                                               │
│  1. Baca data/yt_test_config.json (Daftar channel yang dipantau)       │
│        │                                                               │
│        ▼                                                               │
│  2. Fetch Atom RSS Feed YouTube langsung (Zero Quota):                 │
│     https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}   │
│        │                                                               │
│        ▼                                                               │
│  3. Parse XML & Ambil video_id terbaru                                 │
│        │                                                               │
│        ▼                                                               │
│  4. Cek Memori Cache: data/yt_test_cache.json                          │
│     - Jika sudah pernah dipost -> Lewati.                              │
│     - Jika baru -> Lanjutkan ke klasifikasi status.                    │
│        │                                                               │
│        ▼                                                               │
│  5. Klasifikasi Cepat Status Siaran (Upload / Live / Premiere)         │
│        │                                                               │
│        ▼                                                               │
│  6. Generate AI Hype yang kontekstual dengan Judul & Tipe Siaran       │
│        │                                                               │
│        ▼                                                               │
│  7. Publikasikan pesan V2 Card / Embed ke channel Discord tujuan       │
│        │                                                               │
│        ▼                                                               │
│  8. Simpan video_id ke cache data/yt_test_cache.json                   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 5. MEKANISME DETEKSI MANDIRI: YOUTUBE RSS ATOM ENGINE (ZERO QUOTA)

Mengapa kita menggunakan Public Atom/RSS Feed YouTube?
1. **Bebas Kuota API (0 Unit):** Tidak memerlukan API Key Google Cloud Console, tidak ada batasan kuota harian (YouTube API resmi membatasi 10.000 unit per hari, yang mana 1x search memakan 100 unit dan cepat habis).
2. **Respon Cepat & Resmi:** Feed `https://www.youtube.com/feeds/videos.xml?channel_id={ID}` disediakan langsung oleh infrastruktur Google dan langsung terupdate saat ada video/live baru.
3. **Pustaka Bawaan Ringan:** Parsing XML cukup menggunakan modul Python standar `xml.etree.ElementTree` tanpa perlu menginstal dependensi berat.

---

## 6. KLASIFIKASI TIGA JENIS KONTEN: UPLOAD VS LIVE VS PREMIERE

Saat ada konten baru masuk di RSS Feed, bot memeriksa status penayangannya melalui request HTTP ringan via `aiohttp`:
- **LIVE STREAMING 🔴:**  
  Terdeteksi jika halaman video mengandung `"isLive": true` atau `"status": "LIVE_STREAMING"`.  
  $\rightarrow$ Bot mengirimkan pengumuman khusus siaran langsung dengan tombol *"Tonton Live Sekarang"*.
- **PREMIERE ⏳:**  
  Terdeteksi jika halaman video mengandung `"upcomingEvents"` atau `"scheduledStartTime"`.  
  $\rightarrow$ Bot mengirimkan pengumuman premiere dengan jadwal penayangan perdana.
- **VIDEO UPLOAD 🎬:**  
  Jika video berstatus reguler.  
  $\rightarrow$ Bot mengirimkan pengumuman video baru dengan thumbnail dan tombol *"Tonton Video"*.

---

## 7. SKEMA DATA BERSIH & FLEKSIBEL (TANPA HARDCODED CHANNEL)

Kedua file data pengujian akan disimpan di folder `data/` dengan kondisi awal bersih agar kamu bisa mengisinya dengan channel pilihanmu sendiri:

### `data/yt_test_config.json`
```json
{
  "check_interval_minutes": 2,
  "channels": []
}
```

### `data/yt_test_cache.json`
```json
{
  "posted_video_ids": []
}
```

> **Keuntungan:** Tidak ada channel default yang dipaksakan. Kamu bisa langsung menambahkan channel YouTube sendiri atau channel favoritmu untuk diuji kapan saja.

---

## 8. COMMAND PENGUJIAN SIMPEL & PRAKTIS (SESUAI KARAKTER BOT RTM)

Untuk menyesuaikan dengan filosofi bot RTM yang ringkas, mudah diatur, namun kaya fitur di baliknya, perintah dibuat sangat pendek dan praktis:

### A. Uji Coba Instan (Tanpa Perlu Nunggu Ada yang Live)
- **`!yttest <url_video_atau_live>`**  
  **Fungsi:** Kamu bisa langsung memasukkan URL YouTube apa saja (mau video biasa, rekaman live, atau link premiere yang ada di YouTube).  
  Bot akan langsung:
  1. Mendeteksi apakah itu video upload, live, atau premiere.
  2. Mengambil judul, channel, dan thumbnail-nya.
  3. Meminta Gemini membuat copywriting yang sesuai dengan judul tersebut.
  4. Menampilkan hasil kartu notifikasi di channel Discord tempat kamu mengetikkan perintah ini!  
  *(Sangat cocok untuk melihat tampilan dan gaya bahasa secara instan).*

### B. Manajemen Pemantauan Channel
- **`!ytadd <link_channel_atau_id>`**  
  **Fungsi:** Mendaftarkan channel YouTube ke pemantauan otomatis bot.  
  *Kelebihan Praktis:* Kamu cukup jalankan perintah ini di channel Discord yang kamu inginkan, bot otomatis menetapkan channel Discord tersebut sebagai target notifikasi (tidak perlu repot menyalin Channel ID Discord manual!).
- **`!ytdel <channel_id_atau_nomor>`**  
  **Fungsi:** Menghapus channel dari daftar pemantauan.
- **`!ytlist`**  
  **Fungsi:** Menampilkan daftar channel YouTube yang sedang dipantau, channel Discord tujuannya, serta status interval pengecekan.
- **`!ytcheck`**  
  **Fungsi:** Memaksa bot mengecek RSS feed detik itu juga tanpa perlu menunggu timer 2 menit.
- **`!ytclear`**  
  **Fungsi:** Mengosongkan cache video test agar kamu bisa mencoba mengirimkan video yang sama berulang kali.

*(Catatan: Semua perintah di atas juga bisa diakses melalui format grup `!yt test`, `!yt add`, `!yt list`, `!yt check`, `!yt clear`).*

---

## 9. MATRIKS PERBANDINGAN SISTEM

| Fitur | `cogs/notif.py` (Produksi Saat Ini) | `cogs/yt_checker_test.py` (Test Mandiri) |
|---|---|---|
| **Cara Kerja** | Forwarder / Relayer (menunggu bot lain posting link duluan di Discord) | Pengecek Mandiri Langsung ke YouTube via RSS |
| **Ketergantungan Bot Luar** | Ya (harus ada bot lain pengirim link sumber) | **Nol (Tidak perlu bot luar sama sekali)** |
| **Pengecekan Live / Premiere** | Berdasarkan teks yang dikirim bot luar | Dideteksi langsung oleh bot RTM sendiri |
| **Perintah Pengujian** | `!config`, `!addpath`, `!resetcache` | `!yttest`, `!ytadd`, `!ytcheck`, `!ytlist`, `!ytclear` |
| **Copywriting AI** | Menggunakan template Jarkasih (akan diperbaiki agar membaca judul) | Didesain membaca judul, deskripsi, dan status siaran secara alami |
| **Dampak Risiko** | Berjalan di server produksi | Terisolasi penuh (tidak mengganggu fitur notif lama) |

---

## 10. ROADMAP EKSEKUSI BERTAHAP & VALIDASI

1. **Tahap 1: Pembenahan Copywriting AI pada `cogs/notif.py`**
   - Perbarui baris 1034 agar `clean_title` dan `youtube_description` dikirim ke `_generate_jarkasih_hype()`.
   - Perbarui prompt AI agar berfokus menghubungkan sapaan dengan isi/topik judul video secara natural dan fleksibel (tanpa batasan kata yang kaku).
2. **Tahap 2: Pembuatan Modul `cogs/yt_checker_test.py` & Inisialisasi Data**
   - Buat file baru [cogs/yt_checker_test.py](file:///c:/Users/Administrator/Downloads/rtmbot/cogs/yt_checker_test.py).
   - Inisialisasi `data/yt_test_config.json` dan `data/yt_test_cache.json` dengan struktur bersih/kosong.
   - Daftarkan cog ke [main.py](file:///c:/Users/Administrator/Downloads/rtmbot/main.py) agar siap di-load.
3. **Tahap 3: Implementasi Mesin RSS, Classifier, dan Generator Pesan**
   - Buat fungsi pengambil RSS feed dan resolver URL channel menjadi Channel ID.
   - Buat sub-rutin klasifikasi status (`upload`, `live`, `premier`).
   - Buat builder tampilan kartu notifikasi dan generator copywriting AI.
4. **Tahap 4: Implementasi Rangkaian Command Pendek (`!yttest`, `!ytadd`, dll.)**
   - Pasang command `!yttest` untuk uji instan link apa saja.
   - Pasang command `!ytadd`, `!ytdel`, `!ytlist`, `!ytcheck`, dan `!ytclear`.
5. **Tahap 5: Validasi Kompilasi & Dokumentasi**
   - Jalankan kompilasi: `.\.venv\Scripts\python.exe -m py_compile cogs/notif.py cogs/yt_checker_test.py`.
   - Commit & push ke repositori `rtmbot` pada branch `abogoboga main`.
