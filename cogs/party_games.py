import discord
from discord.ext import commands, tasks
import json
import random
import asyncio
import os
from datetime import datetime, time, timedelta
import string
import sys
from collections import Counter

def load_json_from_root(file_path, default_value=None):
    """
    Memuat data JSON dari file yang berada di root direktori proyek bot.
    Menambahkan `default_value` yang lebih fleksibel.
    """
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        full_path = os.path.join(base_dir, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[{datetime.now()}] [DEBUG HELPER] Peringatan: File {full_path} tidak ditemukan. Menggunakan nilai default.")
        if default_value is not None:
            save_json_to_root(default_value, file_path)
            return default_value
        return {}
    except json.JSONDecodeError:
        print(f"[{datetime.now()}] [DEBUG HELPER] Peringatan: File {full_path} rusak (JSON tidak valid). Menggunakan nilai default.")
        if default_value is not None:
            save_json_to_root(default_value, file_path)
            return default_value
        return {}

def save_json_to_root(data, file_path):
    """Menyimpan data ke file JSON di root direktori proyek secara atomik."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    full_path = os.path.join(base_dir, file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    temp_path = f"{full_path}.tmp"
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    os.replace(temp_path, full_path)


class RoleQuantityModal(discord.ui.Modal):
    def __init__(self, game_cog, role_name, current_quantity, total_players, message_to_update_id, channel_id):
        super().__init__(title=f"Atur Jumlah {role_name}")
        self.game_cog = game_cog
        self.role_name = role_name
        self.total_players = total_players
        self.message_to_update_id = message_to_update_id
        self.channel_id = channel_id

        self.quantity_input = discord.ui.TextInput(
            label=f"Jumlah {role_name} (Max: {total_players})",
            placeholder=f"Masukkan jumlah {role_name} (saat ini: {current_quantity})",
            default=str(current_quantity),
            style=discord.TextStyle.short,
            custom_id="role_quantity",
            max_length=2,
            required=True
        )
        self.add_item(self.quantity_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            new_quantity = int(self.quantity_input.value)
            if new_quantity < 0:
                return await interaction.followup.send("Jumlah peran tidak boleh negatif.", ephemeral=True)
            if new_quantity > self.total_players:
                return await interaction.followup.send(f"Jumlah peran melebihi total pemain ({self.total_players}).", ephemeral=True)

            current_config = self.game_cog.global_werewolf_config.setdefault('default_config', {})
            current_roles = current_config.setdefault('roles', {})
            current_roles[self.role_name] = new_quantity
            save_json_to_root(self.game_cog.global_werewolf_config, 'data/global_werewolf_config.json')

            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Jumlah {self.role_name} diatur ke {new_quantity} oleh {interaction.user.display_name}.")

            try:
                channel = self.game_cog.bot.get_channel(self.channel_id)
                if channel:
                    message = await channel.fetch_message(self.message_to_update_id)
                    updated_view = WerewolfRoleSetupView(
                        self.game_cog,
                        self.channel_id,
                        self.total_players,
                        self.game_cog.global_werewolf_config.get('default_config', {})
                    )
                    await message.edit(embed=updated_view.create_embed(), view=updated_view)
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan setup Werewolf di channel {channel.name} diperbarui setelah modal submit.")
            except discord.NotFound:
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan setup Werewolf tidak ditemukan untuk update setelah modal submit.")
            except Exception as e:
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Error update pesan setup Werewolf setelah modal submit: {e}")

            await interaction.followup.send(f"Jumlah **{self.role_name}** berhasil diatur ke `{new_quantity}`.", ephemeral=True)

        except ValueError:
            await interaction.followup.send("Input tidak valid. Harap masukkan angka.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Terjadi kesalahan: {e}", ephemeral=True)


class WerewolfRoleSetupView(discord.ui.View):
    def __init__(self, game_cog, channel_id, total_players, current_config):
        super().__init__(timeout=300)
        self.game_cog = game_cog
        self.channel_id = channel_id
        self.total_players = total_players
        self.current_roles_config = current_config.get('roles', {}).copy()

        self.available_roles = game_cog.werewolf_roles_data.get('roles', {})

        self._add_role_buttons()

        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] WerewolfRoleSetupView diinisialisasi untuk channel {channel_id}.")

    def _add_role_buttons(self):
        for item in list(self.children):
            if isinstance(item, discord.ui.Button) and item.custom_id.startswith("set_role_"):
                self.remove_item(item)

        roles_to_display = [role for role in self.available_roles.keys() if role != "Warga Polos"]
        roles_to_display.sort(key=lambda r: self.game_cog.werewolf_roles_data['roles'][r].get('order', 99))

        current_row = 0
        buttons_in_row = 0
        for i, role_name in enumerate(roles_to_display):
            current_value = self.current_roles_config.get(role_name, 0)
            button = discord.ui.Button(
                label=f"{role_name} ({current_value})",
                style=discord.ButtonStyle.primary,
                custom_id=f"set_role_{role_name}",
                row=current_row
            )
            button.callback = self._role_button_callback
            self.add_item(button)

            buttons_in_row += 1
            if buttons_in_row >= 5:
                current_row += 1
                buttons_in_row = 0
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Role buttons Werewolf ditambahkan.")

    async def _role_button_callback(self, interaction: discord.Interaction):
        role_name = interaction.data['custom_id'].replace("set_role_", "")
        current_quantity = self.current_roles_config.get(role_name, 0)

        message_to_update_id = interaction.message.id

        modal = RoleQuantityModal(
            self.game_cog,
            role_name,
            current_quantity,
            self.total_players,
            message_to_update_id,
            self.channel_id
        )
        await interaction.response.send_modal(modal)

    def calculate_balance(self):
        total_special_roles_count = sum(self.current_roles_config.values())
        werewolf_count = self.current_roles_config.get('Werewolf', 0) + self.current_roles_config.get('Alpha Werewolf', 0) + self.current_roles_config.get('Mata-Mata Werewolf', 0)
        villager_count = self.total_players - total_special_roles_count

        warnings = []
        if total_special_roles_count > self.total_players:
            warnings.append("⚠️ Jumlah peran khusus melebihi total pemain! Kurangi beberapa peran.")
        if werewolf_count == 0 and self.total_players > 0 and self.total_players >= 3:
            warnings.append("⛔ Tidak ada Werewolf! Game mungkin tidak valid atau membosankan.")
        if werewolf_count > 0 and werewolf_count >= (self.total_players / 2):
            warnings.append("⛔ Jumlah Werewolf terlalu banyak (>= 50% pemain)! Game mungkin tidak seimbang.")
        if villager_count < 0:
            warnings.append("⚠️ Jumlah Warga Polos murni negatif! Pastikan total peran khusus tidak melebihi total pemain.")
        if self.total_players < 3:
            warnings.append("⚠️ Jumlah pemain terlalu sedikit untuk distribusi peran yang bermakna.")
        if 3 <= self.total_players <= 8:
            if self.current_roles_config.get('Werewolf', 0) == 0 and self.current_roles_config.get('Alpha Werewolf', 0) == 0: warnings.append("⚠️ Disarankan ada setidaknya 1 Werewolf untuk 3-8 pemain.")
            if self.current_roles_config.get('Dokter', 0) == 0: warnings.append("⚠️ Disarankan ada setidaknya 1 Dokter untuk 3-8 pemain.")
            if self.current_roles_config.get('Peramal', 0) == 0: warnings.append("⚠️ Disarankan ada setidaknya 1 Peramal untuk 3-8 pemain.")


        return villager_count, warnings

    def create_embed(self):
        self.current_roles_config = self.game_cog.global_werewolf_config.get('default_config', {}).get('roles', {}).copy()

        villager_count, warnings = self.calculate_balance()

        embed = discord.Embed(
            title="🐺 Pengaturan Peran Werewolf (Global) 🐺",
            description=f"Total Pemain: **{self.total_players}**\n\nAtur jumlah peran untuk game ini dengan mengklik tombol peran:",
            color=discord.Color.blue()
        )

        roles_text = ""
        sorted_role_names = sorted(
            [role_name for role_name in self.available_roles.keys() if role_name != "Warga Polos"],
            key=lambda r: self.available_roles[r].get('order', 99)
        )

        for role_name in sorted_role_names:
            count = self.current_roles_config.get(role_name, 0)
            roles_text += f"- **{role_name}**: `{count}`\n"
        roles_text += f"- **Warga Polos**: `{max(0, villager_count)}` (Otomatis Dihitung)\n\n"

        if warnings:
            roles_text += "\n" + "\n".join(warnings)
            embed.color = discord.Color.red()
        else:
            embed.color = discord.Color.green()

        embed.add_field(name="Komposisi Peran Saat Ini", value=roles_text, inline=False)


        return embed

    @discord.ui.button(label="Selesai Mengatur", style=discord.ButtonStyle.success, custom_id="finish_role_setup", row=4)
    async def finish_setup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Tombol 'Selesai Mengatur' diklik oleh {interaction.user.display_name}.")
        
        if not interaction.user.guild_permissions.manage_guild:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Bukan admin server, blokir selesai pengaturan.")
            return await interaction.response.send_message("Hanya administrator server yang bisa menyelesaikan pengaturan peran.", ephemeral=True)

        await interaction.response.defer()

        self.current_roles_config = self.game_cog.global_werewolf_config.get('default_config', {}).get('roles', {}).copy()

        villager_count, warnings = self.calculate_balance()
        if warnings and any("⛔" in w for w in warnings):
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Peringatan kritis komposisi peran: {warnings}.")
            await interaction.followup.send("Ada masalah kritis dengan komposisi peran yang dipilih. Mohon perbaiki sebelum melanjutkan.", ephemeral=True)
            return

        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Konfigurasi peran global Werewolf sudah disimpan (oleh modal).")

        for item in self.children:
            item.disabled = True

        embed = interaction.message.embeds[0]
        embed.description = f"**Komposisi peran untuk game ini telah diatur (Global)!**\n\nTotal Pemain: **{self.total_players}**"
        embed.color = discord.Color.green()
        embed.set_footer(text="Host bisa gunakan !ww mulai untuk memulai game!")

        await interaction.message.edit(embed=embed, view=self)
        self.stop()
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pengaturan Werewolf selesai, view dihentikan.")


class TavernPartyGames(commands.Cog, name="Tavern & Party Games"):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = set()

        self.werewolf_join_queues = {}
        self.werewolf_game_states = {}
        self.active_werewolf_setup_messages = {}

        self.wheel_of_fate_config = {}
        self.wheel_of_fate_data = load_json_from_root('data/wheel_of_mad_fate.json', default_value={"players_stats": {}})
        self.wheel_spin_cost = 200

        self.horse_racing_states = {}
        self.horse_racing_data = load_json_from_root('data/horse_racing_data.json', default_value={"horses": []})

        self.global_werewolf_config = load_json_from_root(
            'data/global_werewolf_config.json',
            default_value={
                "default_config": {
                    "roles": {
                        "Werewolf": 1,
                        "Dokter": 1,
                        "Peramal": 1,
                        "Pengawal": 0,
                        "Pemburu": 0,
                        "Penyihir": 0,
                        "Alpha Werewolf": 0,
                        "Penjaga Malam": 0,
                        "Ksatria Suci": 0,
                        "Mata-Mata Werewolf": 0
                    },
                    "image_urls": {
                        "game_start_image_url": "https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/W1.gif",
                        "night_phase_image_url": "https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/W2.gif",
                        "day_phase_image_url": "https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/W3.gif",
                        "night_resolution_image_url": "https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/W4.gif"
                    },
                    "audio_urls": {
                        "game_start_audio_url": "https://github.com/Abogoboga04/OpenAI/raw/main/W1.mp3",
                        "night_phase_audio_url": "https://github.com/Abogoboga04/OpenAI/raw/main/W2.mp3",
                        "day_phase_audio_url": "https://github.com/Abogoboga04/OpenAI/raw/main/W3.mp3"
                    },
                    "min_players": 3,
                    "night_duration_seconds": 90,
                    "day_discussion_duration_seconds": 180,
                    "voting_duration_seconds": 60
                }
            }
        )
        self.werewolf_roles_data = load_json_from_root(
            'data/werewolf_roles.json',
            default_value={
                "roles": {
                    "Werewolf": {"team": "Werewolf", "action_prompt": "Siapa yang ingin kamu bunuh malam ini?", "dm_command": "!bunuh", "can_target_self": False, "emoji": "🐺", "order": 1, "night_action_order": 2, "description": "Tugasmu adalah membunuh para penduduk desa setiap malam hingga jumlahmu sama atau lebih banyak dari mereka.", "goal": "Musnahkan semua penduduk desa!"},
                    "Dokter": {"team": "Village", "action_prompt": "Siapa yang ingin kamu lindungi malam ini?", "dm_command": "!lindungi", "can_target_self": True, "emoji": "⚕️", "order": 2, "night_action_order": 1, "description": "Kamu bisa melindungi satu orang setiap malam agar tidak dibunuh oleh Werewolf.", "goal": "Lindungi penduduk desa dan singkirkan Werewolf!"},
                    "Peramal": {"team": "Village", "action_prompt": "Siapa yang ingin kamu cek perannya malam ini?", "dm_command": "!cek", "can_target_self": True, "emoji": "🔮", "order": 3, "night_action_order": 3, "description": "Setiap malam, kamu bisa memilih satu pemain untuk mengetahui apakah dia Werewolf atau bukan.", "goal": "Temukan Werewolf dan bantu penduduk desa menggantung mereka!"},
                    "Pengawal": {"team": "Village", "action_prompt": "Siapa yang ingin kamu jaga dari hukuman mati siang nanti?", "dm_command": "!jaga", "can_target_self": True, "emoji": "🛡️", "order": 4, "night_action_order": 4, "description": "Kamu bisa melindungi satu pemain dari hukuman gantung di siang hari.", "goal": "Lindungi warga dari keputusan gantung yang salah."},
                    "Pemburu": {"team": "Village", "action_prompt": "Jika kamu mati, siapa yang ingin kamu tembak sebagai balas dendam?", "dm_command": "!tembak", "can_target_self": False, "emoji": "🏹", "order": 5, "night_action_order": None, "description": "Jika kamu dibunuh oleh Werewolf atau digantung oleh desa, kamu bisa memilih satu pemain untuk ditembak mati sebagai balas dendam.", "goal": "Bantu warga menemukan Werewolf, dan bawa satu Werewolf bersamamu jika kamu mati."},
                    "Penyihir": {"team": "Village", "action_prompt": "Pilih ramuanmu: `!racun <nomor_warga>` (bunuh) atau `!penawar <nomor_warga>` (hidupkan)?", "dm_command": "!racun atau !penawar", "can_target_self": True, "emoji": "🧙‍♀️", "order": 6, "night_action_order": 5, "description": "Kamu memiliki satu ramuan racun untuk membunuh siapapun, dan satu ramuan penawar untuk menghidupkan kembali seseorang yang baru saja mati.", "goal": "Gunakan ramuanmu dengan bijak untuk membantu warga menang."},
                    "Alpha Werewolf": {"team": "Werewolf", "action_prompt": "Siapa yang ingin kamu bunuh malam ini? (Kamu adalah pemimpin Werewolf)", "dm_command": "!bunuh", "can_target_self": False, "emoji": "🐺👑", "order": 7, "night_action_order": 2, "description": "Kamu adalah pemimpin Werewolf. Jika kamu mati, Werewolf lain masih bisa beraksi.", "goal": "Pimpin Werewolf untuk memusnahkan semua penduduk desa!"},
                    "Penjaga Malam": {"team": "Village", "action_prompt": "Siapa yang ingin kamu lindungi dari semua aksi peran lain malam ini?", "dm_command": "!jagamalam", "can_target_self": True, "emoji": "👮", "order": 8, "night_action_order": 0, "description": "Kamu bisa melindungi satu orang setiap malam agar tidak menjadi target aksi peran lain (termasuk Werewolf).", "goal": "Jaga keamanan desa di malam hari."},
                    "Ksatria Suci": {"team": "Village", "action_prompt": "Siapa yang ingin kamu lindungi dengan perisaimu malam ini?", "dm_command": "!perisai", "can_target_self": True, "emoji": "⚔️", "order": 9, "night_action_order": 1, "description": "Kamu bisa melindungi satu pemain dari serangan Werewolf. Jika kamu melindungi Werewolf, kamu akan mati.", "goal": "Lindungi warga dari Werewolf, bahkan dengan risiko nyawamu."},
                    "Mata-Mata Werewolf": {"team": "Werewolf", "action_prompt": "Siapa yang ingin kamu intai perannya malam ini?", "dm_command": "!intai", "can_target_self": False, "emoji": "🤫", "order": 10, "night_action_order": 3, "description": "Kamu adalah Werewolf yang bisa mengintai peran satu pemain setiap malam. Kamu tidak bisa membunuh.", "goal": "Dapatkan informasi penting untuk tim Werewolf."},
                    "Warga Polos": {"team": "Village", "action_prompt": None, "dm_command": None, "can_target_self": False, "emoji": "🧑‍🌾", "order": 11, "night_action_order": None, "description": "Kamu adalah penduduk desa biasa. Tujuanmu adalah menemukan Werewolf dan menggantung mereka.", "goal": "Gantung semua Werewolf!"}
                }
            }
        )

        self.dunia_cog = None
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Cog GamesGlobalEvents diinisialisasi.")

    @commands.Cog.listener()
    async def on_ready(self):
        await self.bot.wait_until_ready()

        self.dunia_cog = self.bot.get_cog('DuniaHidup')
        if not self.dunia_cog:
            pass

        

    def cog_unload(self):
        """Dipanggil saat cog dibongkar, membatalkan semua task loop."""
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Cog GamesGlobalEvents sedang dibongkar...")

        for channel_id in list(self.werewolf_game_states.keys()):
            game_state = self.werewolf_game_states.get(channel_id)
            if game_state and game_state.get('voice_client'):
                self.bot.loop.create_task(game_state['voice_client'].disconnect())
            if game_state and 'game_task' in game_state and not game_state['game_task'].done():
                game_state['game_task'].cancel()
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Task Werewolf di channel {channel_id} dibatalkan.")

        for channel_id in list(self.horse_racing_states.keys()):
            game_state = self.horse_racing_states.get(channel_id)
            if game_state and 'game_task' in game_state and not game_state['game_task'].done():
                game_state['game_task'].cancel()
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Task Balapan Kuda di channel {channel_id} dibatalkan.")

        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Cog GamesGlobalEvents berhasil dibongkar.")

    def get_anomaly_multiplier(self):
        """Mengambil multiplier anomali EXP dari DuniaHidup cog jika ada."""
        try:
            if not self.dunia_cog:
                self.dunia_cog = self.bot.get_cog('DuniaHidup')
            if self.dunia_cog and hasattr(self.dunia_cog, 'active_anomaly') and isinstance(self.dunia_cog.active_anomaly, dict):
                if self.dunia_cog.active_anomaly.get('type') == 'exp_boost':
                    return self.dunia_cog.active_anomaly.get('effect', {}).get('multiplier', 1)
        except Exception:
            pass
        return 1

    async def give_rewards_with_bonus_check(self, user: discord.Member, guild_id: int, channel: discord.TextChannel = None, custom_rsw: int = None, custom_exp: int = None):
        """
        Memberikan hadiah RSWN dan EXP kepada pengguna, dengan pengecekan bonus anomali.
        Ini adalah fungsi helper, bukan command.
        """
        anomaly_multiplier = self.get_anomaly_multiplier()

        base_rsw = custom_rsw if custom_rsw is not None else 100
        base_exp = custom_exp if custom_exp is not None else 100

        final_rsw = int(base_rsw * anomaly_multiplier)
        final_exp = int(base_exp * anomaly_multiplier)

        if self.dunia_cog and hasattr(self.dunia_cog, 'give_rewards_base'):
            self.dunia_cog.give_rewards_base(user, guild_id, final_rsw, final_exp)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Hadiah via DuniaHidup: {user.display_name} mendapat {final_rsw} RSWN & {final_exp} EXP.")
        else:
            bank_data = load_json_from_root('data/bank_data.json')
            level_data = load_json_from_root('data/level_data.json')

            user_id_str = str(user.id)
            guild_id_str = str(guild_id)

            bank_data.setdefault(user_id_str, {'balance': 0})['balance'] += final_rsw
            level_data.setdefault(guild_id_str, {}).setdefault(user_id_str, {'exp': 0})['exp'] += final_exp

            save_json_to_root(bank_data, 'data/bank_data.json')
            save_json_to_root(level_data, 'data/level_data.json')
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Hadiah (fallback): {user.display_name} mendapat {final_rsw} RSWN & {final_exp} EXP.")

        if anomaly_multiplier > 1 and channel:
            await channel.send(f"✨ **BONUS ANOMALI!** {user.mention} mendapatkan hadiah yang dilipatgandakan!", delete_after=15)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Reward diberikan: {user.display_name} mendapatkan {final_rsw} RSWN, {final_exp} EXP (multiplier {anomaly_multiplier}).")

    async def start_game_check_global(self, ctx):
        """Memeriksa apakah ada game aktif di channel ini (untuk cog ini saja)."""
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Memeriksa start_game_check_global untuk channel {ctx.channel.name} ({ctx.channel.id}). Active games (this cog): {self.active_games}")
        if ctx.channel.id in self.active_games:
            await ctx.send("Maaf, sudah ada permainan dari grup game global (Werewolf/Roda Takdir/Balapan Kuda) lain di channel ini. Tunggu selesai ya!", ephemeral=True)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Game dari cog ini sudah aktif di channel ini, blokir.")
            return False
        self.active_games.add(ctx.channel.id)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Game ditambahkan ke active_games (this cog). Current: {self.active_games}")
        return True

    async def _check_mimic_attack(self, ctx):
        """Memeriksa apakah ada serangan mimic yang memblokir game di channel ini (dari DuniaHidup)."""
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Memeriksa _check_mimic_attack untuk channel {ctx.channel.name} ({ctx.channel.id}).")
        if self.dunia_cog and hasattr(self.dunia_cog, 'mimic_effect_active_channel_id') and self.dunia_cog.mimic_effect_active_channel_id == ctx.channel.id:
            await ctx.send("💥 **SERANGAN MIMIC!** Permainan tidak bisa dimulai karena mimic sedang mengamuk di channel ini!", ephemeral=True)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] MIMIC ATTACK aktif di channel ini, blokir game.")
            return True
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] MIMIC ATTACK tidak aktif di channel ini.")
        return False

    async def _check_mimic_effect(self, ctx):
        """Memeriksa apakah event mimic yang memengaruhi jawaban sedang aktif di channel ini (dari DuniaHidup)."""
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Memeriksa _check_mimic_effect untuk channel {ctx.channel.name} ({ctx.channel.id}).")
        if self.dunia_cog and hasattr(self.dunia_cog, 'mimic_effect_active_channel_id') and self.dunia_cog.mimic_effect_active_channel_id == ctx.channel.id:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] MIMIC EFFECT pada jawaban aktif di channel ini.")
            return True
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] MIMIC EFFECT pada jawaban tidak aktif di channel ini.")
        return False

    def end_game_cleanup_global(self, channel_id, game_type=None):
        """Membersihkan state game dari cog ini setelah game berakhir."""
        self.active_games.discard(channel_id)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] end_game_cleanup_global dipanggil untuk channel {channel_id}, tipe {game_type}. Active games (this cog): {self.active_games}")

        if game_type == 'werewolf' and channel_id in self.werewolf_game_states:
            game_state = self.werewolf_game_states.get(channel_id)
            if game_state and game_state.get('voice_client'):
                self.bot.loop.create_task(game_state['voice_client'].disconnect())
            if game_state and 'game_task' in game_state and not game_state['game_task'].done():
                game_state['game_task'].cancel()

            if game_state.get('last_role_setup_message') and hasattr(game_state['last_role_setup_message'], 'delete'):
                try:
                    self.bot.loop.create_task(game_state['last_role_setup_message'].delete())
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan setup Werewolf dihapus di channel {channel_id}.")
                except discord.NotFound:
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan setup Werewolf tidak ditemukan saat cleanup, mungkin sudah dihapus manual.")
                    pass
                except Exception as e:
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Error menghapus pesan setup Werewolf: {e}.")

            if game_state.get('werewolf_dm_thread') and isinstance(game_state['werewolf_dm_thread'], discord.Thread):
                try:
                    self.bot.loop.create_task(game_state['werewolf_dm_thread'].delete())
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Thread Werewolf dihapus di channel {channel_id}.")
                except discord.Forbidden:
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Bot tidak punya izin menghapus thread Werewolf di channel {channel_id}.")
                except Exception as e:
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Error menghapus thread Werewolf: {e}.")

            del self.werewolf_game_states[channel_id]
            self.active_werewolf_setup_messages.pop(channel_id, None)
            self.werewolf_join_queues.pop(channel_id, None)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Cleanup Werewolf state untuk channel {channel_id}.")

        if game_type == 'horse_racing' and channel_id in self.horse_racing_states:
            game_state = self.horse_racing_states[channel_id]
            if game_state.get('betting_timer') and not game_state['betting_timer'].done():
                game_state['betting_timer'].cancel()
            if game_state.get('race_timer') and not game_state['race_timer'].done():
                game_state['race_timer'].cancel()
            if game_state.get('game_task') and not game_state['game_task'].done():
                game_state['game_task'].cancel()
            del self.horse_racing_states[channel_id]
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Cleanup Horse Racing state untuk channel {channel_id}.")

    @commands.group(name="ww", invoke_without_command=True, help="Kumpulan perintah untuk game Werewolf. Gunakan `!ww help` untuk melihat semua perintah.")
    async def werewolf_group(self, ctx):
        print(f"[{datetime.now()}] [DEBUG WW] Command !ww (group) dipanggil oleh {ctx.author.display_name}. Subcommand tidak ditentukan.")
        if ctx.invoked_subcommand is None:
            await self.join_werewolf(ctx)

    @werewolf_group.command(name="join", help="Bergabung ke antrean game Werewolf.")
    async def join_werewolf(self, ctx):
        print(f"[{datetime.now()}] [DEBUG WW] Command !ww join dipanggil oleh {ctx.author.display_name} di {ctx.channel.name}.")
        if ctx.channel.id in self.active_games:
            return await ctx.send("Sudah ada game aktif di channel ini. Kamu tidak bisa bergabung sekarang.", ephemeral=True)

        if not ctx.guild:
            return await ctx.send("Werewolf hanya bisa dimainkan di server Discord.", ephemeral=True)

        channel_id = ctx.channel.id

        if channel_id not in self.werewolf_join_queues:
            self.werewolf_join_queues[channel_id] = []

        if ctx.author not in self.werewolf_join_queues[channel_id]:
            self.werewolf_join_queues[channel_id].append(ctx.author)
            current_players = len(self.werewolf_join_queues[channel_id])
            await ctx.send(f"**{ctx.author.display_name}** telah bergabung ke antrean Werewolf! ({current_players} pemain dalam antrean)")
            print(f"[{datetime.now()}] [DEBUG WW] {ctx.author.display_name} bergabung antrean Werewolf di channel {channel_id}.")

            global_config = self.global_werewolf_config.get('default_config', {})
            min_players_for_game = global_config.get('min_players', 3)

            if current_players >= min_players_for_game:
                await ctx.send(f"Antrean mencapai {current_players} pemain! Ketik `!ww mulai` untuk memulai game sekarang!", delete_after=30)
                print(f"[{datetime.now()}] [DEBUG WW] Antrean cukup, minta host untuk memulai.")
        else:
            await ctx.send(f"Kamu sudah ada di antrean Werewolf.", ephemeral=True)

    @werewolf_group.command(name="keluar", help="Keluar dari antrean game Werewolf.")
    async def leave_werewolf(self, ctx):
        print(f"[{datetime.now()}] [DEBUG WW] Command !ww keluar dipanggil oleh {ctx.author.display_name} di {ctx.channel.name}.")
        channel_id = ctx.channel.id
        if channel_id in self.werewolf_join_queues and ctx.author in self.werewolf_join_queues[channel_id]:
            self.werewolf_join_queues[channel_id].remove(ctx.author)
            current_players = len(self.werewolf_join_queues[channel_id])
            await ctx.send(f"**{ctx.author.display_name}** telah keluar dari antrean Werewolf. ({current_players} pemain tersisa)")
            print(f"[{datetime.now()}] [DEBUG WW] {ctx.author.display_name} keluar antrean Werewolf di channel {channel_id}.")
            if current_players == 0:
                del self.werewolf_join_queues[channel_id]
        else:
            await ctx.send("Kamu tidak ada di antrean Werewolf.", ephemeral=True)

    @werewolf_group.command(name="set", help="[Admin Server] Atur peran default untuk game Werewolf global.")
    @commands.has_permissions(manage_guild=True)
    async def set_werewolf_config(self, ctx):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Command !ww set dipanggil oleh {ctx.author.display_name} di channel: {ctx.channel.name} ({ctx.channel.id}).")

        game_state = self.werewolf_game_states.get(ctx.channel.id)
        
        total_players_for_setup = len(self.werewolf_join_queues.get(ctx.channel.id, []))
        if game_state:
            total_players_for_setup = len(game_state['players'])

        if total_players_for_setup == 0:
            total_players_for_setup = self.global_werewolf_config.get('default_config', {}).get('min_players', 3)
            await ctx.send(f"Antrean pemain kosong. Mengatur peran untuk minimal {total_players_for_setup} pemain. Anda bisa mengubah ini nanti.", delete_after=15)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Antrean kosong, mengatur peran untuk minimal {total_players_for_setup} pemain.")

        initial_view = WerewolfRoleSetupView(self, ctx.channel.id, total_players_for_setup, self.global_werewolf_config.get('default_config', {}))
        message = await ctx.send(embed=initial_view.create_embed(), view=initial_view)
        if game_state:
            game_state['last_role_setup_message'] = message
        self.active_werewolf_setup_messages[ctx.channel.id] = message.id
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Menu setup Werewolf dikirim ke channel {ctx.channel.name}.")


    @werewolf_group.command(name="mulai", help="[Host] Memulai game Werewolf dengan pemain di antrean.")
    @commands.cooldown(1, 30, commands.BucketType.channel)
    async def force_start_werewolf_game(self, ctx):
        print(f"[{datetime.now()}] [DEBUG WW] Command !ww mulai dipanggil oleh {ctx.author.display_name} di {ctx.channel.name}.")
        if await self._check_mimic_attack(ctx): return
        if not await self.start_game_check_global(ctx): return

        channel_id = ctx.channel.id
        guild = ctx.guild

        if channel_id not in self.werewolf_join_queues or not self.werewolf_join_queues[channel_id]:
            return await ctx.send("Tidak ada pemain di antrean untuk memulai game. Gunakan `!ww` dulu!", ephemeral=True)

        queued_players = self.werewolf_join_queues[channel_id]

        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("Untuk memulai Werewolf, kamu (host) harus berada di **voice channel**!", ephemeral=True)

        vc_channel = ctx.author.voice.channel

        game_players_raw = [m for m in vc_channel.members if not m.bot and m in queued_players]

        global_config_data = self.global_werewolf_config.get('default_config', {})
        min_players_for_game = global_config_data.get('min_players', 3)

        if len(game_players_raw) < min_players_for_game:
            return await ctx.send(f"Jumlah pemain di voice channel ({len(game_players_raw)}) terlalu sedikit untuk memulai game Werewolf. Minimal {min_players_for_game} pemain aktif!", ephemeral=True)

        confirm_embed = discord.Embed(
            title="Konfirmasi Mulai Game Werewolf",
            description=(f"Akan memulai game Werewolf dengan **{len(game_players_raw)} pemain** yang saat ini berada di voice channel **{vc_channel.name}**.\n\n"
                         "Pemain yang akan bermain:\n" + "\n".join([p.mention for p in game_players_raw])),
            color=discord.Color.orange()
        )
        confirm_embed.set_footer(text="Tekan ✅ untuk konfirmasi, ❌ untuk batal. (30 detik)")

        confirmation_msg = await ctx.send(embed=confirm_embed)
        await confirmation_msg.add_reaction("✅")
        await confirmation_msg.add_reaction("❌")

        try:
            reaction, user = await self.bot.wait_for(
                'reaction_add',
                timeout=30.0,
                check=lambda r, u: u == ctx.author and str(r.emoji) in ["✅", "❌"] and r.message.id == confirmation_msg.id
            )
            if str(reaction.emoji) == "❌":
                await ctx.send("Memulai game Werewolf dibatalkan.", delete_after=10)
                await confirmation_msg.delete()
                self.active_games.discard(channel_id)
                print(f"[{datetime.now()}] [DEBUG WW] Konfirmasi batal oleh host.")
                return
            await confirmation_msg.delete()
            print(f"[{datetime.now()}] [DEBUG WW] Konfirmasi diterima dari host.")
        except asyncio.TimeoutError:
            await ctx.send("Konfirmasi waktu habis, memulai game Werewolf dibatalkan.", delete_after=10)
            await confirmation_msg.delete()
            self.active_games.discard(channel_id)
            print(f"[{datetime.now()}] [DEBUG WW] Konfirmasi waktu habis.")
            return

        self.active_games.add(channel_id)

        if channel_id in self.werewolf_join_queues:
            del self.werewolf_join_queues[channel_id]
            print(f"[{datetime.now()}] [DEBUG WW] Antrean Werewolf dibersihkan.")

        try:
            if ctx.voice_client:
                if ctx.voice_client.channel != vc_channel:
                    await ctx.voice_client.move_to(vc_channel)
                    await ctx.send(f"Bot pindah ke voice channel: **{vc_channel.name}** untuk Werewolf.", delete_after=10)
                    print(f"[{datetime.now()}] [DEBUG WW] Bot pindah VC ke {vc_channel.name}.")
            else:
                await vc_channel.connect()
                await ctx.send(f"Bot bergabung ke voice channel: **{vc_channel.name}** untuk Werewolf.", delete_after=10)
                print(f"[{datetime.now()}] [DEBUG WW] Bot berhasil bergabung ke VC {vc_channel.name}.")

            game_state = self.werewolf_game_states.setdefault(channel_id, {})
            game_state['voice_client'] = ctx.voice_client

        except discord.Forbidden:
            print(f"[{datetime.now()}] [DEBUG WW] Bot tidak punya izin join/pindah VC. Forbidden.")
            self.end_game_cleanup_global(channel_id, game_type='werewolf')
            return await ctx.send("Bot tidak memiliki izin untuk bergabung atau pindah ke voice channel Anda. Pastikan saya memiliki izin `Connect` dan `Speak`.", ephemeral=True)
        except Exception as e:
            print(f"[{datetime.now()}] [DEBUG WW] Error saat bot bergabung/pindah VC: {e}.")
            self.end_game_cleanup_global(channel_id, game_type='werewolf')
            return await ctx.send(f"Terjadi kesalahan saat bot bergabung/pindah ke voice channel: `{e}`", ephemeral=True)

        await ctx.send("Game Werewolf akan dimulai! Bersiaplah...")
        print(f"[{datetime.now()}] [DEBUG WW] Memulai alur game Werewolf di channel {channel_id}...")

        game_state['host'] = ctx.author
        game_state['players'] = {p.id: {'obj': p, 'role': None, 'status': 'alive', 'death_reason': None, 'poison_potion_used': False, 'healing_potion_used': False, 'hunter_target': None} for p in game_players_raw}
        game_state['living_players'] = {p.id for p in game_players_raw}
        game_state['dead_players'] = set()
        game_state['main_channel'] = ctx.channel
        game_state['voice_channel'] = vc_channel
        game_state['phase'] = 'starting'
        game_state['day_num'] = 0
        game_state['killed_this_night'] = None
        game_state['voted_out_today'] = None
        game_state['role_actions_pending'] = {}
        game_state['werewolf_votes'] = {}
        game_state['timers'] = {}
        game_state['vote_message'] = None
        game_state['players_who_voted'] = set()
        game_state['player_map'] = {}
        game_state['reverse_player_map'] = {}
        game_state['werewolf_dm_thread'] = None
        game_state['total_players'] = len(game_players_raw)
        game_state['role_actions_votes'] = {}

        game_task = self.bot.loop.create_task(self._werewolf_game_flow(ctx, channel_id))
        game_state['game_task'] = game_task


    @werewolf_group.command(name="batal", help="[Host/Admin] Batalkan game Werewolf yang sedang berjalan.")
    async def cancel_werewolf_game(self, ctx):
        print(f"[{datetime.now()}] [DEBUG WW] Command !ww batal dipanggil oleh {ctx.author.display_name}.")
        channel_id = ctx.channel.id
        game_state = self.werewolf_game_states.get(channel_id)

        if not game_state:
            return await ctx.send("Tidak ada game Werewolf yang sedang berjalan di channel ini.", ephemeral=True)

        if not (ctx.author.id == game_state['host'].id or ctx.author.guild_permissions.administrator):
            return await ctx.send("Hanya host game atau administrator yang bisa membatalkan game ini.", ephemeral=True)

        await ctx.send("Game Werewolf dibatalkan secara paksa. Dunia kembali damai... untuk sementara.")
        print(f"[{datetime.now()}] [DEBUG WW] Game Werewolf di channel {channel_id} dibatalkan secara paksa.")
        self.end_game_cleanup_global(channel_id, game_type='werewolf')

    @werewolf_group.command(name="status", help="Melihat status game Werewolf saat ini.")
    async def werewolf_status(self, ctx):
        print(f"[{datetime.now()}] [DEBUG WW] Command !ww status dipanggil oleh {ctx.author.display_name}.")
        channel_id = ctx.channel.id
        game_state = self.werewolf_game_states.get(channel_id)

        if not game_state or game_state['phase'] == 'game_over':
            return await ctx.send("Tidak ada game Werewolf yang sedang berjalan di channel ini.", ephemeral=True)

        living_players_mentions = []
        for p_id in game_state['living_players']:
            player_data = game_state['players'].get(p_id)
            if player_data:
                player_member = player_data['obj']
                player_num = game_state['reverse_player_map'].get(p_id, 'N/A')
                living_players_mentions.append(f"`{player_num}` {player_member.display_name} ({player_member.mention})")
            else:
                living_players_mentions.append(f"Pemain tidak ditemukan (ID: {p_id})")

        dead_players_mentions = []
        for p_id in game_state['dead_players']:
            player_data = game_state['players'].get(p_id)
            if player_data:
                player_member = player_data['obj']
                role = player_data['role']
                dead_players_mentions.append(f"☠️ {player_member.display_name} ({role})")
            else:
                dead_players_mentions.append(f"☠️ Pemain tidak ditemukan (ID: {p_id})")

        embed = discord.Embed(
            title="🐺 Status Game Werewolf 🐺",
            description=f"Host: {game_state['host'].mention}\n"
                        f"Fase Saat Ini: **{game_state['phase'].replace('_', ' ').title()}** (Hari {game_state['day_num']})",
            color=discord.Color.purple()
        )

        embed.add_field(name="Pemain Hidup", value="\n".join(living_players_mentions) if living_players_mentions else "Tidak ada.", inline=False)
        embed.add_field(name="Pemain Mati", value="\n".join(dead_players_mentions) if dead_players_mentions else "Tidak ada.", inline=False)

        if game_state['phase'] == 'night':
            embed.set_footer(text=f"Aksi malam akan berakhir dalam {self._get_time_remaining(game_state['timers'].get('night_end_time'))}")
        elif game_state['phase'] == 'day':
            embed.set_footer(text=f"Diskusi siang akan berakhir dalam {self._get_time_remaining(game_state['timers'].get('day_discussion_end_time'))}")
        elif game_state['phase'] == 'voting':
            embed.set_footer(text=f"Voting akan berakhir dalam {self._get_time_remaining(game_state['timers'].get('voting_end_time'))}")

        await ctx.send(embed=embed)
        print(f"[{datetime.now()}] [DEBUG WW] Status game Werewolf dikirim ke channel {ctx.channel.name}.")

    @werewolf_group.command(name="help", help="Menampilkan semua perintah Werewolf dan cara menggunakannya.")
    async def werewolf_help(self, ctx):
        embed = discord.Embed(
            title="📚 Panduan Perintah Werewolf 🐺",
            description="Berikut adalah daftar perintah yang bisa kamu gunakan dalam game Werewolf:",
            color=discord.Color.purple()
        )
        embed.add_field(
            name="Untuk Pemain (di channel utama):",
            value="""
            `!ww` atau `!ww join` - Bergabung ke antrean game Werewolf.
            `!ww keluar` - Keluar dari antrean game.
            `!ww status` - Melihat status game yang sedang berjalan (fase, pemain hidup/mati).
            `!vote <nomor_warga>` - (Hanya saat fase siang) Mengirimkan suara untuk menggantung pemain dengan nomor tertentu. Contoh: `!vote 3`
            """,
            inline=False
        )
        embed.add_field(
            name="Untuk Pemain (di DM dengan bot/Werewolf thread):",
            value="""
            `!bunuh <nomor_warga>` - (Hanya Werewolf biasa/Alpha Werewolf saat malam) Memilih target pembunuhan.
            `!lindungi <nomor_warga>` - (Hanya Dokter saat malam) Memilih pemain untuk dilindungi.
            `!cek <nomor_warga>` - (Hanya Peramal saat malam) Memeriksa peran pemain.
            `!jaga <nomor_warga>` - (Hanya Pengawal saat malam) Melindungi pemain dari hukuman gantung.
            `!tembak <nomor_warga>` - (Hanya Pemburu saat malam) Memilih target yang akan ditembak jika Pemburu mati.
            `!racun <nomor_warga>` - (Hanya Penyihir saat malam) Menggunakan ramuan racun untuk membunuh. (1x pakai)
            `!penawar <nomor_warga>` - (Hanya Penyihir saat malam) Menggunakan ramuan penawar untuk menghidupkan kembali korban Werewolf. (1x pakai)
            `!jagamalam <nomor_warga>` - (Hanya Penjaga Malam saat malam) Melindungi pemain dari semua aksi malam.
            `!perisai <nomor_warga>` - (Hanya Ksatria Suci saat malam) Melindungi pemain dari Werewolf.
            `!intai <nomor_warga>` - (Hanya Mata-Mata Werewolf saat malam) Mengintai peran pemain.
            """,
            inline=False
        )
        embed.add_field(
            name="Untuk Host/Admin:",
            value="""
            `!ww mulai` - Memulai game Werewolf dengan pemain di antrean. Host harus berada di voice channel.
            `!ww batal` - Membatalkan game Werewolf yang sedang berjalan.
            `!ww set` - Mengatur jumlah peran default untuk game Werewolf (hanya admin server).
            `!stopwerewolfaudio` - Menghentikan audio Werewolf yang sedang diputar.
            """,
            inline=False
        )
        embed.set_footer(text="Catatan: Untuk perintah DM, pastikan DM-mu terbuka!")
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if isinstance(message.channel, discord.DMChannel):
            await self._process_dm_werewolf_command(message)
        elif isinstance(message.channel, discord.Thread) and message.channel.name.startswith("Werewolf Den"):
            await self._process_thread_werewolf_command(message)

    async def _process_dm_werewolf_command(self, message):
        """Processes DM commands for Werewolf roles."""
        player_id = message.author.id
        game_state = None
        for channel_id, state in self.werewolf_game_states.items():
            if player_id in state['players'] and state['players'][player_id]['status'] == 'alive':
                game_state = state
                break

        if not game_state:
            return

        player_data = game_state['players'][player_id]
        role_name = player_data['role']
        role_info = self.werewolf_roles_data['roles'].get(role_name, {})

        if game_state['phase'] != 'night':
            return await message.channel.send("Bukan waktunya untuk beraksi! Tunggu hingga malam tiba.")

        content = message.content.lower().strip()
        parts = content.split()

        if len(parts) != 2 or not parts[1].isdigit():
            return await message.channel.send("Format perintah tidak valid. Gunakan: `!<peran> <nomor_warga>`")

        command = parts[0]
        target_num = int(parts[1])

        target_member_obj = game_state['player_map'].get(target_num)
        if not target_member_obj or target_member_obj.id not in game_state['living_players']:
            return await message.channel.send("Nomor warga tidak valid atau warga sudah mati. Pilih dari daftar pemain hidup.")

        target_id = target_member_obj.id

        if not role_info.get('can_target_self', False) and target_id == player_id:
            return await message.channel.send("Kamu tidak bisa menarget dirimu sendiri untuk aksi ini.")

        if role_name in ["Werewolf", "Alpha Werewolf", "Mata-Mata Werewolf"]:
            if isinstance(game_state.get('werewolf_dm_thread'), discord.Thread) and message.channel.id != game_state['werewolf_dm_thread'].id:
                return await message.channel.send(f"Silakan lakukan aksi Werewolf Anda di thread grup Werewolf: <#{game_state['werewolf_dm_thread'].id}>")
            
            if command == '!bunuh' and role_name in ["Werewolf", "Alpha Werewolf"]:
                alpha_ww_exists = False
                for p_id, p_data in game_state['players'].items():
                    if p_data['status'] == 'alive' and p_data['role'] == "Alpha Werewolf":
                        alpha_ww_exists = True
                        break

                if alpha_ww_exists and role_name == "Werewolf":
                    await message.channel.send("Hanya Alpha Werewolf yang bisa membuat keputusan pembunuhan. Silakan diskusikan di thread dan biarkan Alpha Werewolf memilih.")
                    return
                
                game_state['werewolf_votes'][player_id] = target_id
                await message.channel.send(f"Kamu telah memilih untuk membunuh **{target_member_obj.display_name}**.")
                self.log_game_event(f"{message.author.display_name} ({role_name}) memilih untuk membunuh {target_member_obj.display_name}.")
            elif command == '!intai' and role_name == "Mata-Mata Werewolf":
                game_state['role_actions_pending'][player_id] = {role_name: target_id}
                await message.channel.send(f"Kamu telah memilih untuk mengintai **{target_member_obj.display_name}**.")
                self.log_game_event(f"{message.author.display_name} ({role_name}) memilih untuk mengintai {target_member_obj.display_name}.")
            else:
                return await message.channel.send("Perintah tidak valid untuk peran Anda atau fase saat ini.")
            return

        if command == role_info.get('dm_command'):
            if role_name == "Penyihir":
                if parts[0] == '!racun':
                    if player_data['poison_potion_used']:
                        return await message.channel.send("Kamu sudah menggunakan ramuan racunmu.")
                    game_state['role_actions_pending'][player_id] = {role_name: target_id, 'Penyihir_command': 'racun'}
                    await message.channel.send(f"Kamu telah memilih untuk meracuni **{target_member_obj.display_name}**.")
                    self.log_game_event(f"{message.author.display_name} ({role_name}) memilih untuk meracuni {target_member_obj.display_name}.")
                elif parts[0] == '!penawar':
                    if player_data['healing_potion_used']:
                        return await message.channel.send("Kamu sudah menggunakan ramuan penawarmu.")
                    if game_state['killed_this_night'] == target_id and game_state['players'][target_id]['status'] == 'dead' and game_state['players'][target_id]['death_reason'] == 'werewolf':
                        game_state['role_actions_pending'][player_id] = {role_name: target_id, 'Penyihir_command': 'penawar'}
                        await message.channel.send(f"Kamu telah memilih untuk menawar **{target_member_obj.display_name}**.")
                        self.log_game_event(f"{message.author.display_name} ({role_name}) memilih untuk menawar {target_member_obj.display_name}.")
                    else:
                        return await message.channel.send("Ramuan penawarmu tidak berpengaruh karena target tidak dibunuh Werewolf malam ini atau tidak dalam kondisi mati yang bisa diselamatkan.")
                else:
                    return await message.channel.send("Ramuan tidak dikenal. Gunakan `!racun` atau `!penawar`.")
            
            elif command in ["!lindungi", "!cek", "!jaga", "!jagamalam", "!perisai", "!tembak"]:
                game_state['role_actions_pending'][player_id] = {role_name: target_id}
                await message.channel.send(f"Kamu telah memilih **{target_member_obj.display_name}** untuk aksi {role_name}.")
                self.log_game_event(f"{message.author.display_name} ({role_name}) memilih {target_member_obj.display_name}.")
            else:
                await message.channel.send("Perintah tidak valid untuk peran Anda.")
        else:
            await message.channel.send("Perintah tidak valid untuk peran Anda atau fase saat ini. Cek `!ww help`.")
        
        print(f"[{datetime.now()}] [DEBUG WW] Aksi peran DM diproses: {message.author.display_name} ({role_name}) -> {target_member_obj.display_name}.")


    async def _process_thread_werewolf_command(self, message):
        """Processes commands inside the Werewolf private thread."""
        player_id = message.author.id
        thread_channel_id = message.channel.id

        game_state = None
        for channel_id, state in self.werewolf_game_states.items():
            if state.get('werewolf_dm_thread') and state['werewolf_dm_thread'].id == thread_channel_id:
                game_state = state
                break

        if not game_state:
            return

        player_data = game_state['players'].get(player_id)
        if not player_data or player_data['status'] != 'alive' or player_data['role_info'].get('team') != "Werewolf":
            await message.channel.send("Hanya Werewolf yang hidup yang dapat berinteraksi di sini.", ephemeral=True)
            return

        role_name = player_data['role']
        content = message.content.lower().strip()
        parts = content.split()

        if len(parts) != 2 or not parts[1].isdigit():
            return await message.channel.send("Format perintah tidak valid. Gunakan: `!bunuh <nomor_warga>` atau `!intai <nomor_warga>`")

        command = parts[0]
        target_num = int(parts[1])

        target_member_obj = game_state['player_map'].get(target_num)
        if not target_member_obj or target_member_obj.id not in game_state['living_players']:
            return await message.channel.send(f"Nomor warga `{target_num}` tidak valid atau warga sudah mati. Pilih dari daftar pemain hidup.")

        target_id = target_member_obj.id
        
        if game_state['phase'] != 'night':
            return await message.channel.send("Bukan waktunya untuk beraksi! Tunggu hingga malam tiba.")

        if command == '!bunuh' and role_name in ["Werewolf", "Alpha Werewolf"]:
            alpha_ww_exists = False
            for p_id, p_data in game_state['players'].items():
                if p_data['status'] == 'alive' and p_data['role'] == "Alpha Werewolf":
                    alpha_ww_exists = True
                    break

            if alpha_ww_exists and role_name == "Werewolf":
                await message.channel.send("Hanya Alpha Werewolf yang bisa membuat keputusan pembunuhan. Silakan diskusikan di sini dan biarkan Alpha Werewolf memilih.")
                return

            game_state['werewolf_votes'][player_id] = target_id
            await message.add_reaction("✅")
            await message.channel.send(f"**{message.author.display_name}** telah memilih untuk membunuh **{target_member_obj.display_name}**.", delete_after=10)
            self.log_game_event(f"{message.author.display_name} ({role_name}) memilih untuk membunuh {target_member_obj.display_name} di thread.")
        elif command == '!intai' and role_name == "Mata-Mata Werewolf":
            game_state['role_actions_pending'][player_id] = {role_name: target_id}
            await message.add_reaction("✅")
            await message.channel.send(f"**{message.author.display_name}** telah memilih untuk mengintai **{target_member_obj.display_name}**.", delete_after=10)
            self.log_game_event(f"{message.author.display_name} ({role_name}) memilih untuk mengintai {target_member_obj.display_name} di thread.")
        else:
            await message.channel.send("Perintah tidak valid untuk peran Anda di thread ini.", ephemeral=True)
            return

        print(f"[{datetime.now()}] [DEBUG WW] Aksi peran thread diproses: {message.author.display_name} ({role_name}) -> {target_member_obj.display_name}.")

    def _get_time_remaining(self, end_time_str):
        if not end_time_str:
            return "N/A"
        end_time = datetime.fromisoformat(end_time_str)
        time_left = end_time - datetime.utcnow()
        total_seconds = int(time_left.total_seconds())
        if total_seconds <= 0:
            return "Waktu habis!"

        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes} menit {seconds} detik"

    async def _werewolf_game_flow(self, ctx, channel_id):
        print(f"[{datetime.now()}] [DEBUG WW] _werewolf_game_flow dimulai untuk channel {channel_id}.")
        game_state = self.werewolf_game_states[channel_id]
        main_channel = game_state['main_channel']
        global_config = self.global_werewolf_config.get('default_config', {})

        try:
            await self._assign_roles(game_state)

            game_state['phase'] = 'starting'
            await self._send_werewolf_visual(main_channel, "game_start")
            await self._play_werewolf_audio(game_state, "game_start_audio_url")
            await main_channel.send(f"Selamat datang di {main_channel.guild.name} The Werewolf! Setiap pemain telah menerima peran mereka melalui DM.")
            await asyncio.sleep(5)

            while True:
                winner = self._check_win_condition(game_state)
                if winner:
                    print(f"[{datetime.now()}] [DEBUG WW] Kondisi kemenangan terpenuhi di awal ronde: {winner}.")
                    await self._end_game(game_state, winner)
                    break

                game_state['day_num'] += 1

                game_state['phase'] = 'night'
                game_state['killed_this_night'] = None
                game_state['role_actions_pending'] = {}
                game_state['werewolf_votes'] = {}

                await self._send_werewolf_visual(main_channel, "night_phase")
                await self._play_werewolf_audio(game_state, "night_phase_audio_url")
                await main_channel.send(f"🌙 **MALAM HARI {game_state['day_num']} TIBA!** Semua pemain tertidur. Para peran khusus, periksa DM kalian untuk beraksi!")
                print(f"[{datetime.now()}] [DEBUG WW] Fase Malam Hari {game_state['day_num']} dimulai.")

                await self._send_night_action_DMs(game_state)

                night_duration = global_config.get("night_duration_seconds", 60)
                end_time = datetime.utcnow() + timedelta(seconds=night_duration)
                game_state['timers']['night_end_time'] = end_time
                print(f"[{datetime.now()}] [DEBUG WW] Malam Hari {game_state['day_num']} akan berakhir pada: {game_state['timers']['night_end_time']}.")
                try:
                    while datetime.utcnow() < end_time:
                        living_ww = [p for p in game_state['players'].values() if p['status'] == 'alive' and p['role_info'].get('team') == 'Werewolf' and p['role'] in ['Werewolf', 'Alpha Werewolf']]
                        living_special_village = [p for p in game_state['players'].values() if p['status'] == 'alive' and p['role_info'].get('team') == 'Village' and p['role_info'].get('action_prompt')]
                        ww_done = not living_ww or bool(game_state.get('werewolf_votes'))
                        village_done = all(p['obj'].id in game_state.get('role_actions_pending', {}) for p in living_special_village)
                        if ww_done and village_done and (living_ww or living_special_village):
                            await main_channel.send("✨ **Semua tindakan malam telah diterima.** Fajar menyingsing lebih cepat...", delete_after=5)
                            break
                        await asyncio.sleep(2)
                except asyncio.CancelledError:
                    raise

                game_state['phase'] = 'night_resolution'
                print(f"[{datetime.now()}] [DEBUG WW] Memproses aksi malam untuk Hari {game_state['day_num']}.")
                await self._process_night_actions(game_state)

                victims_this_night_for_announcement = []
                for p_id, p_data in game_state['players'].items():
                    if p_data['status'] == 'dead' and p_data.get('death_reason') in ['werewolf', 'witch_poison', 'sacrificed_for_werewolf']:
                        if p_id not in game_state['dead_players']:
                             victims_this_night_for_announcement.append(p_data)
                
                game_state['living_players'].clear()
                game_state['dead_players'].clear()
                for p_id, p_data in game_state['players'].items():
                    if p_data['status'] == 'alive':
                        game_state['living_players'].add(p_id)
                    else:
                        game_state['dead_players'].add(p_id)


                if victims_this_night_for_announcement:
                    await self._send_werewolf_visual(main_channel, "night_resolution")
                    for victim_data in victims_this_night_for_announcement:
                        victim_member = victim_data['obj']
                        victim_role = victim_data['role']
                        death_reason = victim_data['death_reason']
                        
                        death_message = ""
                        if death_reason == 'werewolf':
                            death_message = f"Warga **{victim_member.display_name}** ({victim_member.mention}) ditemukan tak bernyawa! Dia adalah seorang **{victim_role}**."
                        elif death_reason == 'witch_poison':
                            death_message = f"Warga **{victim_member.display_name}** ({victim_member.mention}) tewas karena ramuan racun Penyihir! Dia adalah seorang **{victim_role}**."
                        elif death_reason == 'sacrificed_for_werewolf':
                            death_message = f"**Ksatria Suci** **{victim_member.display_name}** ({victim_member.mention}) gugur melindungi seorang Werewolf! Dia adalah seorang **{victim_role}**."
                        
                        await main_channel.send(f"☀️ **PAGI HARI {game_state['day_num']}!** Teror semalam berakhir... {death_message}")
                        self.log_game_event(f"Pengumuman kematian: {victim_member.display_name} ({victim_role}) mati karena {death_reason}.")
                        
                        if game_state['voice_client']:
                            try:
                                afk_channel = main_channel.guild.afk_channel
                                if afk_channel and victim_member.voice and victim_member.voice.channel:
                                    await victim_member.move_to(afk_channel)
                                else:
                                    await victim_member.edit(mute=True, deafen=True)
                                print(f"[{datetime.now()}] [DEBUG WW] {victim_member.display_name} dipindahkan/dimute-deafen.")
                            except discord.Forbidden:
                                print(f"[{datetime.now()}] [DEBUG WW] Bot tidak punya izin untuk memindahkan/mute {victim_member.display_name}.")
                            except Exception as e:
                                print(f"[{datetime.now()}] [DEBUG WW] Error memindahkan/mute {victim_member.display_name}: {e}")
                else:
                    await self._send_werewolf_visual(main_channel, "day_phase")
                    await main_channel.send(f"☀️ **PAGI HARI {game_state['day_num']}!** Malam berlalu tanpa korban... Keberuntungan masih berpihak pada penduduk!")
                    self.log_game_event("Malam berlalu tanpa korban.")
                
                print(f"[{datetime.now()}] [DEBUG WW] Resolusi malam untuk Hari {game_state['day_num']} selesai.")
                await asyncio.sleep(5)

                winner = self._check_win_condition(game_state)
                if winner:
                    print(f"[{datetime.now()}] [DEBUG WW] Kondisi kemenangan terpenuhi setelah malam: {winner}.")
                    await self._end_game(game_state, winner)
                    break

                game_state['phase'] = 'day'
                game_state['voted_out_today'] = None
                game_state['players_who_voted'] = set()
                game_state['role_actions_votes']['vote'] = {}

                await self._send_werewolf_visual(main_channel, "day_phase")
                await self._play_werewolf_audio(game_state, "day_phase_audio_url")
                await main_channel.send(f"🗣️ **DISKUSI HARI {game_state['day_num']}!** Para penduduk, diskusikan siapa yang harus digantung hari ini. Gunakan `!vote <nomor_warga>`")
                print(f"[{datetime.now()}] [DEBUG WW] Fase Siang Hari {game_state['day_num']} dimulai.")

                day_discussion_duration = global_config.get("day_discussion_duration_seconds", 180)
                voting_duration = global_config.get("voting_duration_seconds", 60)

                day_discussion_end_time = datetime.utcnow() + timedelta(seconds=day_discussion_duration)
                game_state['timers']['day_discussion_end_time'] = day_discussion_end_time.isoformat()

                voting_start_time = day_discussion_end_time - timedelta(seconds=voting_duration)
                game_state['timers']['voting_end_time'] = (day_discussion_end_time).isoformat()

                self.bot.loop.create_task(self._voting_reminder(game_state, voting_start_time))

                try:
                    await asyncio.sleep(day_discussion_duration)
                except asyncio.CancelledError:
                    raise

                game_state['phase'] = 'voting_resolution'
                print(f"[{datetime.now()}] [DEBUG WW] Memproses voting siang untuk Hari {game_state['day_num']}.")
                await self._process_day_vote(game_state)

                if game_state['voted_out_today']:
                    lynched_member_id = game_state['voted_out_today']
                    lynched_player_data = game_state['players'].get(lynched_member_id)

                    if lynched_player_data:
                        lynched_member = lynched_player_data['obj']
                        lynched_role = lynched_player_data['role']
                        await main_channel.send(f"🔥 **KEPUTUSAN HARI INI!** Warga **{lynched_member.display_name}** ({lynched_member.mention}) telah digantung! Dia adalah seorang **{lynched_role}**.")
                        if game_state['voice_client']:
                            try:
                                afk_channel = main_channel.guild.afk_channel
                                if afk_channel and lynched_member.voice and lynched_member.voice.channel:
                                    await lynched_member.move_to(afk_channel)
                                else:
                                    await lynched_member.edit(mute=True, deafen=True)
                                print(f"[{datetime.now()}] [DEBUG WW] {lynched_member.display_name} dipindahkan/dimute-deafen.")
                            except discord.Forbidden:
                                print(f"[{datetime.now()}] [DEBUG WW] Bot tidak punya izin untuk memindahkan/mute {lynched_member.display_name}.")
                            except Exception as e:
                                print(f"[{datetime.now()}] [DEBUG WW] Error memindahkan/mute {lynched_member.display_name}: {e}")
                    else:
                        await main_channel.send(f"🔥 **KEPUTUSAN HARI INI!** Seorang warga telah digantung! (ID: {lynched_member_id})")
                else:
                    await main_channel.send(f"🔥 **KEPUTUSAN HARI INI!** Tidak ada yang digantung hari ini. Para penduduk desa tidak bisa sepakat, atau tidak ada yang mencurigakan...")
                print(f"[{datetime.now()}] [DEBUG WW] Resolusi voting Hari {game_state['day_num']} selesai.")
                await asyncio.sleep(5)

        except asyncio.CancelledError:
            print(f"[{datetime.now()}] [DEBUG WW] Werewolf game flow for channel {channel_id} dibatalkan.")
            await main_channel.send("Game Werewolf dihentikan.")
        except Exception as e:
            print(f"[{datetime.now()}] [DEBUG WW] Werewolf Flow: ERROR fatal di channel {channel_id}: {e}", file=sys.stderr)
            await main_channel.send(f"Terjadi kesalahan fatal pada game Werewolf: `{e}`. Game dihentikan.")
        finally:
            self.end_game_cleanup_global(channel_id, game_type='werewolf')
            print(f"[{datetime.now()}] [DEBUG WW] _werewolf_game_flow selesai atau dibatalkan untuk channel {channel_id}.")

    async def _assign_roles(self, game_state):
        print(f"[{datetime.now()}] [DEBUG WW] Memulai penetapan peran Werewolf.")
        players_list_raw = list(game_state['players'].values())
        random.shuffle(players_list_raw)

        configured_roles_counts = self.global_werewolf_config.get('default_config', {}).get('roles', {})

        role_pool = []
        for role_name, count in configured_roles_counts.items():
            if role_name != "Warga Polos":
                role_pool.extend([role_name] * count)

        villager_count = len(players_list_raw) - len(role_pool)
        if villager_count > 0:
            role_pool.extend(["Warga Polos"] * villager_count)

        random.shuffle(role_pool)

        if len(role_pool) != len(players_list_raw):
            print(f"[{datetime.now()}] [DEBUG WW] Peringatan: Jumlah peran awal ({len(role_pool)}) tidak sesuai jumlah pemain ({len(players_list_raw)}). Menyesuaikan.")
            if len(role_pool) > len(players_list_raw):
                role_pool = random.sample(role_pool, len(players_list_raw))
            while len(role_pool) < len(players_list_raw):
                role_pool.append("Warga Polos")
            print(f"[{datetime.now()}] [DEBUG WW] Peran disesuaikan, jumlah akhir: {len(role_pool)}.")

        for i, player_data in enumerate(players_list_raw):
            player_member = player_data['obj']
            role_name = role_pool[i]

            game_state['players'][player_member.id]['role'] = role_name
            if role_name == "Penyihir":
                game_state['players'][player_member.id]['poison_potion_used'] = False
                game_state['players'][player_member.id]['healing_potion_used'] = False
            elif role_name == "Pemburu":
                game_state['players'][player_member.id]['hunter_target'] = None
            
            game_state['players'][player_member.id]['role_info'] = self.werewolf_roles_data['roles'].get(role_name, {})


            role_info = self.werewolf_roles_data['roles'].get(role_name, {})
            dm_embed = discord.Embed(
                title=f"🐺 Peranmu dalam Werewolf: **{role_name}** {role_info.get('emoji', '')} 🐺",
                description=role_info.get('description', 'Tidak ada deskripsi peran.'),
                color=discord.Color.dark_grey()
            )
            dm_embed.add_field(name="Tujuanmu", value=role_info.get('goal', 'Tujuanmu adalah membantu timmu menang!'), inline=False)

            if role_name in ["Werewolf", "Alpha Werewolf", "Mata-Mata Werewolf"]:
                werewolves_in_game = [
                    p_data['obj'] for p_id, p_data in game_state['players'].items()
                    if p_id != player_member.id and self.werewolf_roles_data['roles'].get(p_data['role'], {}).get('team') == "Werewolf"
                ]

                if werewolves_in_game:
                    pack_list = "\n".join([f"- {pm.display_name} ({pm.mention})" for pm in werewolves_in_game if pm])
                    if pack_list:
                            dm_embed.add_field(name="Rekan Werewolfmu", value=pack_list, inline=False)
                    else:
                            dm_embed.add_field(name="Rekan Werewolfmu", value="Kamu adalah satu-satunya Werewolf yang kesepian.", inline=False)
                else:
                    dm_embed.add_field(name="Rekan Werewolfmu", value="Kamu adalah satu-satunya Werewolf yang kesepian.", inline=False)

            try:
                await player_member.send(embed=dm_embed)
                print(f"[{datetime.now()}] [DEBUG WW] Peran {role_name} dikirim ke DM {player_member.display_name}.")
            except discord.Forbidden:
                print(f"[{datetime.now()}] [DEBUG WW] Gagal DM {player_member.display_name} untuk peran. DM tertutup.")
                await game_state['main_channel'].send(f"⚠️ Gagal mengirim DM peran ke {player_member.mention}. Pastikan DM-mu terbuka!", delete_after=15)

        print(f"[{datetime.now()}] [DEBUG WW] Peran telah ditetapkan: {game_state['players']}")

        game_state['player_map'] = {i+1: p_data['obj'] for i, p_data in enumerate(players_list_raw)}
        game_state['reverse_player_map'] = {p_data['obj'].id: i+1 for i, p_data in enumerate(players_list_raw)}

    async def _send_night_action_DMs(self, game_state):
        print(f"[{datetime.now()}] [DEBUG WW] Mengirim DM aksi malam.")
        main_channel = game_state['main_channel']
        living_players_list_formatted = []

        current_living_players_obj = [game_state['players'][p_id]['obj'] for p_id in game_state['living_players']]
        game_state['player_map'] = {i+1: p for i, p in enumerate(current_living_players_obj)}
        game_state['reverse_player_map'] = {p.id: i+1 for i, p in enumerate(current_living_players_obj)}

        for p_id in game_state['living_players']:
            player_data = game_state['players'].get(p_id)
            if player_data:
                player_member = player_data['obj']
                player_num = game_state['reverse_player_map'].get(p_id, 'N/A')
                living_players_list_formatted.append(f"{player_num}. {player_member.display_name}")

        player_list_text = "\n".join(living_players_list_formatted)
        if not player_list_text:
            player_list_text = "Tidak ada pemain yang hidup."

        werewolves_and_spies_living = [p_data for p_id, p_data in game_state['players'].items()
                                       if p_data['status'] == 'alive' and p_data['role_info'].get('team') == "Werewolf"]

        if werewolves_and_spies_living:
            if not game_state.get('werewolf_dm_thread') or game_state['werewolf_dm_thread'] is False:
                try:
                    thread = await main_channel.create_thread(
                        name=f"Werewolf Den - Hari {game_state['day_num']}",
                        type=discord.ChannelType.private_thread,
                        invitable=False,
                        auto_archive_duration=60
                    )
                    game_state['werewolf_dm_thread'] = thread
                    print(f"[{datetime.now()}] [DEBUG WW] Private thread Werewolf dibuat: {thread.name}.")
                    
                    for ww_data in werewolves_and_spies_living:
                        ww_member = ww_data['obj']
                        await thread.add_user(ww_member)
                    
                    thread_prompt = f"**MALAM HARI {game_state['day_num']}!** Kalian adalah tim Werewolf. Diskusikan dan pilih target pembunuhan kalian. Kirim `!bunuh <nomor_warga>` di sini."
                    if any(p['role'] == "Mata-Mata Werewolf" for p in werewolves_and_spies_living):
                        thread_prompt += f"\nMata-Mata Werewolf bisa menggunakan `!intai <nomor_warga>` di sini."
                    await thread.send(f"{thread_prompt}\n\n**Daftar Pemain Hidup:**\n{player_list_text}")
                    print(f"[{datetime.now()}] [DEBUG WW] Member Werewolf ditambahkan ke thread dan pesan dikirim.")

                except discord.Forbidden:
                    print(f"[{datetime.now()}] [DEBUG WW] Bot tidak punya izin membuat private thread untuk Werewolf. Akan menggunakan DM pribadi.", file=sys.stderr)
                    game_state['werewolf_dm_thread'] = False
                    for ww_data in werewolves_and_spies_living:
                        ww_member = ww_data['obj']
                        dm_channel = await ww_member.create_dm()
                        dm_prompt = f"**MALAM HARI {game_state['day_num']}!** Kamu adalah **{ww_data['role']}**. "
                        if ww_data['role'] in ["Werewolf", "Alpha Werewolf"]:
                            dm_prompt += f"Diskusikan dengan rekanmu (jika ada) siapa yang akan dibunuh. Kemudian, kirim `!bunuh <nomor_warga>` di DM ini.\n\n"
                        elif ww_data['role'] == "Mata-Mata Werewolf":
                            dm_prompt += f"{ww_data['role_info'].get('action_prompt', 'Saatnya beraksi!')} Kirim `!intai <nomor_warga>` di DM ini.\n\n"
                        await dm_channel.send(f"{dm_prompt}**Daftar Pemain Hidup:**\n{player_list_text}")
                        print(f"[{datetime.now()}] [DEBUG WW] DM aksi malam untuk Werewolf ({ww_member.display_name}) dikirim sebagai fallback.")
                except Exception as e:
                    print(f"[{datetime.now()}] [DEBUG WW] Error creating Werewolf thread: {e}. Falling back to DMs.", file=sys.stderr)
                    game_state['werewolf_dm_thread'] = False
                    for ww_data in werewolves_and_spies_living:
                        ww_member = ww_data['obj']
                        dm_channel = await ww_member.create_dm()
                        dm_prompt = f"**MALAM HARI {game_state['day_num']}!** Kamu adalah **{ww_data['role']}**. "
                        if ww_data['role'] in ["Werewolf", "Alpha Werewolf"]:
                            dm_prompt += f"Diskusikan dengan rekanmu (jika ada) siapa yang akan dibunuh. Kemudian, kirim `!bunuh <nomor_warga>` di DM ini.\n\n"
                        elif ww_data['role'] == "Mata-Mata Werewolf":
                            dm_prompt += f"{ww_data['role_info'].get('action_prompt', 'Saatnya beraksi!')} Kirim `!intai <nomor_warga>` di DM ini.\n\n"
                        await dm_channel.send(f"{dm_prompt}**Daftar Pemain Hidup:**\n{player_list_text}")
                        print(f"[{datetime.now()}] [DEBUG WW] DM aksi malam untuk Werewolf ({ww_member.display_name}) dikirim sebagai fallback.")
            elif isinstance(game_state['werewolf_dm_thread'], discord.Thread):
                thread_prompt = f"**MALAM HARI {game_state['day_num']}!** Waktunya beraksi! Diskusikan dan pilih target. Kirim `!bunuh <nomor_warga>`."
                if any(p['role'] == "Mata-Mata Werewolf" for p in werewolves_and_spies_living):
                    thread_prompt += f"\nMata-Mata Werewolf bisa menggunakan `!intai <nomor_warga>` di sini."
                await game_state['werewolf_dm_thread'].send(f"{thread_prompt}\n\n**Daftar Pemain Hidup:**\n{player_list_text}")
                print(f"[{datetime.now()}] [DEBUG WW] Pesan aksi malam dikirim ke thread Werewolf.")

        roles_with_individual_dm_actions = [
            r_data for r_data in self.werewolf_roles_data['roles'].values()
            if r_data.get('night_action_order') is not None and r_data['team'] == "Village"
        ]
        roles_with_individual_dm_actions.sort(key=lambda x: x['night_action_order'])

        for role_data in roles_with_individual_dm_actions:
            role_name = next(k for k, v in self.werewolf_roles_data['roles'].items() if v == role_data)

            players_of_role = [p_data['obj'] for p_id, p_data in game_state['players'].items()
                               if p_data['status'] == 'alive' and p_data['role'] == role_name]

            for player_member in players_of_role:
                try:
                    dm_channel = await player_member.create_dm()
                    if role_name == "Penyihir":
                        player_data = game_state['players'][player_member.id]
                        potion_status = []
                        if not player_data['poison_potion_used']:
                            potion_status.append("Ramuan Racun: SIAP (`!racun <nomor_warga>`)")
                        if not player_data['healing_potion_used']:
                            potion_status.append("Ramuan Penawar: SIAP (`!penawar <nomor_warga>`)")
                        if not potion_status:
                            potion_status.append("Semua ramuanmu sudah habis.")

                        prompt_message = (
                            f"**MALAM HARI {game_state['day_num']}!** Kamu adalah **{role_name}** {role_data.get('emoji', '')}.\n\n"
                            f"**Status Ramuanmu:**\n" + "\n".join(potion_status) + "\n\n"
                            f"**Daftar Pemain Hidup:**\n{player_list_text}"
                        )
                    else:
                        prompt_message = (
                            f"**MALAM HARI {game_state['day_num']}!** Kamu adalah **{role_name}** {role_data.get('emoji', '')}. "
                            f"{role_data.get('action_prompt', 'Saatnya beraksi!')} "
                            f"Kirim `{role_data.get('dm_command', '!aksi')} <nomor_warga>` di DM ini.\n\n"
                            f"**Daftar Pemain Hidup:**\n{player_list_text}"
                        )
                    await dm_channel.send(prompt_message)
                    print(f"[{datetime.now()}] [DEBUG WW] DM aksi malam untuk {role_name} ({player_member.display_name}) dikirim.")
                except discord.Forbidden:
                    print(f"[{datetime.now()}] [DEBUG WW] Gagal DM {player_member.display_name} untuk aksi malam. DM tertutup.")
                    await main_channel.send(f"⚠️ Gagal mengirim DM aksi malam ke {player_member.mention}. Pastikan DM-mu terbuka!", delete_after=15)

    async def send_dm(self, user_id, message, embed=None):
        """Helper to send DM to a user."""
        user = self.bot.get_user(user_id)
        if not user:
            print(f"[{datetime.now()}] [DEBUG WW] Gagal menemukan user {user_id} untuk DM.")
            return
        try:
            dm_channel = await user.create_dm()
            await dm_channel.send(content=message, embed=embed)
            print(f"[{datetime.now()}] [DEBUG WW] DM berhasil dikirim ke {user.display_name}.")
        except discord.Forbidden:
            print(f"[{datetime.now()}] [DEBUG WW] Gagal DM {user.display_name}. DM tertutup.")
        except Exception as e:
            print(f"[{datetime.now()}] [DEBUG WW] Error mengirim DM ke {user.display_name}: {e}")

    def log_game_event(self, event_message):
        """Helper to log game events."""
        print(f"[{datetime.now()}] [GAME LOG] {event_message}")


    async def _process_night_actions(self, game_state):
        print(f"[{datetime.now()}] [DEBUG WW] Memproses aksi malam.")
        main_channel = game_state['main_channel']

        actions_to_process = []
        for player_id, actions_data in game_state['role_actions_pending'].items():
            player_role_name = game_state['players'][player_id]['role']
            target_id = actions_data.get(player_role_name)

            if player_role_name == "Penyihir":
                command_type = actions_data.get('Penyihir_command')
                if command_type:
                    actions_to_process.append({
                        'player_id': player_id,
                        'role_name': player_role_name,
                        'target_id': target_id,
                        'command_type': command_type,
                        'order': self.werewolf_roles_data['roles'][player_role_name].get('night_action_order', 99)
                    })
            else:
                if target_id is None and player_role_name not in ["Werewolf", "Alpha Werewolf", "Mata-Mata Werewolf"]:
                    continue

                actions_to_process.append({
                    'player_id': player_id,
                    'role_name': player_role_name,
                    'target_id': target_id,
                    'order': self.werewolf_roles_data['roles'][player_role_name].get('night_action_order', 99)
                })
        
        werewolf_target_candidates = Counter(game_state['werewolf_votes'].values())
        potential_werewolf_kill_target_id = None
        if werewolf_target_candidates:
            max_votes_ww = 0
            for target_id, count in werewolf_target_candidates.items():
                if count > max_votes_ww:
                    max_votes_ww = count
            
            top_werewolf_targets = [
                target_id for target_id, count in werewolf_target_candidates.items() 
                if count == max_votes_ww
            ]
            potential_werewolf_kill_target_id = random.choice(top_werewolf_targets)
            print(f"[{datetime.now()}] [DEBUG WW] Werewolf memilih target: {game_state['players'].get(potential_werewolf_kill_target_id, {}).get('obj', 'N/A')}.")

        actions_to_process.sort(key=lambda x: x['order'])

        protected_by_guard_id = None
        protected_by_doctor_id = None
        protected_by_knight_id = None
        
        for p_id in game_state['living_players']:
            game_state['players'][p_id]['death_reason'] = None

        for action in [a for a in actions_to_process if a['order'] == 0]:
            guard_player_data = game_state['players'].get(action['player_id'])
            target_player_data = game_state['players'].get(action['target_id'])
            
            if guard_player_data and guard_player_data['status'] == 'alive' and target_player_data and target_player_data['status'] == 'alive':
                protected_by_guard_id = target_player_data['obj'].id
                await self.send_dm(guard_player_data['obj'].id, f"Kamu telah berhasil menjaga **{target_player_data['obj'].display_name}** malam ini.")
                self.log_game_event(f"Penjaga Malam {guard_player_data['obj'].display_name} menjaga {target_player_data['obj'].display_name}.")
            else:
                if guard_player_data and guard_player_data['status'] == 'alive':
                    await self.send_dm(guard_player_data['obj'].id, "Targetmu tidak valid atau sudah mati. Aksimu gagal.")

        for action in [a for a in actions_to_process if a['order'] == 1]:
            acting_player_data = game_state['players'].get(action['player_id'])
            target_player_data = game_state['players'].get(action['target_id'])

            if not acting_player_data or acting_player_data['status'] != 'alive':
                continue

            if not target_player_data or target_player_data['status'] != 'alive':
                await self.send_dm(acting_player_data['obj'].id, f"Targetmu tidak valid atau sudah mati.")
                continue

            if protected_by_guard_id == target_player_data['obj'].id:
                await self.send_dm(acting_player_data['obj'].id, f"Aksimu gagal karena **{target_player_data['obj'].display_name}** dijaga oleh Penjaga Malam.")
                self.log_game_event(f"{acting_player_data['obj'].display_name} mencoba aksi '{action['role_name']}' pada {target_player_data['obj'].display_name}, tapi gagal karena dijaga.")
                continue

            if action['role_name'] == 'Dokter':
                protected_by_doctor_id = target_player_data['obj'].id
                await self.send_dm(acting_player_data['obj'].id, f"Kamu telah melindungi **{target_player_data['obj'].display_name}** malam ini.")
                self.log_game_event(f"Dokter {acting_player_data['obj'].display_name} melindungi {target_player_data['obj'].display_name}.")
            elif action['role_name'] == 'Ksatria Suci':
                protected_by_knight_id = target_player_data['obj'].id
                await self.send_dm(acting_player_data['obj'].id, f"Kamu telah melindungi **{target_player_data['obj'].display_name}** dengan perisaimu malam ini.")
                self.log_game_event(f"Ksatria Suci {acting_player_data['obj'].display_name} melindungi {target_player_data['obj'].display_name}.")

        if potential_werewolf_kill_target_id:
            target_to_kill_data = game_state['players'].get(potential_werewolf_kill_target_id)
            if target_to_kill_data and target_to_kill_data['status'] == 'alive':
                
                if protected_by_guard_id == target_to_kill_data['obj'].id:
                    self.log_game_event(f"Werewolf gagal membunuh {target_to_kill_data['obj'].display_name} karena dilindungi Penjaga Malam.")
                elif protected_by_doctor_id == target_to_kill_data['obj'].id:
                    self.log_game_event(f"Werewolf gagal membunuh {target_to_kill_data['obj'].display_name} karena dilindungi Dokter.")
                    game_state['killed_this_night'] = None
                elif protected_by_knight_id == target_to_kill_data['obj'].id:
                    knight_player_data = game_state['players'].get(protected_by_knight_id)
                    if knight_player_data and target_to_kill_data['role_info']['team'] == 'Werewolf':
                        knight_player_data['status'] = 'dead'
                        knight_player_data['death_reason'] = 'sacrificed_for_werewolf'
                        game_state['killed_this_night'] = None
                        self.log_game_event(f"Ksatria Suci {knight_player_data['obj'].display_name} mati karena melindungi Werewolf {target_to_kill_data['obj'].display_name}.")
                    else:
                        self.log_game_event(f"Werewolf gagal membunuh {target_to_kill_data['obj'].display_name} karena dilindungi Ksatria Suci.")
                        game_state['killed_this_night'] = None
                else:
                    game_state['players'][target_to_kill_data['obj'].id]['status'] = 'dead'
                    game_state['players'][target_to_kill_data['obj'].id]['death_reason'] = 'werewolf'
                    game_state['killed_this_night'] = target_to_kill_data['obj'].id
                    self.log_game_event(f"Werewolf berhasil membunuh {target_to_kill_data['obj'].display_name}.")
            else:
                self.log_game_event(f"Target pembunuhan Werewolf ({potential_werewolf_kill_target_id}) sudah mati atau tidak valid.")
                game_state['killed_this_night'] = None
        else:
            self.log_game_event(f"Tidak ada target pembunuhan yang disepakati oleh Werewolf.")
            game_state['killed_this_night'] = None

        for action in [a for a in actions_to_process if a['order'] == 3]:
            acting_player_data = game_state['players'].get(action['player_id'])
            target_player_data = game_state['players'].get(action['target_id'])

            if not acting_player_data or acting_player_data['status'] != 'alive':
                continue

            if not target_player_data or target_player_data['status'] != 'alive':
                await self.send_dm(acting_player_data['obj'].id, f"Targetmu tidak valid atau sudah mati.")
                continue

            if protected_by_guard_id == target_player_data['obj'].id:
                await self.send_dm(acting_player_data['obj'].id, f"Aksimu gagal karena **{target_player_data['obj'].display_name}** dijaga oleh Penjaga Malam.")
                self.log_game_event(f"{acting_player_data['obj'].display_name} mencoba aksi '{action['role_name']}' pada {target_player_data['obj'].display_name}, tapi gagal karena dijaga.")
                continue

            if action['role_name'] == 'Peramal':
                target_actual_role_name = target_player_data['role']
                is_werewolf = (self.werewolf_roles_data['roles'].get(target_actual_role_name, {}).get('team') == "Werewolf")
                result_text = f"**{target_player_data['obj'].display_name}** adalah seorang **Werewolf**." if is_werewolf else f"**{target_player_data['obj'].display_name}** adalah **bukan Werewolf**."
                await self.send_dm(acting_player_data['obj'].id, f"Hasil ramalanmu: {result_text}")
                self.log_game_event(f"Peramal {acting_player_data['obj'].display_name} meramal {target_player_data['obj'].display_name} ({target_actual_role_name}).")
            elif action['role_name'] == 'Mata-Mata Werewolf':
                target_actual_role_name = target_player_data['role']
                await self.send_dm(acting_player_data['obj'].id, f"Hasil intaianmu: **{target_player_data['obj'].display_name}** adalah seorang **{target_actual_role_name}**.")
                self.log_game_event(f"Mata-Mata Werewolf {acting_player_data['obj'].display_name} mengintai {target_player_data['obj'].display_name} ({target_actual_role_name}).")

        for action in [a for a in actions_to_process if a['order'] == 5]:
            witch_player_data = game_state['players'].get(action['player_id'])
            target_player_data = game_state['players'].get(action['target_id'])

            if not witch_player_data or witch_player_data['status'] != 'alive':
                continue

            if target_player_data is None:
                if action['command_type'] == 'penawar':
                    continue 
                else:
                    await self.send_dm(witch_player_data['obj'].id, "Target untuk ramuan racun tidak valid.")
                    continue

            if protected_by_guard_id == target_player_data['obj'].id:
                await self.send_dm(witch_player_data['obj'].id, f"Aksimu gagal karena **{target_player_data['obj'].display_name}** dijaga oleh Penjaga Malam.")
                self.log_game_event(f"Penyihir {witch_player_data['obj'].display_name} mencoba aksi '{action['command_type']}' pada {target_player_data['obj'].display_name}, tapi gagal karena dijaga.")
                continue

            if action['command_type'] == 'racun':
                if not witch_player_data['poison_potion_used']:
                    if target_player_data['status'] == 'alive':
                        witch_player_data['poison_potion_used'] = True
                        game_state['players'][target_player_data['obj'].id]['status'] = 'dead'
                        game_state['players'][target_player_data['obj'].id]['death_reason'] = 'witch_poison'
                        await self.send_dm(witch_player_data['obj'].id, f"Kamu telah berhasil meracuni **{target_player_data['obj'].display_name}**.")
                        self.log_game_event(f"Penyihir {witch_player_data['obj'].display_name} meracuni {target_player_data['obj'].display_name}.")
                    else:
                        await self.send_dm(witch_player_data['obj'].id, "Target untuk ramuan racun sudah mati atau tidak valid.")
                        self.log_game_event(f"Penyihir {witch_player_data['obj'].display_name} mencoba meracuni target invalid.")
                else:
                    await self.send_dm(witch_player_data['obj'].id, "Kamu sudah menggunakan ramuan racunmu.")
                    self.log_game_event(f"Penyihir {witch_player_data['obj'].display_name} mencoba meracuni tapi ramuan habis.")
            elif action['command_type'] == 'penawar':
                if not witch_player_data['healing_potion_used']:
                    if game_state['killed_this_night'] == target_player_data['obj'].id and \
                       game_state['players'][target_player_data['obj'].id]['status'] == 'dead' and \
                       game_state['players'][target_player_data['obj'].id]['death_reason'] == 'werewolf':
                        
                        witch_player_data['healing_potion_used'] = True
                        game_state['players'][target_player_data['obj'].id]['status'] = 'alive'
                        game_state['players'][target_player_data['obj'].id]['death_reason'] = None
                        
                        game_state['killed_this_night'] = None
                        self.log_game_event(f"Penyihir {witch_player_data['obj'].display_name} menghidupkan kembali {target_player_data['obj'].display_name}.")
                        await self.send_dm(witch_player_data['obj'].id, f"Kamu telah berhasil menghidupkan kembali **{target_player_data['obj'].display_name}**.")
                    else:
                        await self.send_dm(witch_player_data['obj'].id, "Ramuan penawarmu tidak berpengaruh karena target tidak dibunuh Werewolf malam ini atau tidak dalam kondisi mati yang bisa diselamatkan.")
                        self.log_game_event(f"Penyihir {witch_player_data['obj'].display_name} mencoba menawar {target_player_data['obj'].display_name} tapi gagal.")
                else:
                    await self.send_dm(witch_player_data['obj'].id, "Kamu sudah menggunakan ramuan penawarmu.")
                    self.log_game_event(f"Penyihir {witch_player_data['obj'].display_name} mencoba menawar tapi ramuan habis.")
        

        print(f"[{datetime.now()}] [DEBUG WW] Pemrosesan aksi malam selesai.")


    @commands.command(name="vote")
    async def werewolf_vote_cmd(self, ctx, target_num: int):
        print(f"[{datetime.now()}] [DEBUG WW] !vote command dipanggil oleh {ctx.author.display_name} di {ctx.channel.name}.")
        channel_id = ctx.channel.id
        game_state = self.werewolf_game_states.get(channel_id)

        if not game_state or game_state['phase'] not in ['day', 'voting']:
            return await ctx.send("Tidak ada game Werewolf yang aktif, atau bukan fase diskusi/voting.", ephemeral=True)

        player_data = game_state['players'].get(ctx.author.id)
        if not player_data or player_data['status'] != 'alive':
            return await ctx.send("Kamu sudah mati dan tidak bisa memilih.", ephemeral=True)

        target_member_obj = game_state['player_map'].get(target_num)
        if not target_member_obj:
            return await ctx.send(f"Warga dengan nomor `{target_num}` tidak ditemukan. Pilih warga yang hidup dari daftar.", ephemeral=True)
            
        target_player_data = game_state['players'].get(target_member_obj.id)
        if not target_player_data or target_player_data['status'] != 'alive':
            return await ctx.send(f"Warga **{target_member_obj.display_name}** (`{target_num}`) sudah mati. Pilih warga yang hidup dari daftar.", ephemeral=True)

        if target_member_obj.id == ctx.author.id:
            return await ctx.send("Kamu tidak bisa memilih dirimu sendiri untuk digantung!", ephemeral=True)

        game_state['role_actions_votes'].setdefault('vote', {})
        game_state['role_actions_votes']['vote'][ctx.author.id] = target_member_obj.id
        game_state['players_who_voted'].add(ctx.author.id)

        await ctx.send(f"✅ **{ctx.author.display_name}** telah memilih untuk menggantung **{target_member_obj.display_name}**.", delete_after=5)
        print(f"[{datetime.now()}] [DEBUG WW] {ctx.author.display_name} memilih untuk menggantung {target_member_obj.display_name}.")

    async def _voting_reminder(self, game_state, voting_start_time):
        main_channel = game_state['main_channel']
        while datetime.utcnow() < voting_start_time:
            await asyncio.sleep(10)
            if game_state['phase'] not in ['day', 'voting']:
                return

        if game_state['phase'] == 'day':
            game_state['phase'] = 'voting'
            await main_channel.send("🔔 **WAKTU VOTING!** Kalian punya waktu singkat untuk memilih siapa yang akan digantung. Gunakan `!vote <nomor_warga>` sekarang!")

        voting_end_time = datetime.fromisoformat(game_state['timers']['voting_end_time'])
        while datetime.utcnow() < voting_end_time:
            time_left = voting_end_time - datetime.utcnow()
            total_seconds = int(time_left.total_seconds())
            if total_seconds <= 0: break

            minutes, seconds = divmod(total_seconds, 60)
            if minutes < 1 and seconds % 10 == 0:
                await main_channel.send(f"⏳ **{seconds} detik** tersisa untuk voting!", delete_after=10)
            elif minutes > 0 and minutes % 1 == 0 and seconds == 0:
                    await main_channel.send(f"⏳ **{minutes} menit** tersisa untuk voting!", delete_after=10)
            await asyncio.sleep(min(10, total_seconds if total_seconds > 0 else 1))

    async def _process_day_vote(self, game_state):
        print(f"[{datetime.now()}] [DEBUG WW] Memproses voting siang.")
        main_channel = game_state['main_channel']

        votes = game_state['role_actions_votes'].get('vote', {})

        if not votes:
            game_state['voted_out_today'] = None
            print(f"[{datetime.now()}] [DEBUG WW] Tidak ada vote siang.")
            return

        target_counts = Counter()
        for voter_id, target_id in votes.items():
            if voter_id in game_state['living_players']:
                target_counts[target_id] += 1

        if not target_counts:
            game_state['voted_out_today'] = None
            print(f"[{datetime.now()}] [DEBUG WW] Tidak ada vote valid dari pemain hidup.")
            return

        max_votes = 0
        potential_lynch_targets = []
        for target_id, count in target_counts.items():
            if count > max_votes:
                max_votes = count
                potential_lynch_targets = [target_id]
            elif count == max_votes:
                potential_lynch_targets.append(target_id)

        lynched_player_id = random.choice(potential_lynch_targets)
        print(f"[{datetime.now()}] [DEBUG WW] Target lynch terpilih: {lynched_player_id} dengan {max_votes} suara.")

        guard_target_id = None
        for p_id, p_data in game_state['players'].items():
            if p_data['status'] == 'alive' and p_data['role'] == 'Pengawal':
                if p_id in game_state['role_actions_pending'] and 'Pengawal' in game_state['role_actions_pending'][p_id]:
                    guard_target_id = game_state['role_actions_pending'][p_id]['Pengawal']
                    break

        if lynched_player_id == guard_target_id:
            guarded_member = game_state['players'].get(lynched_player_id, {}).get('obj')
            if guarded_member:
                await main_channel.send(f"🛡️ **{guarded_member.display_name}** diselamatkan dari hukuman mati oleh seorang Pengawal misterius!")
                self.log_game_event(f"{guarded_member.display_name} diselamatkan oleh Pengawal dari hukuman gantung.")
            game_state['voted_out_today'] = None
        else:
            game_state['voted_out_today'] = lynched_player_id
            player_data_lynched = game_state['players'].get(lynched_player_id)
            if player_data_lynched:
                player_data_lynched['status'] = 'dead'
                player_data_lynched['death_reason'] = 'lynched'
                game_state['living_players'].discard(lynched_player_id)
                game_state['dead_players'].add(lynched_player_id)
                self.log_game_event(f"{player_data_lynched['obj'].display_name} dilynch.")

    def _check_win_condition(self, game_state):
        living_werewolves = {p_id for p_id, p_data in game_state['players'].items() if p_data['status'] == 'alive' and p_data['role_info'].get('team') == "Werewolf"}
        living_villagers = {p_id for p_id, p_data in game_state['players'].items() if p_data['status'] == 'alive' and p_data['role_info'].get('team') == "Village"}

        print(f"[{datetime.now()}] [DEBUG WW] Cek kondisi kemenangan. WW hidup: {len(living_werewolves)}, Warga hidup: {len(living_villagers)}.")

        if not living_werewolves and len(living_villagers) > 0:
            print(f"[{datetime.now()}] [DEBUG WW] Kondisi menang: Desa menang (semua WW mati).")
            return "Village"

        if len(living_werewolves) > 0 and len(living_werewolves) >= len(living_villagers):
            print(f"[{datetime.now()}] [DEBUG WW] Kondisi menang: Werewolf menang (jumlah WW >= jumlah Warga).")
            return "Werewolf"

        if not living_villagers and len(living_werewolves) > 0:
            print(f"[{datetime.now()}] [DEBUG WW] Kondisi menang: Werewolf menang (semua warga mati, WW masih ada).")
            return "Werewolf"

        print(f"[{datetime.now()}] [DEBUG WW] Belum ada kondisi kemenangan terpenuhi. (WW: {len(living_werewolves)}, Warga: {len(living_villagers)})")
        return None

    async def _end_game(self, game_state, winner):
        print(f"[{datetime.now()}] [DEBUG WW] _end_game dipanggil. Pemenang: {winner}.")
        main_channel = game_state['main_channel']
        game_state['phase'] = 'game_over'

        players_to_check_hunter = list(game_state['players'].keys())
        for player_id in players_to_check_hunter:
            player_data = game_state['players'].get(player_id)
            if player_data and player_data['status'] == 'dead' and player_data['role'] == 'Pemburu':
                hunter_target_id = player_data.get('hunter_target')
                if hunter_target_id:
                    target_player_data = game_state['players'].get(hunter_target_id)
                    if target_player_data and target_player_data['status'] == 'alive':
                        target_player_data['status'] = 'dead'
                        target_player_data['death_reason'] = 'hunter_revenge'
                        game_state['living_players'].discard(hunter_target_id)
                        game_state['dead_players'].add(hunter_target_id)
                        await main_channel.send(f"🔫 Sebagai balas dendam, Pemburu **{player_data['obj'].display_name}** menembak mati **{target_player_data['obj'].display_name}**!")
                        self.log_game_event(f"Pemburu {player_data['obj'].display_name} menembak mati {target_player_data['obj'].display_name} sebagai balas dendam.")
                        if game_state['voice_client'] and target_player_data['obj'].voice and target_player_data['obj'].voice.channel:
                               try:
                                   await target_player_data['obj'].move_to(main_channel.guild.afk_channel or None)
                               except discord.Forbidden:
                                   pass
                               except Exception as e:
                                   print(f"[{datetime.now()}] [DEBUG WW] Error memindahkan korban Pemburu: {e}")
                    else:
                        await main_channel.send(f"Pemburu **{player_data['obj'].display_name}** mencoba menembak, tetapi targetnya tidak valid atau sudah mati.")
                        self.log_game_event(f"Pemburu {player_data['obj'].display_name} mencoba menembak target invalid.")
                else:
                    await main_channel.send(f"Pemburu **{player_data['obj'].display_name}** mati, tetapi tidak menembak siapapun.")
                    self.log_game_event(f"Pemburu {player_data['obj'].display_name} mati tanpa menembak.")
        
        final_winner = self._check_win_condition(game_state)
        if final_winner:
            winner = final_winner


        if winner == "Werewolf":
            embed = discord.Embed(
                title="🐺 Para Werewolf Berjaya! 🐺",
                description="Kegelapan menyelimuti desa. Para Werewolf telah menguasai dan memangsa semua penduduk!",
                color=discord.Color.dark_red()
            )
            embed.set_image(url=self.global_werewolf_config['default_config']['image_urls'].get('night_phase_image_url'))
        else:
            embed = discord.Embed(
                title="🌟 Penduduk Desa Selamat! 🌟",
                description="Para penduduk telah bersatu dan berhasil mengusir semua Werewolf dari desa!",
                color=discord.Color.gold()
            )
            embed.set_image(url=self.global_werewolf_config['default_config']['image_urls'].get('day_phase_image_url'))

        await main_channel.send(embed=embed)
        await asyncio.sleep(3)

        final_roles_text = ""
        for player_id in game_state['players']:
            player_data = game_state['players'][player_id]
            member = player_data['obj']
            role = player_data['role']
            status = "HIDUP" if player_data['status'] == 'alive' else "MATI"
            
            if member:
                player_num = game_state['reverse_player_map'].get(player_id, '?')
                final_roles_text += f"**{player_num}. {member.display_name}** ({role}) - {status}\n"

        final_roles_embed = discord.Embed(
            title="📜 Ringkasan Akhir Permainan 📜",
            description=final_roles_text,
            color=discord.Color.greyple()
        )
        await main_channel.send(embed=final_roles_embed)

        if game_state.get('voice_client'):
            await game_state['voice_client'].disconnect()
            game_state['voice_client'] = None
            print(f"[{datetime.now()}] [DEBUG WW] Bot disconnect dari VC.")

        for player_id in game_state['players']:
            player_data = game_state['players'][player_id]
            player = player_data['obj']
            if not player:
                print(f"[{datetime.now()}] [DEBUG WW] Pemain {player_id} tidak ditemukan untuk hadiah.")
                continue

            player_role = player_data['role']
            is_living = player_data['status'] == 'alive'

            player_team_won = False
            player_role_data = self.werewolf_roles_data['roles'].get(player_role, {})
            if winner == "Werewolf" and player_role_data.get('team') == "Werewolf":
                player_team_won = True
            elif winner == "Village" and player_role_data.get('team') == "Village":
                player_team_won = True

            if player_team_won:
                if is_living:
                    await self.give_rewards_with_bonus_check(player, main_channel.guild.id, main_channel, custom_rsw=500, custom_exp=300)
                    print(f"[{datetime.now()}] [DEBUG WW] {player.display_name} (HIDUP, TIM MENANG) mendapat hadiah penuh.")
                else:
                    await self.give_rewards_with_bonus_check(player, main_channel.guild.id, main_channel, custom_rsw=100, custom_exp=50)
                    print(f"[{datetime.now()}] [DEBUG WW] {player.display_name} (MATI, TIM MENANG) mendapat hadiah parsial.")
            else:
                await self.give_rewards_with_bonus_check(player, main_channel.guild.id, main_channel, custom_rsw=50, custom_exp=25)
                print(f"[{datetime.now()}] [DEBUG WW] {player.display_name} (TIM KALAH) mendapat hadiah partisipasi.")

        print(f"[{datetime.now()}] [DEBUG WW] Game berakhir di channel {game_state['main_channel'].name}. Pemenang: {winner}.")

        donasi_embed = discord.Embed(
            title="✨ Suka dengan permainannya? Dukung kami! ✨",
            description=(
                "Pengembangan bot ini membutuhkan waktu dan usaha. "
                "Setiap dukungan kecil dari Anda sangat berarti untuk menjaga bot ini tetap aktif "
                "dan menghadirkan fitur-fitur baru yang lebih seru!\n\n"
                "Terima kasih telah bermain!"
            ),
            color=discord.Color.gold()
        )
        donasi_view = discord.ui.View()
        donasi_view.add_item(discord.ui.Button(label="Bagi Bagi (DANA/Gopay/OVO)", style=discord.ButtonStyle.url, url="https://bagibagi.co/Rh7155"))
        donasi_view.add_item(discord.ui.Button(label="Saweria (All Payment Method)", style=discord.ButtonStyle.url, url="https://saweria.co/RH7155"))

        await main_channel.send(embed=donasi_embed, view=donasi_view)
        print(f"[{datetime.now()}] [DEBUG WW] Pesan donasi dikirim di akhir game Werewolf.")


    async def _send_werewolf_visual(self, channel: discord.TextChannel, phase: str):
        print(f"[{datetime.now()}] [DEBUG WW] Mengirim visual Werewolf untuk fase: {phase} di channel {channel.name}.")
        global_config = self.global_werewolf_config.get('default_config', {})
        image_urls = global_config.get('image_urls', {})

        visual_url = None
        title = ""
        description = ""
        color = discord.Color.dark_purple()

        if phase == "game_start":
            visual_url = image_urls.get('game_start_image_url', "https://i.imgur.com/Gj3H2a4.gif")
            title = "🐺 Game Werewolf Dimulai! 🐺"
            description = "Selamat datang di desa yang diserang Werewolf. Setiap pemain telah menerima peran mereka di DM."
            color = discord.Color.blue()
        elif phase == "night_phase":
            visual_url = image_urls.get('night_phase_image_url', "https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/W2.gif")
            title = "🌙 Malam Telah Tiba! 🌙"
            description = "Para penduduk desa tertidur. Peran-peran malam, saatnya beraksi di DM kalian!"
            color = discord.Color.dark_blue()
        elif phase == "day_phase":
            visual_url = image_urls.get('day_phase_image_url', "https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/W3.gif")
            title = "☀️ Pagi Telah Datang! ☀️"
            description = "Teror semalam telah berakhir. Waktunya berdiskusi dan mencari tahu siapa pembunuhnya!"
            color = discord.Color.orange()
        elif phase == "night_resolution":
            visual_url = image_urls.get('night_resolution_image_url', "https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/W4.gif")
            title = "💔 Korban Ditemukan!💔"
            description = "Keheningan pagi dipecah oleh penemuan jasad. Siapa yang menjadi korban tak berdosa ini?"
            color = discord.Color.dark_red()

        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )

        if visual_url and visual_url.lower().endswith(('.gif', '.png', '.jpg', '.jpeg')):
            embed.set_image(url=visual_url)
            await channel.send(embed=embed)
            print(f"[{datetime.now()}] [DEBUG WW] Visual Werewolf dengan URL {visual_url} dikirim.")
        else:
            await channel.send(embed=embed)
            if visual_url:
                await channel.send("ℹ️ URL gambar yang diberikan tidak valid atau bukan format gambar/GIF yang didukung untuk fase ini. Mengirim pesan tanpa gambar.")
                print(f"[{datetime.now()}] [DEBUG WW] URL visual Werewolf tidak valid: {visual_url}.")
            else:
                await channel.send("ℹ️ URL gambar untuk fase ini belum diatur.")
                print(f"[{datetime.now()}] [DEBUG WW] URL visual Werewolf tidak diatur untuk fase {phase}.")


    async def _play_werewolf_audio(self, game_state, audio_type: str):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Mencoba memutar audio Werewolf: {audio_type}.")
        voice_client = game_state.get('voice_client')
        if not voice_client:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Tidak ada voice client aktif untuk audio Werewolf.")
            return

        global_config = self.global_werewolf_config.get('default_config', {})
        audio_urls = global_config.get('audio_urls', {})
        audio_url = audio_urls.get(audio_type)

        if audio_url:
            try:
                if voice_client.is_playing() or voice_client.is_paused():
                    voice_client.stop()
                
                source = discord.FFmpegOpusAudio(audio_url, before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", options="-vn")
                
                voice_client.play(source, after=lambda e: print(f'[{datetime.now()}] [DEBUG GLOBAL EVENTS] Player error in Werewolf audio: {e}') if e else None)
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Audio Werewolf '{audio_type}' berhasil diputar.")
            except Exception as e:
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Gagal memutar audio Werewolf '{audio_type}': {e}.", file=sys.stderr)
                await game_state['main_channel'].send(f"⚠️ Maaf, gagal memutar audio untuk fase ini: `{e}`. Pastikan FFmpeg terinstal dan berfungsi serta URL audio valid.")
        else:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] URL audio untuk '{audio_type}' tidak diatur.")


    @commands.command(name="stopwerewolfaudio", help="Hentikan audio Werewolf yang sedang diputar.")
    async def stop_werewolf_audio(self, ctx):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Command !stopwerewolfaudio dipanggil oleh {ctx.author.display_name}.")
        channel_id = ctx.channel.id
        game_state = self.werewolf_game_states.get(channel_id)
        if not game_state or (ctx.author.id != game_state.get('host', None).id and not ctx.author.guild_permissions.manage_channels):
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !stopwerewolfaudio: Bukan host atau moderator, blokir.")
            return await ctx.send("Hanya host game Werewolf atau moderator yang bisa menghentikan audio.", ephemeral=True)

        voice_client = game_state.get('voice_client')
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            await ctx.send("Audio Werewolf dihentikan.")
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Audio Werewolf dihentikan di channel {ctx.channel.name}.")
        else:
            await ctx.send("Tidak ada audio Werewolf yang sedang diputar.")
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Tidak ada audio Werewolf yang diputar di channel {ctx.channel.name}.")

    @commands.command(name="balapan", aliases=['race'], help="Mulai sesi taruhan Balapan Kuda!")
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def start_horse_race(self, ctx):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Command !balapan dipanggil oleh {ctx.author.display_name} di channel: {ctx.channel.name} ({ctx.channel.id}).")
        if await self._check_mimic_attack(ctx): return
        if not await self.start_game_check_global(ctx): return

        channel_id = ctx.channel.id

        self.horse_racing_states[channel_id] = {
            'status': 'betting',
            'bets': {},
            'horses': [],
            'race_message': None,
            'betting_timer': None,
            'race_timer': None,
            'game_task': None,
            'track_length': 20,
            'betting_duration': 30,
            'odds': {}
        }
        race_state = self.horse_racing_states[channel_id]

        horses_data = load_json_from_root('data/horse_racing_data.json', default_value={"horses": self._get_default_horses()})['horses']

        if len(horses_data) < 5:
            horses_to_race = horses_data
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Data kuda kurang dari 5, menggunakan semua yang ada ({len(horses_data)} kuda).")
        else:
            horses_to_race = random.sample(horses_data, 5)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Memilih 5 kuda acak.")

        total_speed_mod = sum(h.get('speed_mod', 1.0) for h in horses_to_race)
        base_odds_multiplier = 4.0

        for i, horse in enumerate(horses_to_race):
            horse['id'] = i + 1
            horse['position'] = 0.0
            horse['emoji'] = horse.get('emoji', '🐎')
            race_state['horses'].append(horse)

            speed_mod = horse.get('speed_mod', 1.0)
            if speed_mod == 0: speed_mod = 0.1

            calculated_odds = (total_speed_mod / speed_mod) / (len(horses_to_race) / base_odds_multiplier)

            min_odds = 1.2
            max_odds = 5.0
            race_state['odds'][horse['id']] = max(min_odds, min(max_odds, calculated_odds))

        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Inisialisasi state untuk channel {channel_id} dengan odds dinamis.")

        betting_embed = discord.Embed(
            title="🐎 Balapan Kuda Dimulai!🐎",
            description=f"Waktunya memasang taruhan! Kamu punya **{race_state['betting_duration']} detik** untuk bertaruh.\n\n"
                        f"**Taruhan Saat Ini:**\n" + self._get_current_bets_text(race_state['bets'], race_state['horses']),
            color=discord.Color.blue()
        )
        betting_embed.add_field(name="Kuda yang Berkompetisi", value=self._get_horse_list_text(race_state['horses'], race_state['odds']), inline=False)
        betting_embed.add_field(name="Cara Bertaruh", value="Gunakan `!taruhan <jumlah_rsw> <nomor_kuda>`\nContoh: `!taruhan 100 3` (bertaruh 100 RSWN pada Kuda #3)", inline=False)
        betting_embed.set_footer(text="Taruhan ditutup dalam...")
        betting_embed.set_image(url="https://media.giphy.com/media/l4FGJm7hXG1r0J0I/giphy.gif")

        race_state['race_message'] = await ctx.send(embed=betting_embed)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Pesan taruhan dikirim.")

        race_state['betting_timer'] = self.bot.loop.create_task(self._betting_countdown(ctx, channel_id))
        race_state['game_task'] = self.bot.loop.create_task(self._horse_race_flow(ctx, channel_id))


    def _get_default_horses(self):
        """Mengembalikan daftar kuda default."""
        return [
            {"name": "Shadowfax", "emoji": "🐎", "speed_mod": 1.1, "description": "Kuda legendaris yang cepat seperti angin."},
            {"name": "Black Beauty", "emoji": "🏇", "speed_mod": 1.0, "description": "Kuda klasik dengan stamina luar biasa."},
            {"name": "Spirit", "emoji": "🐴", "speed_mod": 1.05, "description": "Kuda liar yang tak kenal lelah."},
            {"name": "Thunderhoof", "emoji": "🦄", "speed_mod": 0.95, "description": "Kuda perkasa dengan kekuatan guntur."},
            {"name": "Starlight", "emoji": "💫", "speed_mod": 1.0, "description": "Kuda elegan yang bersinar di lintasan."},
            {"name": "Nightmare", "emoji": "👻", "speed_mod": 0.9, "description": "Kuda misterius yang sulit ditebak."},
            {"name": "Pegasus", "emoji": "🕊️", "speed_mod": 1.15, "description": "Kuda bersayap, favorit para dewa."},
            {"name": "Comet", "emoji": "🌠", "speed_mod": 1.0, "description": "Kuda lincah secepat komet."},
            {"name": "Ironhide", "emoji": "🧲", "speed_mod": 0.85, "description": "Kuda baja yang sangat tangguh, tapi sedikit lambat."},
            {"name": "Flash", "emoji": "⚡", "speed_mod": 1.2, "description": "Kuda tercepat, jarang terlihat kalah!"}
        ]

    def _get_horse_list_text(self, horses, odds):
        """Membuat teks daftar kuda untuk embed."""
        text = ""
        for horse in horses:
            odd_value = odds.get(horse['id'], 1.0)
            text += f"**{horse['id']}. {horse['emoji']} {horse['name']}** (Odds: {odd_value:.2f}x)\n"
        return text

    def _get_current_bets_text(self, bets: dict, horses: list) -> str:
        if not bets:
            return "- Belum ada taruhan.\n"
        horse_map = {h['id']: h['name'] for h in horses}
        lines = []
        for user_id_str, bet_info in bets.items():
            h_name = horse_map.get(bet_info['horse_id'], f"Kuda #{bet_info['horse_id']}")
            lines.append(f"• <@{user_id_str}>: **{bet_info['amount']:,} RSWN** pada **{h_name}** (#{bet_info['horse_id']})")
        return "\n".join(lines) + "\n"

    async def _betting_countdown(self, ctx, channel_id):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Betting countdown dimulai untuk channel {channel_id}.")
        race_state = self.horse_racing_states.get(channel_id)
        if not race_state: return

        for i in range(race_state['betting_duration'], 0, -5):
            if race_state.get('race_message') and i % 5 == 0:
                try:
                    await race_state['race_message'].edit(embed=race_state['race_message'].embeds[0].set_footer(text=f"Taruhan ditutup dalam {i} detik!"))
                except discord.NotFound:
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan balapan tidak ditemukan saat update countdown.")
                    break
                except Exception as e:
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Error updating betting countdown message: {e}")
                    break
            await asyncio.sleep(5)

        if race_state.get('race_message'):
            try:
                await race_state['race_message'].edit(embed=race_state['race_message'].embeds[0].set_footer(text="Taruhan DITUTUP!"))
            except discord.NotFound:
                pass
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Betting countdown selesai untuk channel {channel_id}.")


    async def _horse_race_flow(self, ctx, channel_id):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Alur balapan dimulai untuk channel {channel_id}.")
        race_state = self.horse_racing_states.get(channel_id)
        if not race_state: return

        try:
            await asyncio.sleep(race_state['betting_duration'])

            if not race_state['bets']:
                await ctx.send("Tidak ada yang bertaruh! Balapan dibatalkan.", delete_after=15)
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Tidak ada taruhan, balapan dibatalkan.")
                self.end_game_cleanup_global(channel_id, game_type='horse_racing')
                return

            race_state['status'] = 'racing'
            await ctx.send("🏁 **BALAPAN DIMULAI!** 🏁")

            race_state['race_message'] = await ctx.send(embed=self._get_race_progress_embed(race_state))
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Pesan progres balapan dikirim.")

            while True:
                await asyncio.sleep(2)

                for horse in race_state['horses']:
                    move_distance = random.uniform(0.5, 2.5) * horse.get('speed_mod', 1.0)
                    horse['position'] += move_distance
                    if horse['position'] >= race_state['track_length']:
                        horse['position'] = race_state['track_length']

                race_state['horses'].sort(key=lambda h: h['position'], reverse=True)

                if race_state.get('race_message'):
                    try:
                        await race_state['race_message'].edit(embed=self._get_race_progress_embed(race_state))
                        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Progres balapan diperbarui.")
                    except discord.NotFound:
                        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan balapan tidak ditemukan saat update progres.")
                        break

                winner = None
                for horse in race_state['horses']:
                    if horse['position'] >= race_state['track_length']:
                        winner = horse
                        break

                if winner:
                    await ctx.send(f"🎉 **{winner['emoji']} {winner['name']}** MENANG! 🎉")
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Pemenang: {winner['name']}.")
                    await self._distribute_winnings(ctx, channel_id, winner['id'])
                    break

        except asyncio.CancelledError:
            await ctx.send("Balapan Kuda dihentikan.")
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Game flow dibatalkan (CancelledError) untuk channel {channel_id}.")
        except Exception as e:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: ERROR fatal di channel {channel_id}: {e}.", file=sys.stderr)
            await ctx.send(f"Terjadi kesalahan fatal pada Balapan Kuda: `{e}`. Game dihentikan.")
        finally:
            self.end_game_cleanup_global(channel_id, game_type='horse_racing')
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: _horse_race_flow selesai atau dibatalkan untuk channel {channel_id}.")

    def _get_race_progress_embed(self, race_state):
        """Membuat embed yang menampilkan progres balapan."""
        embed = discord.Embed(
            title="🏁 Progres Balapan Kuda 🏁",
            description="Siapa yang akan mencapai garis finish duluan?",
            color=discord.Color.green()
        )

        track_length = race_state['track_length']
        progress_text = ""
        for horse in race_state['horses']:
            progress_int = min(int(horse['position']), track_length)

            track_segment = "─" * progress_int
            remaining_segment = "─" * max(0, track_length - progress_int - 1)

            progress_bar = f"[{track_segment}{horse['emoji']}{remaining_segment}]"

            progress_text += f"**{horse['id']}. {horse['name']}**\n`{progress_bar}` {progress_int}/{track_length}\n\n"

        embed.add_field(name="Lintasan", value=progress_text, inline=False)
        embed.set_image(url="https://media.giphy.com/media/l4FGJm7hXG1r0J0I/giphy.gif")
        return embed

    async def _distribute_winnings(self, ctx, channel_id, winning_horse_id):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Mendistribusikan kemenangan untuk channel {channel_id}.")
        race_state = self.horse_racing_states.get(channel_id)
        if not race_state: return

        bank_data = load_json_from_root('data/bank_data.json', default_value={})
        odds = race_state['odds'].get(winning_horse_id, 1.0)

        winners = []
        losers = []

        for user_id_str, bet_info in race_state['bets'].items():
            user = ctx.guild.get_member(int(user_id_str))
            if not user: continue

            if bet_info['horse_id'] == winning_horse_id:
                winnings = int(bet_info['amount'] * odds)
                bank_data.setdefault(user_id_str, {'balance': 0, 'debt': 0})['balance'] += winnings
                winners.append(f"{user.mention} (Menang: **{winnings} RSWN**)")
                await self.give_rewards_with_bonus_check(user, ctx.guild.id, custom_rsw=winnings, custom_exp=50)
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: {user.display_name} menang {winnings} RSWN.")
            else:
                losers.append(f"{user.mention} (Kalah: {bet_info['amount']} RSWN)")
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: {user.display_name} kalah {bet_info['amount']} RSWN.")

        save_json_to_root(bank_data, 'data/bank_data.json')

        winning_horse_name = next((h['name'] for h in race_state['horses'] if h['id'] == winning_horse_id), "Kuda Misterius")

        result_embed = discord.Embed(
            title=f"🏆 Hasil Balapan Kuda! 🏆",
            description=f"Kuda **{winning_horse_name}** (#{winning_horse_id}) adalah pemenangnya dengan odds **{odds:.2f}x**!",
            color=discord.Color.gold()
        )

        if winners:
            result_embed.add_field(name="Pemenang Taruhan", value="\n".join(winners), inline=False)
        else:
            result_embed.add_field(name="Pemenang Taruhan", value="Tidak ada yang berhasil menebak dengan benar!", inline=False)

        if losers:
            result_embed.add_field(name="Kalah Taruhan", value="\n".join(losers), inline=False)

        await ctx.send(embed=result_embed)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Hasil balapan dikirim.")

        donasi_embed = discord.Embed(
            title="✨ Suka dengan Balapan Kudanya? Dukung kami! ✨",
            description=(
                "Pengembangan bot ini membutuhkan waktu dan usaha. "
                "Setiap dukungan kecil dari Anda sangat berarti untuk menjaga bot ini tetap aktif "
                "dan menghadirkan fitur-fitur baru yang lebih seru!\n\n"
                "Terima kasih telah bermain!"
            ),
            color=discord.Color.gold()
        )
        donasi_view = discord.ui.View()
        donasi_view.add_item(discord.ui.Button(label="Bagi Bagi (DANA/Gopay/OVO)", style=discord.ButtonStyle.url, url="https://bagibagi.co/Rh7155"))
        donasi_view.add_item(discord.ui.Button(label="Saweria (All Payment Method)", style=discord.ButtonStyle.url, url="https://saweria.co/RH7155"))

        await ctx.send(embed=donasi_embed, view=donasi_view)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan donasi dikirim di akhir game Balapan Kuda.")

    @commands.command(name="taruhan", help="Pasang taruhan pada kuda di Balapan Kuda. `!taruhan <jumlah_rsw> <nomor_kuda>`")
    async def place_bet_horse_race(self, ctx, amount: int, horse_num: int):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Command !taruhan dipanggil oleh {ctx.author.display_name} dengan {amount} RSWN pada kuda #{horse_num}.")
        channel_id = ctx.channel.id
        race_state = self.horse_racing_states.get(channel_id)

        if not race_state or race_state['status'] != 'betting':
            return await ctx.send("Tidak ada sesi taruhan balapan kuda yang aktif saat ini. Tunggu host memulai balapan!", ephemeral=True)

        if amount <= 0:
            return await ctx.send("Jumlah taruhan harus lebih dari 0.", ephemeral=True)

        user_id_str = str(ctx.author.id)
        bank_data = load_json_from_root('data/bank_data.json')
        current_balance = bank_data.setdefault(user_id_str, {'balance': 0, 'debt': 0})['balance']

        if current_balance < amount:
            return await ctx.send(f"Saldo RSWNmu tidak cukup untuk bertaruh. Kamu punya: **{current_balance} RSWN**.", ephemeral=True)

        target_horse = next((h for h in race_state['horses'] if h['id'] == horse_num), None)
        if not target_horse:
            return await ctx.send(f"Nomor kuda `{horse_num}` tidak valid. Pilih dari daftar kuda yang berpartisipasi.", ephemeral=True)

        if user_id_str in race_state['bets']:
            old_bet = race_state['bets'][user_id_str]
            bank_data[user_id_str]['balance'] += old_bet['amount']
            await ctx.send(f"Taruhanmu sebelumnya ({old_bet['amount']} RSWN pada kuda #{old_bet['horse_id']}) telah dikembalikan. Memasang taruhan baru...", delete_after=5)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Taruhan {ctx.author.display_name} diperbarui (saldo dikembalikan).")


        bank_data[user_id_str]['balance'] -= amount
        race_state['bets'][user_id_str] = {'amount': amount, 'horse_id': horse_num}
        save_json_to_root(bank_data, 'data/bank_data.json')

        await ctx.send(f"✅ **{ctx.author.display_name}** berhasil bertaruh **{amount} RSWN** pada **{target_horse['name']}** (Kuda #{horse_num}).", delete_after=5)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: {ctx.author.display_name} berhasil bertaruh.")

        if race_state.get('race_message'):
            updated_embed = race_state['race_message'].embeds[0]
            updated_embed.description = (f"Waktunya memasang taruhan! Kamu punya **{race_state['betting_duration']} detik** untuk bertaruh.\n\n"
                                         f"**Taruhan Saat Ini:**\n" + self._get_current_bets_text(race_state['bets'], race_state['horses']))
            try:
                await race_state['race_message'].edit(embed=updated_embed)
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Pesan taruhan diperbarui setelah taruhan baru.")
            except discord.NotFound:
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan balapan tidak ditemukan saat update taruhan.")
                pass
            except Exception as e:
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Error updating betting message: {e}")

    @commands.command(name="stopbalapan", help="[Admin/Host] Hentikan balapan kuda yang sedang berjalan.")
    async def stop_horse_race(self, ctx):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Command !stopbalapan dipanggil oleh {ctx.author.display_name}.")
        channel_id = ctx.channel.id
        race_state = self.horse_racing_states.get(channel_id)

        if not race_state:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !stopbalapan: Tidak ada balapan aktif.")
            return await ctx.send("Tidak ada balapan kuda yang sedang berjalan di channel ini.", ephemeral=True)

        if not ctx.author.guild_permissions.manage_channels:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !stopbalapan: Bukan admin, blokir.")
            return await ctx.send("Hanya admin server yang bisa menghentikan balapan kuda.", ephemeral=True)

        await ctx.send("Balapan Kuda dihentikan secara paksa oleh admin.")
        self.end_game_cleanup_global(channel_id, game_type='horse_racing')
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda dihentikan secara paksa di channel {channel_id}.")


async def setup(bot):
    await bot.add_cog(TavernPartyGames(bot))


