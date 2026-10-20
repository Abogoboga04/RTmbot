import os
import ast
import json
import glob
import re

MEMORY_FILE_PATH = "data/bot_codebase_memory.json"

MODULE_METADATA = {
    "moderation.py": {
        "name": "Sentinel Moderation & Server Security",
        "category": "Keamanan & Pengaturan Server",
        "description": "Sistem proteksi menyeluruh, anti-spam trap card self-healing, anti-phishing, timeout otomatis, audit logs, panel role, sistem tiket, dan master dashboard /setup.",
        "key_features": [
            "Master Setup Dashboard (/setup) untuk konfigurasi kanal welcome, booster, tiket, audit log, trap spam",
            "Kartu Jebakan Spam Self-Healing: Otomatis mendeteksi spam/phishing di kanal trap dan auto-timeout pelanggar",
            "Panel Role (/setuppanelrole, /addpanelrole) dengan gaya Dropdown Select atau Button interaktif",
            "Sistem Tiket Terisolasi dengan tombol tutup manual countdown 5 detik dan transkrip",
            "Welcome & Farewell V2 Container Card borderless dengan sertifikat member 1050x660 PNG",
            "Tindakan moderasi lengkap: !mute, !unmute, !warn, !kick, !ban, !clear, !slowmode"
        ]
    },
    "leveling.py": {
        "name": "Leveling & Luxury Member Certification",
        "category": "Komunitas & Gamifikasi",
        "description": "Sistem XP berbasis pesan dan voice, leaderboard server, role rewards otomatis, custom badge, dan sertifikat kartu anggota resmi.",
        "key_features": [
            "Perintah /rank dan !rank untuk melihat kartu keanggotaan resmi berlisensi emas dengan avatar dan stempel wax seal",
            "Papan peringkat /leaderboard dan !top dengan visualisasi status interaktif",
            "Pengaturan konfigurasi level (/setlevelconfig) dan badge eksklusif (/setlevelbadge)",
            "Voice XP & Message XP tracking otomatis dengan proteksi spam XP"
        ]
    },
    "card_generator.py": {
        "name": "Member Card Generator Engine",
        "category": "Grafis & Sertifikasi",
        "description": "Mesin pembuat kartu sertifikat anggota resolusi tinggi (1050x660 PNG) via Pillow dengan wax seal scalloped emas dan nomor lisensi ringkas (5 digit user ID + 4 digit server ID).",
        "key_features": [
            "Rendering kartu sertifikat resmi dengan foto profil pengguna konsentris",
            "Stempel lilin mewah (luxury wax seal) scalloped 16 kelopak dan lis konsentris emas",
            "Nomor lisensi terverifikasi berformat ringkas: 5 angka user ID + 4 angka server ID",
            "Tanda tangan digital Owner Server dan Bot Developer (Rhdevs & RTM Team)"
        ]
    },
    "temp_voice.py": {
        "name": "Temporary Voice Channel (Join-to-Create)",
        "category": "Suara & Utilitas",
        "description": "Sistem pembuatan voice room sementara otomatis saat member bergabung ke kanal trigger, lengkap dengan kontrol ruangan privat.",
        "key_features": [
            "Join-to-Create: Kanal otomatis dibuatkan saat masuk dan otomatis terhapus saat kosong",
            "Kontrol suara: /vc lock (gembok), /vc unlock (buka), /vc name (ganti nama)",
            "Pengaturan kapasitas (/vc limit), bitrate (/vc bitrate), sembunyikan (/vc hide)",
            "Admin setup: /vcadmin settrigger (atur kanal pemicu), /vcadmin setcat (kategori)"
        ]
    },
    "finance.py": {
        "name": "Virtual Economy & Kas Server (RSWN)",
        "category": "Ekonomi & Gamifikasi",
        "description": "Sistem perbankan dan mata uang virtual server RSWN, pekerjaan harian, investasi, dan kasino komunitas.",
        "key_features": [
            "Klaim gaji harian (!daily) dan bekerja dengan pekerjaan random (!work)",
            "Cek saldo dompet & kas bank (!balance / !bal, !bank)",
            "Transfer saldo antar member (!transfer, !pay)",
            "Investasi dan mini-games ekonomi (!invest, !gamble, !slots)"
        ]
    },
    "gemini.py": {
        "name": "Unified AI Assistant & Cyber Security Engine",
        "category": "Kecerdasan Buatan & Keamanan",
        "description": "Asisten AI cerdas berbasis Google Gemini 2.5 Flash, reasoning gambar, filter phising/SARA cerdas, persona dinamis, dan memori percakapan.",
        "key_features": [
            "AI Chatbot percakapan alami melalui tag @RTMBOT, reply pesan, atau awalan !",
            "Codebase Self-Aware Memory: Mengetahui seluruh fitur, sintaks perintah, dan panduan bot",
            "Deteksi link phising dan gambar spam berbahaya dengan visual reasoning",
            "Filter Keamanan & Whitelist Domain (/aifilter): /aifilter tambah_whitelist <domain> untuk whitelist link/domain aman agar tidak dihapus bot, /aifilter hapus_whitelist <domain>",
            "Filter TLD Ekstensi (/aifilter): /aifilter tambah_tld <tld> untuk memblokir ekstensi mencurigakan (.xyz, .top, dll), /aifilter hapus_tld <tld>",
            "Filter Kata & Gambar AI (/aifilter): /aifilter tambah_kata, /aifilter hapus_kata, /aifilter blokir_gambar",
            "Clear chat DM (!clear / !cleardm di DM pribadi untuk menghapus pesan bot & reset memori)"
        ]
    },
    "social_checker.py": {
        "name": "Social Media Real-Time Monitor (YouTube & TikTok)",
        "category": "Radar & Social Media",
        "description": "Pemantau channel YouTube dan akun TikTok secara otomatis dan real-time menggunakan MongoDB untuk pelacakan status live/video baru dan pengiriman kartu notifikasi.",
        "key_features": [
            "YouTube Tracker: /yt add, /yt remove, /yt setchannel, /yt setmention, /yt setmode, /yt toggle, /yt list, /yt test, /yt check",
            "TikTok Tracker: /tt add, /tt remove, /tt setchannel, /tt setmention, /tt setmode, /tt toggle, /tt list, /tt test, /tt check",
            "Checker Control: /checker list, /checker check, /checker interval, /checker cache, /checker resetcache",
            "Penyimpanan database MongoDB untuk riwayat video terakhir dan live status"
        ]
    },
    "minigames.py": {
        "name": "Interactive Minigames Hub",
        "category": "Hiburan & Permainan",
        "description": "Koleksi permainan interaktif teks dan tebak-tebakan multipemain untuk menghidupkan obrolan server.",
        "key_features": [
            "Katalog permainan interaktif via !games",
            "Sambung Kata berantai (!sambung / !sk)",
            "Tebak Emoji (!tebakemoji) dengan opsi petunjuk via DM (!hintemoji)",
            "Susun Kata / Anagram (!susunkata / !acak)",
            "Party Game voting rahasia Si Paling (!siapapaling / !sipaling)",
            "Kuis IPA dan pengetahuan sains (!kuisipa)"
        ]
    },
    "party_games.py": {
        "name": "Werewolf Multiplayer Party Game",
        "category": "Hiburan & Permainan",
        "description": "Permainan klasik Werewolf terintegrasi bot dengan peran Warga, Serigala, Peramal, Dokter, dan narasi malam/siang otomatis.",
        "key_features": [
            "Lobi antrean pemain: !ww join (gabung), !ww keluar (keluar)",
            "Mulai permainan: !ww mulai (start oleh host/admin)",
            "Sistem peran tersembunyi via DM bot dengan alur pemungutan suara transparan"
        ]
    },
    "webhook.py": {
        "name": "Webhook Dispatcher & Broadcast Engine",
        "category": "Utilitas & Penyiaran",
        "description": "Pengiriman pesan penyiaran, webhook Discord Layout V2, pengumuman berjadwal, dan manajemen pengumuman server.",
        "key_features": [
            "Kirim webhook kustom (!swh / send_webhook) dan edit siaran (!eb / edit_broadcast)",
            "Pengumuman server resmi (!announcement)",
            "Pengiriman media dan pesan terjadwal (!schedule)"
        ]
    },
    "notif.py": {
        "name": "Social Media Live Feed Broadcaster",
        "category": "Notifikasi & Penyiaran",
        "description": "Pemantau siaran langsung dan unggahan konten baru dari platform YouTube, Instagram, dan TikTok.",
        "key_features": [
            "Setup kanal feed notifikasi via !config",
            "Tambah dan hapus pemantauan feed via !addpath dan !removepath",
            "Pengecekan dan reset cache feed via !checkcache dan !resetcache"
        ]
    },
    "activity.py": {
        "name": "Server Activity & Voice Tracker",
        "category": "Statistik & Keaktifan",
        "description": "Pelacak durasi keaktifan suara, streaming, dan bermain game para anggota server.",
        "key_features": [
            "Pencatatan jam aktif di voice channel server",
            "Statistik aktivitas member mingguan dan bulanan"
        ]
    },
    "quotes.py": {
        "name": "Daily Quotes & Inscriptions",
        "category": "Komunitas & Hiburan",
        "description": "Pengirim kutipan inspiratif harian, manajemen kanal quote server, dan quote submit member.",
        "key_features": [
            "Kirim quote inspiratif via /resq atau !resq",
            "Admin setup kanal kutipan via !setchannelq",
            "Manajemen daftar kutipan via !listquotes dan !deletequote"
        ]
    },
    "fun.py": {
        "name": "Fun Interactions & Roleplay",
        "category": "Hiburan & Interaksi",
        "description": "Perintah interaksi sosial seru antar member, anime roleplay (peluk, tampar), dan candaan komunitas.",
        "key_features": [
            "Interaksi sosial: slap, hug, pat, kiss",
            "Meme generator dan lelucon ringan komunitas"
        ]
    },
    "info.py": {
        "name": "Information & Utility Specs",
        "category": "Informasi & Diagnostik",
        "description": "Pemeriksa profil pengguna, avatar HD, banner, informasi detail server, statistik bot, uptime, dan latensi ping.",
        "key_features": [
            "Informasi pengguna (/userinfo, !userinfo) dan server (/serverinfo, !serverinfo)",
            "Unduh avatar resolusi penuh (/avatar, !avatar) dan banner (/banner, !banner)",
            "Salin ID role via UI Dropdown (/getroleid, !idrole, !roleid) tanpa tag/mention (Anti-Ping)",
            "Statistik bot, memory usage, uptime, dan ping (/botinfo, !ping)"
        ]
    },
    "v2_layout.py": {
        "name": "Discord Component Type 17 Engine",
        "category": "Arsitektur Komponen V2",
        "description": "Modul pembangun struktur JSON kontainer kartu modern Type 17, Media Gallery Type 12, Text Display Type 10, dan HTTP sender aman flag 32768.",
        "key_features": [
            "build_v2_card: Container Card Type 17 borderless (color=None) dengan penempatan media & footer presisi",
            "send_v2_message: Pengirim HTTP payload Component V2 tanpa root content untuk mencegah error 400",
            "send_v2_interaction: Integrasi aman interaksi callback & persistent view"
        ]
    }
}

