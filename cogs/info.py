import discord
from discord.ext import commands, tasks
from discord import ui, app_commands
from PIL import Image, ImageDraw, ImageFont
import aiohttp
import asyncio
import uuid
import time
import io
import os
import json
from datetime import datetime

FONT_URL = "https://github.com/MFarelS/RajinNulis-BOT/raw/master/font/Zahraaa.ttf"
IMAGE_URL = "https://github.com/MFarelS/RajinNulis-BOT/raw/master/MFarelSZ/Farelll/magernulis1.jpg"
UKURAN_FONT_NAMA = 22
UKURAN_FONT_TEKS = 18

FAQ_CHANNEL_ID = int(os.getenv("FAQ_CHANNEL_ID", 765140300145360896))
ROLE_CHANNEL_ID = int(os.getenv("ROLE_CHANNEL_ID", 1255221263811743836))

async def download_asset(url, session, is_font=False):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
            if response.status == 200:
                content = await response.read()
                if is_font:
                    return content
                else:
                    return io.BytesIO(content)
            print(f"Gagal mengunduh aset dari {url}: status {response.status}")
            return None
    except Exception as e:
        print(f"Error saat mengunduh aset: {e}")
        return None

def wrap_text(draw, text, font, max_width):
    lines = []
    if not text:
        return lines
    
    words = text.split(' ')
    current_line = ""
    for word in words:
        if draw.textlength(current_line + " " + word, font=font) < max_width:
            if current_line == "":
                current_line = word
            else:
                current_line += " " + word
        else:
            lines.append(current_line)
            current_line = word
    lines.append(current_line)
    return lines

