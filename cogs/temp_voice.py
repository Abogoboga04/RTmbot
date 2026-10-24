import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import os
import logging
import json
from datetime import datetime

try:
    from cogs.v2_layout import build_v2_card, send_v2_message
except ImportError:
    build_v2_card = None
    send_v2_message = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

TEMP_CHANNELS_FILE = 'data/temp_voice_channels.json'
GUILD_CONFIG_FILE = 'data/guild_config.json'

ENABLE_SCHEDULED_CREATION = False
CREATION_START_TIME = (20, 0)
CREATION_END_TIME = (6, 0)
TARGET_REGION = 'singapore'

def load_json_file(file_path, default_data={}):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    if not os.path.exists(file_path) or os.stat(file_path).st_size == 0:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, indent=4)
        return default_data
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, (dict, list)):
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(default_data, f, indent=4)
                return data
            return data
    except (json.JSONDecodeError, Exception):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, indent=4)
        return default_data

def save_json_file(file_path, data):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def load_temp_channels():
    data = load_json_file(TEMP_CHANNELS_FILE)
    if not isinstance(data, dict):
        return {}
    return data

def save_temp_channels(data):
    save_json_file(TEMP_CHANNELS_FILE, {str(k): v for k, v in data.items()})

def load_guild_config():
    return load_json_file(GUILD_CONFIG_FILE)

def save_guild_config(data):
    save_json_file(GUILD_CONFIG_FILE, data)