WORKFLOW_GUIDES = [
    {
        "topic": "Setup Server & Dashboard Utama",
        "keywords": ["setup", "dashboard", "konfigurasi", "atur", "pengaturan", "panel"],
        "summary": "Gunakan perintah `/setup` (khusus Administrator) untuk membuka Master Setup Dashboard. Di dashboard ini kamu bisa mengatur: Welcome Channel & Pesan, Booster Channel & Pesan, Ticket Channel & Kategori, Log Channel Audit, dan Trigger Channel Anti-Spam Trap."
    },
    {
        "topic": "Keamanan Link, TLD & Domain Whitelist (AIFilter)",
        "keywords": ["whitelist", "domain", "tld", "kehapus", "aifilter", "link", "aman", "filter link", "blokir link", "izin link", "phishing", "scam"],
        "summary": "Panduan pengelolaan domain aman dan proteksi link via `/aifilter`:\n1. Tambah domain ke whitelist (agar link aman dan tidak terhapus bot):\n   `/aifilter tambah_whitelist domain:<nama_domain>` (contoh: `/aifilter tambah_whitelist domain:example.com` atau `rhdevs.my.id`).\n2. Hapus domain dari whitelist:\n   `/aifilter hapus_whitelist domain:<nama_domain>`.\n3. Tambah ekstensi TLD berbahaya yang otomatis diblokir:\n   `/aifilter tambah_tld tld:<ekstensi>` (contoh: `/aifilter tambah_tld tld:.xyz` atau `.top` atau `.ru`).\n4. Hapus ekstensi TLD dari daftar blokir:\n   `/aifilter hapus_tld tld:<ekstensi>`.\n5. Tambah kata terlarang: `/aifilter tambah_kata kata:<kata>`.\n6. Hapus kata terlarang: `/aifilter hapus_kata kata:<kata>`.\n7. Blokir gambar berbahaya/phising: `/aifilter blokir_gambar deskripsi_gambar:<deskripsi>`.\nCatatan: Perintah `/aifilter` memerlukan izin Bot Owner."
    },
    {
        "topic": "Social Media Real-Time Monitor (YouTube & TikTok)",
        "keywords": ["social", "checker", "tiktok", "youtube", "yt", "tt", "feed", "cek live", "mongo", "notif video"],
        "summary": "Panduan pemantauan media sosial real-time terintegrasi MongoDB:\n1. YouTube Monitor: `/yt add channel_id:<ID> text_channel:<#channel>` untuk memantau channel, `/yt remove channel_id:<ID>`, `/yt list`, `/yt check` untuk cek manual.\n2. TikTok Monitor: `/tt add username:<username> text_channel:<#channel>` untuk memantau akun TikTok, `/tt remove username:<username>`, `/tt list`, `/tt check` untuk cek manual.\n3. Hub Kontrol: `/checker check` untuk memeriksa seluruh feed sekarang, `/checker interval` untuk atur jeda pemindaian, dan `/checker cache` untuk melihat cache video."
    },
    {
        "topic": "Salin ID Role Server Tanpa Tag (Anti-Ping)",
        "keywords": ["role id", "id role", "getroleid", "roleid", "salin id", "ambil id role", "dropdown role", "tanpa tag"],
        "summary": "Gunakan perintah `/getroleid` (atau `!idrole`, `!roleid`) untuk membuka menu dropdown Discord Role Select. Pilih salah satu role server untuk melihat detailnya dan menyalin ID role secara langsung tanpa perlu melakukan tag atau mention yang bisa menimbulkan ping mengganggu ke member."
    },
    {
        "topic": "Setup Pesan Sambutan (Welcome Message & Banner)",
        "keywords": ["welcome", "sambutan", "member baru", "banner welcome", "kartu welcome", "selamat datang"],
        "summary": "1. Jalankan `/setup` -> Pilih 'Pengaturan Dasar' -> Klik tombol 'Welcome Channel'.\n2. Pilih kanal selamat datang pada menu dropdown.\n3. Klik tombol '✏️ Edit Teks & Banner Welcome' untuk mengatur Judul, Nama Pengirim, Isi Pesan (bisa gunakan variabel `{user}` dan `{guild_name}`), serta URL Banner (opsional).\n4. Jika URL banner dikosongkan, bot otomatis membuatkan Kartu Sertifikat Resmi Anggota 1050x660 PNG berisi foto profil member dan stempel emas secara otomatis!"
    },
    {
        "topic": "Setup Sistem Tiket Dukungan",
        "keywords": ["tiket", "ticket", "buka tiket", "tutup tiket", "modmail", "support"],
        "summary": "1. Jalankan `/setup` -> Pilih 'Tiket Support'.\n2. Atur kanal pengiriman panel tiket dan kategori penyimpanan kanal tiket baru.\n3. Klik 'Edit Pesan Tiket' untuk menyesuaikan judul dan deskripsi.\n4. Tiket yang dibuka oleh member bersifat privat dan hanya bisa ditutup secara aman menggunakan tombol '[ 🔒 Tutup Tiket ]' dengan countdown 5 detik oleh pembuat tiket atau staf server."
    },
    {
        "topic": "Setup Sistem Keamanan & Trap Anti-Spam",
        "keywords": ["trap", "jebakan", "anti spam", "phishing", "scam", "timeout", "keamanan", "sentinel"],
        "summary": "1. Jalankan `/setup` -> Pilih 'Sistem Keamanan' -> Tambahkan kanal jebakan (Trigger Channel).\n2. Buat kanal seperti `#verify-here` atau `#peraturan` yang disembunyikan bagi member resmi namun terlihat oleh bot raid/spammer.\n3. Setiap pesan di kanal trap langsung dihapus seketika, pelaku di-timeout otomatis, dan log dikirim ke kanal audit log.\n4. Kartu jebakan menampilkan hitungan pelanggar yang otomatis tersinkronisasi (self-healing), dan dapat diatur manual via `!addtrapcount <jumlah>` atau `!settrapcount <jumlah>`."
    },
    {
        "topic": "Setup Panel Pemilihan Role (Self-Role)",
        "keywords": ["panel role", "setuppanelrole", "addpanelrole", "ambil role", "reaction role"],
        "summary": "1. Jalankan `/setuppanelrole channel:<kanal> mode:<select/button> judul:<Judul Panel>`.\n2. Catat ID pesan panel yang terkirim.\n3. Tambahkan role satu per satu dengan `/addpanelrole message_id:<ID Pesan> role:<@Role> label_teks:<Nama Label> emoji:<Emoji>`.\n4. Member bisa mengambil dan melepas role dengan sekali klik dropdown atau tombol interaktif."
    },
    {
        "topic": "Setup Voice Channel Sementara (Join-to-Create)",
        "keywords": ["temp voice", "voice sementara", "join to create", "kamar suara", "vc", "vcadmin"],
        "summary": "1. Admin menyiapkan kanal pemicu: `/vcadmin settrigger channel:<voice_channel>`.\n2. Admin menyiapkan kategori tujuan: `/vcadmin setcat category:<category>`.\n3. Saat member masuk ke kanal pemicu, bot otomatis membuatkan ruangan suara privat baru dan memindahkan member ke sana.\n4. Pemilik ruangan bisa mengelola via `/vc lock` (gembok), `/vc unlock` (buka), `/vc name <nama>` (ganti nama), `/vc limit <jumlah>` (batas member), atau panel tombol kontrol."
    },
    {
        "topic": "Sistem Leveling & Kartu Anggota Resmi",
        "keywords": ["rank", "level", "leveling", "leaderboard", "kartu member", "lisensi", "exp"],
        "summary": "1. Member mengumpulkan EXP dari mengetik pesan dan aktif di voice channel.\n2. Gunakan `/rank` atau `!rank` untuk menampilkan Kartu Sertifikat Resmi Anggota (1050x660 PNG) mewah berlisensi emas dengan nomor lisensi format ringkas 5 digit user ID + 4 digit server ID.\n3. Gunakan `/leaderboard` atau `!top` untuk melihat peringkat teratas di server.\n4. Admin dapat mengatur konfigurasi level via `/setlevelconfig` dan badge hadiah via `/setlevelbadge`."
    },
    {
        "topic": "Ekonomi Server & Mata Uang RSWN",
        "keywords": ["rswn", "uang", "daily", "work", "balance", "bank", "transfer", "ekonomi", "invest"],
        "summary": "1. Klaim gaji harian dengan `!daily` dan bekerja dengan `!work`.\n2. Cek saldo dompet dan tabungan bank dengan `!balance` (atau `!bal`) dan `!bank`.\n3. Transfer uang antar member dengan `!transfer <@user> <jumlah>` atau `!pay <@user> <jumlah>`.\n4. Simpan uang di bank vault untuk perlindungan atau ikuti mini-game investasi `!invest` dan kasino `!gamble`."
    },
    {
        "topic": "Pembersihan Chat DM Pribadi dengan Bot",
        "keywords": ["clear dm", "cleardm", "hapus dm", "reset dm", "bersihkan dm"],
        "summary": "Di ruang obrolan DM pribadi dengan bot, kirim pesan `!clear` atau `!cleardm`. Bot akan secara otomatis menghapus semua pesan miliknya sendiri di kanal DM tersebut (hingga 100 pesan) dan mereset riwayat memori percakapan AI untuk DM tersebut. (Catatan: Pesan yang dikirim oleh pengguna di DM hanya bisa dihapus oleh pengguna sendiri sesuai kebijakan Discord API)."
    }
]

