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
from cogs.v2_layout import build_v2_card, send_v2_message, send_v2_interaction, update_v2_interaction, register_view

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
        "title": "📋 Panduan Fitur Bot",
        "desc": "Halo! Seluruh 230 perintah aktif bot kini dapat kamu jelajahi langsung pada katalog web interaktif dengan fitur pencarian cepat dan salin syntax 1-klik.\n\n"
                "• **Katalog Web Resmi**: [rtmbot.biz.id/commands](https://rtmbot.biz.id/commands)\n"
                "• **Slash Command (`/`)**: Ketik garis miring `/` di kolom chat untuk opsi otomatis.\n"
                "• **Prefix Command (`!`)**: Gunakan tanda seru `!` untuk perintah teks klasik.",
        "color": 0x3498DB,
        "fields": [
            {"name": "🛡️ Moderasi & Keamanan", "value": "Kelola member, bersihkan chat, kunci channel, peringatan, dan log aktivitas."},
            {"name": "💼 Catatan Keuangan", "value": "Catat uang masuk, belanja harian, cek sisa saldo, dan pasang batas pengeluaran."},
            {"name": "⭐ Level & Toko Server", "value": "Kartu profil rank, hitungan jam voice, quest harian, dan toko item server."},
            {"name": "🎮 Game & Werewolf", "value": "Main Werewolf bersama teman, taruhan balap kuda, tebak kata, dan aneka kuis seru."},
            {"name": "📡 Notifikasi Media Sosial", "value": "Kabar otomatis setiap ada video baru atau live streaming YouTube dan TikTok."},
            {"name": "🤖 Asisten AI & Filter Link", "value": "Tanya jawab santai seputar bot, teman ngobrol, dan pengamanan link berbahaya."},
            {"name": "🔮 Hiburan & Curhat", "value": "Kartu tarot, ramalan zodiak, cek kecocokan, dan ruang curhat rahasia."},
            {"name": "🎙️ Voice Room & Info", "value": "Bikin kamar voice privat otomatis, cek foto avatar jernih, dan kutipan harian."},
            {"name": "🪝 Pesan Siaran & Jadwal", "value": "Kirim pengumuman resmi server, jadwal kirim pesan, dan integrasi webhook."}
        ]
    },
    "moderation": {
        "title": "🛡️ Moderasi & Pengaturan Server",
        "desc": "Kumpulan perintah staf untuk menjaga ketertiban dan keamanan server:",
        "color": 0xE74C3C,
        "fields": [
            {"name": "⚙️ /setup (alias !settings)", "value": "Menu utama pengaturan server: role otomatis, log aktivitas, booster, dan tiket."},
            {"name": "🎭 /panelrole & /setuppanelrole", "value": "Bikin panel ambil role sendiri menggunakan tombol atau menu pilihan."},
            {"name": "➕ /addpanelrole & /removepanelrole", "value": "Tambah atau hapus role dari pesan panel yang sudah ada."},
            {"name": "🎫 /ticket (alias !tiket)", "value": "Pasang tombol pembuatan tiket bantuan untuk member yang butuh bantuan staf."},
            {"name": "🛡️ /modpanel & /toggle_status", "value": "Pantau status keamanan server dan daftar member yang sedang kena timeout."},
            {"name": "🔨 /ban <member> & /unban <user_id>", "value": "Blokir atau buka kembali akses member ke server."},
            {"name": "👢 /kick <member> & /softban <member>", "value": "Keluarkan member atau bersihkan riwayat chat member bermasalah."},
            {"name": "⏳ /timeout <member> <durasi> & /untimeout", "value": "Bungkam member sementara (misal: 10m, 1h, 1d) atau batalkan pembungkaman."},
            {"name": "⚠️ /warn <member>, /unwarn, /warnings", "value": "Beri surat peringatan atau periksa catatan pelanggaran member."},
            {"name": "🗑️ /clear <jumlah>", "value": "Hapus pesan sekaligus di channel teks, thread, atau voice text."},
            {"name": "🔒 /lock & /unlock", "value": "Kunci channel agar member biasa tidak bisa kirim pesan, atau buka kembali."},
            {"name": "⏱️ /slowmode <detik>", "value": "Pasang jeda waktu kirim chat di channel (isi 0 untuk matikan)."},
            {"name": "🍯 /trap", "value": "Pasang channel jebakan untuk membungkam akun bot spam atau phising otomatis."},
            {"name": "🔢 !addtrapcount & !settrapcount", "value": "Cek atau atur jumlah akun yang terjaring di channel jebakan."},
            {"name": "📜 /set_log_channel & /setspamlog", "value": "Tentukan channel untuk mencatat riwayat aktivitas moderasi dan keamanan."},
            {"name": "📜 /setwelcomechannel & /setgoodbye", "value": "Tentukan channel ucapan selamat datang dan perpisahan member."},
            {"name": "📢 /announce <channel> <pesan>", "value": "Kirim pesan pengumuman resmi ke channel pilihan."},
            {"name": "🚨 /report", "value": "Kirim laporan kejadian mencurigakan ke tim moderator secara rahasia."},
            {"name": "🏷️ !addrole <member> <role> & !removerole", "value": "Beri atau lepas role dari member secara cepat."},
            {"name": "✏️ !nick <member> [nama]", "value": "Ganti nama panggilan member di server atau kembalikan ke nama asli."},
            {"name": "🔇 !disconnect <member>", "value": "Putuskan sambungan voice member secara langsung."},
            {"name": "📋 !channelrules <channel>", "value": "Tampilkan aturan khusus yang berlaku di channel tertentu."}
        ]
    },
    "finance": {
        "title": "💼 Pencatatan Keuangan Pribadi",
        "desc": "Catat pemasukan, pantau belanja harian, dan kelola saldo keuangan kamu:",
        "color": 0x2ECC71,
        "fields": [
            {"name": "➕ /cash_in <nominal> [kategori] [catatan]", "value": "Catat uang masuk seperti gaji, hasil usaha, atau bonus (alias `!in`, `!masuk`)."},
            {"name": "➖ /cash_out <nominal> [kategori] [catatan]", "value": "Catat pengeluaran harian dan cek sisa batas belanja (alias `!out`, `!keluar`)."},
            {"name": "📊 /keuangan", "value": "Lihat ringkasan total uang masuk, keluar, dan sisa saldo kamu (alias `!saldo`, `!wallet`)."},
            {"name": "📈 /cashflow", "value": "Lihat riwayat uang masuk dan keluar serta 10 mutasi transaksi terakhir (alias `!mutasi`)."},
            {"name": "🎯 /anggaran <nominal>", "value": "Pasang batas maksimal belanja bulanan agar tidak boros (alias `!budget`)."},
            {"name": "💡 /konsultasi_keuangan", "value": "Minta saran pembagian pos keuangan untuk kebutuhan, tabungan, dan hiburan (alias `!evaluasi_keuangan`)."},
            {"name": "📥 /export_keuangan", "value": "Download rekapan catatan keuangan kamu ke file Excel/CSV (alias `!exportfin`)."},
            {"name": "🗑️ /reset_keuangan", "value": "Hapus semua catatan keuangan kamu dari awal dengan konfirmasi aman (alias `!resetfin`)."}
        ]
    },
    "leveling": {
        "title": "⭐ Level, Aktivitas Voice & Toko",
        "desc": "Pantau perkembangan level obrolan, durasi nongkrong di voice, dan belanja item server:",
        "color": 0x9B59B6,
        "fields": [
            {"name": "🎖️ /rank [member] (alias !rank, !level)", "value": "Tampilkan kartu profil berisi level, progres EXP, jam voice, dan saldo koin."},
            {"name": "🏆 /leaderboard (alias /top)", "value": "Daftar 10 member dengan level obrolan tertinggi di server."},
            {"name": "📅 /weekly", "value": "Peringkat member paling aktif mengumpulkan EXP minggu ini."},
            {"name": "🎙️ /voicepanel & /voicepanel_remove", "value": "Pasang atau copot papan live durasi voice dan rekor obrolan terlama."},
            {"name": "⏱️ /voicetime [member]", "value": "Cek total waktu aktif mengobrol di voice channel server."},
            {"name": "🏆 /voicerecord", "value": "Lihat rekor sesi nongkrong voice paling lama di server."},
            {"name": "⚙️ /setchannelrecord <channel> <jam> [menit]", "value": "Atur catatan rekor voice channel terlama (Staf)."},
            {"name": "➕ /addvoicetime & /setvoicetime", "value": "Tambah atau atur durasi jam voice member (Staf)."},
            {"name": "🎁 /giveaway & /reroll", "value": "Bikin acara bagi-bagi hadiah atau undi ulang pemenang."},
            {"name": "📜 /daily_quest & /complete_quest", "value": "Lihat misi harian dan klaim hadiah koin serta bonus EXP."},
            {"name": "➕ /addquest <nama> <target> <exp> <coins>", "value": "Tambah misi harian baru untuk member server (Staf)."},
            {"name": "🛒 /shop, /toggleshop, /toggleexpshop", "value": "Buka katalog toko server untuk beli barang atau badge profil."},
            {"name": "🏷️ /manageitems, /additem, /removeitem", "value": "Kelola daftar barang dagangan dan harga di toko (Staf)."},
            {"name": "💸 /transfercoins <member> <jumlah>", "value": "Kirim koin milikmu ke teman di server."},
            {"name": "💰 /givecoins & /giveexp", "value": "Beri bonus koin atau EXP gratis ke member (Staf)."},
            {"name": "🛠️ /setlevelconfig & /viewlevelconfig", "value": "Atur kecepatan perolehan EXP chat dan voice di server (Staf)."},
            {"name": "🎖️ /setlevelbadge & /removelevelbadge", "value": "Atur badge keren yang tampil di kartu profil member (Staf)."},
            {"name": "🎭 /setlevelrole, /setvoicerole, /setvoiceboost", "value": "Atur pemberian role otomatis saat mencapai level atau durasi voice tertentu (Staf)."}
        ]
    },
    "games": {
        "title": "🎮 Game Santai & Werewolf",
        "desc": "Pilihan game multiplayer seru yang bisa dimainkan bersama anggota server:",
        "color": 0xF1C40F,
        "fields": [
            {"name": "🎮 !games (alias !minigames)", "value": "Buka katalog lengkap semua game dan panduan bermainnya."},
            {"name": "🐺 /ww join (alias !ww join)", "value": "Ikut masuk ke lobi permainan Werewolf."},
            {"name": "🐺 /ww mulai (alias !ww mulai)", "value": "Mulai game Werewolf kalau pemain sudah kumpul (minimal 4 orang)."},
            {"name": "🐺 /ww keluar & /ww batal", "value": "Keluar dari antrean lobi atau batalkan game yang sedang disiapkan."},
            {"name": "🐺 /ww set & /ww status", "value": "Atur peran game dan lihat siapa saja yang sudah masuk lobi."},
            {"name": "🌙 Aksi Malam Werewolf", "value": "Perintah malam via DM/Thread: bunuh, lindungi, terawang, jaga, racun, atau intai."},
            {"name": "☀️ !vote <nomor_warga>", "value": "Pilih warga yang dicurigai serigala di siang hari untuk digantung."},
            {"name": "🏇 !balapan (alias !race)", "value": "Game balap kuda rame-rame dengan hadiah koin."},
            {"name": "🪙 !taruhan <jumlah> <nomor_kuda>", "value": "Pasang taruhan koin pada nomor kuda jagoanmu (1 sampai 5)."},
            {"name": "🛑 !stopbalapan & !stopwerewolfaudio", "value": "Hentikan sesi balapan kuda atau matikan suara latar Werewolf."},
            {"name": "🔗 !sambung (alias !sk)", "value": "Tantangan sambung suku kata berantai tanpa putus."},
            {"name": "🗳️ !siapapaling (alias !sipaling)", "value": "Tebak bareng siapa orang di server yang paling cocok dengan pertanyaan."},
            {"name": "🧩 !tebakemoji & !hintemoji", "value": "Tebak frasa kata dari susunan petunjuk emoji."},
            {"name": "🔤 !susunkata (alias !acak)", "value": "Susun kembali huruf yang diacak menjadi kata yang tepat."},
            {"name": "🔬 !kuisipa", "value": "Kuis tebak-tebakan sains dan pengetahuan umum berhadiah koin."},
            {"name": "🪢 !hangman", "value": "Tebak kata rahasia huruf demi huruf sebelum kesempatan habis."},
            {"name": "🕵️ !siapaaku", "value": "Tebak tokoh, barang, atau profesi dari petunjuk yang diberikan bertahap."},
            {"name": "⚡ !hitungcepat", "value": "Adu cepat menjawab soal matematika sederhana."},
            {"name": "🤔 !pernahgak", "value": "Game pengakuan seru pakai tombol interaktif."},
            {"name": "🎭 !matamata, !tuduh, !ungkap_lokasi", "value": "Cari tahu siapa mata-mata yang menyamar di antara pemain."},
            {"name": "🎵 !kuismusik & !jawab", "value": "Tebak judul lagu dari lirik atau potongan audio."},
            {"name": "🧹 !stopgame", "value": "Reset dan bersihkan status game jika terjadi kendala di channel."}
        ]
    },
    "social": {
        "title": "📡 Notifikasi YouTube & TikTok",
        "desc": "Pantau channel YouTube dan akun TikTok agar otomatis dapat pemberitahuan saat ada konten baru:",
        "color": 0xE67E22,
        "fields": [
            {"name": "📺 /yt add <channel_id> <channel_tujuan>", "value": "Daftarkan channel YouTube untuk dipantau video baru dan livenya."},
            {"name": "📺 /yt remove <channel_id> & /yt list", "value": "Hapus atau lihat daftar semua channel YouTube yang sedang dipantau."},
            {"name": "📺 /yt check", "value": "Periksa langsung apakah ada upload terbaru di channel YouTube yang didaftarkan."},
            {"name": "📺 /yt test <channel_id>", "value": "Kirim contoh tampilan kartu notifikasi YouTube ke channel tujuan."},
            {"name": "📺 /yt setchannel, /yt setmention, /yt toggle", "value": "Ganti channel tujuan, role yang dimention, atau matikan sementara notifikasi."},
            {"name": "🎵 /tt add <username> <channel_tujuan>", "value": "Daftarkan akun TikTok untuk dipantau video baru dan siaran langsungnya."},
            {"name": "🎵 /tt remove <username> & /tt list", "value": "Hapus atau lihat daftar semua akun TikTok yang sedang dipantau."},
            {"name": "🎵 /tt check", "value": "Periksa langsung pembaruan video dari akun TikTok yang didaftarkan."},
            {"name": "🎵 /tt test <username>", "value": "Kirim contoh tampilan kartu notifikasi TikTok ke channel tujuan."},
            {"name": "🎵 /tt setchannel, /tt setmention, /tt toggle", "value": "Ganti channel tujuan notifikasi TikTok atau atur role mention."},
            {"name": "⚙️ /checker list & /checker check", "value": "Lihat rangkuman semua target pantauan YouTube & TikTok serta jalankan pengecekan."},
            {"name": "⚙️ /checker interval <menit>", "value": "Atur seberapa sering bot mengecek konten baru secara otomatis."},
            {"name": "⚙️ /checker cache & /checker resetcache", "value": "Cek atau bersihkan catatan cache video terakhir yang sudah dikirim."},
            {"name": "📡 !config, !addpath, !removepath", "value": "Atur jalur pengiriman feed notifikasi (Owner)."},
            {"name": "📦 !checkcache & !resetcache", "value": "Cek atau bersihkan antrean feed notifikasi (Owner)."}
        ]
    },
    "ai": {
        "title": "🤖 Asisten AI & Keamanan Link",
        "desc": "Tanya jawab cerdas, panduan pemakaian bot, dan perlindungan otomatis dari link berbahaya:",
        "color": 0x1ABC9C,
        "fields": [
            {"name": "🧠 Tanya Jawab Bot", "value": "Tanya apa saja seputar cara pakai bot, izin admin, atau bantuan umum. Cukup tag `@RTMBOT <pertanyaan>`, balas pesan bot, atau gunakan awalan `!<pertanyaan>`."},
            {"name": "🛡️ /aifilter tambah_whitelist <domain>", "value": "Daftarkan website yang aman agar link-nya tidak terhapus bot (contoh: `/aifilter tambah_whitelist domain:example.com`)."},
            {"name": "🛡️ /aifilter hapus_whitelist <domain>", "value": "Hapus website dari daftar aman."},
            {"name": "🚫 /aifilter tambah_tld <tld>", "value": "Blokir ekstensi domain mencurigakan secara otomatis (contoh: `/aifilter tambah_tld tld:.xyz`)."},
            {"name": "🚫 /aifilter hapus_tld <tld>", "value": "Hapus ekstensi domain dari daftar pemblokiran."},
            {"name": "🛑 /aifilter tambah_kata & hapus_kata", "value": "Atur kata-kata terlarang yang tidak boleh dikirim di server."},
            {"name": "🖼️ /aifilter blokir_gambar <deskripsi>", "value": "Cegah kiriman gambar berbahaya atau phising secara otomatis."},
            {"name": "🛡️ /cyber_toggle", "value": "Aktifkan atau matikan proteksi keamanan link dan filter otomatis."},
            {"name": "🤖 /ai ngobrol, /ai selesai, /ai reset", "value": "Mulai obrolan santai tanpa perlu tag bot berulang kali, atau akhiri sesi obrolan."},
            {"name": "🤖 /ai rangkum [jumlah]", "value": "Rangkum obrolan chat terbaru di channel ini secara singkat."},
            {"name": "🎭 /aisifat atur_sifat & /aisifat hapus_sifat", "value": "Atur gaya bicara atau karakter respons asisten."},
            {"name": "🎭 /aisifat ngambek & /aisifat patuh", "value": "Pilihan mode respon khusus untuk seru-seruan."},
            {"name": "📚 /aimemori pelajari, ingatan, lupakan", "value": "Simpan catatan penting atau bersihkan ingatan jangka panjang asisten di server."},
            {"name": "⚙️ /aiconfig set_learn_channel & reset_memori", "value": "Tentukan channel tempat asisten belajar informasi server (Staf)."},
            {"name": "🧹 !cleardm (alias !clear)", "value": "Bersihkan riwayat chat bot di pesan pribadi (DM) dan mulai percakapan baru dari awal."}
        ]
    },
    "fun": {
        "title": "🔮 Hiburan, Zodiak & Curhat",
        "desc": "Menu seru-seruan bareng teman server, cek ramalan santai, dan kirim pesan rahasia:",
        "color": 0xE91E63,
        "fields": [
            {"name": "🔮 /tarot", "value": "Buka 3 kartu tarot untuk melihat gambaran masa lalu, sekarang, dan waktu yang akan datang."},
            {"name": "♈ /zodiak <nama/tanggal>", "value": "Cek peruntungan bintang, suasana hati, dan karier hari ini."},
            {"name": "🔢 /lifepath <tanggal_lahir>", "value": "Hitung angka kepribadian dan potensi diri berdasarkan tanggal lahir."},
            {"name": "🔥 /roast [user]", "value": "Kirim candaan sindiran lucu dan mengena ke teman."},
            {"name": "💘 /ship <user1> [user2]", "value": "Hitung tingkat kecocokan persentase jodoh antara dua orang."},
            {"name": "🎱 /8ball <pertanyaan>", "value": "Tanya ke bola ajaib untuk dapat jawaban acak yang tak terduga."},
            {"name": "🤫 /confess", "value": "Buka formulir rahasia untuk kirim curhatan anonim ke channel confess tanpa ketahuan."},
            {"name": "⚙️ /confess_setup & /set_confess_channel", "value": "Tentukan channel untuk menampung kiriman curhat rahasia (Admin)."},
            {"name": "🎭 !pranknama <member> <nama> & !resetnama", "value": "Ganti nama teman untuk iseng atau kembalikan ke nama aslinya."}
        ]
    },
    "voice_util": {
        "title": "🎙️ Voice Otomatis & Utilitas",
        "desc": "Kamar suara privat otomatis dan aneka info praktis seputar akun serta server:",
        "color": 0x34495E,
        "fields": [
            {"name": "🔊 Kamar Voice Otomatis", "value": "Cukup klik channel pemicu untuk dibuatkan kamar voice privat sendiri."},
            {"name": "🔒 /vc lock & /vc unlock", "value": "Kunci kamar suara agar orang lain tidak bisa masuk, atau buka kembali."},
            {"name": "👥 /vc limit <jumlah>", "value": "Batasi jumlah orang yang boleh bergabung di kamarmu (isi 0 untuk bebas)."},
            {"name": "✏️ /vc rename <nama_baru>", "value": "Ubah nama kamar suara pribadimu sesuka hati."},
            {"name": "👢 /vc kick <member>", "value": "Keluarkan orang tertentu dari kamar suara pribadimu."},
            {"name": "🔑 /vc grant & /vc revoke", "value": "Beri atau cabut izin masuk khusus untuk teman tertentu."},
            {"name": "👑 /vc transfer <member>", "value": "Serahkan kepemilikan kamar suara kepada teman yang ada di dalam kamar."},
            {"name": "🗑️ /vc delete", "value": "Tutup dan hapus langsung kamar suara pribadimu."},
            {"name": "🛠️ /vcadmin settrigger & setcat", "value": "Atur channel pemicu dan kategori untuk kamar suara otomatis (Admin)."},
            {"name": "📊 /act", "value": "Lihat rangkuman aktivitas voice, streaming, dan bermain game di server."},
            {"name": "💬 /resq (alias !resq, !sendquote)", "value": "Kirim kutipan kata-kata bijak berdesain rapi."},
            {"name": "📜 /setchannelq, /listquotes, /deletequote", "value": "Atur channel kutipan dan kelola daftar kutipan harian server (Admin)."},
            {"name": "📝 /tulis <nama> <teks>", "value": "Ubah teks kamu jadi gambar lembaran buku bergaris seperti tulisan tangan."},
            {"name": "👤 /user [user]", "value": "Lihat kartu profil akun, tanggal pembuatan akun, dan role yang dimiliki."},
            {"name": "🖼️ /avatar [user]", "value": "Ambil gambar foto profil akun dalam ukuran besar dan jernih."},
            {"name": "❓ /faq", "value": "Buka daftar pertanyaan yang sering ditanyakan seputar server."},
            {"name": "🏛️ /getserverasset", "value": "Download logo jernih dan gambar banner resmi server."},
            {"name": "🆔 /getroleid (alias !idrole, !roleid)", "value": "Pilih role dari menu dropdown untuk menyalin ID role tanpa perlu tag/mention."},
            {"name": "⚙️ /set_gender", "value": "Buka formulir pengaturan role gender otomatis (Admin)."}
        ]
    },
    "webhook": {
        "title": "🪝 Pesan Siaran & Jadwal",
        "desc": "Kirim pesan siaran pengumuman server, jadwal pengiriman, dan kelola webhook:",
        "color": 0x16A085,
        "fields": [
            {"name": "🪝 !send_webhook <target_url> (alias !swh)", "value": "Kirim pesan siaran berformat kartu rapi ke alamat webhook."},
            {"name": "✏️ !edit_broadcast <message_id> (alias !eb)", "value": "Edit pesan siaran yang sudah pernah dikirimkan."},
            {"name": "📢 !announcement <channel> <pesan>", "value": "Kirim siaran pengumuman resmi ke channel pilihan."},
            {"name": "🖼️ !send_media <target_url> <media_url>", "value": "Kirim lampiran media beresolusi jernih ke webhook."},
            {"name": "⏰ !schedule <waktu> <pesan>", "value": "Atur jadwal agar pesan terkirim otomatis di waktu tertentu."},
            {"name": "📋 !list_schedules", "value": "Lihat daftar jadwal kirim pesan yang sedang aktif."},
            {"name": "💾 !backup_config & !load_config", "value": "Simpan atau pulihkan cadangan pengaturan pesan server."},
            {"name": "🔗 !setwebhook & !delwebhook", "value": "Hubungkan atau lepas tautan cermin pesan otomatis antar channel."},
            {"name": "🧪 !teswebhook [pesan]", "value": "Kirim pesan uji coba untuk memastikan alamat webhook aktif."}
        ]
    }
}