class RenameVCModal(discord.ui.Modal, title="Ganti Nama Ruangan"):
    new_name = discord.ui.TextInput(
        label="Nama Baru",
        placeholder="Masukkan nama ruangan baru...",
        min_length=2,
        max_length=100
    )
    def __init__(self, cog_instance):
        super().__init__()
        self.cog = cog_instance

    async def on_submit(self, interaction: discord.Interaction):
        if not self.cog.is_owner_vc_by_interaction(interaction):
            return await interaction.response.send_message("❌ Kamu bukan pemilik ruangan ini!", ephemeral=True)
        vc = interaction.user.voice.channel
        new_name_val = self.new_name.value.strip()
        try:
            await vc.edit(name=new_name_val, reason=f"Ganti nama ruangan oleh {interaction.user.display_name}")
            embed = discord.Embed(
                title="✏️ Nama Ruangan Diubah",
                description=f"Nama ruangan berhasil diubah menjadi **{new_name_val}**.",
                color=0x57F287
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot tidak memiliki izin untuk mengubah nama channel ini.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

class CustomLimitModal(discord.ui.Modal, title="Atur Batas Kursi"):
    seat_limit = discord.ui.TextInput(
        label="Jumlah Kursi (0 = Tak Terbatas)",
        placeholder="Contoh: 0, 2, 4, 8...",
        min_length=1,
        max_length=2
    )

    def __init__(self, cog_instance):
        super().__init__()
        self.cog = cog_instance

    async def on_submit(self, interaction: discord.Interaction):
        if not self.cog.is_owner_vc_by_interaction(interaction):
            return await interaction.response.send_message("❌ Kamu bukan pemilik ruangan ini!", ephemeral=True)
        val_str = self.seat_limit.value.strip()
        if not val_str.isdigit():
            return await interaction.response.send_message("❌ Masukkan angka valid antara 0 sampai 99.", ephemeral=True)
        limit_val = int(val_str)
        if limit_val < 0 or limit_val > 99:
            return await interaction.response.send_message("❌ Batas kursi harus antara 0 hingga 99.", ephemeral=True)
        vc = interaction.user.voice.channel
        try:
            await vc.edit(user_limit=limit_val, reason=f"Atur batas kursi oleh {interaction.user.display_name}")
            txt = f"{limit_val} orang" if limit_val > 0 else "Tak Terbatas (Bebas)"
            embed = discord.Embed(
                title="👥 Batas Kursi Diperbarui",
                description=f"Kapasitas ruangan sekarang: **{txt}**.",
                color=0x57F287
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

class LimitPresetSelect(discord.ui.Select):
    def __init__(self, cog_instance):
        options = [
            discord.SelectOption(label="Bebas (Tanpa Batas)", value="0", emoji="🌐", description="Siapa saja boleh masuk tanpa batasan kursi"),
            discord.SelectOption(label="Duet (2 Orang)", value="2", emoji="👥", description="Cocok untuk ngobrol berdua / privat"),
            discord.SelectOption(label="Trio (3 Orang)", value="3", emoji="🥉", description="Cocok untuk mabar tim 3 orang"),
            discord.SelectOption(label="Squad (4 Orang)", value="4", emoji="🎮", description="Standar tim game 4 orang"),
            discord.SelectOption(label="Party (8 Orang)", value="8", emoji="🎉", description="Kapasitas ruang pesta / nobar"),
            discord.SelectOption(label="Rombongan (15 Orang)", value="15", emoji="🚌", description="Ruangan diskusi besar"),
            discord.SelectOption(label="Kustom (Ketik Angka)", value="custom", emoji="🔢", description="Ketik jumlah kursi bebas 0-99")
        ]
        super().__init__(placeholder="Pilih kapasitas kursi ruangan...", options=options, min_values=1, max_values=1)
        self.cog = cog_instance

    async def callback(self, interaction: discord.Interaction):
        if not self.cog.is_owner_vc_by_interaction(interaction):
            return await interaction.response.send_message("❌ Kamu bukan pemilik ruangan ini!", ephemeral=True)
        chosen = self.values[0]
        if chosen == "custom":
            return await interaction.response.send_modal(CustomLimitModal(self.cog))
        limit_val = int(chosen)
        vc = interaction.user.voice.channel
        try:
            await vc.edit(user_limit=limit_val, reason=f"Preset kursi oleh {interaction.user.display_name}")
            txt = f"{limit_val} orang" if limit_val > 0 else "Tak Terbatas (Bebas)"
            embed = discord.Embed(
                title="👥 Batas Kursi Diperbarui",
                description=f"Kapasitas ruangan berhasil diatur ke **{txt}**.",
                color=0x57F287
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

class FriendSelect(discord.ui.UserSelect):
    def __init__(self, cog_instance):
        super().__init__(
            placeholder="Pilih teman yang ingin diberi izin masuk & bicara...",
            min_values=1,
            max_values=10
        )
        self.cog = cog_instance

    async def callback(self, interaction: discord.Interaction):
        if not self.cog.is_owner_vc_by_interaction(interaction):
            return await interaction.response.send_message("❌ Kamu bukan pemilik ruangan ini!", ephemeral=True)
        vc = interaction.user.voice.channel
        invited_mentions = []
        invite_url = None
        try:
            invite_obj = await vc.create_invite(max_age=3600, max_uses=10, unique=True, reason=f"Undangan teman oleh {interaction.user.display_name}")
            invite_url = invite_obj.url
        except Exception:
            invite_url = None

        for user_obj in self.values:
            member = interaction.guild.get_member(user_obj.id) or user_obj
            try:
                await vc.set_permissions(member, connect=True, speak=True, view_channel=True, reason=f"Izin khusus teman oleh {interaction.user.display_name}")
                invited_mentions.append(member.mention)
                if invite_url and hasattr(member, 'send'):
                    try:
                        dm_embed = discord.Embed(
                            title="👋 Undangan Ruangan Suara",
                            description=(
                                f"Kamu telah diberi akses khusus oleh **{interaction.user.display_name}** "
                                f"untuk masuk dan berbicara di ruang pribadinya (**{vc.name}**)!\n\n"
                                f"🔗 **Klik tautan ini untuk langsung bergabung:**\n{invite_url}"
                            ),
                            color=0x5865F2
                        )
                        await member.send(embed=dm_embed)
                    except Exception:
                        pass
            except Exception:
                pass

        if invited_mentions:
            names_str = ", ".join(invited_mentions)
            embed = discord.Embed(
                title="✅ Akses Teman Diberikan",
                description=(
                    f"Akses masuk dan izin berbicara berhasil diberikan kepada: {names_str}\n\n"
                    f"*(Mereka sekarang bisa masuk dan berbicara bebas meskipun ruangan sedang digembok)*"
                ),
                color=0x57F287
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Gagal memberikan izin ke user yang dipilih.", ephemeral=True)

class KickSelect(discord.ui.Select):
    def __init__(self, members_to_kick):
        options = []
        for m in members_to_kick:
            options.append(discord.SelectOption(label=m.display_name, value=str(m.id), emoji="👢"))
        super().__init__(placeholder="Pilih anggota yang ingin dikeluarkan...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        vc = interaction.user.voice.channel if interaction.user.voice else None
        if not vc:
            return await interaction.response.send_message("❌ Kamu tidak berada di dalam voice channel.", ephemeral=True)
        target_id = int(self.values[0])
        target_member = vc.guild.get_member(target_id)
        if target_member and target_member in vc.members:
            try:
                await target_member.move_to(None, reason=f"Dikeluarkan oleh pemilik ruangan {interaction.user.display_name}")
                await interaction.response.send_message(f"👢 **{target_member.display_name}** telah dikeluarkan dari ruangan.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Gagal mengeluarkan member: {e}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Anggota tersebut sudah tidak ada di dalam ruangan.", ephemeral=True)

class KnockDecisionView(discord.ui.View):
    def __init__(self, cog_instance, guest_id: int, vc_id: int):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.guest_id = guest_id
        self.vc_id = vc_id

    @discord.ui.button(label="Izinkan & Buka Pintu", emoji="✅", style=discord.ButtonStyle.success)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel_info = self.cog.active_temp_channels.get(str(self.vc_id))
        if not channel_info or channel_info.get("owner_id") != str(interaction.user.id):
            return await interaction.response.send_message("❌ Hanya pemilik ruangan yang dapat memutuskan izin masuk.", ephemeral=True)

        guild = interaction.guild
        vc = guild.get_channel(self.vc_id)
        if not vc:
            return await interaction.response.send_message("❌ Ruangan sudah tidak ada.", ephemeral=True)

        guest = guild.get_member(self.guest_id)
        if not guest:
            return await interaction.response.send_message("❌ Tamu yang mengetuk sudah tidak ditemukan di server.", ephemeral=True)

        try:
            await vc.set_permissions(guest, connect=True, speak=True, view_channel=True, reason=f"Ketuk pintu disetujui oleh {interaction.user.display_name}")
            moved_in = False
            if guest.voice and guest.voice.channel:
                try:
                    await guest.move_to(vc)
                    moved_in = True
                except Exception:
                    moved_in = False

            try:
                invite_obj = await vc.create_invite(max_age=3600, max_uses=1, unique=True)
                join_text = f"\n🔗 Klik untuk langsung masuk: {invite_obj.url}" if not moved_in else "\n*(Kamu telah dipindahkan langsung ke dalam ruangan)*"
                await guest.send(f"🚪 Pemilik ruangan **{vc.name}** telah menerima permintaan masukmu! Kamu sekarang memiliki akses masuk dan hak berbicara.{join_text}")
            except Exception:
                pass

            for item in self.children:
                item.disabled = True

            embed = discord.Embed(
                title="✅ Tamu Diterima Masuk",
                description=f"{guest.mention} telah diizinkan masuk dan diberi hak berbicara di ruangan ini.",
                color=0x57F287
            )
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception as e:
            await interaction.response.send_message(f"❌ Terjadi kesalahan saat memproses izin: {e}", ephemeral=True)

    @discord.ui.button(label="Tolak", emoji="❌", style=discord.ButtonStyle.danger)
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel_info = self.cog.active_temp_channels.get(str(self.vc_id))
        if not channel_info or channel_info.get("owner_id") != str(interaction.user.id):
            return await interaction.response.send_message("❌ Hanya pemilik ruangan yang dapat memutuskan izin masuk.", ephemeral=True)

        guest = interaction.guild.get_member(self.guest_id)
        if guest:
            try:
                await guest.send(f"🚪 Maaf, pemilik ruangan suara belum dapat menerima permintaan masukmu saat ini.")
            except Exception:
                pass

        for item in self.children:
            item.disabled = True

        embed = discord.Embed(
            title="🛑 Tamu Ditolak",
            description=f"Permintaan masuk dari <@{self.guest_id}> telah ditolak.",
            color=0xED4245
        )
        await interaction.response.edit_message(embed=embed, view=self)

class VCControlView(discord.ui.View):
    def __init__(self, cog_instance):
        super().__init__(timeout=None)
        self.cog = cog_instance
        self.load_donation_buttons()

    def load_donation_buttons(self):
        try:
            donation_file_path = 'data/donation_buttons.json'
            if os.path.exists(donation_file_path):
                with open(donation_file_path, 'r', encoding='utf-8') as f:
                    donation_data = json.load(f)
                    for button_data in donation_data:
                        self.add_item(discord.ui.Button(
                            label=button_data['label'],
                            style=discord.ButtonStyle.url,
                            url=button_data['url'],
                            row=2
                        ))
        except Exception:
            pass

    async def _check_owner(self, interaction: discord.Interaction):
        if not self.cog.is_owner_vc_by_interaction(interaction):
            await interaction.response.send_message("❌ Kamu bukan pemilik ruangan ini!", ephemeral=True)
            return False
        return True

    @discord.ui.button(emoji="🔒", label="Kunci / Buka Gembok", style=discord.ButtonStyle.secondary, custom_id="vc:toggle_lock", row=0)
    async def toggle_lock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        vc = interaction.user.voice.channel
        everyone_role = interaction.guild.default_role
        current_ov = vc.overwrites_for(everyone_role)
        is_currently_locked = current_ov.connect is False

        try:
            if is_currently_locked:
                current_ov.connect = True
                current_ov.speak = True
                await vc.set_permissions(everyone_role, overwrite=current_ov, reason=f"Gembok dibuka oleh {interaction.user.display_name}")
                embed = discord.Embed(
                    title="🔓 Gembok Ruangan Dibuka",
                    description="Pintu ruangan sekarang **TERBUKA UMUM**. Siapa saja dapat bergabung dan berbicara.",
                    color=0x57F287
                )
            else:
                current_ov.connect = False
                current_ov.speak = True
                await vc.set_permissions(everyone_role, overwrite=current_ov, reason=f"Ruangan digembok oleh {interaction.user.display_name}")
                embed = discord.Embed(
                    title="🔒 Ruangan Digembok",
                    description=(
                        "Pintu ruangan sekarang **TERKUNCI**.\n"
                        "Orang luar tidak dapat masuk kecuali kamu beri akses lewat tombol **Beri Akses Teman** "
                        "atau kamu setujui ketukan pintunya."
                    ),
                    color=0xED4245
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot tidak memiliki izin untuk mengubah perizinan channel ini.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

    @discord.ui.button(emoji="👥", label="Batas Kursi", style=discord.ButtonStyle.secondary, custom_id="vc:set_limit", row=0)
    async def set_limit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        sub_view = discord.ui.View(timeout=120)
        sub_view.add_item(LimitPresetSelect(self.cog))
        embed = discord.Embed(
            title="👥 Pengaturan Batas Kursi",
            description="Pilih kapasitas maksimal jumlah anggota yang diizinkan masuk ke ruangan suaramu:",
            color=0x5865F2
        )
        await interaction.response.send_message(embed=embed, view=sub_view, ephemeral=True)

    @discord.ui.button(emoji="✏️", label="Ganti Nama", style=discord.ButtonStyle.secondary, custom_id="vc:rename", row=0)
    async def rename_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        await interaction.response.send_modal(RenameVCModal(self.cog))

    @discord.ui.button(emoji="🛑", label="Tutup Ruangan", style=discord.ButtonStyle.danger, custom_id="vc:delete", row=0)
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        vc = interaction.user.voice.channel
        vc_id_str = str(vc.id)
        if vc_id_str in self.cog.active_temp_channels:
            del self.cog.active_temp_channels[vc_id_str]
            save_temp_channels(self.cog.active_temp_channels)
        try:
            await interaction.response.send_message("🛑 Ruangan telah dibongkar dan ditutup.", ephemeral=True)
            await vc.delete(reason=f"Ruangan dihapus oleh pemilik {interaction.user.display_name}")
        except discord.NotFound:
            await interaction.response.send_message("❌ Ruangan ini sudah terhapus.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot tidak memiliki izin untuk menghapus ruangan ini.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

    @discord.ui.button(emoji="➕", label="Beri Akses Teman", style=discord.ButtonStyle.primary, custom_id="vc:grant_friend", row=1)
    async def grant_friend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        sub_view = discord.ui.View(timeout=120)
        sub_view.add_item(FriendSelect(self.cog))
        embed = discord.Embed(
            title="➕ Beri Akses Masuk & Bicara Teman",
            description=(
                "Pilih satu atau beberapa teman dari daftar di bawah.\n"
                "Teman yang dipilih akan **otomatis dibuka gemboknya** (diberi izin Connect, Speak, dan View), "
                "serta bot akan mengirimkan tautan undangan langsung ke DM mereka."
            ),
            color=0x5865F2
        )
        await interaction.response.send_message(embed=embed, view=sub_view, ephemeral=True)

    @discord.ui.button(emoji="🚪", label="Ketuk Pintu", style=discord.ButtonStyle.secondary, custom_id="vc:knock_action", row=1)
    async def knock_action_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.user.voice.channel if interaction.user.voice else None
        if vc and self.cog.is_owner_vc_by_interaction(interaction):
            embed = discord.Embed(
                title="🚪 Panduan Fitur Ketuk Pintu",
                description=(
                    "Fitur **Ketuk Pintu** memungkinkan teman di luar ruangan untuk meminta izin masuk saat ruanganmu sedang terkunci.\n\n"
                    "Saat ada yang mengetuk pintu, bot akan mengirim notifikasi tombol **[Izinkan & Buka Pintu]** atau **[Tolak]** langsung di sini."
                ),
                color=0x5865F2
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if not vc:
            return await interaction.response.send_message("❌ Kamu harus terhubung ke voice channel untuk mengetuk pintu ruangan lain.", ephemeral=True)

        await interaction.response.send_message("ℹ️ Gunakan perintah `/knock` untuk mengetuk pintu ruangan yang terkunci.", ephemeral=True)

    @discord.ui.button(emoji="👻", label="Mode Siluman", style=discord.ButtonStyle.secondary, custom_id="vc:toggle_ghost", row=1)
    async def toggle_ghost_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        vc = interaction.user.voice.channel
        everyone_role = interaction.guild.default_role
        current_perm = vc.overwrites_for(everyone_role).view_channel
        try:
            if current_perm is True or current_perm is None:
                await vc.set_permissions(everyone_role, view_channel=False)
                await interaction.response.send_message("👻 **Mode Siluman Aktif!** Ruangan ini sekarang tersembunyi dari daftar sidebar member biasa.", ephemeral=True)
            else:
                await vc.set_permissions(everyone_role, view_channel=True)
                await interaction.response.send_message("👀 **Mode Siluman Dimatikan!** Ruangan sekarang terlihat di sidebar umum.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

    @discord.ui.button(emoji="👢", label="Usir Member", style=discord.ButtonStyle.secondary, custom_id="vc:kick", row=1)
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        vc = interaction.user.voice.channel
        others = [m for m in vc.members if m.id != interaction.user.id and not m.bot]
        if not others:
            return await interaction.response.send_message("❌ Tidak ada orang lain di dalam ruanganmu untuk dikeluarkan.", ephemeral=True)
        sub_view = discord.ui.View(timeout=120)
        sub_view.add_item(KickSelect(others))
        await interaction.response.send_message("Pilih anggota yang ingin dikeluarkan:", view=sub_view, ephemeral=True)

    @discord.ui.button(emoji="👑", label="Klaim Pemilik", style=discord.ButtonStyle.secondary, custom_id="vc:claim", row=1)
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.user.voice.channel if interaction.user.voice else None
        if not vc:
            return await interaction.response.send_message("❌ Kamu harus berada di dalam ruangan suara untuk mengklaimnya.", ephemeral=True)

        vc_id_str = str(vc.id)
        if vc_id_str not in self.cog.active_temp_channels:
            return await interaction.response.send_message("❌ Ini bukan ruangan sementara yang terdaftar.", ephemeral=True)

        current_owner_id = int(self.cog.active_temp_channels[vc_id_str].get("owner_id", 0))
        if current_owner_id == interaction.user.id:
            return await interaction.response.send_message("✅ Kamu sudah menjadi pemilik sah ruangan ini!", ephemeral=True)

        current_owner_in_vc = any(member.id == current_owner_id for member in vc.members)
        if current_owner_in_vc:
            return await interaction.response.send_message("❌ Pemilik ruangan masih ada di dalam! Kamu tidak bisa merebut kepemilikan.", ephemeral=True)

        self.cog.active_temp_channels[vc_id_str]["owner_id"] = str(interaction.user.id)
        save_temp_channels(self.cog.active_temp_channels)
        try:
            await vc.set_permissions(
                interaction.user,
                connect=True, speak=True, send_messages=True, view_channel=True,
                manage_channels=True, manage_roles=True,
                mute_members=True, deafen_members=True, move_members=True
            )
        except Exception:
            pass
        await interaction.response.send_message("👑 **Berhasil!** Kamu sekarang adalah pemilik ruangan ini.", ephemeral=True)


class DynamicVoice(commands.Cog, name="Dynamic Voice Hub"):
    def __init__(self, bot):
        self.bot = bot
        self.guild_config = load_guild_config()
        self.active_temp_channels = load_temp_channels()
        self.bot.add_view(VCControlView(self))
        self.cleanup_task.start()

    def cog_unload(self):
        self.cleanup_task.cancel()

    async def deep_clean_ghost_channels(self):
        for guild_id_str, config in list(self.guild_config.items()):
            if not isinstance(config, dict):
                continue
            target_cat_id = config.get('target_category_id')
            trigger_vc_id = config.get('trigger_vc_id')
            if not target_cat_id:
                continue

            try:
                guild = self.bot.get_guild(int(guild_id_str))
                if not guild:
                    continue
                category = guild.get_channel(int(target_cat_id))
                if not category or not isinstance(category, discord.CategoryChannel):
                    continue

                for vc in list(category.voice_channels):
                    if trigger_vc_id and vc.id == int(trigger_vc_id):
                        continue
                    humans = [m for m in vc.members if not m.bot]
                    vc_id_str = str(vc.id)
                    if len(humans) == 0:
                        try:
                            await vc.delete(reason="Pembersihan otomatis: channel suara sementara kosong.")
                        except (discord.NotFound, discord.Forbidden):
                            pass
                        except Exception:
                            pass
                        self.active_temp_channels.pop(vc_id_str, None)
                    else:
                        if vc_id_str not in self.active_temp_channels:
                            first_human = humans[0]
                            self.active_temp_channels[vc_id_str] = {
                                "owner_id": str(first_human.id),
                                "guild_id": guild_id_str
                            }
                        else:
                            current_owner_id = self.active_temp_channels[vc_id_str].get("owner_id")
                            if not any(str(m.id) == current_owner_id for m in humans):
                                new_owner = humans[0]
                                self.active_temp_channels[vc_id_str]["owner_id"] = str(new_owner.id)
            except Exception:
                pass

        orphans = []
        for ch_id_str, ch_info in list(self.active_temp_channels.items()):
            try:
                ch_id = int(ch_id_str)
                g_id = int(ch_info.get("guild_id", 0))
                guild = self.bot.get_guild(g_id)
                if not guild or not guild.get_channel(ch_id):
                    orphans.append(ch_id_str)
            except Exception:
                orphans.append(ch_id_str)

        for o in orphans:
            self.active_temp_channels.pop(o, None)

        if orphans:
            save_temp_channels(self.active_temp_channels)

    @tasks.loop(seconds=30)
    async def cleanup_task(self):
        await self.deep_clean_ghost_channels()

    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        await self.bot.wait_until_ready()
        await self.deep_clean_ghost_channels()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        if before.channel and str(before.channel.id) in self.active_temp_channels:
            human_members = [m for m in before.channel.members if not m.bot]
            vc_id_str = str(before.channel.id)
            if not human_members:
                try:
                    await before.channel.delete(reason="Channel suara kosong (semua anggota keluar).")
                except (discord.NotFound, discord.Forbidden):
                    pass
                except Exception:
                    pass
                self.active_temp_channels.pop(vc_id_str, None)
                save_temp_channels(self.active_temp_channels)
            else:
                current_owner_id = self.active_temp_channels.get(vc_id_str, {}).get("owner_id")
                if str(member.id) == current_owner_id:
                    new_owner = human_members[0]
                    self.active_temp_channels[vc_id_str]["owner_id"] = str(new_owner.id)
                    save_temp_channels(self.active_temp_channels)
                    try:
                        await before.channel.set_permissions(
                            new_owner,
                            connect=True, speak=True, send_messages=True, view_channel=True,
                            manage_channels=True, manage_roles=True,
                            mute_members=True, deafen_members=True, move_members=True
                        )
                        embed = discord.Embed(
                            title="👑 Kepemilikan Dialihkan",
                            description=f"Pemilik sebelumnya meninggalkan ruangan. Kepemilikan ruangan sekarang dialihkan ke {new_owner.mention}.",
                            color=0xFEE75C
                        )
                        await before.channel.send(embed=embed)
                    except Exception:
                        pass

        guild_id_str = str(member.guild.id)
        config = self.guild_config.get(guild_id_str, {})
        trigger_vc_id = config.get('trigger_vc_id')
        target_cat_id = config.get('target_category_id')

        if not trigger_vc_id or not target_cat_id:
            return

        if after.channel and after.channel.id == trigger_vc_id:
            if ENABLE_SCHEDULED_CREATION:
                now = datetime.now()
                start_time = now.replace(hour=CREATION_START_TIME[0], minute=CREATION_START_TIME[1], second=0, microsecond=0)
                end_time = now.replace(hour=CREATION_END_TIME[0], minute=CREATION_END_TIME[1], second=0, microsecond=0)
                if CREATION_END_TIME < CREATION_START_TIME:
                    if now < start_time and now > end_time:
                        return await self.send_scheduled_message(member, "Bot: Maaf, pembuatan channel pribadi hanya tersedia pada waktu yang ditentukan.")
                elif not (start_time <= now <= end_time):
                    return await self.send_scheduled_message(member, "Bot: Maaf, pembuatan channel pribadi hanya tersedia pada waktu yang ditentukan.")

            for ch_id_str, ch_info in list(self.active_temp_channels.items()):
                if not isinstance(ch_info, dict):
                    continue
                if ch_info.get("owner_id") == str(member.id) and ch_info.get("guild_id") == guild_id_str:
                    existing_channel = member.guild.get_channel(int(ch_id_str))
                    if existing_channel:
                        try:
                            await member.move_to(existing_channel)
                            return
                        except Exception:
                            return
                    else:
                        self.active_temp_channels.pop(ch_id_str, None)
                        save_temp_channels(self.active_temp_channels)

            guild = member.guild
            category = guild.get_channel(target_cat_id)
            if not category or not isinstance(category, discord.CategoryChannel):
                try: await member.send("Bot: Gagal membuat channel suara pribadi. Kategori target tidak valid.")
                except discord.Forbidden: pass
                try: await member.move_to(None)
                except Exception: pass
                return

            current_category_channels = [ch for ch in category.voice_channels if ch.name.startswith("Music ") or ch.name.startswith("Voice ")]
            next_channel_number = len(current_category_channels) + 1
            new_channel_name = f"Voice {next_channel_number}"

            try:
                everyone_role = guild.default_role
                overwrites = {
                    everyone_role: discord.PermissionOverwrite(connect=False, speak=True, view_channel=True),
                    guild.me: discord.PermissionOverwrite(connect=True, speak=True, send_messages=True, view_channel=True, read_message_history=True),
                    member: discord.PermissionOverwrite(
                        connect=True, speak=True, send_messages=True, view_channel=True,
                        manage_channels=True, manage_roles=True,
                        mute_members=True, deafen_members=True, move_members=True
                    )
                }

                bitrate_to_set = guild.bitrate_limit
                bitrate_kbps = bitrate_to_set // 1000

                new_vc = await guild.create_voice_channel(
                    name=new_channel_name,
                    category=category,
                    user_limit=0,
                    overwrites=overwrites,
                    bitrate=bitrate_to_set,
                    rtc_region=TARGET_REGION,
                    reason=f"{member.display_name} membuat ruangan suara sementara."
                )

                await member.move_to(new_vc)
                self.active_temp_channels[str(new_vc.id)] = {"owner_id": str(member.id), "guild_id": guild_id_str}
                save_temp_channels(self.active_temp_channels)

                sent_panel = False
                if build_v2_card and send_v2_message:
                    try:
                        buttons = [
                            {"label": "Kunci / Buka Gembok", "emoji": "🔒", "style": 2, "custom_id": "vc:toggle_lock"},
                            {"label": "Batas Kursi", "emoji": "👥", "style": 2, "custom_id": "vc:set_limit"},
                            {"label": "Ganti Nama", "emoji": "✏️", "style": 2, "custom_id": "vc:rename"},
                            {"label": "Tutup Ruangan", "emoji": "🛑", "style": 4, "custom_id": "vc:delete"},
                            {"label": "Beri Akses Teman", "emoji": "➕", "style": 1, "custom_id": "vc:grant_friend"},
                            {"label": "Ketuk Pintu", "emoji": "🚪", "style": 2, "custom_id": "vc:knock_action"},
                            {"label": "Mode Siluman", "emoji": "👻", "style": 2, "custom_id": "vc:toggle_ghost"},
                            {"label": "Usir Member", "emoji": "👢", "style": 2, "custom_id": "vc:kick"},
                            {"label": "Klaim Pemilik", "emoji": "👑", "style": 2, "custom_id": "vc:claim"}
                        ]

                        donation_file_path = 'data/donation_buttons.json'
                        if os.path.exists(donation_file_path):
                            try:
                                with open(donation_file_path, 'r', encoding='utf-8') as f:
                                    donation_data = json.load(f)
                                    for button_data in donation_data:
                                        buttons.append({
                                            "label": button_data['label'],
                                            "style": 5,
                                            "url": button_data['url']
                                        })
                            except Exception:
                                pass

                        card_json = build_v2_card(
                            title="🎙️ Ruang Suara Pribadi",
                            description=(
                                f"Selamat datang di {new_vc.name}, <@{member.id}>!\n"
                                f"Ruangan ini sepenuhnya milikmu.\n"
                                f"Bitrate: **{bitrate_kbps} kbps** | Region: **{TARGET_REGION.upper()}**\n\n"
                                f"**🎮 Kontrol Ruangan Cepat:**\n"
                                f"🔒 **Kunci / Buka Gembok**: Mengatur perizinan masuk ruangan.\n"
                                f"👥 **Batas Kursi**: Pilih preset kapasitas instan (Duet, Squad, Bebas).\n"
                                f"✏️ **Ganti Nama**: Mengubah nama ruanganmu.\n"
                                f"➕ **Beri Akses Teman**: Pilih teman untuk langsung diberi akses masuk & bicara.\n"
                                f"🚪 **Ketuk Pintu**: Teman di luar bisa meminta izin masuk.\n"
                                f"👻 **Mode Siluman**: Sembunyikan ruangan dari sidebar server.\n"
                                f"👢 **Usir Member**: Tendang penyusup dari ruangan.\n"
                                f"👑 **Klaim Pemilik**: Ambil alih ruangan jika pemilik sebelumnya keluar.\n"
                                f"🛑 **Tutup Ruangan**: Menutup dan menghapus ruangan ini seketika.\n\n"
                                f"*Ruangan akan otomatis dihapus jika seluruh anggota keluar.*"
                            ),
                            color=0x2ecc71,
                            buttons=buttons
                        )
                        resp = await send_v2_message(self.bot, new_vc.id, components=[card_json])
                        if resp and not (isinstance(resp, dict) and "error_msg" in resp):
                            sent_panel = True
                    except Exception:
                        sent_panel = False

                if not sent_panel:
                    embed = discord.Embed(
                        title="🎙️ Ruang Suara Pribadi",
                        description=(
                            f"Selamat datang di {new_vc.name}, {member.mention}! Kamu adalah pemilik channel ini.\n"
                            f"Bitrate: **{bitrate_kbps} kbps** | Region: **{TARGET_REGION.upper()}**\n\n"
                            f"Gunakan tombol di bawah untuk mengelola ruanganmu dengan mudah.\n"
                            f"*Ruangan akan otomatis dihapus saat kosong.*"
                        ),
                        color=discord.Color.green()
                    )
                    view = VCControlView(self)
                    await new_vc.send(embed=embed, view=view)
            except discord.Forbidden:
                try: await member.send("Bot: Gagal membuat channel suara pribadi, pastikan bot memiliki izin yang cukup.")
                except discord.Forbidden: pass
                try: await member.move_to(None)
                except Exception: pass
            except Exception as e:
                try: await member.send(f"Bot: Terjadi kesalahan saat membuat channel pribadi: {e}")
                except discord.Forbidden: pass
                try: await member.move_to(None)
                except Exception: pass

    async def send_scheduled_message(self, member, message_content):
        try:
            await member.move_to(None)
        except Exception:
            pass
        try:
            await member.send(message_content)
        except discord.Forbidden:
            pass

    def is_owner_vc(self, ctx):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return False
        channel_id_str = str(ctx.author.voice.channel.id)
        guild_id_str = str(ctx.guild.id)
        if channel_id_str not in self.active_temp_channels:
            return False
        channel_info = self.active_temp_channels[channel_id_str]
        if channel_info.get("guild_id") != guild_id_str:
            return False
        return channel_info.get("owner_id") == str(ctx.author.id)

    def is_owner_vc_by_interaction(self, interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return False
        channel_id_str = str(interaction.user.voice.channel.id)
        guild_id_str = str(interaction.guild.id)
        if channel_id_str not in self.active_temp_channels:
            return False
        channel_info = self.active_temp_channels[channel_id_str]
        if channel_info.get("guild_id") != guild_id_str:
            return False
        return channel_info.get("owner_id") == str(interaction.user.id)

    @commands.hybrid_command(
        name="knock",
        aliases=["vcknock", "ketukpintu"],
        description="Ketuk pintu ruangan sementara yang terkunci untuk meminta izin masuk dan berbicara"
    )
    @app_commands.describe(room="Pilih ruangan suara sementara yang ingin kamu masuki")
    async def knock(self, ctx: commands.Context, room: discord.VoiceChannel = None):
        if not ctx.guild:
            return await ctx.send("❌ Perintah ini hanya dapat digunakan di dalam server.", ephemeral=True)

        target_vc = room
        if not target_vc:
            config = self.guild_config.get(str(ctx.guild.id), {})
            cat_id = config.get("target_category_id")
            if cat_id:
                category = ctx.guild.get_channel(int(cat_id))
                if category and isinstance(category, discord.CategoryChannel):
                    locked_rooms = []
                    for vc in category.voice_channels:
                        if str(vc.id) in self.active_temp_channels:
                            if vc.overwrites_for(ctx.guild.default_role).connect is False:
                                locked_rooms.append(vc)
                    if len(locked_rooms) == 1:
                        target_vc = locked_rooms[0]
                    elif len(locked_rooms) > 1:
                        names_list = "\n".join(f"• {r.name} (ID: `{r.id}`)" for r in locked_rooms[:5])
                        return await ctx.send(
                            f"🔍 Ditemukan beberapa ruangan terkunci. Silakan sebutkan ruangannya, contoh:\n`/knock room:#nama-ruangan`\n\nDaftar ruangan:\n{names_list}",
                            ephemeral=True
                        )

        if not target_vc:
            return await ctx.send("❌ Silakan pilih atau sebutkan ruangan yang ingin kamu ketuk pintunya: `/knock room:#nama-ruangan`", ephemeral=True)

        vc_id_str = str(target_vc.id)
        if vc_id_str not in self.active_temp_channels:
            return await ctx.send("❌ Channel tersebut bukan ruangan suara sementara yang aktif.", ephemeral=True)

        channel_info = self.active_temp_channels[vc_id_str]
        owner_id = int(channel_info.get("owner_id", 0))

        if owner_id == ctx.author.id:
            return await ctx.send("ℹ️ Kamu adalah pemilik ruangan ini, kamu tidak perlu mengetuk pintu.", ephemeral=True)

        if ctx.author in target_vc.members:
            return await ctx.send("ℹ️ Kamu sudah berada di dalam ruangan ini.", ephemeral=True)

        owner = ctx.guild.get_member(owner_id)
        if not owner:
            return await ctx.send("❌ Pemilik ruangan sedang tidak ditemukan di server.", ephemeral=True)

        view = KnockDecisionView(self, ctx.author.id, target_vc.id)
        knock_embed = discord.Embed(
            title="🚪 Tamu Mengetuk Pintu!",
            description=(
                f"**{ctx.author.mention}** (`{ctx.author.display_name}`) sedang mengetuk pintu ruanganmu "
                f"dan meminta izin untuk bergabung serta berbicara di **{target_vc.name}**.\n\n"
                f"Pilih tindakan di bawah:"
            ),
            color=0xFEE75C
        )
        knock_embed.set_thumbnail(url=ctx.author.display_avatar.url)
        knock_embed.set_footer(text="Izin akan otomatis disematkan jika kamu klik Izinkan")

        sent_notif = False
        try:
            await target_vc.send(content=f"{owner.mention}", embed=knock_embed, view=view)
            sent_notif = True
        except Exception:
            try:
                await owner.send(embed=knock_embed, view=view)
                sent_notif = True
            except Exception:
                pass

        if sent_notif:
            await ctx.send(f"🚪 Kamu telah mengetuk pintu ruangan **{target_vc.name}**. Permintaan telah dikirim ke pemilik ({owner.display_name}). Mohon tunggu responnya!", ephemeral=True)
        else:
            await ctx.send("❌ Gagal mengirimkan ketukan pintu ke pemilik ruangan.", ephemeral=True)

    @commands.hybrid_group(name="vcadmin", description="Admin: Kelola konfigurasi channel suara sementara", fallback="help")
    async def vcadmin_group(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Gunakan subcommand seperti `/vcadmin settrigger` atau `/vcadmin setcat`.", ephemeral=True)

    @vcadmin_group.command(name="settrigger", description="Admin: Atur channel pemicu untuk join-to-create")
    @commands.has_permissions(administrator=True)
    async def set_trigger_channel(self, ctx, channel: discord.VoiceChannel):
        try:
            self.guild_config[str(ctx.guild.id)] = self.guild_config.get(str(ctx.guild.id), {})
            self.guild_config[str(ctx.guild.id)]['trigger_vc_id'] = channel.id
            save_guild_config(self.guild_config)
            await ctx.send(f"Bot: Saluran pemicu untuk server ini telah diatur ke {channel.mention}.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"Bot: Terjadi kesalahan: {e}", ephemeral=True)

    @vcadmin_group.command(name="setcat", description="Admin: Atur kategori tempat channel sementara dibuat")
    @commands.has_permissions(administrator=True)
    async def set_target_category(self, ctx, category: discord.CategoryChannel):
        try:
            self.guild_config[str(ctx.guild.id)] = self.guild_config.get(str(ctx.guild.id), {})
            self.guild_config[str(ctx.guild.id)]['target_category_id'] = category.id
            save_guild_config(self.guild_config)
            await ctx.send(f"Bot: Kategori target untuk saluran sementara telah diatur ke {category.mention}.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"Bot: Terjadi kesalahan: {e}", ephemeral=True)

    @vcadmin_group.command(name="reset", description="Admin: Hapus total/reset pengaturan trigger & kategori (Mematikan fitur Temp VC)")
    @commands.has_permissions(administrator=True)
    async def reset_config(self, ctx):
        try:
            guild_id_str = str(ctx.guild.id)
            if guild_id_str in self.guild_config:
                self.guild_config[guild_id_str].pop('trigger_vc_id', None)
                self.guild_config[guild_id_str].pop('target_category_id', None)
                save_guild_config(self.guild_config)
                await ctx.send("🧹 Konfigurasi berhasil dihapus! Fitur Join-to-Create sekarang dalam kondisi **MATI** di server ini.", ephemeral=True)
            else:
                await ctx.send("❌ Server ini belum memiliki pengaturan Temp VC.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

    @commands.hybrid_group(name="vc", description="Kelola ruangan pribadimu", fallback="help")
    async def vc_group(self, ctx):
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(
                title="🎙️ Panduan Ruang Suara Pribadi",
                description="Saat kamu bergabung ke Channel Pemicu, bot akan otomatis membuat ruangan suara baru khusus untukmu!",
                color=0x5865F2
            )
            embed.add_field(
                name="Perintah Utama:",
                value=(
                    "`/vc lock`: Gembok ruangan dari orang luar\n"
                    "`/vc unlock`: Buka gembok ruangan\n"
                    "`/vc limit <angka>`: Atur kapasitas kursi (0 = bebas)\n"
                    "`/vc rename <nama_baru>`: Ubah nama ruangan\n"
                    "`/vc grant @user`: Beri izin khusus teman masuk & bicara\n"
                    "`/vc revoke @user`: Cabut izin teman\n"
                    "`/vc kick @user`: Keluarkan member dari ruangan\n"
                    "`/vc transfer @user`: Alihkan kepemilikan ruangan\n"
                    "`/vc delete`: Tutup ruangan sekarang"
                ),
                inline=False
            )
            embed.add_field(
                name="Fitur Tamu:",
                value="`/knock [room]`: Minta izin masuk ke ruangan yang sedang digembok",
                inline=False
            )
            await ctx.send(embed=embed)

    @vc_group.command(name="lock", description="Gembok ruangan agar orang lain tidak bisa masuk")
    @commands.check(lambda ctx: ctx.cog.is_owner_vc(ctx))
    async def vc_lock(self, ctx):
        try:
            vc = ctx.author.voice.channel
            current_ov = vc.overwrites_for(ctx.guild.default_role)
            current_ov.connect = False
            current_ov.speak = True
            await vc.set_permissions(ctx.guild.default_role, overwrite=current_ov, reason=f"Ruangan digembok oleh {ctx.author.display_name}")
            await ctx.send(f"🔐 Pintu ruangan {vc.name} telah digembok.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"Bot: Terjadi kesalahan: {e}", ephemeral=True)

    @vc_group.command(name="unlock", description="Buka gembok ruangan agar siapa saja bisa masuk")
    @commands.check(lambda ctx: ctx.cog.is_owner_vc(ctx))
    async def vc_unlock(self, ctx):
        try:
            vc = ctx.author.voice.channel
            current_ov = vc.overwrites_for(ctx.guild.default_role)
            current_ov.connect = True
            current_ov.speak = True
            await vc.set_permissions(ctx.guild.default_role, overwrite=current_ov, reason=f"Gembok dibuka oleh {ctx.author.display_name}")
            await ctx.send(f"🔓 Gembok ruangan {vc.name} telah dibuka.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"Bot: Terjadi kesalahan: {e}", ephemeral=True)

    @vc_group.command(name="limit", description="Atur maksimal jumlah orang di ruangan")
    @commands.check(lambda ctx: ctx.cog.is_owner_vc(ctx))
    async def vc_set_limit(self, ctx, limit: int):
        if limit < 0 or limit > 99:
            return await ctx.send("Bot: Batas user harus antara 0 hingga 99.", ephemeral=True)
        try:
            vc = ctx.author.voice.channel
            await vc.edit(user_limit=limit, reason=f"User limit diatur oleh {ctx.author.display_name}")
            await ctx.send(f"👥 Batas kursi diatur ke: {limit if limit > 0 else 'tak terbatas'}.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"Bot: Terjadi kesalahan: {e}", ephemeral=True)

    @vc_group.command(name="rename", description="Ganti papan nama ruangan")
    @commands.check(lambda ctx: ctx.cog.is_owner_vc(ctx))
    async def vc_rename(self, ctx, *, new_name: str):
        if len(new_name) < 2 or len(new_name) > 100:
            return await ctx.send("Bot: Nama channel harus antara 2 hingga 100 karakter.", ephemeral=True)
        try:
            vc = ctx.author.voice.channel
            await vc.edit(name=new_name, reason=f"Nama channel diubah oleh {ctx.author.display_name}")
            await ctx.send(f"✏️ Nama ruangan diubah menjadi {new_name}.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"Bot: Terjadi kesalahan: {e}", ephemeral=True)

    @vc_group.command(name="kick", description="Keluarkan penyusup dari ruangan")
    @commands.check(lambda ctx: ctx.cog.is_owner_vc(ctx))
    async def vc_kick(self, ctx, member: discord.Member):
        if member.id == ctx.author.id or member.bot:
            return await ctx.send("Bot: Kamu tidak bisa menendang dirimu sendiri atau bot.", ephemeral=True)
        vc = ctx.author.voice.channel
        if member.voice and member.voice.channel == vc:
            try:
                await member.move_to(None, reason=f"Dikeluarkan oleh pemilik ruangan {ctx.author.display_name}")
                await ctx.send(f"👢 {member.display_name} telah dikeluarkan dari ruangan.", ephemeral=True)
            except Exception as e:
                await ctx.send(f"Bot: Terjadi kesalahan: {e}", ephemeral=True)
        else:
            await ctx.send("Bot: Pengguna tersebut tidak berada di ruanganmu.", ephemeral=True)

    @vc_group.command(name="grant", description="Beri izin teman khusus masuk dan berbicara")
    @commands.check(lambda ctx: ctx.cog.is_owner_vc(ctx))
    async def vc_grant(self, ctx, member: discord.Member):
        if member.bot: return
        try:
            vc = ctx.author.voice.channel
            await vc.set_permissions(member, connect=True, speak=True, view_channel=True, reason=f"Izin diberikan oleh {ctx.author.display_name}")
            await ctx.send(f"✅ {member.display_name} sekarang diizinkan bergabung dan berbicara di ruanganmu.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"Bot: Terjadi kesalahan: {e}", ephemeral=True)

    @vc_group.command(name="revoke", description="Cabut izin masuk dari user tertentu")
    @commands.check(lambda ctx: ctx.cog.is_owner_vc(ctx))
    async def vc_revoke(self, ctx, member: discord.Member):
        if member.bot: return
        try:
            vc = ctx.author.voice.channel
            await vc.set_permissions(member, connect=False, reason=f"Izin dicabut oleh {ctx.author.display_name}")
            await ctx.send(f"❌ Izin akses {member.display_name} telah dicabut.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"Bot: Terjadi kesalahan: {e}", ephemeral=True)

    @vc_group.command(name="transfer", description="Berikan hak milik ruangan ke temanmu")
    @commands.check(lambda ctx: ctx.cog.is_owner_vc(ctx))
    async def vc_transfer_owner(self, ctx, new_owner: discord.Member):
        vc = ctx.author.voice.channel
        vc_id_str = str(vc.id)
        if new_owner.bot or new_owner.id == ctx.author.id: return
        try:
            self.active_temp_channels[vc_id_str]["owner_id"] = str(new_owner.id)
            save_temp_channels(self.active_temp_channels)

            old_owner_overwrites = vc.overwrites_for(ctx.author)
            old_owner_overwrites.manage_channels = None
            old_owner_overwrites.manage_roles = None
            old_owner_overwrites.mute_members = None
            old_owner_overwrites.deafen_members = None
            old_owner_overwrites.move_members = None
            await vc.set_permissions(ctx.author, overwrite=old_owner_overwrites)

            new_owner_overwrites = vc.overwrites_for(new_owner)
            new_owner_overwrites.manage_channels = True
            new_owner_overwrites.manage_roles = True
            new_owner_overwrites.mute_members = True
            new_owner_overwrites.deafen_members = True
            new_owner_overwrites.move_members = True
            await vc.set_permissions(new_owner, overwrite=new_owner_overwrites)

            await ctx.send(f"👑 Kepemilikan ruangan berhasil dialihkan ke {new_owner.mention}!", ephemeral=True)
        except Exception as e:
            await ctx.send(f"Bot: Terjadi kesalahan saat mengalihkan kepemilikan: {e}", ephemeral=True)

    @vc_group.command(name="delete", description="Tutup paksa dan hapus ruanganmu sekarang")
    @commands.check(lambda ctx: ctx.cog.is_owner_vc(ctx))
    async def vc_delete(self, ctx):
        vc = ctx.author.voice.channel
        vc_id_str = str(vc.id)
        try:
            if vc_id_str in self.active_temp_channels:
                del self.active_temp_channels[vc_id_str]
                save_temp_channels(self.active_temp_channels)
            await ctx.send("🛑 Ruangan telah dibongkar dan ditutup.", ephemeral=True)
            await vc.delete(reason=f"Ruangan dihapus oleh pemilik {ctx.author.display_name}")
        except Exception as e:
            await ctx.send(f"Bot: Terjadi kesalahan saat menghapus channel: {e}", ephemeral=True)

    @vcadmin_group.command(name="transfer", description="Admin: Paksa alihkan hak milik sebuah ruangan sementara")
    @commands.has_permissions(administrator=True)
    async def admin_vc_transfer_owner(self, ctx, channel: discord.VoiceChannel, new_owner: discord.Member):
        channel_id_str = str(channel.id)
        if channel_id_str not in self.active_temp_channels or new_owner.bot: return

        old_owner_id = self.active_temp_channels[channel_id_str].get('owner_id')
        old_owner = ctx.guild.get_member(int(old_owner_id)) if old_owner_id else None

        try:
            self.active_temp_channels[channel_id_str]['owner_id'] = str(new_owner.id)
            save_temp_channels(self.active_temp_channels)

            if old_owner and old_owner.id != new_owner.id:
                old_owner_overwrites = channel.overwrites_for(old_owner)
                old_owner_overwrites.manage_channels = None
                old_owner_overwrites.manage_roles = None
                old_owner_overwrites.mute_members = None
                old_owner_overwrites.deafen_members = None
                old_owner_overwrites.move_members = None
                await channel.set_permissions(old_owner, overwrite=old_owner_overwrites)

            new_owner_overwrites = channel.overwrites_for(new_owner)
            new_owner_overwrites.manage_channels = True
            new_owner_overwrites.manage_roles = True
            new_owner_overwrites.mute_members = True
            new_owner_overwrites.deafen_members = True
            new_owner_overwrites.move_members = True
            await channel.set_permissions(new_owner, overwrite=new_owner_overwrites)

            await ctx.send(f"👑 Kepemilikan saluran {channel.mention} dialihkan ke {new_owner.mention}.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"Bot: Terjadi kesalahan: {e}", ephemeral=True)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if ctx.cog != self:
            return

        try:
            if isinstance(error, commands.CheckFailure):
                await ctx.send("Bot: Kamu harus berada di channel suara pribadi milikmu untuk menggunakan perintah ini.", ephemeral=True)
            elif isinstance(error, commands.MissingRequiredArgument):
                await ctx.send(f"Bot: Argumen tidak lengkap. Contoh penggunaan: !{ctx.command.name} {ctx.command.signature}", ephemeral=True)
            elif isinstance(error, commands.BadArgument):
                await ctx.send("Bot: Argumen tidak valid.", ephemeral=True)
            elif isinstance(error, discord.Forbidden):
                await ctx.send("Bot: Bot tidak memiliki izin yang diperlukan.", ephemeral=True)
        except Exception:
            pass

async def setup(bot):
    os.makedirs('data', exist_ok=True)
    donation_file_path = 'data/donation_buttons.json'
    if not os.path.exists(donation_file_path) or os.stat(donation_file_path).st_size == 0:
        default_data = [
            {
                "label": "Dukung via Bagi-Bagi!",
                "url": "https://bagibagi.co/Rh7155"
            },
            {
                "label": "Dukung via Saweria!",
                "url": "https://saweria.co/RH7155"
            },
            {
                "label": "Dukung via Sosiabuzz",
                "url": "https://sociabuzz.com/abogoboga7155/tribe"
            }
        ]
        with open(donation_file_path, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, indent=4)
    await bot.add_cog(DynamicVoice(bot))