class FAQView(ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @ui.button(label="FAQ Umum", style=discord.ButtonStyle.primary, emoji="❔")
    async def faq_umum_button(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="❔ FAQ Umum",
            description="Pertanyaan dan jawaban dasar seputar server ini.",
            color=discord.Color.from_rgb(123, 0, 255)
        )
        embed.add_field(name="Apa itu Discord?", value="Discord adalah aplikasi komunikasi gratis yang dirancang untuk komunitas, gamer, dan grup. Di Discord, Anda dapat mengobrol melalui teks, suara, dan video, serta berbagi layar di dalam server.", inline=False)
        embed.add_field(name="Bagaimana cara bergabung ke server Njan Discord?", value="Anda dapat bergabung ke server Njan Discord dengan menggunakan tautan undangan yang valid. Setelah mengklik tautan tersebut, Anda akan otomatis diarahkan untuk bergabung ke server. Pastikan Anda sudah memiliki akun Discord.", inline=False)
        embed.add_field(name="Apa itu 'role' di Discord?", value="'Role' adalah peran atau status yang diberikan kepada anggota di sebuah server. Role ini memberikan warna khusus pada nama, dan juga dapat memberikan akses ke channel atau fitur tertentu di dalam server, seperti channel khusus anggota atau moderator.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Profil & Media Sosial", style=discord.ButtonStyle.success, emoji="👤")
    async def profil_button(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="👤 Tentang Rizwan Fadilah",
            description="Saya Rizwan Fadilah, dikenal sebagai Njan. Saya adalah seorang gamer, streamer, dan penyanyi dengan banyak konten seru di YouTube. Bergabunglah bersama saya dan komunitas ini untuk mabar, mendengarkan lagu, dan berbagai keseruan lainnya!",
            color=discord.Color.from_rgb(0, 255, 209)
        )
        embed.add_field(name="Link Resmi", value="""
• [Youtube Game](https://youtube.com/@njanlive)
• [Youtube Music](https://music.youtube.com/channel/UCJGkN_PN8fnFirhbPCCOnvg?si=hVbVq8RnWJe298Mv)
• [Spotify](https://open.spotify.com/artist/6usptTdSkyzOX8rWIE4Y12?si=OFvTWh2MS1SCI9BfFVm-wA)
• [Apple Music](https://music.apple.com/id/artist/rizwan-fadilah/1644827546)
• [TikTok](https://tiktok.com/@rizwanfadilah.a.s)
• [Instagram](https://instagram.com/rizwanfadilah.a.s)
• [Youtube Utama](https://www.youtube.com/@RizwanFadilah)
""", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Membership YouTube", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def membership_button(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="▶️ Membership YouTube",
            description="Informasi penting untuk mendapatkan role membership YouTube Anda.",
            color=discord.Color.from_rgb(255, 94, 94)
        )
        embed.add_field(name="Cara menjadi anggota (member) di YouTube Njan?", value="Untuk menjadi anggota resmi channel YouTube Njan dan mendukungnya, Anda bisa bergabung melalui tautan resmi berikut ini: [Bergabung Menjadi Anggota YouTube](https://www.youtube.com/channel/UCW2TTb26sRBrU7jlKpjCHVA/join)", inline=False)
        embed.add_field(name="Cara menautkan akun YouTube dengan Discord?", value="""
1. Buka **User Settings** (tombol gerigi di kiri bawah layar Discord Anda).
2. Masuk ke tab **Connections**.
3. Klik ikon **YouTube**.
4. Ikuti petunjuk untuk login ke akun Google/YouTube Anda. Pastikan Anda login dengan akun yang memiliki membership.
5. Setelah berhasil, akun YouTube Anda akan terhubung. Secara otomatis, Discord akan memberikan role khusus bagi anggota (member) YouTube Anda.
""", inline=False)
        embed.add_field(name="Saya sudah menautkan akun, tapi role tidak muncul. Apa yang harus saya lakukan?", value="""
Ada beberapa alasan mengapa role membership mungkin tidak langsung muncul:
1. **Sinkronisasi**: Terkadang ada jeda waktu (hingga 1 jam) untuk proses sinkronisasi. Tunggu sebentar dan cek kembali.
2. **Periksa Role**: Pastikan Anda sudah menjadi anggota (*member*) dari channel YouTube yang sesuai.
3. **Hubungkan Kembali**: Coba putuskan koneksi YouTube Anda dari Discord, lalu hubungkan kembali untuk menyegarkan data.
""", inline=False)
        embed.add_field(name="Bagaimana cara mengatasi jika koneksi YouTube gagal?", value="Jika Anda mengalami masalah saat menautkan atau sinkronisasi akun YouTube, Anda bisa mencoba beberapa solusi. Untuk panduan yang lebih detail, silakan tonton video tutorial berikut ini: [Tutorial Mengatasi Gagal Sinkronisasi YouTube ke Discord](https://youtu.be/p6XtY6qXDpk)", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Aturan Server", style=discord.ButtonStyle.danger, emoji="📜")
    async def rules_button(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="📜 Aturan Utama Server",
            description="Aturan ini dibuat untuk menjaga lingkungan yang nyaman dan positif bagi semua anggota. Berikut adalah ringkasan peraturan penting yang harus dipatuhi:",
            color=discord.Color.from_rgb(255, 69, 0)
        )
        embed.add_field(name="Peraturan Server", value="""
• **Peraturan Utama:** Jaga sikap dan bahasa. Hindari pelecehan, rasisme, atau serangan pribadi. Jangan membuat drama dan bersikap "toxic" yang tidak perlu.
• **Gunakan Channel Sesuai Topik:** Setiap channel memiliki fungsinya masing-masing. Pastikan Anda mengirim pesan atau bergabung di channel yang sesuai.
• **Konten yang Sesuai:** Dilarang keras memposting konten dewasa (NSFW), gore, phishing, atau spam.
• **Bergabung Voice Chat:** Voice chat adalah tempat untuk berinteraksi dan bersenang-senang. Jangan ragu untuk bergabung dan ciptakan suasana yang akrab.
• **Hindari Ping Massal:** Jangan melakukan ping `@everyone` atau `@here` tanpa alasan yang benar-benar penting.
• **Kerja Sama dengan Staf:** Staf siap membantu. Silakan berkoordinasi dengan mereka jika ada kendala.
• **Cara Melaporkan:** Jika Anda menemukan pelanggaran, laporkan ke tim moderasi (Moderator atau Admin) dengan bukti yang jelas.
""", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @ui.button(label="Ambil Role", style=discord.ButtonStyle.success, emoji="✅")
    async def get_role_button(self, interaction: discord.Interaction, button: ui.Button):
        channel_mention = f"<#{ROLE_CHANNEL_ID}>" if (ROLE_CHANNEL_ID and interaction.guild and interaction.guild.get_channel(ROLE_CHANNEL_ID)) else "channel role server"
        await interaction.response.send_message(f"Silakan kunjungi {channel_mention} untuk mengambil role Anda!", ephemeral=True)

class SetGenderModal(discord.ui.Modal, title='Pengaturan Role Gender'):
    def __init__(self, cog, bot):
        super().__init__()
        self.cog = cog
        self.bot = bot
        
    male_role_id = discord.ui.TextInput(
        label='ID Role Male',
        placeholder='Masukkan ID role Male...',
        required=True
    )
    
    female_role_id = discord.ui.TextInput(
        label='ID Role Female',
        placeholder='Masukkan ID role Female...',
        required=True
    )
    
    custom_message = discord.ui.TextInput(
        label='Pesan Kustom (Opsional)',
        placeholder='Contoh: Halo {user}, silakan pilih role gender.',
        style=discord.TextStyle.paragraph,
        required=False
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("🚫 Kamu tidak memiliki izin `Manage Server`.", ephemeral=True)
            return
        try:
            male_id = int(self.male_role_id.value)
            female_id = int(self.female_role_id.value)
            
            guild = interaction.guild
            male_role = guild.get_role(male_id)
            female_role = guild.get_role(female_id)
            
            if not male_role or not female_role:
                await interaction.response.send_message("ID role tidak ditemukan. Pastikan ID-nya benar.", ephemeral=True)
                return

            guild_id = str(guild.id)
            
            if guild_id not in self.cog.config:
                self.cog.config[guild_id] = {}
            
            self.cog.config[guild_id]['male'] = male_role.id
            self.cog.config[guild_id]['female'] = female_role.id
            self.cog.config[guild_id]['custom_message'] = self.custom_message.value or None
            
            self.cog.save_config()

            embed = discord.Embed(
                title="✅ Pengaturan Selesai!",
                description="Pengaturan role gender untuk server ini berhasil disimpan.",
                color=discord.Color.green()
            )
            embed.add_field(name="Role Male", value=f"`{male_role.name}` (ID: {male_role.id})", inline=False)
            embed.add_field(name="Role Female", value=f"`{female_role.name}` (ID: {female_role.id})", inline=False)
            if self.custom_message.value:
                embed.add_field(name="Pesan Kustom", value=self.custom_message.value, inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except ValueError:
            await interaction.response.send_message("ID role harus berupa angka.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Terjadi kesalahan: {e}", ephemeral=True)

class RoleIdSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(
            placeholder="🔍 Pilih role untuk melihat & menyalin ID...",
            min_values=1,
            max_values=1,
            custom_id="rtmbot:role_id_select"
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            if not self.values:
                return await interaction.response.send_message("❌ Tidak ada role yang dipilih.", ephemeral=True)
            selected_role = self.values[0]
            color_val = selected_role.color if selected_role.color.value != 0 else discord.Color.blurple()
            guild_name = interaction.guild.name if interaction.guild else "Server"

            embed = discord.Embed(
                title="📋 Informasi & ID Role (Anti-Ping)",
                description="Detail role tanpa notifikasi atau mention:",
                color=color_val
            )
            embed.add_field(name="Nama Role", value=f"`{selected_role.name}`", inline=True)
            embed.add_field(name="ID Role (Klik / Tap untuk Salin)", value=f"```{selected_role.id}```", inline=False)
            total_members = len(selected_role.members) if hasattr(selected_role, 'members') else 0
            embed.add_field(name="Total Anggota", value=f"{total_members:,} member", inline=True)
            embed.add_field(name="Warna Hex", value=f"`{str(selected_role.color)}`", inline=True)
            embed.add_field(name="Posisi Hierarki", value=f"#{selected_role.position}", inline=True)
            embed.add_field(name="Mentionable", value="Ya" if selected_role.mentionable else "Tidak", inline=True)
            embed.add_field(name="Dikelola Bot / Integrasi", value="Ya" if selected_role.managed else "Tidak", inline=True)
            embed.add_field(name="Tampil Terpisah (Hoist)", value="Ya" if selected_role.hoist else "Tidak", inline=True)
            embed.set_footer(text=f"Server: {guild_name} • Salin ID role dengan mudah")

            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Terjadi kesalahan: {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)
            except Exception:
                pass

class RoleIdView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(RoleIdSelect())

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Terjadi kendala: {error}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Terjadi kendala: {error}", ephemeral=True)
        except Exception:
            pass

class SetGenderButton(discord.ui.Button):
    def __init__(self, bot, cog):
        super().__init__(label="Buka Formulir Pengaturan", style=discord.ButtonStyle.primary)
        self.cog = cog
        self.bot = bot
        
    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("🚫 Kamu tidak memiliki izin `Manage Server` untuk mengatur role gender.", ephemeral=True)
            return
        await interaction.response.send_modal(SetGenderModal(self.cog, self.bot))

HELP_CATEGORIES = {
    "overview": {
        "title": "🚀 RTM-Bot • PANDUAN PUSAT BANTUAN",
        "desc": "Selamat datang di pusat panduan **RTM-Bot**! Bot ini dilengkapi 17 modul sistem dengan 200+ perintah untuk mengelola administrasi, hiburan, media sosial, dan komunitas Anda.\n\n"
                "📌 **Format Penggunaan:**\n"
                "• Mendukung **Slash Command** (`/`) dengan autokomplet di Mobile & PC.\n"
                "• Mendukung **Prefix Command** (`!`) untuk perintah klasik.\n\n"
                "👉 **Pilih kategori di menu Dropdown di bawah** untuk melihat daftar perintah terperinci.",
        "color": 0x3498DB,
        "fields": [
            {"name": "🛡️ Moderasi & Sentinel", "value": "Proteksi server, timeout, trap honeypot, panel role, dan sistem tiket."},
            {"name": "💼 Asisten Keuangan", "value": "Arus kas (Cash In/Out), mutasi, target anggaran belanja, dan evaluasi 50/30/20."},
            {"name": "⭐ Leveling, EXP & Toko", "value": "EXP chat/voice, kartu profil rank Pillow emas, quest harian, dan toko item."},
            {"name": "🎮 Minigames & Werewolf", "value": "Werewolf multipemain peran lengkap, taruhan balapan kuda, kuis sains, dan tebak kata."},
            {"name": "📡 Radar & Social Media", "value": "Pemantau channel YouTube & akun TikTok real-time via MongoDB, broadcast live/video baru."},
            {"name": "🤖 AI Assistant & AIFilter", "value": "Chat Gemini 2.5 Flash, tanya kode bot, proteksi phising, dan whitelist domain/TLD."},
            {"name": "🔮 Interaksi Fun & Curhat", "value": "Tarot, zodiak, roast, ship persentase cinta, dan formulir curhat anonim (Confess)."},
            {"name": "🎙️ Voice Dinamis & Utilitas", "value": "Join-to-Create Voice Room sementara privat, profil HD, dan kutipan harian."},
            {"name": "🪝 Webhook & Penyiaran", "value": "Penyiaran Layout V2 Type 17, pengumuman berjadwal, dan relay pesan."}
        ]
    },
    "moderation": {
        "title": "🛡️ MODERASI & SENTINEL DEFENSE",
        "desc": "Sistem penegakan disiplin dan pertahanan otomatis server:",
        "color": 0xE74C3C,
        "fields": [
            {"name": "⚙️ /setup (alias !settings, !setupserver)", "value": "Master Server Control Center: Auto Role, Log, Booster, Tiket, & Panel Role."},
            {"name": "🎭 /panelrole & /setuppanelrole", "value": "Wizard pembuatan panel ambil role mandiri (Dropdown Menu / Tombol)."},
            {"name": "➕ /addpanelrole & /removepanelrole", "value": "Tambah atau hapus role dari pesan panel interaktif."},
            {"name": "🎫 /ticket (alias !tiket, !setupticket)", "value": "Setup kategori & pasang panel tiket bantuan interaktif terpadu."},
            {"name": "🛡️ /modpanel & /toggle_status", "value": "Dasbor moderasi real-time: status keamanan, timeout aktif, & quick actions."},
            {"name": "🔨 /ban <member> [alasan] & /unban <user_id>", "value": "Blokir atau buka blokir member dari server secara aman."},
            {"name": "👢 /kick <member> [alasan] & /softban <member>", "value": "Keluarkan member atau ban-unban instan untuk bersihkan riwayat chat 7 hari."},
            {"name": "⏳ /timeout <member> <durasi> & /untimeout", "value": "Bungkam member sementara (contoh: 10m, 1h, 1d) atau cabut timeout."},
            {"name": "⚠️ /warn <member> [alasan], /unwarn, /warnings", "value": "Catat, cabut, dan periksa riwayat surat peringatan resmi member."},
            {"name": "🗑️ /clear <jumlah> [channel]", "value": "Hapus pesan massal di channel (mendukung Text, Voice Channel, Stage, dan Thread)."},
            {"name": "🔒 /lock & /unlock", "value": "Kunci atau buka kembali izin berbicara channel dari member biasa."},
            {"name": "⏱️ /slowmode <detik>", "value": "Atur batas waktu jeda cooldown kirim pesan di channel (0 untuk matikan)."},
            {"name": "🍯 /trap", "value": "Atur channel jebakan (Honey-Pot) untuk auto-timeout 28 hari spammer/phishing."},
            {"name": "🔢 !addtrapcount <jumlah> & !settrapcount", "value": "Sinkronisasi atau atur manual counter pelanggar jebakan spam."},
            {"name": "📜 /set_log_channel <channel> & /setspamlog", "value": "Atur channel pencatatan log audit sistem keamanan & moderasi."},
            {"name": "📜 /setwelcomechannel & /setgoodbye", "value": "Atur channel ucapan selamat datang dan perpisahan member."},
            {"name": "📢 /announce <channel> <pesan>", "value": "Kirim pengumuman resmi bertanda tangan staf ke channel target."},
            {"name": "🚨 /report", "value": "Kirimkan laporan pelanggaran rahasia kepada tim moderator server via form modal."},
            {"name": "🏷️ !addrole <member> <role> & !removerole", "value": "Tambahkan atau copot role dari anggota server."},
            {"name": "✏️ !nick <member> [nama_baru]", "value": "Ubah nama panggilan member atau reset kembali ke nama asli."},
            {"name": "🔇 !disconnect <member>", "value": "Putuskan koneksi voice channel member secara paksa."},
            {"name": "📋 !channelrules <channel>", "value": "Tampilkan aturan khusus channel tertentu kepada pengguna."}
        ]
    },
    "finance": {
        "title": "💼 ASISTEN KEUANGAN & MANAJER CASHFLOW",
        "desc": "Manajer keuangan profesional untuk mengelola arus kas pribadi, target anggaran, dan konsultasi finansial:",
        "color": 0x2ECC71,
        "fields": [
            {"name": "➕ /cash_in <nominal> [kategori] [catatan]", "value": "Catat pemasukan kas (Gaji, Bisnis, Freelance, Dividen, dll.) (alias `!in`, `!masuk`)."},
            {"name": "➖ /cash_out <nominal> [kategori] [catatan]", "value": "Catat pengeluaran kas harian dengan proteksi batas anggaran (alias `!out`, `!keluar`)."},
            {"name": "📊 /keuangan", "value": "Buka dasbor finansial lengkap, saldo kas bersih, rasio tabungan, dan tombol interaktif (alias `!saldo`, `!wallet`)."},
            {"name": "📈 /cashflow", "value": "Laporan arus kas bulanan, komposisi persentase belanja, dan 10 mutasi terakhir (alias `!mutasi`)."},
            {"name": "🎯 /anggaran <nominal>", "value": "Tetapkan pagu batas belanja bulanan dengan peringatan overbudget (alias `!budget`)."},
            {"name": "💡 /konsultasi_keuangan", "value": "Evaluasi kesehatan finansial menggunakan kaidah perencana keuangan profesional 50/30/20 (alias `!evaluasi_keuangan`)."},
            {"name": "📥 /export_keuangan", "value": "Unduh seluruh riwayat transaksi keuangan pribadi ke format file CSV spreadsheet (alias `!exportfin`)."},
            {"name": "🗑️ /reset_keuangan", "value": "Hapus dan bersihkan seluruh catatan keuangan pribadi Anda dengan konfirmasi aman (alias `!resetfin`)."}
        ]
    },
    "leveling": {
        "title": "⭐ LEVELING, RANK & PROGRESSION",
        "desc": "Sistem pengalaman (EXP), Voice Tracking, papan aktivitas, dan pasar komunitas:",
        "color": 0x9B59B6,
        "fields": [
            {"name": "🎖️ /rank [member] (alias !rank, !level, !kartu)", "value": "Lihat kartu profil grafis HD lengkap dengan stempel emas wax seal, nomor lisensi, progress bar, level, dan saldo RSWN."},
            {"name": "🏆 /leaderboard (alias /top)", "value": "Tampilkan 10 member dengan perolehan level tertinggi di server."},
            {"name": "📅 /weekly", "value": "Papan peringkat perolehan EXP mingguan server."},
            {"name": "🎙️ /voicepanel & /voicepanel_remove", "value": "Pasang atau hapus papan live aktivitas voice, rekor room terlama, dan peringkat voice di channel."},
            {"name": "⏱️ /voicetime [member]", "value": "Cek total waktu aktif di voice channel server all-time, mingguan, & peringkat server."},
            {"name": "🏆 /voicerecord", "value": "Cek rekor durasi sesi voice channel terlama server dan channel pemegang rekor."},
            {"name": "⚙️ /setchannelrecord <channel> <jam> [menit]", "value": "Atur atau adopsi rekor voice room terlama server agar bot melanjutkan hitungan."},
            {"name": "➕ /addvoicetime & /setvoicetime", "value": "Tambahkan atau atur ulang durasi voice diri sendiri atau member target (Admin)."},
            {"name": "🎁 /giveaway & /reroll", "value": "Mulai giveaway berhadiah via modal formulir interaktif dan undi ulang pemenang."},
            {"name": "📜 /daily_quest & /complete_quest", "value": "Periksa quest harian dan klaim hadiah EXP serta koin RSWN."},
            {"name": "➕ /addquest <nama> <target> <exp> <coins>", "value": "Tambahkan quest harian baru ke sistem server (Admin)."},
            {"name": "🛒 /shop, /toggleshop, /toggleexpshop", "value": "Buka katalog toko interaktif beli item/badge, dan atur status buka/tutup toko."},
            {"name": "🏷️ /manageitems, /additem, /removeitem", "value": "Kelola item inventaris toko, harga koin, dan badge profil (Admin)."},
            {"name": "💸 /transfercoins <member> <jumlah>", "value": "Kirimkan saldo koin RSWN milikmu ke pengguna lain."},
            {"name": "💰 /givecoins <member> <jumlah> & /giveexp", "value": "Berikan bonus saldo koin atau EXP gratis kepada member (Admin)."},
            {"name": "🛠️ /setlevelconfig & /viewlevelconfig", "value": "Atur laju pengali EXP pesan dan voice server (Admin)."},
            {"name": "🎖️ /setlevelbadge & /removelevelbadge", "value": "Atur badge eksklusif yang ditampilkan di kartu rank member (Admin)."},
            {"name": "🎭 /setlevelrole, /setvoicerole, /setvoiceboost", "value": "Atur role rewards otomatis saat mencapai level atau durasi voice tertentu (Admin)."}
        ]
    },
    "games": {
        "title": "🎮 TAVERN PARTY & MINIGAMES",
        "desc": "Game interaktif multipemain, party voting, taruhan balap kuda, dan Werewolf klasik:",
        "color": 0xF1C40F,
        "fields": [
            {"name": "🎮 !games (alias !minigames)", "value": "Buka katalog interaktif seluruh minigames dan panduan bermain via menu dropdown."},
            {"name": "🐺 /ww join (alias !ww join)", "value": "Bergabung ke dalam antrean lobi permainan Werewolf."},
            {"name": "🐺 /ww mulai (alias !ww mulai)", "value": "Mulai sesi permainan Werewolf (Minimal 4 pemain)."},
            {"name": "🐺 /ww keluar & /ww batal", "value": "Keluar dari antrean lobi atau batalkan sesi permainan aktif."},
            {"name": "🐺 /ww set & /ww status", "value": "Atur komposisi jumlah peran dan periksa status lobi pemain aktif."},
            {"name": "🌙 Aksi Malam Werewolf (DM/Thread)", "value": "Perintah malam: `!bunuh <no>` (Serigala), `!lindungi <no>` (Dokter), `!terawang <no>` (Peramal), `!jaga <no>` (Pengawal), `!racun <no>` (Penyihir), `!intai <no>` (Mata-Mata)."},
            {"name": "☀️ !vote <nomor_warga>", "value": "Voting warga di siang hari untuk menggantung tersangka Werewolf."},
            {"name": "🏇 !balapan (alias !race)", "value": "Arena taruhan balap kuda multiplayer berhadiah koin RSWN."},
            {"name": "🪙 !taruhan <jumlah> <nomor_kuda>", "value": "Pasang taruhan pada kuda jagoanmu (1 s/d 5) sebelum balapan dimulai."},
            {"name": "🛑 !stopbalapan & !stopwerewolfaudio", "value": "Hentikan sesi balapan kuda atau matikan audio latar Werewolf."},
            {"name": "🔗 !sambung (alias !sk, !ressambung)", "value": "Tantangan sambung suku kata berantai multiplayer dengan combo multiplier."},
            {"name": "🗳️ !siapapaling (alias !paling, !sipaling)", "value": "Party game seru sistem voting rahasia 'Si Paling...' dengan grafik bar suara."},
            {"name": "🧩 !tebakemoji & !hintemoji", "value": "Tebak kata/frasa berdasarkan petunjuk emoji dengan opsi petunjuk via DM."},
            {"name": "🔤 !susunkata (alias !acak)", "value": "Susun kembali kata yang diacak hurufnya (Anagram) secepat mungkin."},
            {"name": "🔬 !kuisipa", "value": "Kuis tebak fakta sains & pengetahuan umum berhadiah koin RSWN & EXP."},
            {"name": "🪢 !hangman & !bantuanhangman", "value": "Tebak kata rahasia huruf demi huruf dalam 10 ronde seru."},
            {"name": "🕵️ !siapaaku", "value": "Kuis detektif tebak tokoh, benda, atau profesi via petunjuk bertahap."},
            {"name": "⚡ !hitungcepat", "value": "Adu kecepatan dan ketelitian berhitung matematika dasar."},
            {"name": "🤔 !pernahgak", "value": "Permainan kejujuran Never Have I Ever dengan tombol interaktif."},
            {"name": "🎭 !matamata, !tuduh, !ungkap_lokasi", "value": "Game peran tersembunyi mengungkap mata-mata di antara pemain."},
            {"name": "🎵 !kuismusik & !jawab", "value": "Tebak judul lagu dari petunjuk lirik atau audio."},
            {"name": "🧹 !stopgame", "value": "Reset dan bersihkan status game yang macet atau terkunci di channel."}
        ]
    },
    "social": {
        "title": "📡 RADAR & SOCIAL MEDIA CHECKER",
        "desc": "Sistem monitoring otomatis YouTube & TikTok real-time terintegrasi MongoDB:",
        "color": 0xE67E22,
        "fields": [
            {"name": "🚀 MongoDB Integration", "value": "Seluruh target channel YouTube dan akun TikTok tersimpan permanen di database MongoDB dengan pelacakan ID video dan status live."},
            {"name": "📺 /yt add <channel_id> <text_channel>", "value": "Daftarkan channel YouTube untuk dipantau notifikasi video dan siaran livenya."},
            {"name": "📺 /yt remove <channel_id> & /yt list", "value": "Hapus atau tampilkan daftar seluruh channel YouTube yang sedang dipantau."},
            {"name": "📺 /yt check", "value": "Paksa bot memeriksa pembaruan channel YouTube seketika untuk pengetesan (Test Run)."},
            {"name": "📺 /yt test <channel_id>", "value": "Kirimkan simulasi kartu notifikasi YouTube ke channel tujuan."},
            {"name": "📺 /yt setchannel, /yt setmention, /yt setmode, /yt toggle", "value": "Kustomisasi channel tujuan, role mention, mode notifikasi, dan toggle aktif/nonaktif."},
            {"name": "🎵 /tt add <username> <text_channel>", "value": "Daftarkan akun TikTok untuk dipantau video baru dan siaran langsungnya."},
            {"name": "🎵 /tt remove <username> & /tt list", "value": "Hapus atau tampilkan seluruh akun TikTok yang sedang dipantau bot."},
            {"name": "🎵 /tt check", "value": "Paksa bot memeriksa pembaruan TikTok seketika untuk pengetesan (Test Run)."},
            {"name": "🎵 /tt test <username>", "value": "Kirimkan simulasi kartu notifikasi TikTok ke channel tujuan."},
            {"name": "🎵 /tt setchannel, /tt setmention, /tt setmode, /tt toggle", "value": "Kustomisasi channel tujuan, mention role, mode notifikasi, dan toggle status aktif."},
            {"name": "⚙️ /checker list & /checker check", "value": "Tampilkan rekap seluruh target YouTube & TikTok, serta trigger pemindaian massal."},
            {"name": "⚙️ /checker interval <menit>", "value": "Atur frekuensi interval pemindaian otomatis di latar belakang."},
            {"name": "⚙️ /checker cache & /checker resetcache", "value": "Periksa atau bersihkan data cache ID video terakhir di database."},
            {"name": "📡 !config, !addpath, !removepath", "value": "Konfigurasi jalur feed notifikasi relay lintas channel (Owner)."},
            {"name": "📦 !checkcache & !resetcache", "value": "Periksa atau bersihkan antrean cache feed notifikasi relay (Owner)."}
        ]
    },
    "ai": {
        "title": "🤖 ASISTEN AI RAKA & KEAMANAN LINK / TLD",
        "desc": "Kecerdasan buatan Gemini 2.5 Flash, self-knowledge memori internal kode, dan filter link:",
        "color": 0x1ABC9C,
        "fields": [
            {"name": "🧠 Self-Knowledge Codebase Memory", "value": "Tanyakan apa saja seputar kode bot, cara pakai perintah, izin admin, atau alur modul bot! Cukup tag `@RTMBOT <tanya>`, reply pesan bot, atau awalan `!<tanya>`."},
            {"name": "🛡️ /aifilter tambah_whitelist <domain>", "value": "Tambahkan domain website ke daftar aman agar tautan tidak terhapus bot (contoh: `/aifilter tambah_whitelist domain:example.com`)."},
            {"name": "🛡️ /aifilter hapus_whitelist <domain>", "value": "Hapus domain website dari daftar whitelist aman."},
            {"name": "🚫 /aifilter tambah_tld <tld>", "value": "Tambahkan ekstensi domain mencurigakan yang diblokir otomatis (contoh: `/aifilter tambah_tld tld:.xyz`)."},
            {"name": "🚫 /aifilter hapus_tld <tld>", "value": "Hapus ekstensi domain dari daftar hitam pemblokiran."},
            {"name": "🛑 /aifilter tambah_kata <kata> & hapus_kata", "value": "Tambahkan atau hapus kata-kata sensitif yang dilarang di server."},
            {"name": "🖼️ /aifilter blokir_gambar <deskripsi>", "value": "Blokir konsep gambar berbahaya/phising secara visual menggunakan vision AI."},
            {"name": "🛡️ /cyber_toggle", "value": "Aktifkan atau matikan proteksi anti-phising, anti-scam, dan filter AI."},
            {"name": "🤖 /ai ngobrol, /ai selesai, /ai reset", "value": "Buka sesi percakapan fokus tanpa perlu mention berulang kali."},
            {"name": "🤖 /ai rangkum [jumlah]", "value": "Rangkum poin-poin obrolan channel terakhir secara otomatis."},
            {"name": "🎭 /aisifat atur_sifat & /aisifat hapus_sifat", "value": "Atur kepribadian atau persona kustom AI untuk pengguna."},
            {"name": "🎭 /aisifat ngambek & /aisifat patuh", "value": "Mode respon emosional khusus untuk interaksi tertentu."},
            {"name": "📚 /aimemori pelajari, ingatan, lupakan", "value": "Simpan atau hapus ingatan jangka panjang AI server."},
            {"name": "⚙️ /aiconfig set_learn_channel & reset_memori", "value": "Konfigurasi channel belajar dan reset memori AI server."},
            {"name": "🧹 !cleardm (alias !clear)", "value": "Bersihkan riwayat pesan bot di DM pribadi dan reset sesi obrolan AI."}
        ]
    },
    "fun": {
        "title": "🔮 INTERAKSI SOSIAL, FUN & CURHAT",
        "desc": "Fitur interaksi seru, ramalan, numerologi, dan curhat anonim:",
        "color": 0xE91E63,
        "fields": [
            {"name": "🔮 /tarot", "value": "Tarik 3 kartu Tarot mistis (Masa Lalu, Sekarang, Depan) dengan tafsiran filosofis ala Raka."},
            {"name": "♈ /zodiak <nama/tanggal>", "value": "Ramalan peruntungan zodiak, karier, dan asmara hari ini."},
            {"name": "🔢 /lifepath <tanggal_lahir>", "value": "Hitung angka takdir Life Path (Numerologi) kepribadian dan potensi diri."},
            {"name": "🔥 /roast [user]", "value": "Minta Raka meroast seseorang dengan sindiran pedas tapi kocak."},
            {"name": "💘 /ship <user1> [user2]", "value": "Kalkulator kecocokan persentase cinta dua pengguna."},
            {"name": "🎱 /8ball <pertanyaan>", "value": "Tanya ke bola ajaib Magic 8-Ball untuk mendapatkan jawaban absurd dan jenaka."},
            {"name": "🤫 /confess", "value": "Buka formulir modal rahasia untuk mengirim curhatan anonim ke channel confess."},
            {"name": "⚙️ /confess_setup & /set_confess_channel", "value": "Atur channel penampung pesan curhatan anonim server (Admin)."},
            {"name": "🎭 !pranknama <member> <nama> & !resetnama", "value": "Ubah nama panggilan member secara iseng atau kembalikan ke nama asli."}
        ]
    },
    "voice_util": {
        "title": "🎙️ VOICE DINAMIS, QUOTES & UTILITAS",
        "desc": "Saluran suara otomatis, profil member, kutipan, dan utilitas server:",
        "color": 0x34495E,
        "fields": [
            {"name": "🔊 Join-to-Create Voice", "value": "Masuk ke channel suara trigger untuk membuat room private otomatis."},
            {"name": "🔒 /vc lock & /vc unlock", "value": "Kunci voice room dari orang lain atau buka kembali untuk umum."},
            {"name": "👥 /vc limit <jumlah>", "value": "Atur kapasitas batas member maksimal di ruangan (0 = tanpa batas)."},
            {"name": "✏️ /vc rename <nama_baru>", "value": "Ganti nama voice room pribadi Anda sesuai selera."},
            {"name": "👢 /vc kick <member>", "value": "Usir member tertentu keluar dari voice room pribadi Anda."},
            {"name": "🔑 /vc grant <member> & /vc revoke", "value": "Berikan atau cabut izin akses khusus ke member tertentu."},
            {"name": "👑 /vc transfer <member>", "value": "Pindahkan hak kepemilikan room kepada member lain di ruangan."},
            {"name": "🗑️ /vc delete", "value": "Hapus ruangan voice privat seketika."},
            {"name": "🛠️ /vcadmin settrigger & setcat", "value": "Atur kanal pemicu dan kategori penampung kamar suara (Admin)."},
            {"name": "📊 /act", "value": "Lihat statistik durasi keaktifan suara, streaming, dan bermain game server."},
            {"name": "💬 /resq (alias !resq, !sendquote)", "value": "Kirim kutipan inspiratif harian berdesain elegan."},
            {"name": "📜 /setchannelq, /listquotes, /deletequote", "value": "Setup kanal kutipan dan kelola daftar kutipan server (Admin)."},
            {"name": "📝 /tulis <nama> <teks>", "value": "Renders teks menjadi gambar lembaran tulisan tangan di buku bergaris."},
            {"name": "👤 /user [user]", "value": "Lihat kartu informasi lengkap akun, tanggal gabung, dan peran member."},
            {"name": "🖼️ /avatar [user]", "value": "Ambil gambar avatar profil pengguna dalam resolusi tinggi."},
            {"name": "❓ /faq", "value": "Buka menu FAQ interaktif seputar server dan aturan komunitas."},
            {"name": "🏛️ /getserverasset [guild_id]", "value": "Ekstrak nama resmi, logo HD (1024px), dan banner server Discord."},
            {"name": "🆔 /getroleid (alias !idrole, !roleid)", "value": "Pilih role dari menu dropdown UI untuk melihat dan menyalin ID role secara instan tanpa tag/mention (Anti-Ping)."},
            {"name": "⚙️ /set_gender", "value": "Buka formulir modal untuk pengaturan role gender otomatis (Admin)."}
        ]
    },
    "webhook": {
        "title": "🪝 WEBHOOK RELAY & PENYIARAN",
        "desc": "Sistem relayer pesan, penyiaran layout V2 Type 17, dan pesan berjadwal:",
        "color": 0x16A085,
        "fields": [
            {"name": "🪝 !send_webhook <target_url> (alias !swh)", "value": "Kirim pesan siaran dan kartu komponen Layout V2 Type 17 ke Webhook."},
            {"name": "✏️ !edit_broadcast <message_id> (alias !eb)", "value": "Edit pesan siaran yang sudah terkirim via Webhook."},
            {"name": "📢 !announcement <channel> <pesan>", "value": "Kirim siaran pengumuman resmi bertanda tangan server."},
            {"name": "🖼️ !send_media <target_url> <media_url>", "value": "Kirimkan lampiran media resolusi tinggi ke Webhook Discord."},
            {"name": "⏰ !schedule <waktu> <pesan>", "value": "Jadwalkan pengiriman pesan atau siaran otomatis di waktu mendatang."},
            {"name": "📋 !list_schedules", "value": "Lihat daftar seluruh jadwal pengiriman pesan yang sedang aktif."},
            {"name": "💾 !backup_config, !load_config, !list_configs", "value": "Cadangkan atau muat ulang konfigurasi webhook server."},
            {"name": "🔗 !setwebhook <target_url> & !delwebhook", "value": "Tautkan atau copot relayer pencerminan pesan otomatis antar channel."},
            {"name": "🧪 !teswebhook [pesan]", "value": "Kirim pesan uji coba untuk memverifikasi koneksi webhook target."}
        ]
    }
}

class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(
        placeholder="📂 Pilih kategori perintah di sini...",
        custom_id="rtmbot:help_category_select",
        row=0,
        options=[
            discord.SelectOption(label="Beranda Panduan", value="overview", description="Ringkasan umum sistem RTM-Bot", emoji="🏠"),
            discord.SelectOption(label="Moderasi & Keamanan", value="moderation", description="Setup server, ban, kick, timeout, trap", emoji="🛡️"),
            discord.SelectOption(label="Keuangan Pribadi", value="finance", description="Manajer arus kas, cash in/out, budgeting", emoji="💼"),
            discord.SelectOption(label="Leveling & Toko Server", value="leveling", description="Kartu rank emas, voicetime, shop, quest", emoji="⭐"),
            discord.SelectOption(label="Party Games & Werewolf", value="games", description="Werewolf RPG, balapan kuda, kuis", emoji="🎮"),
            discord.SelectOption(label="Radar & Social Media", value="social", description="YouTube & TikTok real-time monitor", emoji="📡"),
            discord.SelectOption(label="AI Assistant & AIFilter", value="ai", description="Gemini chat, whitelist domain, filter TLD", emoji="🤖"),
            discord.SelectOption(label="Interaksi Fun & Curhat", value="fun", description="Tarot, zodiak, roast, ship, confess anonim", emoji="🔮"),
            discord.SelectOption(label="Voice Dinamis & Utilitas", value="voice_util", description="Temp VC, profil HD, quotes, tulis", emoji="🎙️"),
            discord.SelectOption(label="Webhook & Penyiaran", value="webhook", description="Relay pesan, schedule, Layout V2 Type 17", emoji="🪝")
        ]
    )
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.Select):
        selected_key = select.values[0]
        cat_data = HELP_CATEGORIES.get(selected_key, HELP_CATEGORIES["overview"])
        embed = discord.Embed(
            title=cat_data["title"],
            description=cat_data["desc"],
            color=cat_data["color"]
        )
        for f in cat_data["fields"]:
            embed.add_field(name=f["name"], value=f["value"], inline=False)
            
        embed.set_footer(text=f"RTM-Bot • Modul Aktif: 17 • Kategori: {selected_key.capitalize()}")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Beranda", style=discord.ButtonStyle.primary, emoji="🏠", custom_id="rtmbot:help_home_btn", row=1)
    async def home_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        cat_data = HELP_CATEGORIES["overview"]
        embed = discord.Embed(
            title=cat_data["title"],
            description=cat_data["desc"],
            color=cat_data["color"]
        )
        for f in cat_data["fields"]:
            embed.add_field(name=f["name"], value=f["value"], inline=False)
        embed.set_footer(text="RTM-Bot • Modul Aktif: 17 • Kategori: Overview")
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Terjadi kendala saat memperbarui tampilan. Coba jalankan kembali `/help`.", ephemeral=True)
        except Exception:
            pass

class InsightHub(commands.Cog, name="Community Insights & Utility"):
    def __init__(self, bot):
        self.bot = bot
        self.config_file = 'gender_roles_config.json'
        self.config = self.load_config()
        self.gender_warning_cooldown = {}

    async def cog_load(self):
        self.bot.add_view(HelpView())
        try:
            if not self.sync_server_stats.is_running():
                self.sync_server_stats.start()
        except Exception:
            pass

    def cog_unload(self):
        try:
            self.sync_server_stats.cancel()
        except Exception:
            pass

    @tasks.loop(minutes=2)
    async def sync_server_stats(self):
        try:
            stats = {
                "timestamp": int(time.time()),
                "guilds": {}
            }
            target_ids = [765138959625486357, 722619465644113962]
            for gid in target_ids:
                g = self.bot.get_guild(gid)
                if g:
                    stats["guilds"][str(gid)] = {
                        "id": str(gid),
                        "name": g.name,
                        "member_count": g.member_count,
                        "approximate_presence_count": getattr(g, "approximate_presence_count", 0),
                        "icon_url": g.icon.url if g.icon else None
                    }
            if stats["guilds"]:
                os.makedirs("data", exist_ok=True)
                with open("data/server_stats.json", "w", encoding="utf-8") as f:
                    json.dump(stats, f, indent=2)

                web_path = r"C:\Users\Administrator\Downloads\rtmbot html\html-main\costum\server_stats.json"
                if os.path.exists(os.path.dirname(web_path)):
                    with open(web_path, "w", encoding="utf-8") as f:
                        json.dump(stats, f, indent=2)
        except Exception:
            pass

    @sync_server_stats.before_loop
    async def before_sync_server_stats(self):
        await self.bot.wait_until_ready()

    async def buat_tulisan_tangan(self, teks, nama):
        session = getattr(self.bot, 'session', None)
        close_session = False
        if not session or session.closed:
            session = aiohttp.ClientSession()
            close_session = True
        try:
            gambar_data = await download_asset(IMAGE_URL, session)
            if not gambar_data:
                return None
                
            font_data = await download_asset(FONT_URL, session, is_font=True)
            if not font_data:
                return None

            file_id = uuid.uuid4().hex[:8]
            temp_font_path = f"temp_font_{file_id}.ttf"
            with open(temp_font_path, "wb") as f:
                f.write(font_data)

            def _render():
                try:
                    gambar_latar = Image.open(gambar_data)
                    font_tulisan = ImageFont.truetype(temp_font_path, UKURAN_FONT_TEKS)
                    font_nama = ImageFont.truetype(temp_font_path, UKURAN_FONT_NAMA)

                    start_x = 345
                    start_y = 130
                    line_spacing = 22
                    max_width = 500
                    nama_x = 500
                    nama_y = 70

                    draw = ImageDraw.Draw(gambar_latar)
                    draw.text((nama_x, nama_y), nama, font=font_nama, fill=(0, 0, 0))

                    x_pos, y_pos = start_x, start_y
                    paragraphs = teks.split('\n')

                    for paragraph in paragraphs:
                        lines_to_draw = wrap_text(draw, paragraph, font_tulisan, max_width)
                        for line in lines_to_draw:
                            draw.text((x_pos, y_pos), line, font=font_tulisan, fill=(0, 0, 0))
                            y_pos += line_spacing
                        y_pos += line_spacing * 0.5

                    nama_file_hasil = f"tulisan_tangan_{file_id}.png"
                    gambar_latar.save(nama_file_hasil)
                    return nama_file_hasil
                finally:
                    if os.path.exists(temp_font_path):
                        try:
                            os.remove(temp_font_path)
                        except Exception:
                            pass

            return await asyncio.to_thread(_render)
        except Exception as e:
            print(f"Error dalam memuat aset: {e}")
            return None
        finally:
            if close_session and not session.closed:
                await session.close()

    def load_config(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                return json.load(f)
        return {}

    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)

    def has_gender_role(self, member, guild_id):
        guild_settings = self.config.get(str(guild_id), {})
        male_id = guild_settings.get('male')
        female_id = guild_settings.get('female')

        if male_id and any(role.id == male_id for role in member.roles):
            return True
        if female_id and any(role.id == female_id for role in member.roles):
            return True
        
        return False

    def format_time(self, dt):
        return dt.strftime("%A, %d %B %Y pukul %H:%M WIB")

    def get_user_info_embed(self, user, member):
        embed = discord.Embed(
            title=f"Profil {user.display_name}",
            description=f"**Username:** {user.name}",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"ID: {user.id}")
        embed.add_field(name="Waktu Pembuatan Akun", value=self.format_time(user.created_at), inline=False)
        
        if member:
            embed.add_field(name="Waktu Bergabung Server", value=self.format_time(member.joined_at), inline=False)
            roles = [role.mention for role in member.roles if role.name != '@everyone']
            if roles:
                embed.add_field(name="Roles", value=" ".join(roles), inline=False)
            else:
                embed.add_field(name="Roles", value="Tidak ada role.", inline=False)

        if user.banner:
            embed.set_image(url=user.banner.url)
        
        return embed

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        guild_id = str(message.guild.id)
        if guild_id not in self.config:
            return
        
        try:
            prefix = self.bot.command_prefix
            if isinstance(prefix, str) and message.content.startswith(prefix):
                 return
            elif callable(prefix):
                 prefixes = await prefix(self.bot, message)
                 if any(message.content.startswith(p) for p in prefixes):
                      return
        except Exception:
             pass

        member = message.author
        if not self.has_gender_role(member, guild_id):
            now = time.time()
            last_warn = self.gender_warning_cooldown.get(member.id, 0)
            if now - last_warn < 600:  # Cooldown 10 menit per user agar tidak spam channel
                return
            self.gender_warning_cooldown[member.id] = now

            guild_settings = self.config.get(guild_id, {})
            custom_message = guild_settings.get('custom_message')
            
            if custom_message:
                description = custom_message.replace('{user}', member.mention)
            else:
                description = (
                    f"Halo {member.mention}, sepertinya kamu belum memilih role gender.\n\n"
                    f"Mohon ambil salah satu role yang tersedia, seperti **Male** atau **Female**, "
                    f"untuk bisa berinteraksi di server ini."
                )

            embed = discord.Embed(
                title="⚠️ Peringatan Role Gender!",
                description=description,
                color=discord.Color.gold()
            )
            embed.set_footer(text="Pengingat ini muncul berkala sampai kamu mengambil role.")
            await message.channel.send(embed=embed)

    @commands.hybrid_command(name='tulis', description='Mengubah teks menjadi gambar tulisan tangan.')
    @app_commands.describe(nama="Nama pembuat tulisan", teks="Teks yang ingin diubah menjadi tulisan tangan")
    async def tulis_tangan(self, ctx, nama: str, *, teks: str):
        if not nama or not teks:
            await ctx.send("Mohon berikan nama dan teks yang ingin Anda ubah menjadi tulisan tangan.\nContoh: `!tulis Rhdevs Ini adalah teks`")
            return

        await ctx.send("Sedang menulis... Mohon tunggu sebentar.")
        
        nama_file_hasil = await self.buat_tulisan_tangan(teks, nama)

        if nama_file_hasil:
            try:
                await ctx.send(file=discord.File(nama_file_hasil))
            finally:
                if os.path.exists(nama_file_hasil):
                    try:
                        os.remove(nama_file_hasil)
                    except Exception:
                        pass
        else:
            await ctx.send("Terjadi kesalahan saat membuat gambar. Coba lagi nanti.")

    @commands.hybrid_command(name="faq", description="Menampilkan FAQ dengan tombol.")
    async def faq_command(self, ctx: commands.Context):
        if ctx.message:
            try: await ctx.message.delete()
            except: pass
        if FAQ_CHANNEL_ID and ctx.guild and ctx.guild.get_channel(FAQ_CHANNEL_ID):
            if ctx.channel.id != FAQ_CHANNEL_ID:
                await ctx.send("Perintah ini hanya bisa digunakan di channel FAQ.", delete_after=5)
                return

        embed = discord.Embed(
            title="📚 FAQ - Njan Discord",
            description="Halo! Silakan pilih salah satu tombol di bawah untuk melihat informasi yang Anda butuhkan.",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed, view=FAQView(), delete_after=300)

    @commands.hybrid_command(name='user', description='Menampilkan info profil user.')
    @app_commands.describe(user="User yang ingin diperiksa")
    async def user_info(self, ctx, user: discord.User = None):
        if not user:
            user = ctx.author

        member = ctx.guild.get_member(user.id) if ctx.guild else None
        embed = self.get_user_info_embed(user, member)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='avatar', description='Menampilkan avatar user.')
    @app_commands.describe(user="User yang ingin dilihat avatarnya")
    async def avatar(self, ctx, user: discord.User = None):
        target = user or ctx.author
        embed = discord.Embed(
            title=f"Avatar dari {target.display_name}",
            color=discord.Color.random()
        )
        embed.set_image(url=target.display_avatar.url)
        embed.set_footer(text=f"Diminta oleh {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='set_gender', help='Menyiapkan pengaturan role gender via UI.')
    @commands.has_permissions(manage_guild=True)
    async def set_gender(self, ctx):
        embed = discord.Embed(
            title="⚙️ Pengaturan Role Gender",
            description="Klik tombol di bawah ini untuk membuka formulir pengaturan.",
            color=discord.Color.blue()
        )
        view = discord.ui.View()
        view.add_item(SetGenderButton(self.bot, self))
        await ctx.send(embed=embed, view=view, ephemeral=True)

    @set_gender.error
    async def set_gender_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Maaf, kamu tidak punya izin `Manage Server` untuk menggunakan perintah ini.", ephemeral=True)
        else:
            print(f'Error: {error}')

    @commands.hybrid_command(name="getserverasset", description="Mengambil nama resmi, foto icon HD, dan banner server Discord.")
    @app_commands.describe(guild_id="ID Server target (opsional, default: server saat ini)")
    async def get_server_asset(self, ctx: commands.Context, guild_id: str = None):
        """Mengambil nama, icon HD, dan banner server untuk dokumentasi/web."""
        target_guild = ctx.guild
        if guild_id:
            try:
                gid = int(guild_id.strip())
                found = self.bot.get_guild(gid)
                if found:
                    target_guild = found
            except Exception:
                pass

        if not target_guild:
            await ctx.send("Server tidak ditemukan atau bot belum bergabung ke server tersebut.", ephemeral=True)
            return

        icon_url = target_guild.icon.replace(size=1024, format="png").url if target_guild.icon else None
        banner_url = target_guild.banner.replace(size=1024, format="png").url if target_guild.banner else None

        embed = discord.Embed(
            title=f"Aset Visual Resmi: {target_guild.name}",
            description=f"**ID Server:** `{target_guild.id}`\n**Total Member:** {getattr(target_guild, 'member_count', 'N/A'):,} Anggota",
            color=discord.Color.gold()
        )
        if icon_url:
            embed.set_thumbnail(url=icon_url)
            embed.add_field(name="Icon Resmi HD (1024px)", value=f"[Download Icon HD]({icon_url})", inline=True)
        if banner_url:
            embed.set_image(url=banner_url)
            embed.add_field(name="Banner Resmi HD (1024px)", value=f"[Download Banner HD]({banner_url})", inline=True)

        embed.set_footer(text=f"Diekstrak via RTMBOT System • {target_guild.name}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="getroleid", aliases=["idrole", "roleid"], description="Ambil dan salin ID role server via UI Dropdown tanpa perlu tag role.")
    async def get_role_id(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send("Perintah ini hanya dapat digunakan di dalam server.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🔍 Pemilih ID Role Server (Anti-Ping)",
            description="Pilih salah satu role pada menu dropdown di bawah untuk melihat dan menyalin ID-nya secara instan tanpa perlu melakukan tag/mention ke role tersebut.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Aman & Bersih • Salin ID role dengan sekali klik")
        await ctx.send(embed=embed, view=RoleIdView(), ephemeral=True)

    @commands.hybrid_command(name="help", aliases=["h", "bantuan"], description="Pusat panduan perintah dan fitur interaktif RTM-Bot")
    async def help_command(self, ctx: commands.Context):
        cat_data = HELP_CATEGORIES["overview"]
        embed = discord.Embed(
            title=cat_data["title"],
            description=cat_data["desc"],
            color=cat_data["color"]
        )
        for f in cat_data["fields"]:
            embed.add_field(name=f["name"], value=f["value"], inline=False)
        embed.set_footer(text="RTM-Bot • Modul Aktif: 17 • Kategori: Overview")

        view = HelpView()
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(InsightHub(bot))