def scan_all_codebase():
    target_files = ["main.py"] + sorted(glob.glob("cogs/*.py"))
    modules_data = {}

    for fpath in target_files:
        base_name = os.path.basename(fpath)
        if not os.path.exists(fpath):
            continue

        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        try:
            tree = ast.parse(content)
        except Exception:
            continue

        file_meta = MODULE_METADATA.get(base_name, {
            "name": base_name,
            "category": "Modul Sistem",
            "description": f"Modul fungsional {base_name}",
            "key_features": []
        })

        commands_list = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cmd_type = None
                cmd_name = node.name
                parent_group = None
                aliases = []
                permissions = []
                params = []
                doc = ast.get_docstring(node) or ""

                for dec in node.decorator_list:
                    dec_str = ast.unparse(dec)
                    if "commands.hybrid_command" in dec_str:
                        cmd_type = "Hybrid (/ & !)"
                    elif "app_commands.command" in dec_str:
                        cmd_type = "Slash (/)"
                    elif "commands.command" in dec_str:
                        cmd_type = "Prefix (!)"
                    elif "commands.hybrid_group" in dec_str or "commands.group" in dec_str:
                        cmd_type = "Command Group"
                    else:
                        subgroup_match = re.search(r'([a-zA-Z0-9_]+)\.command', dec_str)
                        if subgroup_match:
                            grp_candidate = subgroup_match.group(1)
                            if grp_candidate not in ["commands", "app_commands"]:
                                cmd_type = f"Subcommand ({grp_candidate})"
                                parent_group = grp_candidate

                    name_match = re.search(r'name=["\'](.*?)["\']', dec_str)
                    if name_match:
                        cmd_name = name_match.group(1)

                    desc_match = re.search(r'description=["\'](.*?)["\']', dec_str)
                    if desc_match and not doc:
                        doc = desc_match.group(1)

                    alias_match = re.search(r'aliases=\[(.*?)\]', dec_str)
                    if alias_match:
                        raw_aliases = alias_match.group(1)
                        aliases = [a.strip().strip("'\"") for a in raw_aliases.split(",") if a.strip()]

                    if "has_permissions" in dec_str or "default_permissions" in dec_str or "is_owner" in dec_str:
                        perm_match = re.search(r'\((.*?)\)', dec_str)
                        if perm_match:
                            permissions.append(perm_match.group(1).replace("=True", ""))

                if cmd_type:
                    for arg in node.args.args:
                        if arg.arg not in ["self", "ctx", "interaction"]:
                            params.append(arg.arg)

                    display_name = f"{parent_group} {cmd_name}" if parent_group else cmd_name
                    commands_list.append({
                        "name": display_name,
                        "raw_name": cmd_name,
                        "parent_group": parent_group,
                        "aliases": aliases,
                        "type": cmd_type,
                        "parameters": params,
                        "permissions": permissions,
                        "description": doc.strip().split("\n")[0] if doc else "Tidak ada deskripsi"
                    })

        modules_data[base_name] = {
            "metadata": file_meta,
            "commands_count": len(commands_list),
            "commands": commands_list
        }

    full_memory = {
        "bot_name": "RTMBOT",
        "description": "Multi-purpose Discord Bot Profesional untuk Moderasi, Keamanan Sentinel, Leveling Bersertifikat Resmi, Tiket Support, Voice Sementara, AI Gemini, Ekonomi RSWN, dan Party Minigames.",
        "modules": modules_data,
        "workflow_guides": WORKFLOW_GUIDES
    }

    os.makedirs(os.path.dirname(MEMORY_FILE_PATH), exist_ok=True)
    with open(MEMORY_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(full_memory, f, indent=2, ensure_ascii=False)

    return full_memory

def load_bot_memory():
    if os.path.exists(MEMORY_FILE_PATH):
        try:
            with open(MEMORY_FILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return scan_all_codebase()

def find_relevant_knowledge(query: str, max_chars: int = 2400) -> str:
    memory = load_bot_memory()
    q_lower = query.lower()
    q_tokens = set(re.findall(r'[a-zA-Z0-9]+', q_lower))

    matched_guides = []
    for guide in memory.get("workflow_guides", []):
        for kw in guide.get("keywords", []):
            if kw in q_lower or any(k in q_tokens for k in kw.split()):
                matched_guides.append(f"📌 PANDUAN {guide['topic'].upper()}:\n{guide['summary']}")
                break

    matched_commands = []
    for mod_file, mod_info in memory.get("modules", {}).items():
        for cmd in mod_info.get("commands", []):
            cmd_name = cmd.get("name", "").lower()
            raw_name = cmd.get("raw_name", "").lower()
            aliases = [a.lower() for a in cmd.get("aliases", [])]
            cmd_tokens = set(re.findall(r'[a-zA-Z0-9]+', cmd_name))
            desc_tokens = set(re.findall(r'[a-zA-Z0-9]+', cmd.get("description", "").lower()))

            score = 0
            if cmd_name == q_lower or cmd_name in q_lower:
                score += 15
            if raw_name == q_lower or raw_name in q_lower:
                score += 12
            if any(a == q_lower or a in q_lower for a in aliases):
                score += 10

            common_cmd_tokens = {t for t in cmd_tokens if len(t) > 2}.intersection(q_tokens)
            if common_cmd_tokens:
                score += len(common_cmd_tokens) * 6

            common_desc = {t for t in desc_tokens if len(t) > 2}.intersection(q_tokens) - {"dan", "yang", "untuk", "dari", "ini", "itu", "atau", "bisa", "ada"}
            if common_desc:
                score += len(common_desc) * 3

            if score > 0:
                perm_str = f" [Izin: {', '.join(cmd['permissions'])}]" if cmd.get('permissions') else ""
                param_str = f" <{'> <'.join(cmd['parameters'])}>" if cmd.get('parameters') else ""
                matched_commands.append((score, f"• `{cmd['type']}` {cmd['name']}{param_str}{perm_str}: {cmd['description']}"))

    matched_commands.sort(key=lambda x: x[0], reverse=True)

    matched_modules = []
    if not matched_commands and not matched_guides:
        for mod_file, mod_info in memory.get("modules", {}).items():
            meta = mod_info.get("metadata", {})
            name_lower = meta.get("name", "").lower()
            desc_lower = meta.get("description", "").lower()
            cat_lower = meta.get("category", "").lower()
            if any(w in q_lower for w in name_lower.split() + cat_lower.split() if len(w) > 3):
                sample_cmds = [c['name'] for c in mod_info.get("commands", [])[:6]]
                matched_modules.append(f"📦 MODUL {meta.get('name')}: {meta.get('description')}\nPerintah: {', '.join(sample_cmds)}")

    context_parts = []
    if matched_guides:
        context_parts.extend(matched_guides[:2])
    if matched_commands:
        context_parts.append("⚙️ PERINTAH TERKAIT:\n" + "\n".join([item[1] for item in matched_commands[:8]]))
    if matched_modules:
        context_parts.append("\n".join(matched_modules[:2]))

    full_context = "\n\n".join(context_parts)
    if len(full_context) > max_chars:
        full_context = full_context[:max_chars] + "..."
    return full_context

if __name__ == "__main__":
    mem = scan_all_codebase()
    total_cmds = sum(m.get("commands_count", 0) for m in mem.get("modules", {}).values())
    print(f"Pemindaian selesai! Berhasil mencatat {len(mem.get('modules', {}))} modul dan {total_cmds} perintah ke {MEMORY_FILE_PATH}")
