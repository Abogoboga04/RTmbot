# RTmbot

RTmbot adalah bot Discord multipurpos modular yang dibangun menggunakan Python dan discord.py versi 2.x. Bot ini mengintegrasikan kecerdasan buatan Google Gemini, automasi moderasi dengan verifikasi perceptual hash, sistem ekonomi virtual, pelacakan level aktivitas teks dan suara, serta kanal suara dinamis.

Proyek ini dirancang dengan arsitektur Cog modular yang memisahkan tanggung jawab fungsional ke dalam modul terpisah, didukung penyimpanan MongoDB dengan fallback ke berkas JSON lokal.

---

## Daftar Isi

- [Arsitektur dan Modul](#arsitektur-dan-modul)
- [Fitur Utama](#fitur-utama)
  - [Integrasi Google Gemini](#integrasi-google-gemini)
  - [Keamanan dan Moderasi Server](#keamanan-dan-moderasi-server)
  - [Ekonomi dan Keuangan Virtual](#ekonomi-dan-keuangan-virtual)
  - [Leveling dan Pelacakan Voice](#leveling-dan-pelacakan-voice)
  - [Pengumuman dan Webhook](#pengumuman-dan-webhook)
  - [Mini-Games dan Interaksi Komunitas](#mini-games-dan-interaksi-komunitas)
  - [Temporary Voice Channels](#temporary-voice-channels)
  - [Web Command Queue (IPC)](#web-command-queue-ipc)
- [Struktur Direktori](#struktur-direktori)
- [Persyaratan Sistem](#persyaratan-sistem)
- [Panduan Instalasi](#panduan-instalasi)
- [Konfigurasi Lingkungan (.env)](#konfigurasi-lingkungan-env)
- [Cara Menjalankan Bot](#cara-menjalankan-bot)
- [Referensi Perintah Populer](#referensi-perintah-populer)
- [Sistem Logging dan Penanganan Error](#sistem-logging-dan-penanganan-error)

---

## Arsitektur dan Modul

RTmbot dibangun di atas pustaka discord.py dengan pola ekstensi Cog:

- **Asynchronous Execution**: Seluruh event I/O, koneksi database, dan request API diproses secara non-blocking via asyncio dan aiohttp.
- **Dual Data Layer**: Mendukung koneksi MongoDB via driver PyMongo untuk sinkronisasi cloud, dengan sistem fallback otomatis ke file JSON lokal di direktori `data/` saat MongoDB tidak diaktifkan.
- **Hybrid Commands**: Sebagian besar modul mendukung eksekusi via Prefix teks konvensional (`!` atau `?`) maupun Discord Slash Commands modern (`/`).
- **Web Console IPC**: Background loop task yang memantau dokumen perintah pending pada koleksi `rtmbot.bot_commands` untuk memungkinkan panel web eksternal mengeksekusi instruksi bot ke channel server Discord.

---

## Fitur Utama

### Integrasi Google Gemini
Modul `cogs/gemini.py` mengintegrasikan Google GenAI SDK:
- **Analisis Multi-Modal**: Mampu menerima dan menganalisis lampiran gambar langsung dari chat pengguna untuk mendeskripsikan konten, membaca teks, atau menjawab pertanyaan visual.
- **Percakapan Kontekstual**: Memproses interaksi obrolan berbasis konteks di channel yang diizinkan.
- **Target Channel Routing**: Bot dapat diarahkan untuk merespons atau mengirim hasil generasi teks ke channel tujuan tertentu.
- **Whitelist Sistem**: Menyediakan mekanisme whitelist kata dan administrasi otorisasi modul.

### Keamanan dan Moderasi Server
Modul `cogs/moderation.py` menyediakan utilitas pengelolaan komunitas:
- **Filter Spam Media via Perceptual Hash (pHash)**: Memeriksa kemiripan gambar spam menggunakan perbandingan hash visual (ImageHash), bukan hanya pencocokan URL atau nama file. Gambar target spam dapat dipelajari dari channel referensi khusus.
- **Bukti Pelanggaran Lengkap**: Ketika bot mendeteksi pelanggaran teks atau media, laporan yang dikirimkan ke webhook staf mencantumkan kutipan isi pesan pelanggar beserta file media asli yang dilampirkan.
- **Honeypot & Trap Channel**: Mendukung konfigurasi channel jebakan untuk menjaring akun bot spam secara otomatis.
- **Aksi Moderasi Lengkap**: Mendukung `warn`, `unwarn`, `timeout` (mute), `removetimeout`, `kick`, `ban`, `softban` (ban dan langsung unban untuk menghapus riwayat pesan), `clear` (purge), serta `lock`/`unlock` channel.
- **Komponen Interaktif**: Setup panel verifikasi tombol dan panel pemilihan role berbasis dropdown UI Discord.

### Ekonomi dan Keuangan Virtual
Modul `cogs/finance.py` mengelola ekosistem saldo server:
- **Sistem Rekening Ganda**: Saldo dompet (wallet) dan saldo tabungan bank.
- **Aktivitas Finansial**: Klaim bonus harian, transfer saldo antar-anggota, transaksi deposit/withdraw, dan mini-games taruhan koin.
- **Penyimpanan Terstruktur**: Data keuangan tersimpan rapi dengan validasi saldo sebelum setiap mutasi.

### Leveling dan Pelacakan Voice
Modul `cogs/leveling.py` mengukur keterlibatan anggota komunitas:
- **EXP Chat & Voice**: Perhitungan poin pengalaman dari keaktifan obrolan teks serta durasi berbicara di voice channel.
- **Kartu Rank Visual**: Pembuatan kartu profil dinamis yang menampilkan progres level, avatar pengguna, dan statistik poin.
- **Leaderboard Global & Mingguan**: Menampilkan sepuluh anggota teratas dalam server berdasarkan total perolehan EXP.
- **Panel Aktivitas Voice**: Panel embed otomatis yang menampilkan statistik durasi sesi voice channel secara berkala.
- **Quest & Giveaway**: Sistem misi harian terstruktur dan modul undian giveaway dengan mekanisme reroll otomatis.

### Pengumuman dan Webhook
Modul `cogs/webhook.py` dan perintah `/announce`:
- **Siaran Embed Interaktif**: Pembuatan pengumuman terformat dengan opsi judul, deskripsi, warna, dan lampiran URL gambar.
- **Dukungan Polling**: Menyertakan jajak pendapat interaktif langsung pada pesan pengumuman.
- **Kanal Suara Teks**: Pengiriman pengumuman dapat ditargetkan ke text-chat di dalam voice channel secara langsung.
- **Pengiriman Webhook Kustom**: Dukungan pengiriman pesan memakai avatar dan nama bot yang dikustomisasi per pengumuman.

### Mini-Games dan Interaksi Komunitas
Modul `cogs/minigames.py`, `cogs/party_games.py`, `cogs/fun.py`, dan `cogs/quotes.py`:
- **Kuis & Tebakan**: Tebak gambar, tebak kata acak, tebak istilah IPA, kuis trivia pengetahuan umum, dan sambung kata.
- **Permainan Grup**: Balapan kuda interaktif dengan sistem taruhan koin RSWN virtual.
- **Curhat Anonim (`/confess`)**: Modal Discord untuk anggota mengirimkan pesan anonim ke channel curhat yang telah ditentukan tanpa membocorkan identitas pengirim.
- **Koleksi Kutipan**: Pengelolaan dan pengiriman kutipan inspiratif terkurasi ke channel khusus.

### Temporary Voice Channels
Modul `cogs/temp_voice.py`:
- Membuat ruang obrolan suara pribadi secara otomatis ketika pengguna bergabung ke channel pemicu (trigger channel).
- Mengatur izin akses kanal suara sesuai pemilik sesi.
- Menghapus kanal suara secara otomatis saat seluruh anggota telah keluar untuk menjaga daftar channel server tetap rapi.

### Web Command Queue (IPC)
Fitur background task di `main.py`:
- Melakukan polling berkala pada koleksi database `rtmbot.bot_commands`.
- Mengeksekusi instruksi yang dikirimkan oleh kontrol panel dashboard eksternal.
- Mengirimkan output eksekusi atau pesan teks ke guild dan channel tujuan Discord secara langsung.

---

## Struktur Direktori

```
rtmbot/
├── cogs/
│   ├── activity.py          # Pelacakan status dan keaktifan member
│   ├── finance.py           # Sistem keuangan virtual dan perbankan
│   ├── fun.py               # Perintah hiburan, interaksi, dan sistem confess
│   ├── gemini.py            # Integrasi kecerdasan buatan Google Gemini
│   ├── info.py              # Informasi bot, profil pengguna, dan pusat bantuan
│   ├── leveling.py          # Sistem EXP, rank card, quest, dan voice tracker
│   ├── minigames.py         # Kuis interaktif dan tebak-tebakan teks
│   ├── moderation.py        # Moderasi, anti-spam pHash, log insiden, dan broadcast
│   ├── notif.py             # Sistem notifikasi dan pengingat server
│   ├── party_games.py       # Game grup, taruhan balapan kuda, dan permainan sosial
│   ├── quotes.py            # Sistem manajemen kutipan harian
│   ├── temp_voice.py        # Pengelolaan temporary voice channel otomatis
│   ├── v2_layout.py         # Skema tampilan antarmuka pelengkap
│   ├── webhook.py           # Utilitas broadcast webhook dan embed generator
│   └── archive/             # Arsip modul pendukung terdahulu
├── config/                  # Berkas konfigurasi tambahan
├── data/                    # Penyimpanan data runtime lokal (JSON)
├── main.py                  # Entrypoint utama bot, konfigurasi event, dan IPC queue
├── run.bat                  # Skrip starter otomatis untuk Windows
├── requirements.txt         # Daftar dependensi Python
├── .env.example             # Contoh format konfigurasi variabel lingkungan
└── README.md                # Dokumentasi teknis proyek
```

---

## Persyaratan Sistem

- **Sistem Operasi**: Windows 10/11, Linux (Ubuntu 20.04+ direkomendasikan), atau macOS.
- **Python**: Versi 3.10 atau versi 3.11.
- **Discord Bot Token**: Akun bot dari Discord Developer Portal dengan hak akses Privileged Gateway Intents aktif:
  - Presence Intent
  - Server Members Intent
  - Message Content Intent
- **Google AI Studio API Key**: Kunci API Google Gemini untuk fitur AI dan pemrosesan visual.
- **MongoDB** (Opsional): MongoDB Atlas atau instance MongoDB lokal. Jika tidak diisi, bot tetap dapat beroperasi dengan penyimpanan JSON lokal.

---

## Panduan Instalasi

### 1. Kloning Repositori
```bash
git clone https://github.com/Abogoboga04/RTmbot.git
cd RTmbot
```

### 2. Siapkan Virtual Environment
Membuat virtual environment disarankan untuk menjaga dependensi tetap terisolasi:

**Windows (PowerShell/CMD):**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Pasang Dependensi
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Konfigurasi Lingkungan (.env)

Salin berkas template `.env.example` menjadi `.env`:

```bash
cp .env.example .env
```

Buka berkas `.env` dan lengkapi nilai variabel berikut:

```ini
# Token Bot Discord (Wajib)
DISCORD_TOKEN=your_discord_bot_token_here
BOT_TOKEN=your_discord_bot_token_here

# API Key Google Gemini (Wajib untuk cogs/gemini.py)
GOOGLE_API_KEY=your_google_gemini_api_key_here

# URI MongoDB (Opsional, gunakan format mongodb+srv://)
MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net/?retryWrites=true&w=majority

# Webhook URL untuk Logging Error Kritikal (Opsional)
LOG_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Webhook URL untuk Log Notifikasi Saat Bot Masuk Server Baru (Opsional)
JOIN_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Webhook URL untuk Rekap Action Global (Opsional)
ACTION_LOG_WEBHOOK_URL=https://discord.com/api/webhooks/...

# ID Pemilik Bot (ID Pengguna Discord)
BOT_OWNER_ID=1000737066822410311
```

Catatan: Pastikan file `.env` tidak pernah dikomit ke repositori publik untuk menjaga kerahasiaan token dan kredensial bot Anda.

---

## Cara Menjalankan Bot

### Melalui Skrip Batch (Windows)
Cukup klik ganda pada file `run.bat` atau jalankan lewat terminal:
```cmd
run.bat
```
Skrip akan secara otomatis memeriksa ketersediaan `.venv`, memvalidasi keberadaan `.env`, dan mengeksekusi `main.py` dalam mode UTF-8.

### Melalui Terminal / CLI
Pastikan virtual environment telah aktif, lalu jalankan:
```bash
python main.py
```

Setelah bot siap, pesan status akan muncul di konsol dan slash command akan disinkronkan secara otomatis ke Discord API.

---

## Referensi Perintah Populer

Berikut adalah ringkasan beberapa perintah utama yang tersedia. Perintah dapat dipanggil menggunakan prefix `!` atau via Slash Command `/`:

| Perintah | Kategori | Keterangan |
|---|---|---|
| `/help` | Info | Membuka katalog bantuan interaktif dan daftar perintah per modul |
| `/announce` | Moderasi | Mengirim pengumuman via modal (mendukung webhook, polling, dan voice chat) |
| `/trap` | Moderasi | Mengatur atau mencabut status channel sebagai jebakan anti-spam |
| `/warn` | Moderasi | Memberikan peringatan resmi kepada anggota yang melanggar aturan |
| `/timeout` | Moderasi | Membungkam anggota sementara waktu dengan batas durasi tertentu |
| `/clear` | Moderasi | Menghapus sejumlah pesan dalam satu channel secara massal |
| `/rank` | Leveling | Menampilkan kartu profil level, EXP terkini, dan saldo virtual |
| `/leaderboard` | Leveling | Melihat daftar sepuluh anggota dengan EXP tertinggi di server |
| `/voicetime` | Leveling | Memeriksa akumulasi durasi aktif pengguna di voice channel |
| `/confess` | Komunitas | Mengirim pesan curhatan anonim melalui modal Discord |
| `/balapan` | Hiburan | Memulai arena taruhan balapan kuda bersama anggota server |
| `!resq` | Kutipan | Mengirimkan kutipan inspiratif acak ke channel teks |

---

## Sistem Logging dan Penanganan Error

RTmbot dilengkapi arsitektur logging bertingkat:

1. **Konsol Standar**: Menggunakan pustaka standar Python `logging` dengan format timestamp presisi untuk memantau status operasional bot.
2. **Global Discord Webhook Logger**: Setiap exception berlevel `CRITICAL` atau `ERROR` yang terjadi pada runtime akan dikirimkan langsung ke channel khusus pengembang melalui `LOG_WEBHOOK_URL`.
3. **Audit Log Insiden**: Pelanggaran aturan yang terdeteksi oleh modul moderasi dicatat lengkap dengan data pelaku, isi teks pesan asli, tautan invite server, dan lampiran file media terkait.
4. **Action Tracker**: Rekap perintah dan aktivitas bot di berbagai server dapat dipantau terpusat untuk mendeteksi anomali penggunaan secara real-time.

---

## Lisensi dan Kontribusi

Repositori ini dikelola untuk kebutuhan pengembangan komunitas. Apabila Anda ingin berkontribusi, silakan buat branch baru dan ajukan Pull Request dengan penjelasan perubahan yang jelas dan teruji.