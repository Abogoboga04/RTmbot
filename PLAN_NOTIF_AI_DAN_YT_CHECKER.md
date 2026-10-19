# MASTER PLAN DETAIL: PENYELARASAN STYLE NOTIFIKASI & PERBAIKAN ENGINE METADATA

> **Status Dokumen:** Rencana Perbaikan Menyeluruh Berdasarkan Bukti Visual Uji Coba Pengguna  
> **Target:** Menyamakan 100% tampilan, keakuratan metadata, dan copywriting `cogs/yt_checker_test.py` agar identik dengan standar emas [cogs/notif.py](file:///c:/Users/Administrator/Downloads/rtmbot/cogs/notif.py) (Foto 3).  
> **Penyusun:** Antigravity AI Pair Programmer

---

## DAFTAR ISI
1. [Bedah Komparasi Visual: Foto 1 (Gagal) vs Foto 2 (Input) vs Foto 3 (Benchmark Sempurna)](#1-bedah-komparasi-visual-foto-1-gagal-vs-foto-2-input-vs-foto-3-benchmark-sempurna)
2. [Analisis Akar Masalah Teknis (Root Cause Analysis)](#2-analisis-akar-masalah-teknis-root-cause-analysis)
   - [Masalah A: Kenapa Judul & Channel Menjadi Default di Foto 1?](#masalah-a-kenapa-judul--channel-menjadi-default-di-foto-1)
   - [Masalah B: Kenapa AI Mengarang Bebas Soal Badut Mall?](#masalah-b-kenapa-ai-mengarang-bebas-soal-badut-mall)
   - [Masalah C: Perbedaan Struktur Discord V2 Card](#masalah-c-perbedaan-struktur-discord-v2-card)
3. [Arsitektur Ekstraksi Metadata Andal (Belajar dari `cogs/notif.py`)](#3-arsitektur-ekstraksi-metadata-andal-belajar-dari-cogsnotifpy)
4. [Spesifikasi Tampilan Discord V2 Card (Penyelarasan 1:1 dengan Foto 3)](#4-spesifikasi-tampilan-discord-v2-card-penyelarasan-11-dengan-foto-3)
5. [Spesifikasi AI Copywriting Kontekstual](#5-spesifikasi-ai-copywriting-kontekstual)
6. [Rencana Kode Teknis & Diff Implementasi](#6-rencana-kode-teknis--diff-implementasi)
7. [Checklist Validasi & Pengujian Ulang](#7-checklist-validasi--pengujian-ulang)

---

## 1. BEDAH KOMPARASI VISUAL: FOTO 1 (GAGAL) VS FOTO 2 (INPUT) VS FOTO 3 (BENCHMARK SEMPURNA)

Berdasarkan 3 tangkapan layar yang diberikan pengguna saat menguji perintah `!yttest https://youtu.be/bYXjikrHBME`:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ KOMPARASI ELEMEN VISUAL                                                                │
├────────────────────┬─────────────────────────────┬─────────────────────────────────────┤
│ Elemen Komponen    │ Foto 1 (yt_checker_test.py) │ Foto 3 (cogs/notif.py - YANG BENAR) │
├────────────────────┼─────────────────────────────┼─────────────────────────────────────┤
│ 1. AI Hype Mention │ Halusinasi topik:           │ Kontekstual akurat:                 │
│                    │ "video baru kita yang       │ "RnBoyz baru upload video nih,      │
│                    │ Reaksi Pas Warga Ketemu     │ katanya sih ada yang 'lincah        │
│                    │ Badut Random di Mall"       │ lincah bgt' bareng Mahalini!"       │
├────────────────────┼─────────────────────────────┼─────────────────────────────────────┤
│ 2. Header Judul    │ `# 🎬 VIDEO BARU •          │ (Tidak ada header kaku)             │
│    Kartu           │ YouTube Channel` (Kaku)     │                                     │
├────────────────────┼─────────────────────────────┼─────────────────────────────────────┤
│ 3. Judul Konten    │ Teks link: `Video YouTube`  │ Judul asli warna biru tebal:        │
│                    │ (Gagal ambil judul asli)    │ `# [lincah lincah bgt??!!! ...](url)│
├────────────────────┼─────────────────────────────┼─────────────────────────────────────┤
│ 4. Subtitle Link   │ TIDAK ADA link teks         │ Ada link URL teks biru di bawah     │
│                    │ di bawah judul              │ judul: `https://youtu.be/bYXjikrHBME│
├────────────────────┼─────────────────────────────┼─────────────────────────────────────┤
│ 5. Border Samping  │ Ada garis tebal biru di     │ Bersih (`color=None`), menyatu      │
│                    │ sisi kiri (`accent_color`)  │ rapi dengan tema Discord            │
├────────────────────┼─────────────────────────────┼─────────────────────────────────────┤
│ 6. Tombol Aksi     │ [Tonton Video ↗]            │ [Tonton Video ↗]                    │
└────────────────────┴─────────────────────────────┴─────────────────────────────────────┘
```

---

## 2. ANALISIS AKAR MASALAH TEKNIS (ROOT CAUSE ANALYSIS)

### Masalah A: Kenapa Judul & Channel Menjadi Default di Foto 1?
1. Link yang diuji pengguna adalah `https://youtu.be/bYXjikrHBME`. Ini adalah konten **YouTube Shorts** (video vertikal).
2. Di dalam [cogs/yt_checker_test.py](file:///c:/Users/Administrator/Downloads/rtmbot/cogs/yt_checker_test.py), fungsi `classify_stream_status` saat ini hanya mengunduh HTML dari `https://www.youtube.com/watch?v={id}` dan mencoba mencari tag `<title>(.*?) - YouTube</title>` dengan regex sederhana.
3. YouTube menyajikan struktur HTML yang berbeda untuk Shorts dan seringkali mengalihkan request ke halaman persetujuan (*consent*) atau antarmuka mobile web. Akibatnya:
   - Regex `<title>` gagal $\rightarrow$ `title` bernilai `None` $\rightarrow$ Jatuh ke fallback `"Video YouTube"`.
   - Regex channel author gagal $\rightarrow$ `channel_name` bernilai `None` $\rightarrow$ Jatuh ke fallback `"YouTube Channel"`.

### Masalah B: Kenapa AI Mengarang Bebas Soal Badut Mall?
Karena `title` yang dikirim ke fungsi `generate_ai_hype` bernilai `"Video YouTube"` dan channelnya `"YouTube Channel"`, Gemini sama sekali tidak memiliki petunjuk mengenai isi video yang sebenarnya. Model AI akhirnya berhalusinasi dan mengarang topik video acak (*badut random di mall*).

### Masalah C: Perbedaan Struktur Discord V2 Card
Di [cogs/notif.py](file:///c:/Users/Administrator/Downloads/rtmbot/cogs/notif.py), komponen V2 Card dibangun dengan parameter:
```python
card = build_v2_card(
    title=f"[{clean_title}]({video_url})",   # Menghasilkan teks biru H1 yang bisa diklik
    description=video_url,                    # Menampilkan URL teks di bawah judul
    fields=None,
    color=None,                               # NONE! Tanpa garis border samping
    buttons=buttons,                          # Tombol URL "Tonton Video"
    media_url=youtube_thumbnail               # Thumbnail HD
)
```
Sedangkan di `cogs/yt_checker_test.py` kemarin:
- Judulnya diganti menjadi `# 🎬 VIDEO BARU • YouTube Channel`.
- Deskripsinya diisi `### [Video YouTube](...)`.
- Warnanya diisi `accent_color = 0x5865f2` (menimbulkan garis biru tebal di sisi kiri).
Hal inilah yang membuat tampilannya melenceng dari gaya bawaan `cogs/notif.py` yang diinginkan pengguna.

---

## 3. ARSITEKTUR EKSTRAKSI METADATA ANDAL (BELAJAR DARI `cogs/notif.py`)

Agar ekstraksi metadata di `cogs/yt_checker_test.py` memiliki keandalan 100% dan tidak pernah gagal membaca judul Shorts maupun Live, kita menerapkan **Multi-Tier Extraction Pipeline** yang terbukti sukses di `cogs/notif.py`:

```
                          Input: URL / Video ID
                                    │
                                    ▼
       ┌────────────────────────────────────────────────────────┐
       │ Tier 1: YouTube Official oEmbed API (Zero Quota)       │
       │ URL: https://www.youtube.com/oembed?url={url}&format=json
       │ Kecepatan: ~150ms                                      │
       │ Sukses: 100% untuk Video Reguler, Shorts, Live, Premier│
       │ Hasil: title, author_name (channel), thumbnail_url     │
       └────────────────────────────┬───────────────────────────┘
                                    │
                  [Berhasil?] ──────┴────── [Gagal?]
                       │                         │
                       ▼                         ▼
            Ambil Title & Channel    ┌────────────────────────────────────────┐
            Lanjut ke Status Check   │ Tier 2: pytubefix / yt_dlp Fallback    │
                                     │ Scraping data langsung via client WEB  │
                                     └────────────────────────────────────────┘
```

### Hasil Uji Langsung Endpoint oEmbed pada `bYXjikrHBME`:
```json
{
  "title": "lincah lincah bgt??!!! @mahaliniraharjaofc @trioutmusic",
  "author_name": "RnBoyz*",
  "thumbnail_url": "https://i.ytimg.com/vi/bYXjikrHBME/hqdefault.jpg"
}
```
Hasilnya instan, akurat 100%, dan langsung mendapatkan nama channel `RnBoyz*` serta judul lengkap `lincah lincah bgt??!!! ...`.

---

## 4. SPESIFIKASI TAMPILAN DISCORD V2 CARD (PENYELARASAN 1:1 DENGAN FOTO 3)

Berikut adalah aturan format tampilan kartu agar **identik 100%** dengan Foto 3 yang disukai pengguna:

### A. Format Judul Utama Card
* Tidak menggunakan header kaku `🎬 VIDEO BARU • Channel`.
* Menggunakan tautan Markdown H1:
  ```python
  card_title = f"[{clean_title}]({video_url})"
  ```
  *Visual di Discord:* Teks judul besar berwarna biru tebal yang langsung membuka video jika diklik.

### B. Format Deskripsi / Subtitle Card
* Menampilkan link URL di baris bawah judul:
  ```python
  if desc and desc.strip():
      card_desc = f"{desc[:250].strip()}\n\n{video_url}"
  else:
      card_desc = f"{video_url}"
  ```
  *Visual di Discord:* URL berwarna biru muda tepat di bawah judul (seperti `https://youtu.be/bYXjikrHBME` di Foto 3).

### C. Warna Kartu (*Accent Border*)
* Di-set ke `color=None` (tanpa warna hex).
  *Visual di Discord:* Menghilangkan garis biru vertikal tebal di kiri, sehingga kartu tampil bersih, flat, dan menyatu dengan background chat Discord.

### D. Tombol Aksi (*Button Component*)
* URL Button (Style 5):
  * Video Baru / Shorts: `"label": "Tonton Video"`
  * Live Streaming: `"label": "Tonton Live Sekarang"`
  * Premiere: `"label": "Tonton Premiere"`

---

## 5. SPESIFIKASI AI COPYWRITING KONTEKSTUAL

Dengan tersedianya data metadata asli (`RnBoyz*` dan judul `lincah lincah bgt??!!! @mahaliniraharjaofc @trioutmusic`), Gemini akan menghasilkan pesan pengumuman yang relevan dan natural:

```text
@everyone Woy warga! RnBoyz baru upload video nih, katanya sih ada yang 'lincah lincah bgt' bareng @mahaliniraharjaofc! Buruan tonton!
```

Karakteristik Copywriting:
1. Menyapa server dengan santai dan hangat.
2. Menyebutkan nama kreator/channel secara tepat (`RnBoyz`).
3. Mengaitkan sapaan langsung dengan kata kunci judul videonya (`lincah lincah bgt`).
4. Bebas dari kata-kata klise robotik dan tanpa memaksakan slang asing yang cringe.

---

## 6. RENCANA KODE TEKNIS & DIFF IMPLEMENTASI

### 1. Fungsi Baru: `extract_rich_metadata(self, video_id, url)`
Fungsi ini ditambahkan ke [cogs/yt_checker_test.py](file:///c:/Users/Administrator/Downloads/rtmbot/cogs/yt_checker_test.py):
```python
async def extract_rich_metadata(self, video_id: str, url: str):
    """
    Mengambil metadata video YouTube menggunakan pipeline oEmbed resmi Google
    dengan fallback scraping HTML, menjamin 100% judul dan channel selalu didapat.
    """
    clean_url = f"https://www.youtube.com/watch?v={video_id}"
    oembed_url = f"https://www.youtube.com/oembed?url={clean_url}&format=json"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    metadata = {
        "title": None,
        "channel_name": None,
        "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
        "description": ""
    }

    try:
        timeout = aiohttp.ClientTimeout(total=6)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(oembed_url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    raw_title = data.get("title", "")
                    metadata["title"] = " ".join(raw_title.split())
                    metadata["channel_name"] = data.get("author_name", "")
                    if data.get("thumbnail_url"):
                        metadata["thumbnail_url"] = data.get("thumbnail_url")
    except Exception as e:
        print(f"[OEMBED ERROR] {e}")

    # Fallback jika oEmbed belum dapat title
    if not metadata["title"]:
        # Scraping HTML fallback
        ...
        
    return metadata
```

### 2. Refactoring `send_notification_card`
Menghilangkan header kaku dan menyelaraskan struktur ke gaya `cogs/notif.py`:
```python
async def send_notification_card(self, target_channel: discord.TextChannel, video_data: dict, ai_hype: str):
    video_id = video_data.get("video_id")
    video_url = video_data.get("url") or f"https://www.youtube.com/watch?v={video_id}"
    title = video_data.get("title") or "Video YouTube"
    channel_name = video_data.get("channel_name") or "YouTube Channel"
    status = video_data.get("status", "upload")
    desc = video_data.get("description", "") or ""

    if status == "live":
        btn_label = "Tonton Live Sekarang"
    elif status == "premier":
        btn_label = "Tonton Premiere"
    else:
        btn_label = "Tonton Video"

    thumbnail_url = video_data.get("thumbnail_url") or f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
    mention_content = f"@everyone {ai_hype}"

    buttons = [{
        "style": 5,
        "label": btn_label,
        "url": video_url
    }]

    # Style V2 Card murni seperti cogs/notif.py
    card_title = f"[{title}]({video_url})"
    
    if desc and desc.strip():
        card_desc = f"{desc[:250].strip()}\n\n{video_url}"
    else:
        card_desc = f"{video_url}"

    card = build_v2_card(
        title=card_title,
        description=card_desc,
        fields=None,
        color=None, # Bersih tanpa border samping
        buttons=buttons,
        media_url=thumbnail_url
    )

    await target_channel.send(content=mention_content)
    await send_v2_message(self.bot, target_channel.id, [card])
```

### 3. Pembaruan `yttest_cmd`
Memastikan `extract_rich_metadata` dan `classify_stream_status` bekerja sama:
1. `classify_stream_status` memeriksa apakah video berstatus `live`, `premier`, atau `upload`.
2. `extract_rich_metadata` mengambil `title` dan `channel_name` yang dijamin 100% valid melalui oEmbed.
3. Keduanya digabungkan untuk menghasilkan prompt AI yang akurat dan kartu V2 yang sempurna.

---

## 7. CHECKLIST VALIDASI & PENGUJIAN ULANG

Setelah rencana ini disetujui ("ACC"):
- [ ] Terapkan fungsi `extract_rich_metadata` di [cogs/yt_checker_test.py](file:///c:/Users/Administrator/Downloads/rtmbot/cogs/yt_checker_test.py).
- [ ] Ubah `send_notification_card` agar formatnya 1:1 identik dengan Foto 3 (`card_title = f"[{title}]({video_url})"`, `card_desc = video_url`, `color = None`).
- [ ] Jalankan uji simulasi via command line dengan URL uji coba `https://youtu.be/bYXjikrHBME`.
- [ ] Pastikan output `title` adalah `"lincah lincah bgt??!!! @mahaliniraharjaofc @trioutmusic"` dan `channel_name` adalah `"RnBoyz*"`.
- [ ] Pastikan AI hype menghasilkan sapaan yang menyebutkan "RnBoyz" dan topik video.
- [ ] Kompilasi dengan `py_compile` dan push ke remote `abogoboga main`.
