import discord
from discord.ext import commands, tasks
import json
import random
import asyncio
import os
import aiohttp
from io import BytesIO
from datetime import datetime, time, timedelta
import pytz

def load_json_from_root(file_path):
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    full_path = os.path.join(base_dir, file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        if 'config.json' in file_path:
            return {'last_spy_id': None}
        if any(key in file_path for key in ['bank_data.json', 'level_data.json', 'protected_users.json', 'sick_users_cooldown.json', 'game_channels.json']):
            return {}
        if any(key in file_path for key in ['monsters', 'anomalies', 'medicines', 'siapakah_aku', 'pernah_gak_pernah', 'hitung_cepat', 'mata_mata_locations', 'deskripsi_tebak', 'perang_otak', 'cerita_pembuka', 'teka_teki_harian', 'siapa_paling']):
            return []
        if 'donation_buttons.json' in file_path:
            return []
        return {}

def save_json_to_root(data, file_path):
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    full_path = os.path.join(base_dir, file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    temp_path = f"{full_path}.tmp"
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    os.replace(temp_path, full_path)


class DonationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.load_donation_buttons()

    def load_donation_buttons(self):
        donation_buttons_data = load_json_from_root('data/donation_buttons.json')
        if not donation_buttons_data:
            default_buttons = [
                {"label": "Dukung via Bagi-Bagi!", "url": "https://bagibagi.co/Rh7155"},
                {"label": "Donasi via Saweria!", "url": "https://saweria.co/RH7155"}
            ]
            donation_buttons_data = default_buttons
        for button_info in donation_buttons_data:
            if "label" in button_info and "url" in button_info:
                button = discord.ui.Button(
                    label=button_info["label"],
                    style=discord.ButtonStyle.link,
                    url=button_info["url"]
                )
                self.add_item(button)


class GameCatalogView(discord.ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=90)
        self.cog = cog
        self.ctx = ctx

        options = [
            discord.SelectOption(label="Sambung Kata", value="sambung", description="Menyambung 2 suku kata berantai dengan multiplier combo", emoji="🔗"),
            discord.SelectOption(label="Si Paling...", value="siapapaling", description="Party game voting opini 'Si Paling' terheboh di server", emoji="🗳️"),
            discord.SelectOption(label="Tebak Emoji", value="tebakemoji", description="Tebak kata/frasa berdasarkan deretan emoji", emoji="🧩"),
            discord.SelectOption(label="Susun Kata", value="susunkata", description="Susun kembali kata acak (Anagram) secepatnya", emoji="🔤"),
            discord.SelectOption(label="Kuis IPA & Sains", value="kuisipa", description="Kuis tebak istilah biologi, kimia, dan fisika", emoji="🔬"),
            discord.SelectOption(label="Hangman", value="hangman", description="Tebak kata rahasia huruf demi huruf dalam 10 ronde", emoji="🪢"),
            discord.SelectOption(label="Siapa Aku?", value="siapaaku", description="Kuis detektif tebak tokoh atau benda dari petunjuk bertahap", emoji="🕵️"),
            discord.SelectOption(label="Hitung Cepat", value="hitungcepat", description="Adu cepat dan tepat perhitungan matematika dasar", emoji="⚡"),
            discord.SelectOption(label="Pernah Gak Pernah", value="pernahgak", description="Game kejujuran Never Have I Ever via tombol interaktif", emoji="🤔"),
            discord.SelectOption(label="Mata-Mata (Spyfall)", value="matamata", description="Game peran rahasia mengungkap mata-mata di antara pemain", emoji="🎭"),
            discord.SelectOption(label="Kuis Musik", value="kuismusik", description="Kuis tebak trivia lagu & musik di Voice Channel", emoji="🎤"),
        ]

        select = discord.ui.Select(
            placeholder="Pilih game untuk melihat panduan & command...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="game_catalog_select"
        )
        select.callback = self.select_callback
        self.add_item(select)

        reset_btn = discord.ui.Button(label="Reset Channel Game", style=discord.ButtonStyle.secondary, emoji="🧹", custom_id="game_catalog_reset")
        reset_btn.callback = self.reset_callback
        self.add_item(reset_btn)

    async def select_callback(self, interaction: discord.Interaction):
        val = interaction.data['values'][0]
        catalog_info = {
            "sambung": {
                "title": "🔗 Sambung Kata (Multiplayer)",
                "cmd": "`!sambung` (alias: `!sk`, `!sambungkata`)",
                "rules": "1. Pemain bergantian menyambung kata dari **2 huruf terakhir** kata sebelumnya.\n2. Waktu berpikir **20 detik** per giliran.\n3. Berhasil menyambung kata berturut-turut akan memicu **Combo Multiplier** (hingga 2x reward)!\n4. Pemain yang gagal menjawab akan tereliminasi hingga tersisa 1 juara.",
                "reward": "50-150 RSWN & 100-300 EXP (Tergantung Combo)",
                "color": 0xe91e63
            },
            "siapapaling": {
                "title": "🗳️ Si Paling... (Party Voting Game)",
                "cmd": "`!siapapaling` (alias: `!paling`, `!vote`, `!wholikely`)",
                "rules": "1. Minimal 2 pemain bergabung di lobby.\n2. Bot memberikan pertanyaan lucu/relatable seputar tongkrongan.\n3. Semua pemain memilih 1 orang yang paling cocok secara rahasia via tombol/menu.\n4. Bot merekap hasil voting dengan grafik bar suara dan menobatkan 'Si Paling...' ronde tersebut!",
                "reward": "Juara Voting: 60 RSWN & 120 EXP | Partisipan: 25 RSWN & 50 EXP",
                "color": 0x9b59b6
            },
            "tebakemoji": {
                "title": "🧩 Tebak Emoji & Frasa",
                "cmd": "`!tebakemoji` (alias: `!emoji`, `!tebakgambar`)",
                "rules": "1. Bot menampilkan kombinasi emoji misterius.\n2. Tebak makna kata atau frasa yang dimaksud dalam 60 detik.\n3. Tersedia bantuan hint via `!hintemoji`.",
                "reward": "30 RSWN & 60 EXP per jawaban benar",
                "color": 0x8e44ad
            },
            "susunkata": {
                "title": "🔤 Susun Kata (Anagram)",
                "cmd": "`!susunkata` (alias: `!acak`)",
                "rules": "1. Bot mengacak huruf-huruf dari suatu kata.\n2. Tebak kata aslinya secepat mungkin berdasarkan kategori dan kisi-kisi.\n3. Terdiri dari 10 ronde seru.",
                "reward": "50 RSWN & 100 EXP per ronde",
                "color": 0x2ecc71
            },
            "kuisipa": {
                "title": "🔬 Kuis IPA & Sains",
                "cmd": "`!kuisipa` (alias: `!ipa`)",
                "rules": "1. Bot menyajikan teka-teki istilah ilmiah/sains.\n2. Jawab dengan benar berdasarkan kisi-kisi dalam batas waktu 30 detik.",
                "reward": "50 RSWN & 100 EXP per ronde",
                "color": 0x1abc9c
            },
            "hangman": {
                "title": "🪢 Hangman (Tebak Kata)",
                "cmd": "`!hangman` (alias: `!tebakkata`)",
                "rules": "1. Bot memberikan jumlah huruf yang disembunyikan beserta kategori dan petunjuk.\n2. Tebak kata lengkapnya sebelum waktu 120 detik habis.\n3. Tersedia bantuan jawaban via `!bantuanhangman`.",
                "reward": "30 RSWN & 60 EXP per ronde",
                "color": 0x34495e
            },
            "siapaaku": {
                "title": "🕵️ Siapa Aku? (Tebak Karakter)",
                "cmd": "`!siapaaku` (alias: `!tebaksiapa`)",
                "rules": "1. Bot memberikan 3 petunjuk bertahap (setiap 10 detik).\n2. Setiap pemain memiliki maksimal 2 kesempatan menebak per petunjuk.\n3. Terdiri dari 10 ronde teka-teki tokoh, hewan, dan objek.",
                "reward": "50 RSWN & 100 EXP per tebakan tepat",
                "color": 0x3498db
            },
            "hitungcepat": {
                "title": "⚡ Hitung Cepat (Matematika)",
                "cmd": "`!hitungcepat` (alias: `!math`, `!hitung`)",
                "rules": "1. Bot menyajikan 10 soal perhitungan aritmatika dasar.\n2. Pemain pertama yang menjawab angka dengan benar dalam 15 detik mendapatkan poin.",
                "reward": "50 RSWN & 100 EXP per soal benar",
                "color": 0xe74c3c
            },
            "pernahgak": {
                "title": "🤔 Pernah Gak Pernah (Never Have I Ever)",
                "cmd": "`!pernahgak` (alias: `!nhie`)",
                "rules": "1. Bot membagikan 10 pernyataan unik/lucu.\n2. Jawab jujur menggunakan tombol interaktif [Pernah] atau [Gak Pernah].\n3. Ringkasan hasil kejujuran akan ditampilkan di akhir sesi.",
                "reward": "Hadiah koin RSWN & EXP partisipasi per ronde",
                "color": 0xf1c40f
            },
            "matamata": {
                "title": "🎭 Mata-Mata (Spyfall)",
                "cmd": "`!matamata` (alias: `!spyfall`)",
                "rules": "1. Minimal 3 orang di Voice Channel.\n2. Semua pemain mendapat lokasi rahasia via DM, KECUALI 1 orang yang menjadi Mata-Mata.\n3. Diskusi selama 5 menit untuk mencari siapa mata-matanya via `!tuduh @user`.",
                "reward": "Kemenangan tim Warga / Mata-Mata: Hadiah besar RSWN & EXP",
                "color": 0x7289da
            },
            "kuismusik": {
                "title": "🎤 Kuis Musik (Voice Trivia)",
                "cmd": "`!kuismusik` (alias: `!musicquiz`)",
                "rules": "1. Pemain berada di Voice Channel.\n2. Bot memberikan pertanyaan pilihan ganda (A/B/C/D) via tombol interaktif.\n3. Jawaban benar tercepat mengumpulkan skor dan bonus hadiah.",
                "reward": "Top 3 Leaderboard mendapat bonus RSWN & EXP tinggi",
                "color": 0x1db954
            }
        }

        info = catalog_info.get(val)
        if not info:
            return await interaction.response.send_message("Informasi game tidak ditemukan.", ephemeral=True)

        embed = discord.Embed(title=info["title"], color=info["color"])
        embed.add_field(name="⌨️ Perintah", value=info["cmd"], inline=False)
        embed.add_field(name="📜 Aturan Main", value=info["rules"], inline=False)
        embed.add_field(name="💰 Hadiah", value=info["reward"], inline=False)
        embed.set_footer(text="Gunakan !stopgame jika ada game yang macet di channel ini.")
        await interaction.response.edit_message(embed=embed, view=self)

    async def reset_callback(self, interaction: discord.Interaction):
        await self.cog.end_game_cleanup(interaction.channel_id, interaction.channel)
        embed = discord.Embed(
            title="🧹 Status Game Direset",
            description=f"Status permainan di channel {interaction.channel.mention} telah berhasil dibersihkan!\nSekarang kamu bisa memulai permainan baru.",
            color=0x2ecc71
        )
        await interaction.response.send_message(embed=embed, ephemeral=False)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class StartGameView(discord.ui.View):
    def __init__(self, cog, channel_id, author_id, on_start, timeout=60):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.channel_id = channel_id
        self.author_id = author_id
        self.on_start = on_start
        self.started = False

    @discord.ui.button(label="Mulai Sekarang", style=discord.ButtonStyle.primary, emoji="▶️")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Hanya pemanggil perintah yang bisa menekan tombol mulai.", ephemeral=True)
        self.started = True
        self.stop()
        try:
            await interaction.message.delete()
        except Exception:
            pass
        await self.on_start()

    async def on_timeout(self):
        if not self.started:
            self.cog.active_games.discard(self.channel_id)


class SambungKataLobbyView(discord.ui.View):
    def __init__(self, cog, channel_id, host: discord.Member, on_start, timeout=45):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.channel_id = channel_id
        self.host = host
        self.on_start = on_start
        self.players = {host.id: host}
        self.started = False

        if host.voice and host.voice.channel:
            for member in host.voice.channel.members:
                if not member.bot:
                    self.players[member.id] = member

    @discord.ui.button(label="Ikut Bermain", style=discord.ButtonStyle.success, emoji="⚔️")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.players:
            return await interaction.response.send_message("Kamu sudah bergabung di dalam lobby!", ephemeral=True)
        self.players[interaction.user.id] = interaction.user
        player_list = ", ".join([p.mention for p in self.players.values()])
        embed = interaction.message.embeds[0]
        embed.set_field_at(0, name=f"👥 Pemain Bergabung ({len(self.players)})", value=player_list, inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Mulai Game", style=discord.ButtonStyle.primary, emoji="▶️")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id and not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("Hanya host atau moderator yang bisa memulai permainan.", ephemeral=True)
        if len(self.players) < 2:
            return await interaction.response.send_message("⚠️ Permainan Sambung Kata membutuhkan minimal 2 pemain!", ephemeral=True)
        self.started = True
        self.stop()
        try:
            await interaction.message.delete()
        except Exception:
            pass
        await self.on_start(list(self.players.values()))

    async def on_timeout(self):
        if not self.started:
            self.cog.active_games.discard(self.channel_id)


class SiPalingLobbyView(discord.ui.View):
    def __init__(self, cog, channel_id, host: discord.Member, on_start, timeout=45):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.channel_id = channel_id
        self.host = host
        self.on_start = on_start
        self.players = {host.id: host}
        self.started = False

        if host.voice and host.voice.channel:
            for member in host.voice.channel.members:
                if not member.bot and len(self.players) < 25:
                    self.players[member.id] = member

    @discord.ui.button(label="Ikut Main", style=discord.ButtonStyle.success, emoji="🙋")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.players:
            return await interaction.response.send_message("Kamu sudah bergabung dalam permainan!", ephemeral=True)
        if len(self.players) >= 25:
            return await interaction.response.send_message("Lobby sudah penuh (maksimal 25 pemain).", ephemeral=True)
        self.players[interaction.user.id] = interaction.user
        player_list = ", ".join([p.mention for p in self.players.values()])
        embed = interaction.message.embeds[0]
        embed.set_field_at(0, name=f"👥 Pemain Terdaftar ({len(self.players)})", value=player_list, inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Mulai Voting", style=discord.ButtonStyle.primary, emoji="▶️")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id and not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("Hanya pemanggil game atau moderator yang bisa memulai.", ephemeral=True)
        if len(self.players) < 2:
            return await interaction.response.send_message("⚠️ Butuh minimal 2 pemain untuk memulai voting!", ephemeral=True)
        self.started = True
        self.stop()
        try:
            await interaction.message.delete()
        except Exception:
            pass
        await self.on_start(list(self.players.values()))

    async def on_timeout(self):
        if not self.started:
            self.cog.active_games.discard(self.channel_id)


class SiPalingVoteView(discord.ui.View):
    def __init__(self, players, timeout=25):
        super().__init__(timeout=timeout)
        self.players = players
        self.votes = {}

        options = [
            discord.SelectOption(
                label=p.display_name[:25],
                value=str(p.id),
                description=f"Pilih {p.display_name[:20]} sebagai 'Si Paling...' ronde ini",
                emoji="👉"
            )
            for p in players[:25]
        ]

        select = discord.ui.Select(
            placeholder="🗳️ Pilih pemain yang paling cocok...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="sipaling_vote_select"
        )
        select.callback = self.vote_callback
        self.add_item(select)

    async def vote_callback(self, interaction: discord.Interaction):
        voter_id = interaction.user.id
        target_id = int(interaction.data['values'][0])
        target_member = next((p for p in self.players if p.id == target_id), None)
        target_name = target_member.display_name if target_member else "Pemain Terpilih"

        self.votes[voter_id] = target_id
        await interaction.response.send_message(f"✅ Suaramu untuk **{target_name}** telah dicatat secara rahasia!", ephemeral=True)


class PernahGakView(discord.ui.View):
    def __init__(self, participants, timeout=15):
        super().__init__(timeout=timeout)
        self.participants = {p.id: p for p in participants}
        self.answers = {}

    @discord.ui.button(label="Pernah", style=discord.ButtonStyle.success, emoji="✅")
    async def pernah_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.answers[interaction.user.id] = "Pernah"
        await interaction.response.send_message("✅ Jawabanmu: **Pernah**!", ephemeral=True)

    @discord.ui.button(label="Gak Pernah", style=discord.ButtonStyle.danger, emoji="❌")
    async def gak_pernah_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.answers[interaction.user.id] = "Gak Pernah"
        await interaction.response.send_message("❌ Jawabanmu: **Gak Pernah**!", ephemeral=True)


class QuizButton(discord.ui.Button):
    def __init__(self, label, option_letter, parent_view):
        super().__init__(label=f"{option_letter}. {label}", style=discord.ButtonStyle.primary)
        self.parent_view = parent_view
        self.option_letter = option_letter

    async def callback(self, interaction: discord.Interaction):
        if not hasattr(self.parent_view, "participants") or interaction.user.id not in self.parent_view.participants:
            await interaction.response.send_message("Ini bukan pertanyaan untukmu!", ephemeral=True)
            return
        await interaction.response.defer()
        is_correct = self.option_letter.upper() == self.parent_view.correct_answer.upper()
        await self.parent_view.on_answer(interaction, is_correct)
        for child in self.parent_view.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self.parent_view)
        except Exception:
            pass
        self.parent_view.stop()


class QuizView(discord.ui.View):
    def __init__(self, options, correct_answer, participants, on_answer):
        super().__init__(timeout=15)
        self.correct_answer = correct_answer
        self.participants = participants
        self.on_answer = on_answer
        letters = ["A", "B", "C", "D"]
        for i, option in enumerate(options[:4]):
            self.add_item(QuizButton(option, letters[i], self))


class ArcadeMinigames(commands.Cog, name="Arcade Mini-Games"):
    DONATION_BUTTONS_FILE = 'data/donation_buttons.json'

    def __init__(self, bot):
        self.bot = bot
        self.active_emoji_games = {}
        self.active_music_quizzes = {}
        self.active_hangman_games = {}
        self.active_resacak_games = {}
        self.active_resipa_games = {}
        self.active_sambung_games = {}
        self.active_voting_games = {}
        self.active_games = set()
        self.spyfall_game_states = {}
        self.session_scores = {}
        self.bank_data = load_json_from_root('data/bank_data.json')
        self.level_data = load_json_from_root('data/level_data.json')
        self.allowed_channels = load_json_from_root('data/game_channels.json')
        self.config_data = load_json_from_root('data/config.json')
        self.last_spy_id = self.config_data.get('last_spy_id', None)

        self.emoji_questions = self.load_data_file('data/emoji_questions.json', "questions")
        self.music_questions = self.load_data_file('data/questions_music.json', "questions")
        if not self.music_questions:
            self.music_questions = self.load_data_file('questions.json', "questions")
        self.hangman_questions = self.load_data_file('data/questions_hangman.json')
        self.resacak_questions = self.load_data_file('data/questions_hangman.json')
        self.resipa_questions = self.load_data_file('data/questions_resipa.json')
        self.sambung_kata_words = self.load_data_file('data/sambung_kata_words.json')
        self.siapakah_aku_data = load_json_from_root('data/siapakah_aku.json')
        self.pernah_gak_pernah_data = load_json_from_root('data/pernah_gak_pernah.json')
        self.hitung_cepat_data = load_json_from_root('data/hitung_cepat.json')
        self.mata_mata_locations = load_json_from_root('data/mata_mata_locations.json')
        self.deskripsi_data = load_json_from_root('data/deskripsi_tebak.json')
        self.perang_otak_data = load_json_from_root('data/perang_otak.json')
        self.cerita_pembuka_data = load_json_from_root('data/cerita_pembuka.json')
        self.tekateki_harian_data = load_json_from_root('data/teka_teki_harian.json')
        self.siapa_paling_questions = load_json_from_root('data/siapa_paling.json')

        self.bantuan_price_emoji = 35
        self.reward_per_correct_emoji = 30
        self.time_limit_emoji = 60
        self.bantuan_price_hangman = 40
        self.reward_per_correct_hangman = 30
        self.resacak_reward = {"rsw": 50, "exp": 100}
        self.resipa_reward = {"rsw": 50, "exp": 100}
        self.sambung_kata_winner_reward = {"rsw": 60, "exp": 120}
        self.voting_winner_reward = {"rsw": 60, "exp": 120}
        self.voting_participant_reward = {"rsw": 25, "exp": 50}
        self.resacak_time_limit = 30
        self.resipa_time_limit = 30
        self.sambung_kata_time_limit = 20
        self.reward = {"rsw": 50, "exp": 100}

        self.daily_puzzle = None
        self.daily_puzzle_solvers = set()
        self.daily_puzzle_channel_id = int(os.getenv("DAILY_PUZZLE_CHANNEL_ID", 765140300145360896))
        self.quiz_attempts_per_question = {}
        self.cooldown_users = {}

    def cog_unload(self):
        if hasattr(self, 'post_daily_puzzle') and self.post_daily_puzzle.is_running():
            self.post_daily_puzzle.cancel()

    def load_data_file(self, file_path, key=None):
        data = load_json_from_root(file_path)
        if key:
            return data.get(key, [])
        return data

    def get_anomaly_multiplier(self):
        try:
            dunia_cog = self.bot.get_cog('DuniaHidup')
            if dunia_cog and hasattr(dunia_cog, 'active_anomaly') and isinstance(dunia_cog.active_anomaly, dict):
                if dunia_cog.active_anomaly.get('type') == 'exp_boost':
                    return dunia_cog.active_anomaly.get('effect', {}).get('multiplier', 1)
        except Exception:
            pass
        return 1

    async def end_game_cleanup(self, channel_id, channel_obj=None, game_type=None):
        """Memastikan channel_id selalu dibersihkan dari active_games."""
        if channel_id:
            self.active_games.discard(channel_id)
        if channel_obj and hasattr(channel_obj, 'id'):
            self.active_games.discard(channel_obj.id)
            if hasattr(channel_obj, 'guild'):
                self.active_music_quizzes.pop(channel_obj.guild.id, None)

        if channel_id in self.spyfall_game_states:
            spy_member = self.spyfall_game_states[channel_id].get('spy')
            self.last_spy_id = spy_member.id if spy_member else None
            self.config_data['last_spy_id'] = self.last_spy_id
            save_json_to_root(self.config_data, 'data/config.json')
            self.spyfall_game_states.pop(channel_id, None)

        if channel_id in self.quiz_attempts_per_question:
            self.quiz_attempts_per_question.pop(channel_id, None)

        users_in_cooldown = [uid for uid, c_time in self.cooldown_users.items() if c_time > datetime.now()]
        for uid in users_in_cooldown:
            self.cooldown_users.pop(uid, None)

        for g_dict in [self.active_emoji_games, self.active_hangman_games, self.active_resacak_games,
                       self.active_resipa_games, self.active_sambung_games, self.active_voting_games]:
            g_dict.pop(channel_id, None)

        if channel_obj:
            self.game_completion_count = getattr(self, 'game_completion_count', 0) + 1
            if self.game_completion_count % 4 == 0:
                donation_message = (
                    "🎮 **Permainan Telah Usai!** Terima kasih sudah bermain bersama kami.\n\n"
                    "Apakah kamu menikmati keseruan ini? Dukung terus pengembangan bot agar kami "
                    "bisa terus menghadirkan minigames yang makin asyik dan menantang! 🙏"
                )
                try:
                    await channel_obj.send(donation_message, view=DonationView())
                except Exception:
                    pass

    async def give_rewards_with_bonus_check(self, user: discord.Member, channel: discord.TextChannel, reward_base: dict = None):
        if reward_base is None:
            reward_base = self.reward.copy()

        anomaly_multiplier = self.get_anomaly_multiplier()
        final_rsw = int(reward_base.get('rsw', 0) * anomaly_multiplier)
        final_exp = int(reward_base.get('exp', 0) * anomaly_multiplier)

        user_id_str, guild_id_str = str(user.id), str(user.guild.id)
        self.bank_data = load_json_from_root('data/bank_data.json')
        self.level_data = load_json_from_root('data/level_data.json')

        self.bank_data.setdefault(user_id_str, {'balance': 0, 'debt': 0})['balance'] += final_rsw
        user_level_data = self.level_data.setdefault(guild_id_str, {}).setdefault(user_id_str, {'exp': 0, 'level': 1})
        user_level_data['exp'] += final_exp

        save_json_to_root(self.bank_data, 'data/bank_data.json')
        save_json_to_root(self.level_data, 'data/level_data.json')

        if anomaly_multiplier > 1 and channel:
            await channel.send(f"✨ **BONUS ANOMALI!** {user.mention} mendapatkan hadiah berlipat ganda ({final_rsw} RSWN & {final_exp} EXP)!", delete_after=15)

    async def start_game_check(self, ctx):
        if ctx.channel.id in self.active_games:
            embed = discord.Embed(
                title="⚠️ Ada Game Aktif",
                description="Masih ada permainan yang sedang berlangsung di channel ini.\n"
                            "Tunggu hingga selesai, atau ketik **`!stopgame`** untuk mereset status channel jika game macet.",
                color=0xe67e22
            )
            await ctx.send(embed=embed, delete_after=12)
            return False
        self.active_games.add(ctx.channel.id)
        return True

    def is_channel_allowed(self, game_name, channel_id):
        game_channels = self.allowed_channels.get(game_name)
        if game_channels and channel_id not in game_channels:
            return False
        return True


    @commands.command(name="games", aliases=['minigames', 'daftargame', 'listgame'])
    async def games_catalog_cmd(self, ctx):
        """Membuka menu katalog minigames interaktif."""
        embed = discord.Embed(
            title="🎮 RTM-Bot • PUSAT ARCADE & MINIGAMES",
            description="Selamat datang di arena bermain **RTM-Bot**! Kami menyediakan berbagai game interaktif "
                        "multipemain, party voting, kuis kata, hingga asah otak dengan hadiah koin RSWN & EXP.\n\n"
                        "👉 **Pilih game pada menu dropdown di bawah** untuk membaca panduan cara bermain, hadiah, dan perintahnya!",
            color=0xf1c40f
        )
        embed.add_field(name="🔗 Multiplayer & Party", value="`!sambung`, `!siapapaling`, `!matamata`, `!pernahgak`, `!kuismusik`", inline=False)
        embed.add_field(name="🧠 Kuis & Asah Otak", value="`!tebakemoji`, `!susunkata`, `!kuisipa`, `!hangman`, `!siapaaku`, `!hitungcepat`", inline=False)
        embed.add_field(name="🧹 Emergency Reset", value="Ketik `!stopgame` jika ada game yang macet di channel ini.", inline=False)
        view = GameCatalogView(self, ctx)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="stopgame", aliases=['resetgame', 'batalgame', 'cancelgame', 'endgame'])
    async def stop_game_cmd(self, ctx):
        """Memaksa reset status game di channel jika macet."""
        channel_id = ctx.channel.id
        await self.end_game_cleanup(channel_id, ctx.channel)
        embed = discord.Embed(
            title="🧹 Status Permainan Direset",
            description=f"Antrean dan status permainan di channel {ctx.channel.mention} telah berhasil dibersihkan.\n"
                        f"Sekarang kamu bebas memulai minigame baru tanpa kendala!",
            color=0x2ecc71
        )
        await ctx.send(embed=embed)

    @commands.command(name="setgamechannel")
    @commands.has_permissions(administrator=True)
    async def set_game_channel(self, ctx, game_name: str, action: str, channel: discord.TextChannel = None):
        game_name = game_name.lower()
        alias_map = {
            'sambung': 'ressambung', 'sk': 'ressambung', 'sambungkata': 'ressambung',
            'tebakemoji': 'resmoji', 'emoji': 'resmoji',
            'hangman': 'resman', 'tebakkata': 'resman',
            'susunkata': 'resacak', 'acak': 'resacak',
            'kuisipa': 'resipa', 'ipa': 'resipa',
            'kuismusik': 'startquiz', 'musicquiz': 'startquiz',
            'siapapaling': 'siapapaling', 'paling': 'siapapaling'
        }
        canonical_name = alias_map.get(game_name, game_name)
        valid_games = ['resmoji', 'startquiz', 'resman', 'resacak', 'resipa', 'ressambung', 'siapapaling']
        if canonical_name not in valid_games:
            return await ctx.send(f"Nama game tidak valid. Pilih dari: `sambung`, `tebakemoji`, `hangman`, `susunkata`, `kuisipa`, `kuismusik`, `siapapaling`.")
        if canonical_name not in self.allowed_channels:
            self.allowed_channels[canonical_name] = []
        action = action.lower()
        if action == 'add':
            if not channel:
                return await ctx.send("Sebutkan channel yang ingin diizinkan.")
            if channel.id not in self.allowed_channels[canonical_name]:
                self.allowed_channels[canonical_name].append(channel.id)
                await ctx.send(f"✅ Channel {channel.mention} diizinkan untuk game `{canonical_name}`.")
            else:
                await ctx.send(f"Channel {channel.mention} sudah terdaftar.")
        elif action == 'remove':
            if not channel:
                return await ctx.send("Sebutkan channel yang ingin dihapus.")
            if channel.id in self.allowed_channels[canonical_name]:
                self.allowed_channels[canonical_name].remove(channel.id)
                await ctx.send(f"Channel {channel.mention} telah dihapus dari izin game `{canonical_name}`.")
            else:
                await ctx.send(f"Channel {channel.mention} tidak ditemukan dalam izin.")
        elif action == 'list':
            channels = self.allowed_channels.get(canonical_name, [])
            if not channels:
                return await ctx.send(f"Tidak ada pembatasan channel untuk `{canonical_name}`. Game bisa dimainkan di mana saja.")
            channel_mentions = [f"<#{cid}>" for cid in channels]
            await ctx.send(f"Channel yang diizinkan untuk `{canonical_name}`: {', '.join(channel_mentions)}")
        else:
            await ctx.send("Aksi tidak valid. Gunakan `add`, `remove`, atau `list`.")
        save_json_to_root(self.allowed_channels, 'data/game_channels.json')


    @commands.command(name="sambung", aliases=['sk', 'sambungkata', 'ressambung'])
    async def sambung_kata_cmd(self, ctx):
        """Memulai permainan Sambung Kata multiplayer berantai."""
        if not self.is_channel_allowed('ressambung', ctx.channel.id):
            return await ctx.send("Permainan Sambung Kata tidak diizinkan di channel ini.", delete_after=10)

        if not await self.start_game_check(ctx):
            return

        embed = discord.Embed(
            title="🔗 ARENA SAMBUNG KATA BERANTAI",
            description="Tantang kecepatan berpikir dan kosakatamu bersama teman-teman!\n\n"
                        "**Aturan Permainan:**\n"
                        "1. Pemain bergantian menyambung kata berdasarkan **2 huruf terakhir**.\n"
                        "2. Batas waktu menjawab **20 detik** per giliran.\n"
                        "3. **🔥 Combo Multiplier:** Semakin panjang rantai kata tanpa salah, hadiah koin RSWN & EXP semakin berlipat ganda!\n"
                        "4. Pemain yang gagal menjawab atau mengulang kata akan tereliminasi.\n\n"
                        "Klik tombol **⚔️ Ikut Bermain** untuk bergabung (minimal 2 pemain)!",
            color=0xe91e63
        )
        embed.add_field(name="👥 Pemain Bergabung (1)", value=ctx.author.mention, inline=False)
        embed.set_footer(text="Host atau Moderator bisa klik Mulai Game jika semua pemain siap.")

        async def start_game_callback(players):
            try:
                await self.play_sambung_kata(ctx, players)
            finally:
                await self.end_game_cleanup(ctx.channel.id, ctx.channel, 'sambung_kata')

        view = SambungKataLobbyView(self, ctx.channel.id, ctx.author, start_game_callback, timeout=45)
        await ctx.send(embed=embed, view=view)

    async def play_sambung_kata(self, ctx, players):
        if not self.sambung_kata_words:
            await ctx.send("⚠️ Database bank kata belum tersedia.")
            return

        active_players = list(players)
        random.shuffle(active_players)

        current_word = random.choice(self.sambung_kata_words).lower()
        used_words = {current_word}
        turn_index = 0
        combo = 0

        embed_start = discord.Embed(
            title="🚀 PERMAINAN SAMBUNG KATA DIMULAI!",
            description=f"Kata pembuka dari bot:\n\n# 🔤 `{current_word.upper()}`\n\n"
                        f"Urutan bermain: {' ➔ '.join([p.display_name for p in active_players])}",
            color=0x2ecc71
        )
        await ctx.send(embed=embed_start)
        await asyncio.sleep(3)

        while len(active_players) > 1:
            current_player = active_players[turn_index]
            prefix = current_word[-2:].lower()

            combo_text = f"🔥 Combo x{combo} (+{combo * 15}%)" if combo > 1 else "Normal"
            turn_embed = discord.Embed(
                title=f"⏳ Giliran: {current_player.display_name}!",
                description=f"Kata sebelumnya: **`{current_word.upper()}`**\n\n"
                            f"Ketik kata yang diawali dengan:\n# 🔤 「 `{prefix.upper()}`... 」",
                color=current_player.color if current_player.color != discord.Color.default() else 0xe91e63
            )
            turn_embed.add_field(name="👥 Pemain Bertahan", value=f"{len(active_players)} orang", inline=True)
            turn_embed.add_field(name="🔥 Combo Multiplier", value=combo_text, inline=True)
            turn_embed.set_footer(text=f"Waktu berpikir: {self.sambung_kata_time_limit} detik")
            await ctx.send(embed=turn_embed)

            def check(m):
                return m.channel == ctx.channel and m.author.id == current_player.id and not m.author.bot

            eliminated = False
            try:
                while True:
                    msg = await self.bot.wait_for('message', check=check, timeout=self.sambung_kata_time_limit)
                    content = msg.content.strip().lower().strip('.,!?~')
                    if content.startswith(('!', '/', '$', '.')):
                        continue
                    break

                if not content.startswith(prefix):
                    await ctx.send(f"❌ **Salah!** Kata `{content.upper()}` tidak diawali dengan **`{prefix.upper()}`**. {current_player.mention} tereliminasi!")
                    eliminated = True
                elif content in used_words:
                    await ctx.send(f"❌ **Sudah Dipakai!** Kata `{content.upper()}` sudah pernah disebutkan sebelumnya. {current_player.mention} tereliminasi!")
                    eliminated = True
                elif len(content) < 3:
                    await ctx.send(f"❌ **Terlalu Pendek!** Kata harus minimal 3 huruf. {current_player.mention} tereliminasi!")
                    eliminated = True
                else:
                    try:
                        await msg.add_reaction("✅")
                    except Exception:
                        pass
                    current_word = content
                    used_words.add(content)
                    combo += 1
                    turn_index = (turn_index + 1) % len(active_players)

            except asyncio.TimeoutError:
                await ctx.send(f"⌛ **Waktu Habis!** {current_player.mention} tidak menjawab tepat waktu dan tereliminasi!")
                eliminated = True

            if eliminated:
                combo = 0
                active_players.pop(turn_index)
                if active_players:
                    turn_index = turn_index % len(active_players)

            await asyncio.sleep(2)

        if len(active_players) == 1:
            winner = active_players[0]
            bonus_mult = 1.0 + (min(combo, 10) * 0.1)
            final_reward = {
                "rsw": int(self.sambung_kata_winner_reward["rsw"] * bonus_mult),
                "exp": int(self.sambung_kata_winner_reward["exp"] * bonus_mult)
            }
            await self.give_rewards_with_bonus_check(winner, ctx.channel, final_reward)
            win_embed = discord.Embed(
                title="🏆 JUARA SAMBUNG KATA!",
                description=f"Selamat kepada {winner.mention} yang berhasil bertahan hingga akhir!\n\n"
                            f"🎁 **Hadiah Juara:** +{final_reward['rsw']} RSWN & +{final_reward['exp']} EXP\n"
                            f"🔥 **Puncak Combo:** x{combo}",
                color=discord.Color.gold()
            )
            await ctx.send(embed=win_embed)


    @commands.command(name="siapapaling", aliases=['paling', 'wholikely', 'mostlikely', 'votepertanyaan', 'sipaling'])
    async def siapa_paling_cmd(self, ctx):
        """Memulai party game voting rahasia 'Si Paling...'."""
        if not self.is_channel_allowed('siapapaling', ctx.channel.id):
            return await ctx.send("Game Si Paling tidak diizinkan di channel ini.", delete_after=10)

        if not await self.start_game_check(ctx):
            return

        embed = discord.Embed(
            title="🗳️ PARTY GAME: SI PALING...",
            description="Siapakah di antara teman tongkronganmu yang kelakuannya paling cocok dengan situasi kocak?\n\n"
                        "**Cara Bermain:**\n"
                        "1. Bergabung ke lobby dengan menekan tombol **🙋 Ikut Main** (minimal 2 pemain).\n"
                        "2. Bot akan memberikan 3 pertanyaan superlatif/relatable seputar server.\n"
                        "3. Semua pemain memberikan suara rahasia via menu dropdown.\n"
                        "4. Hasil voting akan diumumkan dengan grafik bar suara!\n\n"
                        "Pemenang voting dan seluruh partisipan berhak mendapatkan koin RSWN & EXP!",
            color=0x9b59b6
        )
        embed.add_field(name="👥 Pemain Terdaftar (1)", value=ctx.author.mention, inline=False)
        embed.set_footer(text="Host atau Moderator bisa klik Mulai Voting jika sudah siap.")

        async def start_voting_callback(players):
            try:
                await self.play_siapa_paling(ctx, players)
            finally:
                await self.end_game_cleanup(ctx.channel.id, ctx.channel, 'voting')

        view = SiPalingLobbyView(self, ctx.channel.id, ctx.author, start_voting_callback, timeout=45)
        await ctx.send(embed=embed, view=view)

    async def play_siapa_paling(self, ctx, players):
        if not self.siapa_paling_questions:
            questions = [
                "Siapa yang paling sering bilang 'otw' padahal baru mau mandi?",
                "Siapa yang paling gampang bucin tapi paling gengsian buat ngaku?",
                "Siapa yang paling mungkin jadi miliarder tapi tetep perhitungan soal receh 500 perak?",
                "Siapa yang paling sering salah kirim chat ke grup terus panik setengah mati?",
                "Siapa yang paling sering begadang gak jelas cuma buat scroll medsos sampe subuh?",
                "Siapa yang diam-diam paling jago nge-stalk mantan sampe ke akar-akarnya?",
                "Siapa yang chat-nya paling sering cuma di-read dan baru bales 3 hari kemudian?"
            ]
        else:
            questions = self.siapa_paling_questions

        total_rounds = 3
        chosen_questions = random.sample(questions, min(total_rounds, len(questions)))
        round_winners = {}

        for round_num, question in enumerate(chosen_questions, 1):
            embed = discord.Embed(
                title=f"🗳️ SI PALING... • RONDE {round_num}/{total_rounds}",
                description=f"# 💭 _{question}_\n\n"
                            f"Pilih salah satu pemain dari menu dropdown di bawah! Pilihanmu bersifat **rahasia**.\n"
                            f"Waktu voting: **20 detik**.",
                color=0x9b59b6
            )
            vote_view = SiPalingVoteView(players, timeout=20)
            msg = await ctx.send(embed=embed, view=vote_view)
            await asyncio.sleep(20)

            for child in vote_view.children:
                child.disabled = True
            try:
                await msg.edit(view=vote_view)
            except Exception:
                pass

            vote_counts = {p.id: 0 for p in players}
            for voter_id, target_id in vote_view.votes.items():
                if target_id in vote_counts:
                    vote_counts[target_id] += 1

            sorted_votes = sorted(vote_counts.items(), key=lambda x: x[1], reverse=True)
            total_votes_in = len(vote_view.votes)

            result_desc = f"# 🏆 Pertanyaan:\n> **\"{question}\"**\n\n"
            if total_votes_in == 0:
                result_desc += "⚠️ Tidak ada suara yang masuk pada ronde ini!"
            else:
                top_player_id, top_count = sorted_votes[0]
                top_player = next((p for p in players if p.id == top_player_id), None)
                if top_player and top_count > 0:
                    round_winners[top_player.id] = round_winners.get(top_player.id, 0) + 1
                    result_desc += f"👑 **Pemenang Gelar:** {top_player.mention} ({top_count} suara)!\n\n"
                    await self.give_rewards_with_bonus_check(top_player, ctx.channel, self.voting_winner_reward)

                result_desc += "**📊 Rincian Perolehan Suara:**\n"
                for p_id, count in sorted_votes[:6]:
                    p_obj = next((p for p in players if p.id == p_id), None)
                    name = p_obj.display_name if p_obj else f"User ({p_id})"
                    percent = int((count / total_votes_in * 100)) if total_votes_in > 0 else 0
                    bar_len = int(percent / 10)
                    bar = "█" * bar_len + "░" * (10 - bar_len)
                    result_desc += f"`{bar}` **{count}** suara ({percent}%) — **{name}**\n"

            result_embed = discord.Embed(
                title=f"📊 HASIL VOTING RONDE {round_num}",
                description=result_desc,
                color=0xf1c40f
            )
            await ctx.send(embed=result_embed)

            for voter_id in vote_view.votes.keys():
                voter_mem = next((p for p in players if p.id == voter_id), None)
                if voter_mem:
                    await self.give_rewards_with_bonus_check(voter_mem, ctx.channel, self.voting_participant_reward)

            if round_num < total_rounds:
                await asyncio.sleep(4)

        final_embed = discord.Embed(
            title="🎉 SESI 'SI PALING...' SELESAI!",
            description="Terima kasih telah berpartisipasi dan meramaikan keseruan server!\n"
                        "Seluruh reward koin RSWN & EXP telah dikirimkan ke saldo akun masing-masing.",
            color=0x2ecc71
        )
        await ctx.send(embed=final_embed)


    @commands.command(name="tebakemoji", aliases=['emoji', 'resmoji', 'tebakgambar'])
    async def tebak_emoji_cmd(self, ctx):
        """Memulai permainan Kuis Tebak Emoji."""
        if not self.is_channel_allowed('resmoji', ctx.channel.id):
            return await ctx.send("Kuis Emoji tidak diizinkan di channel ini.")
        if not await self.start_game_check(ctx):
            return

        self.session_scores = {}
        embed = discord.Embed(
            title="🧩 KUIS TEBAK EMOJI",
            description="Uji imajinasi dan ketelitianmu!\n\n"
                        "📌 Bot akan memberikan petunjuk deretan emoji.\n"
                        "🫵 Tebak kata atau frasa yang sesuai dalam waktu 60 detik.\n"
                        f"🎁 Jawaban benar mendapatkan **+{self.reward_per_correct_emoji} RSWN**.\n\n"
                        f"💡 Butuh petunjuk? Gunakan `!hintemoji` (Biaya: {self.bantuan_price_emoji} RSWN via DM).",
            color=0x8e44ad
        )
        async def on_start():
            try:
                self.active_emoji_games[ctx.channel.id] = {
                    "user": ctx.author, "correct": 0, "wrong": 0,
                    "current_question": None, "questions": [], "game_over": False
                }
                await self.play_emoji_game(ctx)
            finally:
                await self.end_game_cleanup(ctx.channel.id, ctx.channel, 'emoji')

        view = StartGameView(self, ctx.channel.id, ctx.author.id, on_start, timeout=60)
        await ctx.send(embed=embed, view=view)

    async def play_emoji_game(self, ctx):
        game_data = self.active_emoji_games.get(ctx.channel.id)
        if not game_data or not self.emoji_questions:
            await ctx.send("Database soal emoji belum tersedia.")
            return

        sample_size = min(10, len(self.emoji_questions))
        game_data["questions"] = random.sample(self.emoji_questions, sample_size)

        for index, question in enumerate(game_data["questions"]):
            if game_data.get("game_over"): break
            game_data["current_question"] = index
            await self.ask_emoji_question(ctx, question, index + 1, sample_size)
            await asyncio.sleep(2)

        if not game_data.get("game_over"):
            await self.end_emoji_game(ctx)

    async def ask_emoji_question(self, ctx, question, q_num, total_q):
        game_data = self.active_emoji_games.get(ctx.channel.id)
        if not game_data: return

        expected_answer = question['answer'].strip().lower()
        embed = discord.Embed(
            title=f"❓ SOAL EMOJI #{q_num}/{total_q}",
            description=f"# {question['emoji']}\n\nSebutkan frasa/kata yang dimaksud!",
            color=0x2ecc71
        )
        embed.set_footer(text=f"Waktu menjawab: {self.time_limit_emoji} detik")
        await ctx.send(embed=embed)

        def check(m):
            return m.channel == ctx.channel and not m.author.bot

        start_time = datetime.now()
        while (datetime.now() - start_time).total_seconds() < self.time_limit_emoji:
            rem_time = self.time_limit_emoji - (datetime.now() - start_time).total_seconds()
            if rem_time <= 0: break
            try:
                user_msg = await self.bot.wait_for('message', timeout=rem_time, check=check)
                content = user_msg.content.strip().lower().strip('.,!?~')
                if content.startswith(('!', '/', '$', '.')):
                    continue

                if content == expected_answer or (len(content) >= 4 and content in expected_answer and len(content) >= len(expected_answer) * 0.6):
                    author = user_msg.author
                    multiplier = self.get_anomaly_multiplier()
                    final_reward = int(self.reward_per_correct_emoji * multiplier)

                    if author.id not in self.session_scores:
                        self.session_scores[author.id] = {"score": 0, "correct": 0, "wrong": 0, "user": author}
                    self.session_scores[author.id]["score"] += final_reward
                    self.session_scores[author.id]["correct"] += 1
                    game_data["correct"] += 1

                    await ctx.send(f"✅ **Benar!** Jawaban dari {author.mention} tepat: **{question['answer'].upper()}** (+{final_reward} RSWN)!")
                    try:
                        await user_msg.add_reaction("🎉")
                    except Exception:
                        pass
                    return
            except asyncio.TimeoutError:
                break

        await ctx.send(f"⌛ **Waktu Habis!** Jawaban yang benar adalah: **{question['answer'].upper()}**.")

    async def end_emoji_game(self, ctx):
        self.bank_data = load_json_from_root('data/bank_data.json')
        for user_id, score_data in self.session_scores.items():
            uid_str = str(user_id)
            self.bank_data.setdefault(uid_str, {"balance": 0, "debt": 0})['balance'] += score_data['score']
        save_json_to_root(self.bank_data, 'data/bank_data.json')
        await self.display_leaderboard(ctx, 'Tebak Emoji')

    @commands.command(name="hintemoji", aliases=['bantuanemoji', 'resplis'])
    async def bantuan_emoji_cmd(self, ctx):
        """Membeli petunjuk jawaban tebak emoji via DM."""
        user_id = str(ctx.author.id)
        self.bank_data = load_json_from_root('data/bank_data.json')
        user_data = self.bank_data.setdefault(user_id, {"balance": 0, "debt": 0})
        if user_data.get('balance', 0) < self.bantuan_price_emoji:
            return await ctx.send(f"😢 Saldo RSWN tidak cukup. Harga: {self.bantuan_price_emoji} RSWN.")
        if ctx.channel.id not in self.active_emoji_games or self.active_emoji_games[ctx.channel.id].get("current_question") is None:
            return await ctx.send("Tidak ada sesi Tebak Emoji yang sedang berjalan di channel ini.")

        game = self.active_emoji_games[ctx.channel.id]
        curr_q = game["questions"][game["current_question"]]
        user_data['balance'] -= self.bantuan_price_emoji
        save_json_to_root(self.bank_data, 'data/bank_data.json')
        try:
            await ctx.author.send(f"🔐 **Bocoran Tebak Emoji:** Jawaban untuk soal saat ini adalah: **{curr_q['answer']}**")
            await ctx.send(f"{ctx.author.mention}, bantuan telah dikirim via DM!", delete_after=10)
        except discord.Forbidden:
            user_data['balance'] += self.bantuan_price_emoji
            save_json_to_root(self.bank_data, 'data/bank_data.json')
            await ctx.send("❌ Gagal mengirim DM. Pastikan DM akunmu terbuka!")


    @commands.command(name="susunkata", aliases=['acak', 'resacak'])
    async def susunkata_cmd(self, ctx):
        """Memulai permainan Susun Kata (Anagram)."""
        if not self.is_channel_allowed('resacak', ctx.channel.id):
            return await ctx.send("Permainan Susun Kata tidak diizinkan di channel ini.", delete_after=10)
        if not await self.start_game_check(ctx):
            return

        embed = discord.Embed(
            title="🔤 ARENA SUSUN KATA (ANAGRAM)",
            description="Asah kecepatan berpikir dan ketelitian menyusun huruf!\n\n"
                        "1. Bot mengacak huruf-huruf dari suatu kata.\n"
                        "2. Pemain pertama yang menjawab dengan benar mendapat **50 RSWN** & **100 EXP**.\n"
                        "3. Permainan terdiri dari 10 ronde seru.",
            color=0x2ecc71
        )
        async def on_start():
            try:
                await self.play_susunkata(ctx)
            finally:
                await self.end_game_cleanup(ctx.channel.id, ctx.channel, 'resacak')

        view = StartGameView(self, ctx.channel.id, ctx.author.id, on_start, timeout=60)
        await ctx.send(embed=embed, view=view)

    async def play_susunkata(self, ctx):
        if not self.resacak_questions:
            return await ctx.send("Database soal susun kata belum tersedia.")

        sample_size = min(10, len(self.resacak_questions))
        questions = random.sample(self.resacak_questions, sample_size)
        leaderboard = {}

        for i, q in enumerate(questions, 1):
            original = q['word'].strip()
            letters = list(original.upper())
            scrambled = letters.copy()
            for _ in range(5):
                random.shuffle(scrambled)
                if "".join(scrambled) != original.upper(): break

            embed = discord.Embed(
                title=f"📝 SOAL #{i}/{sample_size} — SUSUN KATA",
                color=0x2ecc71
            )
            embed.add_field(name="Kategori", value=q.get('category', 'Umum'), inline=True)
            embed.add_field(name="Huruf Teracak", value=f"# `{ ' '.join(scrambled) }`", inline=False)
            embed.add_field(name="Kisi-kisi", value=q.get('clue', 'Pikirkan baik-baik!'), inline=False)
            embed.set_footer(text=f"Batas waktu: {self.resacak_time_limit} detik")
            await ctx.send(embed=embed)

            def check(m):
                return m.channel == ctx.channel and not m.author.bot

            start_t = datetime.now()
            winner = None
            while (datetime.now() - start_t).total_seconds() < self.resacak_time_limit:
                rem = self.resacak_time_limit - (datetime.now() - start_t).total_seconds()
                if rem <= 0: break
                try:
                    msg = await self.bot.wait_for('message', timeout=rem, check=check)
                    content = msg.content.strip().lower().strip('.,!?~')
                    if content.startswith(('!', '/', '$', '.')): continue
                    if content == original.lower():
                        winner = msg.author
                        try:
                            await msg.add_reaction("🎉")
                        except Exception:
                            pass
                        break
                except asyncio.TimeoutError:
                    break

            if winner:
                await self.give_rewards_with_bonus_check(winner, ctx.channel, self.resacak_reward)
                leaderboard[winner.display_name] = leaderboard.get(winner.display_name, 0) + 1
                await ctx.send(f"✅ **Tepat!** {winner.mention} berhasil menyusun kata: **{original.upper()}**!")
            else:
                await ctx.send(f"⌛ **Waktu Habis!** Kata yang benar adalah **{original.upper()}**.")

            await asyncio.sleep(2)

        if leaderboard:
            sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
            desc = "\n".join([f"**#{n}.** {u}: {s} poin" for n, (u, s) in enumerate(sorted_lb, 1)])
            await ctx.send(embed=discord.Embed(title="🏆 Papan Skor Susun Kata", description=desc, color=discord.Color.gold()))


    @commands.command(name="kuisipa", aliases=['ipa', 'resipa', 'sains'])
    async def kuisipa_cmd(self, ctx):
        """Memulai Kuis IPA dan Pengetahuan Sains."""
        if not self.is_channel_allowed('resipa', ctx.channel.id):
            return await ctx.send("Kuis IPA tidak diizinkan di channel ini.", delete_after=10)
        if not await self.start_game_check(ctx):
            return

        embed = discord.Embed(
            title="🔬 KUIS IPA & PENGETAHUAN SAINS",
            description="Tebak istilah biologi, fisika, dan kimia!\n\n"
                        "1. Bot menyajikan 10 soal sains acak.\n"
                        "2. Jawab dengan benar dalam batas waktu 30 detik.\n"
                        "3. Pemenang mendapat **50 RSWN** & **100 EXP** per soal.",
            color=0x1abc9c
        )
        async def on_start():
            try:
                await self.play_kuisipa(ctx)
            finally:
                await self.end_game_cleanup(ctx.channel.id, ctx.channel, 'resipa')

        view = StartGameView(self, ctx.channel.id, ctx.author.id, on_start, timeout=60)
        await ctx.send(embed=embed, view=view)

    async def play_kuisipa(self, ctx):
        if not self.resipa_questions:
            return await ctx.send("Database soal IPA belum tersedia.")

        sample_size = min(10, len(self.resipa_questions))
        questions = random.sample(self.resipa_questions, sample_size)
        leaderboard = {}

        for i, q in enumerate(questions, 1):
            original = q['word'].strip()
            letters = list(original.upper())
            scrambled = letters.copy()
            for _ in range(5):
                random.shuffle(scrambled)
                if "".join(scrambled) != original.upper(): break

            embed = discord.Embed(
                title=f"🔬 SOAL SAINS #{i}/{sample_size}",
                color=0x1abc9c
            )
            embed.add_field(name="Kategori", value=q.get('category', 'Sains'), inline=True)
            embed.add_field(name="Huruf Teracak", value=f"# `{ ' '.join(scrambled) }`", inline=False)
            embed.add_field(name="Petunjuk Sains", value=q.get('clue', 'Definisi konsep sains'), inline=False)
            embed.set_footer(text=f"Batas waktu: {self.resipa_time_limit} detik")
            await ctx.send(embed=embed)

            def check(m):
                return m.channel == ctx.channel and not m.author.bot

            start_t = datetime.now()
            winner = None
            while (datetime.now() - start_t).total_seconds() < self.resipa_time_limit:
                rem = self.resipa_time_limit - (datetime.now() - start_t).total_seconds()
                if rem <= 0: break
                try:
                    msg = await self.bot.wait_for('message', timeout=rem, check=check)
                    content = msg.content.strip().lower().strip('.,!?~')
                    if content.startswith(('!', '/', '$', '.')): continue
                    if content == original.lower():
                        winner = msg.author
                        try:
                            await msg.add_reaction("🎉")
                        except Exception:
                            pass
                        break
                except asyncio.TimeoutError:
                    break

            if winner:
                await self.give_rewards_with_bonus_check(winner, ctx.channel, self.resipa_reward)
                leaderboard[winner.display_name] = leaderboard.get(winner.display_name, 0) + 1
                await ctx.send(f"✅ **Benar!** {winner.mention} menjawab istilah: **{original.upper()}**!")
            else:
                await ctx.send(f"⌛ **Waktu Habis!** Istilah yang benar adalah **{original.upper()}**.")

            await asyncio.sleep(2)

        if leaderboard:
            sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
            desc = "\n".join([f"**#{n}.** {u}: {s} poin" for n, (u, s) in enumerate(sorted_lb, 1)])
            await ctx.send(embed=discord.Embed(title="🏆 Papan Skor Kuis IPA", description=desc, color=discord.Color.teal()))


    @commands.command(name="hangman", aliases=['tebakkata', 'resman'])
    async def hangman_cmd(self, ctx):
        """Memulai permainan Hangman klasik."""
        if not self.is_channel_allowed('resman', ctx.channel.id):
            return await ctx.send("Permainan Hangman tidak diizinkan di channel ini.")
        if not await self.start_game_check(ctx):
            return

        self.session_scores = {}
        embed = discord.Embed(
            title="🪢 DUNIA HANGMAN (TEBAK KATA)",
            description="Tebak kata rahasia huruf demi huruf!\n\n"
                        "1. Bot menyajikan 10 soal dengan kisi-kisi dan jumlah huruf.\n"
                        "2. Jawab kata lengkapnya sebelum batas waktu 120 detik habis.\n"
                        f"3. Butuh bantuan? Beli via `!bantuanhangman` (Harga: {self.bantuan_price_hangman} RSWN via DM).",
            color=0x34495e
        )
        async def on_start():
            try:
                self.active_hangman_games[ctx.channel.id] = {
                    "score": 0, "correct": 0, "wrong": 0, "current_question": 0,
                    "time_limit": 120, "question": None, "game_over": False
                }
                await self.play_hangman(ctx)
            finally:
                await self.end_game_cleanup(ctx.channel.id, ctx.channel, 'hangman')

        view = StartGameView(self, ctx.channel.id, ctx.author.id, on_start, timeout=60)
        await ctx.send(embed=embed, view=view)

    async def play_hangman(self, ctx):
        game_data = self.active_hangman_games.get(ctx.channel.id)
        if not game_data or not self.hangman_questions:
            return await ctx.send("Database soal Hangman belum tersedia.")

        sample_size = min(10, len(self.hangman_questions))
        game_data["question"] = random.sample(self.hangman_questions, sample_size)

        for index, question in enumerate(game_data["question"]):
            if game_data.get("game_over"): break
            game_data["current_question"] = index + 1
            await self.ask_hangman(ctx, question, index + 1, sample_size)
            await asyncio.sleep(2)

        await self.end_hangman(ctx)

    async def ask_hangman(self, ctx, question, q_num, total_q):
        game_data = self.active_hangman_games.get(ctx.channel.id)
        if not game_data: return

        target_word = question['word'].strip()
        hidden = " ".join(["_" for _ in target_word])
        embed = discord.Embed(
            title=f"❓ SOAL HANGMAN #{q_num}/{total_q}",
            description=f"Kategori: **{question.get('category', 'Umum')}**\n"
                        f"Kisi-kisi: *{question.get('clue', 'Tebak kata ini')}*\n\n"
                        f"# `{hidden}` ({len(target_word)} Huruf)",
            color=0x00ff00
        )
        embed.set_footer(text="Waktu berpikir: 120 detik")
        await ctx.send(embed=embed)

        def check(m):
            return m.channel == ctx.channel and not m.author.bot

        start_t = datetime.now()
        while (datetime.now() - start_t).total_seconds() < 120:
            rem = 120 - (datetime.now() - start_t).total_seconds()
            if rem <= 0: break
            try:
                msg = await self.bot.wait_for('message', timeout=rem, check=check)
                content = msg.content.strip().lower().strip('.,!?~')
                if content.startswith(('!', '/', '$', '.')): continue
                if content == target_word.lower():
                    author = msg.author
                    mult = self.get_anomaly_multiplier()
                    final_r = int(self.reward_per_correct_hangman * mult)

                    if author.id not in self.session_scores:
                        self.session_scores[author.id] = {"user": author, "correct": 0, "wrong": 0, "total_rsw": 0}
                    self.session_scores[author.id]["correct"] += 1
                    self.session_scores[author.id]["total_rsw"] += final_r
                    game_data["correct"] += 1

                    await ctx.send(f"✅ **Tepat Sekali!** {author.mention} berhasil menebak: **{target_word.upper()}** (+{final_r} RSWN)!")
                    try:
                        await msg.add_reaction("🎉")
                    except Exception:
                        pass
                    return
            except asyncio.TimeoutError:
                break

        await ctx.send(f"⌛ **Waktu Habis!** Jawaban yang benar adalah: **{target_word.upper()}**.")

    async def end_hangman(self, ctx):
        self.bank_data = load_json_from_root('data/bank_data.json')
        self.level_data = load_json_from_root('data/level_data.json')
        guild_id = str(ctx.guild.id)
        for user_id, score_data in self.session_scores.items():
            uid_str = str(user_id)
            self.bank_data.setdefault(uid_str, {"balance": 0, "debt": 0})['balance'] += score_data['total_rsw']
            self.level_data.setdefault(guild_id, {}).setdefault(uid_str, {"exp": 0, "level": 1})['exp'] += score_data['correct'] * 50
        save_json_to_root(self.bank_data, 'data/bank_data.json')
        save_json_to_root(self.level_data, 'data/level_data.json')
        await self.display_leaderboard(ctx, 'Hangman')

    @commands.command(name="bantuanhangman", aliases=['hmanplis', 'hinthangman'])
    async def bantuan_hangman_cmd(self, ctx):
        """Membeli bocoran jawaban Hangman via DM."""
        user_id = str(ctx.author.id)
        if ctx.channel.id not in self.active_hangman_games:
            return await ctx.send("Tidak ada sesi Hangman yang sedang berjalan di channel ini.")
        self.bank_data = load_json_from_root('data/bank_data.json')
        user_data = self.bank_data.setdefault(user_id, {"balance": 0, "debt": 0})
        if user_data.get('balance', 0) < self.bantuan_price_hangman:
            return await ctx.send(f"😢 Saldo RSWN tidak cukup. Harga: {self.bantuan_price_hangman} RSWN.")

        game = self.active_hangman_games[ctx.channel.id]
        curr_idx = game["current_question"] - 1
        if 0 <= curr_idx < len(game["question"]):
            correct_word = game["question"][curr_idx]['word']
            user_data['balance'] -= self.bantuan_price_hangman
            save_json_to_root(self.bank_data, 'data/bank_data.json')
            try:
                await ctx.author.send(f"🔐 **Bocoran Hangman:** Jawaban soal saat ini adalah: **{correct_word}**")
                await ctx.send(f"{ctx.author.mention}, bantuan dikirim via DM!", delete_after=10)
            except discord.Forbidden:
                user_data['balance'] += self.bantuan_price_hangman
                save_json_to_root(self.bank_data, 'data/bank_data.json')
                await ctx.send("❌ Gagal mengirim DM. Pastikan DM akunmu terbuka!")


    @commands.command(name="siapaaku", aliases=['tebaksiapa', 'siapakahaku'])
    async def siapa_aku_cmd(self, ctx):
        """Kuis petunjuk bertahap tebak tokoh, hewan, atau benda."""
        if not await self.start_game_check(ctx):
            return
        try:
            await self.play_siapa_aku(ctx)
        finally:
            await self.end_game_cleanup(ctx.channel.id, ctx.channel)

    async def play_siapa_aku(self, ctx):
        if not self.siapakah_aku_data or len(self.siapakah_aku_data) < 5:
            return await ctx.send("Database soal 'Siapa Aku' belum cukup.")

        sample_size = min(10, len(self.siapakah_aku_data))
        questions = random.sample(self.siapakah_aku_data, sample_size)
        leaderboard = {}

        await ctx.send(embed=discord.Embed(
            title="🕵️ SESI KUIS 'SIAPA AKU?' DIMULAI!",
            description=f"Akan ada **{sample_size} soal** berturut-turut.\nPetunjuk akan dibuka setiap **10 detik**!",
            color=0x1abc9c
        ))
        await asyncio.sleep(3)

        for i, item in enumerate(questions, 1):
            target = item['name'].strip()
            clues = item['clues']
            embed = discord.Embed(title=f"🕵️ SOAL #{i}/{sample_size}", description=f"Kategori: **{item.get('category', 'Umum')}**", color=0x1abc9c)
            embed.set_footer(text="Maksimal 2 kali tebakan salah per orang pada setiap soal!")
            msg = await ctx.send(embed=embed)

            round_solved = False
            winner = None
            attempts = {}

            for c_idx, clue in enumerate(clues):
                if round_solved: break
                embed.add_field(name=f"Petunjuk #{c_idx + 1}", value=f"_{clue}_", inline=False)
                try:
                    await msg.edit(embed=embed)
                except Exception:
                    pass

                def check(m):
                    return m.channel == ctx.channel and not m.author.bot

                start_c = datetime.now()
                while (datetime.now() - start_c).total_seconds() < 10.0:
                    rem = 10.0 - (datetime.now() - start_c).total_seconds()
                    if rem <= 0: break
                    try:
                        user_m = await self.bot.wait_for('message', timeout=rem, check=check)
                        content = user_m.content.strip().lower().strip('.,!?~')
                        if content.startswith(('!', '/', '$', '.')): continue

                        uid = user_m.author.id
                        if attempts.get(uid, 0) >= 2:
                            continue

                        if content == target.lower():
                            winner = user_m.author
                            round_solved = True
                            try:
                                await user_m.add_reaction("🎉")
                            except Exception:
                                pass
                            break
                        else:
                            attempts[uid] = attempts.get(uid, 0) + 1
                            try:
                                await user_m.add_reaction("❌")
                            except Exception:
                                pass
                            if attempts[uid] == 2:
                                await ctx.send(f"⚠️ {user_m.author.mention}, batas tebakanmu untuk soal ini habis!", delete_after=5)
                    except asyncio.TimeoutError:
                        break

            if winner:
                await self.give_rewards_with_bonus_check(winner, ctx.channel)
                leaderboard[winner.display_name] = leaderboard.get(winner.display_name, 0) + 1
                await ctx.send(f"🎉 **Tepat Sekali!** {winner.mention} berhasil menebak: **{target.upper()}**!")
            else:
                await ctx.send(f"⌛ **Waktu Habis!** Jawaban yang benar adalah: **{target.upper()}**.")

            await asyncio.sleep(3)

        if leaderboard:
            sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
            desc = "\n".join([f"**#{n}.** {u}: **{s}** poin" for n, (u, s) in enumerate(sorted_lb, 1)])
            await ctx.send(embed=discord.Embed(title="🏆 Papan Skor Akhir 'Siapa Aku?'", description=desc, color=0xffd700))


    @commands.command(name="hitungcepat", aliases=['math', 'hitung', 'matematika'])
    async def hitung_cepat_cmd(self, ctx):
        """Adu kecepatan perhitungan matematika dasar."""
        if not await self.start_game_check(ctx):
            return
        try:
            await self.play_hitung_cepat(ctx)
        finally:
            await self.end_game_cleanup(ctx.channel.id, ctx.channel)

    async def play_hitung_cepat(self, ctx):
        if not self.hitung_cepat_data:
            return await ctx.send("Database soal hitung cepat belum tersedia.")

        sample_size = min(10, len(self.hitung_cepat_data))
        problems = random.sample(self.hitung_cepat_data, sample_size)
        leaderboard = {}

        await ctx.send(embed=discord.Embed(
            title="⚡ SESI HITUNG CEPAT DIMULAI!",
            description=f"Akan ada **{sample_size} soal** aritmatika! Siapa paling cepat dan tepat menjawab dialah juaranya!",
            color=0xe74c3c
        ))
        await asyncio.sleep(3)

        for i, item in enumerate(problems, 1):
            problem = item['problem']
            answer_str = str(item['answer']).strip()

            embed = discord.Embed(
                title=f"🧮 SOAL MATEMATIKA #{i}/{sample_size}",
                description=f"# `{problem} = ?`",
                color=0xe74c3c
            )
            embed.set_footer(text="Batas waktu: 15 detik")
            await ctx.send(embed=embed)

            def check(m):
                return m.channel == ctx.channel and not m.author.bot

            start_t = datetime.now()
            winner = None
            while (datetime.now() - start_t).total_seconds() < 15.0:
                rem = 15.0 - (datetime.now() - start_t).total_seconds()
                if rem <= 0: break
                try:
                    msg = await self.bot.wait_for('message', timeout=rem, check=check)
                    content = msg.content.strip()
                    if content.startswith(('!', '/', '$', '.')): continue
                    if content == answer_str:
                        winner = msg.author
                        try:
                            await msg.add_reaction("⚡")
                        except Exception:
                            pass
                        break
                except asyncio.TimeoutError:
                    break

            if winner:
                await self.give_rewards_with_bonus_check(winner, ctx.channel)
                leaderboard[winner.display_name] = leaderboard.get(winner.display_name, 0) + 1
                await ctx.send(f"⚡ **Tepat!** {winner.mention} menjawab **{answer_str}** dengan benar!")
            else:
                await ctx.send(f"⌛ **Waktu Habis!** Jawaban yang benar adalah **{answer_str}**.")

            await asyncio.sleep(2)

        if leaderboard:
            sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
            desc = "\n".join([f"**#{n}.** {u}: **{s}** soal benar" for n, (u, s) in enumerate(sorted_lb, 1)])
            await ctx.send(embed=discord.Embed(title="🏆 Papan Skor Hitung Cepat", description=desc, color=0x2ecc71))


    @commands.command(name="pernahgak", aliases=['nhie', 'pernah'])
    async def pernah_gak_cmd(self, ctx):
        """Permainan kejujuran Never Have I Ever via tombol interaktif."""
        if not await self.start_game_check(ctx):
            return
        try:
            await self.play_pernah_gak(ctx)
        finally:
            await self.end_game_cleanup(ctx.channel.id, ctx.channel)

    async def play_pernah_gak(self, ctx):
        if not self.pernah_gak_pernah_data:
            return await ctx.send("Database pertanyaan belum tersedia.")

        sample_size = min(10, len(self.pernah_gak_pernah_data))
        questions = random.sample(self.pernah_gak_pernah_data, sample_size)
        session_results = []

        await ctx.send(embed=discord.Embed(
            title="🤔 PERMAINAN 'PERNAH GAK PERNAH' DIMULAI!",
            description="Akan ada 10 pernyataan! Jawab sejujur-jujurnya menggunakan tombol interaktif!",
            color=0xf1c40f
        ))
        await asyncio.sleep(3)

        for i, statement in enumerate(questions, 1):
            embed = discord.Embed(
                title=f"❓ PERNYATAAN #{i}/{sample_size}",
                description=f"# 💬 _{statement}_\n\nKlik tombol di bawah untuk menjawab!",
                color=0xf1c40f
            )
            embed.set_footer(text="Waktu menjawab: 15 detik")
            view = PernahGakView(ctx.guild.members, timeout=15)
            msg = await ctx.send(embed=embed, view=view)
            await asyncio.sleep(15)

            for child in view.children: child.disabled = True
            try:
                await msg.edit(view=view)
            except Exception:
                pass

            pernah_names = []
            gak_pernah_names = []
            for uid, ans in view.answers.items():
                mem = ctx.guild.get_member(uid)
                if mem:
                    if ans == "Pernah": pernah_names.append(mem.display_name)
                    else: gak_pernah_names.append(mem.display_name)
                    await self.give_rewards_with_bonus_check(mem, ctx.channel, {"rsw": 15, "exp": 30})

            session_results.append({
                "statement": statement,
                "pernah": pernah_names,
                "gak_pernah": gak_pernah_names
            })
            await asyncio.sleep(2)

        summary_desc = ""
        for i, res in enumerate(session_results, 1):
            summary_desc += f"**{i}. {res['statement']}**\n"
            summary_desc += f"  ✅ Pernah ({len(res['pernah'])}): {', '.join(res['pernah']) if res['pernah'] else '-'}\n"
            summary_desc += f"  ❌ Gak Pernah ({len(res['gak_pernah'])}): {', '.join(res['gak_pernah']) if res['gak_pernah'] else '-'}\n\n"

        summary_embed = discord.Embed(
            title="📊 RINGKASAN KEJUJURAN 'PERNAH GAK PERNAH'",
            description=summary_desc[:4000],
            color=0x3498db
        )
        await ctx.send(embed=summary_embed)


    @commands.command(name="matamata", aliases=['spyfall', 'spy'])
    async def matamata_cmd(self, ctx):
        """Memulai permainan peran Mata-Mata (Spyfall)."""
        if not await self.start_game_check(ctx):
            return
        try:
            await self.play_matamata(ctx)
        finally:
            await self.end_game_cleanup(ctx.channel.id, ctx.channel)

    async def play_matamata(self, ctx):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("Kamu harus berada di Voice Channel untuk memulai game ini.", delete_after=10)
        vc = ctx.author.voice.channel
        members = [m for m in vc.members if not m.bot]
        if len(members) < 3:
            return await ctx.send("Game Mata-Mata membutuhkan minimal 3 pemain di Voice Channel.", delete_after=10)
        if not self.mata_mata_locations:
            return await ctx.send("Database lokasi belum tersedia.")

        location = random.choice(self.mata_mata_locations)
        eligible = [m for m in members if m.id != self.last_spy_id]
        spy = random.choice(eligible) if eligible else random.choice(members)

        self.spyfall_game_states[ctx.channel.id] = {
            'spy': spy, 'location': location, 'players': members,
            'vote_in_progress': False, 'game_ended': False
        }

        failed_dms = []
        for mem in members:
            try:
                if mem.id == spy.id:
                    await mem.send("🤫 Kamu adalah **MATA-MATA**! Tugasmu adalah menebak lokasi rahasia tanpa ketahuan pemain lain.")
                else:
                    await mem.send(f"📍 Lokasi Rahasia adalah: **{location}**. Cari tahu siapa mata-mata di antara kalian!")
            except discord.Forbidden:
                failed_dms.append(mem.mention)

        if failed_dms:
            await ctx.send(f"⚠️ Gagal mengirimkan DM ke: {', '.join(failed_dms)}. Pastikan DM terbuka!")
            return

        embed = discord.Embed(
            title="🎭 GAME MATA-MATA DIMULAI!",
            description="Peran dan lokasi telah dikirimkan via DM.\n\n"
                        "• **Warga:** Cari siapa yang berpura-pura tahu lokasi.\n"
                        "• **Mata-Mata:** Bertahanlah dan coba tebak lokasinya.\n\n"
                        "Kalian punya **5 menit** untuk berdiskusi. Gunakan `!tuduh @user` jika mencurigai seseorang!",
            color=0x7289da
        )
        await ctx.send(embed=embed)
        await asyncio.sleep(300)

        if ctx.channel.id in self.spyfall_game_states and not self.spyfall_game_states[ctx.channel.id]['game_ended']:
            await ctx.send(f"⏰ **Waktu 5 Menit Habis!** Fase penuduhan akhir dibuka.\n"
                           f"Mata-mata ({spy.mention}) menang jika tidak ada yang berhasil menuduh atau mata-mata menebak lokasi dengan `!ungkap_lokasi <nama>`!")
            await asyncio.sleep(120)

            if ctx.channel.id in self.spyfall_game_states and not self.spyfall_game_states[ctx.channel.id]['game_ended']:
                await ctx.send(f"🎉 Waktu habis! **Mata-Mata ({spy.mention}) Menang!** Lokasi aslinya adalah **{location}**.")
                await self.give_rewards_with_bonus_check(spy, ctx.channel)
                self.spyfall_game_states[ctx.channel.id]['game_ended'] = True

    @commands.command(name="tuduh")
    async def tuduh_cmd(self, ctx, member: discord.Member):
        """Menuduh seorang pemain sebagai mata-mata dalam sesi game Mata-Mata."""
        if ctx.channel.id not in self.spyfall_game_states:
            return await ctx.send("Game Mata-Mata belum dimulai di channel ini.", ephemeral=True)
        game = self.spyfall_game_states[ctx.channel.id]
        if game.get('game_ended'): return
        spy, location, players = game['spy'], game['location'], game['players']

        if ctx.author not in players or member not in players:
            return await ctx.send("Hanya pemain yang terdaftar yang bisa menuduh.", ephemeral=True)
        if game.get('vote_in_progress'):
            return await ctx.send("Sedang ada voting berlangsung. Tunggu sebentar.", ephemeral=True)

        game['vote_in_progress'] = True
        vote_embed = discord.Embed(
            title="🗳️ VOTING PENUDUHAN MATA-MATA",
            description=f"{ctx.author.mention} menuduh {member.mention} sebagai mata-mata!\n\n"
                        f"Setuju (✅) atau Tolak (❌)? Voting berakhir dalam 30 detik.",
            color=discord.Color.red()
        )
        msg = await ctx.send(embed=vote_embed)
        try:
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
        except Exception:
            pass

        await asyncio.sleep(30)
        try:
            cached = await ctx.channel.fetch_message(msg.id)
            yes_count, no_count = 0, 0
            for r in cached.reactions:
                if str(r.emoji) == "✅": yes_count = r.count - 1
                elif str(r.emoji) == "❌": no_count = r.count - 1

            if yes_count > no_count:
                if member.id == spy.id:
                    await ctx.send(f"🎉 **Tuduhan Tepat!** {member.mention} memang Mata-Mata! Tim Warga menang!\nLokasi rahasianya adalah **{location}**.")
                    for p in players:
                        if p.id != spy.id: await self.give_rewards_with_bonus_check(p, ctx.channel)
                else:
                    await ctx.send(f"❌ **Tuduhan Salah!** {member.mention} adalah warga tak bersalah. **Mata-Mata ({spy.mention}) Menang!**\nLokasi rahasianya adalah **{location}**.")
                    await self.give_rewards_with_bonus_check(spy, ctx.channel)
                game['game_ended'] = True
                await self.end_game_cleanup(ctx.channel.id, ctx.channel)
            else:
                await ctx.send(f"❌ Voting penuduhan gagal (tidak mencapai suara mayoritas). Permainan dilanjutkan!")
                game['vote_in_progress'] = False
        except Exception:
            game['vote_in_progress'] = False

    @commands.command(name="ungkap_lokasi", aliases=['ulokasi'])
    async def ungkap_lokasi_cmd(self, ctx, *, guessed_location: str):
        """Mata-mata mencoba menebak lokasi rahasia."""
        if ctx.channel.id not in self.spyfall_game_states:
            return await ctx.send("Game Mata-Mata belum dimulai.", ephemeral=True)
        game = self.spyfall_game_states[ctx.channel.id]
        if game.get('game_ended'): return
        spy, location = game['spy'], game['location']

        if ctx.author.id != spy.id:
            return await ctx.send("Hanya Mata-Mata yang berhak mengungkapkan lokasi rahasia.", ephemeral=True)

        if guessed_location.strip().lower() == location.strip().lower():
            await ctx.send(f"🎉 **Luar Biasa!** Mata-Mata ({spy.mention}) berhasil menebak lokasi rahasia: **{location}**!\n**Mata-Mata Menang!**")
            await self.give_rewards_with_bonus_check(spy, ctx.channel)
        else:
            await ctx.send(f"❌ **Tebakan Salah!** Tebakan `{guessed_location}` meleset. Lokasi sebenarnya adalah **{location}**.\n**Tim Warga Menang!**")
            for p in game['players']:
                if p.id != spy.id: await self.give_rewards_with_bonus_check(p, ctx.channel)

        game['game_ended'] = True
        await self.end_game_cleanup(ctx.channel.id, ctx.channel)


    @commands.command(name="kuismusik", aliases=['startquiz', 'musicquiz'])
    async def kuis_musik_cmd(self, ctx):
        """Memulai Kuis Trivia Musik di Voice Channel."""
        if not self.is_channel_allowed('startquiz', ctx.channel.id):
            return await ctx.send("Kuis Musik tidak diizinkan di channel ini.")
        if not await self.start_game_check(ctx):
            return

        try:
            if not ctx.author.voice or not ctx.author.voice.channel:
                await ctx.send("Kamu harus berada di Voice Channel untuk memulai kuis musik.")
                return

            participants = [m.id for m in ctx.author.voice.channel.members if not m.bot]
            if not participants:
                await ctx.send("Tidak ada peserta non-bot di Voice Channel.")
                return

            if not self.music_questions:
                await ctx.send("Database soal kuis musik belum tersedia.")
                return

            self.session_scores = {str(mid): 0 for mid in participants}
            await ctx.send("⏳ Bersiaplah... Kuis Musik akan dimulai dalam 3 detik!")
            await asyncio.sleep(3)

            def make_callback(q, is_bonus, correct_users):
                async def callback(interaction, is_correct):
                    uid = str(interaction.user.id)
                    if uid not in self.session_scores: self.session_scores[uid] = 0
                    if is_correct:
                        self.session_scores[uid] += 1
                        if is_bonus: correct_users.append(uid)
                        await interaction.followup.send(f"✅ {interaction.user.mention} Jawaban benar!", ephemeral=False)
                    else:
                        await interaction.followup.send(f"❌ {interaction.user.mention} Salah! Jawaban: **{q['answer']}**", ephemeral=False)
                return callback

            sample_size = min(15, len(self.music_questions))
            questions = random.sample(self.music_questions, sample_size)
            bonus_winners = []

            for num, q in enumerate(questions, 1):
                is_bonus = num >= 12
                correct_this_round = []
                view = QuizView(q["options"], q["answer"], participants, make_callback(q, is_bonus, correct_this_round))
                embed = discord.Embed(
                    title=f"🎤 SOAL MUSIK #{num}/{sample_size}{' (BONUS)' if is_bonus else ''}",
                    description=f"# {q['question']}",
                    color=discord.Color.gold() if is_bonus else discord.Color.blurple()
                )
                await ctx.send(embed=embed, view=view)
                await view.wait()
                if is_bonus: bonus_winners.extend(correct_this_round)
                await asyncio.sleep(4)

            sorted_scores = sorted(self.session_scores.items(), key=lambda x: x[1], reverse=True)
            self.bank_data = load_json_from_root('data/bank_data.json')
            self.level_data = load_json_from_root('data/level_data.json')
            g_id = str(ctx.guild.id)
            lb_embed = discord.Embed(title="🏆 LEADERBOARD KUIS MUSIK", color=0x1db954)

            rewards = [(50, 150), (30, 100), (20, 50)]
            for rank, (u_id, sc) in enumerate(sorted_scores[:3]):
                u_obj = self.bot.get_user(int(u_id))
                name = u_obj.display_name if u_obj else f"User ({u_id})"
                exp_r, rsw_r = rewards[rank] if rank < len(rewards) else (10, 20)
                self.bank_data.setdefault(u_id, {"balance": 0, "debt": 0})['balance'] += rsw_r
                self.level_data.setdefault(g_id, {}).setdefault(u_id, {"exp": 0, "level": 1})['exp'] += exp_r
                lb_embed.add_field(name=f"#{rank + 1}. {name}", value=f"Skor: **{sc}** (+{rsw_r} RSWN & +{exp_r} EXP)", inline=False)

            save_json_to_root(self.bank_data, 'data/bank_data.json')
            save_json_to_root(self.level_data, 'data/level_data.json')
            await ctx.send(embed=lb_embed)

        finally:
            await self.end_game_cleanup(ctx.channel.id, ctx.channel, 'music')


    async def display_leaderboard(self, ctx, game_title):
        if not self.session_scores: return
        sorted_scores = sorted(self.session_scores.values(), key=lambda x: x.get("score", x.get("correct", 0)), reverse=True)
        embed = discord.Embed(title=f"🏆 Papan Peringkat Sesi {game_title}", color=discord.Color.gold())
        for i, data in enumerate(sorted_scores[:5]):
            user = data['user']
            score = data.get('score', data.get('total_rsw', 0))
            embed.add_field(
                name=f"#{i + 1}. {user.display_name}",
                value=f"💰 **Hadiah RSWN:** +{score}\n✅ **Benar:** {data.get('correct', 0)}\n❌ **Salah:** {data.get('wrong', 0)}",
                inline=False
            )
        await ctx.send(embed=embed)


    @commands.command(name="jawab")
    async def jawab_teka_teki_cmd(self, ctx, *, user_answer: str):
        """Menjawab Teka-Teki Harian bot."""
        if not self.daily_puzzle:
            return await ctx.send("Belum ada Teka-Teki Harian yang aktif untuk hari ini.")
        if ctx.author.id in self.daily_puzzle_solvers:
            return await ctx.send("Kamu sudah berhasil memecahkan teka-teki hari ini!")

        correct_answer = self.daily_puzzle.get('answer', '').strip().lower()
        if user_answer.strip().lower() == correct_answer:
            self.daily_puzzle_solvers.add(ctx.author.id)
            await self.give_rewards_with_bonus_check(ctx.author, ctx.channel)
            try:
                await ctx.message.add_reaction("🎉")
            except Exception:
                pass
            await ctx.send(f"🎉 **Luar Biasa!** {ctx.author.mention} berhasil memecahkan teka-teki harian!")
        else:
            try:
                await ctx.message.add_reaction("❌")
            except Exception:
                pass

    @commands.command(name="adddonasibtn")
    @commands.has_permissions(administrator=True)
    async def add_donation_button_cmd(self, ctx, label: str, url: str):
        if not url.startswith("http://") and not url.startswith("https://"):
            return await ctx.send("❌ URL tidak valid. Harus dimulai dengan `http://` atau `https://`.", ephemeral=True)
        data = load_json_from_root(self.DONATION_BUTTONS_FILE)
        new_button = {"label": label, "url": url}
        for btn in data:
            if btn["label"] == label or btn["url"] == url:
                return await ctx.send(f"❌ Tombol dengan label atau URL yang sama sudah ada: '{label}'.", ephemeral=True)
        data.append(new_button)
        save_json_to_root(data, self.DONATION_BUTTONS_FILE)
        await ctx.send(f"✅ Tombol donasi '{label}' berhasil ditambahkan!")

    @commands.command(name="listdonasibtn")
    @commands.has_permissions(administrator=True)
    async def list_donation_buttons_cmd(self, ctx):
        data = load_json_from_root(self.DONATION_BUTTONS_FILE)
        if not data:
            return await ctx.send("Tidak ada tombol donasi yang terdaftar.")
        embed = discord.Embed(title="💸 Daftar Tombol Donasi", color=discord.Color.blue())
        for i, btn in enumerate(data):
            embed.add_field(name=f"Tombol #{i+1}", value=f"Label: `{btn['label']}`\nURL: <{btn['url']}>", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="removedonasibtn")
    @commands.has_permissions(administrator=True)
    async def remove_donation_button_cmd(self, ctx, index: int):
        data = load_json_from_root(self.DONATION_BUTTONS_FILE)
        if not data or not (1 <= index <= len(data)):
            return await ctx.send(f"❌ Indeks tidak valid.", ephemeral=True)
        removed_button = data.pop(index - 1)
        save_json_to_root(data, self.DONATION_BUTTONS_FILE)
        await ctx.send(f"✅ Tombol donasi '{removed_button['label']}' berhasil dihapus.")


async def setup(bot):
    await bot.add_cog(ArcadeMinigames(bot))