class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Buka Katalog Perintah Web", url="https://rtmbot.biz.id/commands", style=discord.ButtonStyle.link, emoji="📖"))
        self.add_item(discord.ui.Button(label="Website Resmi", url="https://rtmbot.biz.id", style=discord.ButtonStyle.link, emoji="🌐"))

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

    @commands.hybrid_command(name="help", aliases=["h", "bantuan"], description="Katalog lengkap seluruh perintah bot di website")
    async def help_command(self, ctx: commands.Context):
        title = "📖 Panduan & Katalog Perintah RTMBOT"
        description = (
            "Seluruh dokumentasi dan panduan pemakaian **230 perintah aktif** kini dapat kamu akses langsung melalui situs web resmi kami:\n\n"
            "👉 **https://rtmbot.biz.id/commands**\n\n"
            "**Fitur Katalog Dokumentasi:**\n"
            "• **Pencarian Instan**: Cari nama perintah, alias, atau parameter secara cepat.\n"
            "• **Filter Lengkap**: Kategori Moderasi, Keuangan Kas Riil, Kamar Suara, Minigames, dll.\n"
            "• **Salin Syntax 1-Klik**: Salin format perintah langsung ke clipboard.\n"
            "• **Akses Ringan**: Nyaman dibuka melalui HP maupun PC."
        )
        buttons = [
            {
                "label": "Buka Katalog Perintah Web",
                "style": 5,
                "url": "https://rtmbot.biz.id/commands",
                "emoji": "📖"
            },
            {
                "label": "Website Resmi",
                "style": 5,
                "url": "https://rtmbot.biz.id",
                "emoji": "🌐"
            }
        ]
        view = HelpView()

        embed = discord.Embed(
            title=title,
            description=description,
            color=0x238636
        )
        embed.set_footer(text="RTMBOT • Dokumentasi & Direktori Perintah Resmi")

        card = build_v2_card(
            title=title,
            description=description,
            color=0x238636,
            buttons=buttons,
            footer="RTMBOT • Dokumentasi & Direktori Perintah Resmi"
        )

        if ctx.interaction:
            await send_v2_interaction(self.bot, ctx.interaction, card, ephemeral=False)
        else:
            resp = await send_v2_message(self.bot, ctx.channel.id, [card])
            if not resp or (isinstance(resp, dict) and "error_msg" in resp):
                await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(InsightHub(bot))
