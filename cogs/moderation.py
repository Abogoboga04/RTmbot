import discord
from discord.ext import commands, tasks
import json
import os
import re
import asyncio
from typing import Optional, Literal
from datetime import datetime, timedelta
import time
import aiohttp
import sys
from discord import app_commands
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont
import io
import unicodedata

try:
    from cogs.card_generator import generate_official_member_card, get_or_create_member_serial_id
except ImportError:
    generate_official_member_card = None
    get_or_create_member_serial_id = None

from cogs.v2_layout import build_v2_card, send_v2_message, send_v2_interaction, register_view



WIB = timezone(timedelta(hours=7))

def load_data(file_path):
    try:
        if not os.path.exists(file_path):
            if not os.path.exists(os.path.dirname(file_path)):
                os.makedirs(os.path.dirname(file_path))
            return {}
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content:
                return {}
            data = json.loads(content)
            return data
    except (json.JSONDecodeError, IOError) as e:
        return {}

def save_data(file_path, data):
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        pass

def parse_duration(duration_str: str) -> Optional[timedelta]:
    match = re.match(r"(\d+)([smhd])", duration_str.lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == 's': return timedelta(seconds=value)
    if unit == 'm': return timedelta(minutes=value)
    if unit == 'h': return timedelta(hours=value)
    if unit == 'd': return timedelta(days=value)
    return None

async def process_and_send_announcement(cog, interaction, original_ctx, target_channel_obj, title, description_text, username, profile_url, image_url, ping_everyone, poll_obj=None, github_raw_url=None):
    full_description = (description_text or "").strip()
    if not full_description and github_raw_url:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(github_raw_url) as resp:
                    if resp.status == 200:
                        full_description = (await resp.text()).strip()
        except Exception:
            pass

    if not full_description:
        await interaction.followup.send(embed=cog._create_embed(description="❌ Deskripsi atau isi pengumuman kosong. Mohon masukkan pesan pengumuman.", color=cog.color_error), ephemeral=True)
        return
    
    description_chunks = [full_description[i:i+4096] for i in range(0, len(full_description), 4096)]

    sent_any_embed = False
    try:
        from cogs.v2_layout import build_v2_card, send_v2_message
        
        webhook = None
        if hasattr(target_channel_obj, "create_webhook") and not isinstance(target_channel_obj, discord.Thread):
            try:
                webhook = await cog.get_or_create_announcement_webhook(target_channel_obj, username or "Pengumuman Resmi")
            except Exception:
                webhook = None

        if ping_everyone:
            try:
                if webhook:
                    await webhook.send(content="@everyone", username=username or "Pengumuman Resmi", avatar_url=profile_url or (target_channel_obj.guild.icon.url if target_channel_obj.guild.icon else None))
                else:
                    await target_channel_obj.send("@everyone")
            except Exception:
                pass

        for i, chunk in enumerate(description_chunks):
            if not chunk.strip(): continue
            footer_text = f"Pengumuman dari: {username}" if i == 0 else f"Lanjutan Pengumuman ({i+1}/{len(description_chunks)})"
            
            if webhook:
                embed = discord.Embed(
                    title=title if i == 0 else None,
                    description=chunk,
                    color=cog.color_announce or 0xFFE000
                )
                if i == 0 and image_url:
                    embed.set_image(url=image_url)
                embed.set_footer(text=footer_text)
                await webhook.send(
                    embed=embed,
                    username=username or "Pengumuman Resmi",
                    avatar_url=profile_url or (target_channel_obj.guild.icon.url if target_channel_obj.guild.icon else None)
                )
                sent_any_embed = True
            else:
                card = build_v2_card(
                    title=title if i == 0 else None,
                    description=chunk,
                    color=None,
                    footer=footer_text,
                    media_url=image_url if i == 0 and image_url else None
                )
                result = await send_v2_message(
                    bot=cog.bot, 
                    channel_id=target_channel_obj.id, 
                    components=[card]
                )
                if not result or (isinstance(result, dict) and "error_msg" in result):
                    embed = discord.Embed(
                        title=title if i == 0 else None,
                        description=chunk,
                        color=cog.color_announce or 0xFFE000
                    )
                    if i == 0 and image_url:
                        embed.set_image(url=image_url)
                    embed.set_footer(text=footer_text)
                    await target_channel_obj.send(embed=embed)
                sent_any_embed = True
            
        if sent_any_embed and poll_obj:
            try:
                await target_channel_obj.send(poll=poll_obj)
            except Exception as e:
                await interaction.followup.send(embed=cog._create_embed(description=f"⚠️ Pengumuman terkirim, namun Polling gagal dikirim: {e}", color=cog.color_error), ephemeral=True)

    except Exception as e:
        if not sent_any_embed:
            await interaction.followup.send(embed=cog._create_embed(description=f"❌ Terjadi kesalahan saat mengirim pengumuman: {e}", color=cog.color_error), ephemeral=True)
        return

    if sent_any_embed:
        await interaction.followup.send(embed=cog._create_embed(description=f"✅ Pengumuman berhasil dikirim ke <#{target_channel_obj.id}>!", color=cog.color_success), ephemeral=True)
        await cog.log_action(original_ctx.guild, "📢 Pengumuman Baru Dibuat", {"Pengirim (Eksekutor)": original_ctx.author.mention, "Pengirim (Tampilan)": f"{username} ({profile_url if profile_url else 'Default'})", "Channel Target": f"<#{target_channel_obj.id}>", "Judul": title, "Panjang Pesan": f"{len(full_description)} karakter", "Fitur Tambahan": f"Ping Everyone: {'Ya' if ping_everyone else 'Tidak'} | Polling: {'Ya' if poll_obj else 'Tidak'}"}, cog.color_announce)

class PollModal(discord.ui.Modal, title="Atur Polling (Jajak Pendapat)"):
    poll_question = discord.ui.TextInput(
        label="Pertanyaan Polling",
        placeholder="Contoh: Bagaimana pendapat kalian?",
        max_length=256,
        required=True,
        row=0
    )
    poll_opt1 = discord.ui.TextInput(label="Opsi 1", max_length=50, required=True, row=1)
    poll_opt2 = discord.ui.TextInput(label="Opsi 2", max_length=50, required=True, row=2)
    poll_opt3 = discord.ui.TextInput(label="Opsi 3 (Kosongkan jika tak perlu)", max_length=50, required=False, row=3)
    poll_opt4 = discord.ui.TextInput(label="Opsi 4 (Kosongkan jika tak perlu)", max_length=50, required=False, row=4)

    def __init__(self, cog, original_ctx, target_channel_obj, ping_everyone, title, content, username, profile_url, image_url, github_raw_url=None):
        super().__init__()
        self.cog = cog
        self.original_ctx = original_ctx
        self.target_channel_obj = target_channel_obj
        self.ping_everyone = ping_everyone
        self.announcement_title = title
        self.announcement_content = content
        self.username = username
        self.profile_url = profile_url
        self.image_url = image_url
        self.github_raw_url = github_raw_url

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        question = self.poll_question.value.strip()
        answers = [self.poll_opt1.value.strip(), self.poll_opt2.value.strip()]
        if self.poll_opt3.value.strip(): answers.append(self.poll_opt3.value.strip())
        if self.poll_opt4.value.strip(): answers.append(self.poll_opt4.value.strip())
        
        from datetime import timedelta
        import discord
        poll_obj = discord.Poll(question=question, duration=timedelta(days=1))
        for answer in answers:
            poll_obj.add_answer(text=answer)
            
        await process_and_send_announcement(
            self.cog, interaction, self.original_ctx, self.target_channel_obj,
            self.announcement_title, self.announcement_content, self.username, self.profile_url, self.image_url,
            self.ping_everyone, poll_obj, self.github_raw_url
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan saat memproses polling: {error}", color=self.cog.color_error), ephemeral=True)
        else:
            await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan saat memproses polling: {error}", color=self.cog.color_error), ephemeral=True)

class AnnouncementModalGlobal(discord.ui.Modal, title="Buat Pengumuman"):
    announcement_title = discord.ui.TextInput(
        label="Judul Pengumuman",
        placeholder="Contoh: Pembaruan Server Penting!",
        max_length=256,
        required=True,
        row=0
    )
    announcement_content = discord.ui.TextInput(
        label="Isi Pengumuman / Pesan",
        placeholder="Tuliskan isi pesan pengumuman di sini...",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=True,
        row=1
    )
    custom_username = discord.ui.TextInput(
        label="Nama Pengirim (Webhook)",
        placeholder="Contoh: Pengumuman Resmi / Tim Admin",
        max_length=80,
        default="Pengumuman Resmi",
        required=False,
        row=2
    )
    announcement_image_url = discord.ui.TextInput(
        label="URL Banner / Gambar (Opsional)",
        placeholder="Contoh: https://example.com/banner.png",
        max_length=2000,
        required=False,
        row=3
    )
    custom_profile_url = discord.ui.TextInput(
        label="URL Avatar Pengirim (Opsional)",
        placeholder="Contoh: https://example.com/avatar.png",
        max_length=2000,
        required=False,
        row=4
    )

    def __init__(self, cog_instance, original_ctx, target_channel_obj, ping_everyone, include_poll, github_raw_url=None):
        super().__init__()
        self.cog = cog_instance
        self.original_ctx = original_ctx
        self.target_channel_obj = target_channel_obj
        self.ping_everyone = ping_everyone
        self.include_poll = include_poll
        self.github_raw_url = github_raw_url
        self.title = f"Pengumuman #{target_channel_obj.name}"[:45]

    async def on_submit(self, interaction: discord.Interaction):
        title = self.announcement_title.value.strip()
        content = self.announcement_content.value.strip()
        username = self.custom_username.value.strip() or "Pengumuman Resmi"
        profile_url = self.custom_profile_url.value.strip()
        image_url = self.announcement_image_url.value.strip()

        if profile_url and not (profile_url.startswith("http://") or profile_url.startswith("https://")):
            await interaction.response.send_message(embed=self.cog._create_embed(description="❌ URL Avatar Pengirim tidak valid. Harus dimulai dengan `http://` atau `https://`.", color=self.cog.color_error), ephemeral=True); return
        if image_url and not (image_url.startswith("http://") or image_url.startswith("https://")):
            await interaction.response.send_message(embed=self.cog._create_embed(description="❌ URL Gambar Pengumuman tidak valid. Harus dimulai dengan `http://` atau `https://`.", color=self.cog.color_error), ephemeral=True); return
        
        if self.include_poll:
            class ContinuePollView(discord.ui.View):
                def __init__(self, cog, original_ctx, target_channel_obj, ping_everyone, title, content, username, profile_url, image_url, github_raw_url=None):
                    super().__init__(timeout=300)
                    self.cog = cog
                    self.original_ctx = original_ctx
                    self.target_channel_obj = target_channel_obj
                    self.ping_everyone = ping_everyone
                    self.announcement_title = title
                    self.announcement_content = content
                    self.username = username
                    self.profile_url = profile_url
                    self.image_url = image_url
                    self.github_raw_url = github_raw_url

                @discord.ui.button(label="Lanjut: Isi Polling", style=discord.ButtonStyle.primary, emoji="📋")
                async def open_poll_modal(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                    poll_modal = PollModal(
                        self.cog, self.original_ctx, self.target_channel_obj,
                        self.ping_everyone, self.announcement_title, self.announcement_content, self.username, self.profile_url, self.image_url, self.github_raw_url
                    )
                    await btn_interaction.response.send_modal(poll_modal)
                    button.disabled = True
                    try:
                        await btn_interaction.message.edit(view=self)
                    except:
                        pass

            view = ContinuePollView(
                self.cog, self.original_ctx, self.target_channel_obj,
                self.ping_everyone, title, content, username, profile_url, image_url, self.github_raw_url
            )
            await interaction.response.send_message(
                embed=self.cog._create_embed(description="✅ Data pengumuman disimpan! Klik tombol di bawah untuk mengisi opsi Polling.", color=self.cog.color_info),
                view=view,
                ephemeral=True
            )
            return
            
        await interaction.response.defer(ephemeral=True)
        await process_and_send_announcement(
            self.cog, interaction, self.original_ctx, self.target_channel_obj,
            title, content, username, profile_url, image_url, self.ping_everyone, None, self.github_raw_url
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan tak terduga saat memproses formulir: {error}", color=self.cog.color_error), ephemeral=True)
        else:
            await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan tak terduga saat memproses formulir: {error}", color=self.cog.color_error), ephemeral=True)

class WelcomeMessageModal(discord.ui.Modal, title="Atur Pesan Selamat Datang"):
    welcome_title = discord.ui.TextInput(
        label="Judul Pesan Selamat Datang",
        placeholder="Contoh: Selamat Datang Anggota Baru!",
        max_length=256,
        required=True,
        row=0
    )
    custom_sender_name = discord.ui.TextInput(
        label="Pengirim (Contoh: Tim Admin)",
        placeholder="Contoh: Tim Admin / Bot Resmi",
        max_length=256,
        required=True,
        row=1
    )
    welcome_content = discord.ui.TextInput(
        label="Isi Pesan (Gunakan {user}, {guild_name})",
        placeholder="Contoh: Halo {user}, selamat datang di {guild_name}!",
        max_length=4000,
        required=True,
        style=discord.TextStyle.paragraph,
        row=2
    )
    welcome_banner_url = discord.ui.TextInput(
        label="URL Banner (Opsional)",
        placeholder="Contoh: https://example.com/welcome_banner.png",
        max_length=2000,
        required=False,
        row=3
    )

    def __init__(self, cog_instance, guild_id, current_settings):
        super().__init__()
        self.cog = cog_instance
        self.guild_id = guild_id
        self.welcome_title.default = current_settings.get("welcome_embed_title", "")
        self.custom_sender_name.default = current_settings.get("welcome_sender_name", "")
        self.welcome_content.default = current_settings.get("welcome_message", "Selamat datang di **{guild_name}**, {user}! 🎉")
        self.welcome_banner_url.default = current_settings.get("welcome_banner_url", "")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        banner_url = self.welcome_banner_url.value.strip()
        if banner_url and not (banner_url.startswith("http://") or banner_url.startswith("https://")):
            await interaction.followup.send(embed=self.cog._create_embed(description="❌ URL Banner tidak valid. Harus dimulai dengan `http://` atau `https://`.", color=self.cog.color_error), ephemeral=True); return

        guild_settings = self.cog.get_guild_settings(self.guild_id)
        
        guild_settings["welcome_embed_title"] = self.welcome_title.value.strip()
        guild_settings["welcome_sender_name"] = self.custom_sender_name.value.strip()
        guild_settings["welcome_message"] = self.welcome_content.value.strip()
        guild_settings["welcome_banner_url"] = banner_url
        
        self.cog.save_settings()
        
        await interaction.followup.send(embed=self.cog._create_embed(description="✅ Pengaturan pesan selamat datang berhasil diperbarui!", color=self.cog.color_success), ephemeral=True)
        
        await self.cog.log_action(
            interaction.guild,
            "🎉 Pengaturan Selamat Datang Diperbarui",
            {
                "Moderator": interaction.user.mention,
                "Judul Embed": guild_settings["welcome_embed_title"],
                "Nama Pengirim": guild_settings["welcome_sender_name"],
                "Isi Pesan": f"```{guild_settings['welcome_message']}```",
                "URL Banner": guild_settings["welcome_banner_url"] if guild_settings["welcome_banner_url"] else "Tidak diatur"
            },
            self.cog.color_welcome
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan tak terduga saat memproses formulir: {error}", color=self.cog.color_error), ephemeral=True)
        else:
            await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan tak terduga saat memproses formulir: {error}", color=self.cog.color_error), ephemeral=True)

class AnnounceButtonView(discord.ui.View):
    def __init__(self, bot_instance, cog_instance, original_ctx, target_channel_obj, github_raw_url=None):
        super().__init__(timeout=60)
        self.bot = bot_instance
        self.cog = cog_instance
        self.original_ctx = original_ctx
        self.target_channel_obj = target_channel_obj
        self.github_raw_url = github_raw_url 
        self.message = None
        self.ping_everyone = False
        self.include_poll = False
        self._update_buttons()

    def _update_buttons(self):
        self.toggle_ping_btn.label = "Ping @everyone: ON" if self.ping_everyone else "Ping @everyone: OFF"
        self.toggle_ping_btn.style = discord.ButtonStyle.green if self.ping_everyone else discord.ButtonStyle.secondary
        
        self.toggle_poll_btn.label = "Polling: ON" if self.include_poll else "Polling: OFF"
        self.toggle_poll_btn.style = discord.ButtonStyle.green if self.include_poll else discord.ButtonStyle.secondary

    @discord.ui.button(label="Ping @everyone: OFF", style=discord.ButtonStyle.secondary, emoji="🔔", row=0)
    async def toggle_ping_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_ctx.author.id: return await interaction.response.send_message("Bukan pesananmu.", ephemeral=True)
        self.ping_everyone = not self.ping_everyone
        self._update_buttons()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Polling: OFF", style=discord.ButtonStyle.secondary, emoji="📊", row=0)
    async def toggle_poll_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_ctx.author.id: return await interaction.response.send_message("Bukan pesananmu.", ephemeral=True)
        self.include_poll = not self.include_poll
        self._update_buttons()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Lanjut: Buka Formulir", style=discord.ButtonStyle.primary, emoji="📣", row=1)
    async def open_announcement_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_ctx.author.id:
            return await interaction.response.send_message("Hanya orang yang memulai perintah yang dapat membuat pengumuman ini.", ephemeral=True)
        
        if not self.original_ctx.author.guild_permissions.manage_guild:
            return await interaction.response.send_message("Anda tidak memiliki izin `Manage Server` untuk membuat pengumuman.", ephemeral=True)
        
        modal = AnnouncementModalGlobal(self.cog, self.original_ctx, self.target_channel_obj, self.ping_everyone, self.include_poll, self.github_raw_url)
        try:
            await interaction.response.send_modal(modal)
        except discord.Forbidden:
            await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Bot tidak memiliki izin untuk mengirim modal.", color=self.cog.color_error), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan saat menampilkan formulir: {e}", color=self.cog.color_error), ephemeral=True)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except:
            pass

class ModeratorActionView(discord.ui.View):
    def __init__(self, cog_instance, member: discord.Member, message: discord.Message, timeout_status: bool = False):
        super().__init__(timeout=180)
        self.cog = cog_instance
        self.member = member
        self.message = message
        self.timeout_status = timeout_status
        self._add_buttons()

    def _add_buttons(self):
        if self.member.is_timed_out():
            self.remove_timeout_button = discord.ui.Button(
                label="Remove Timeout",
                style=discord.ButtonStyle.success,
                emoji="✅",
            )
            self.remove_timeout_button.callback = self.remove_timeout_callback
            self.add_item(self.remove_timeout_button)

        self.timeout_button = discord.ui.Button(
            label="Timeout (1 Jam)",
            style=discord.ButtonStyle.green,
            emoji="⏳",
            disabled=self.timeout_status
        )
        self.timeout_button.callback = self.timeout_callback
        self.add_item(self.timeout_button)

        self.ban_button = discord.ui.Button(
            label="Ban",
            style=discord.ButtonStyle.red,
            emoji="🔨"
        )
        self.ban_button.callback = self.ban_callback
        self.add_item(self.ban_button)

        self.kick_button = discord.ui.Button(
            label="Kick",
            style=discord.ButtonStyle.secondary,
            emoji="👢"
        )
        self.kick_button.callback = self.kick_callback
        self.add_item(self.kick_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.kick_members or interaction.user.guild_permissions.ban_members

    async def remove_timeout_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.guild_permissions.moderate_members:
            return await interaction.followup.send("❌ Anda tidak memiliki izin untuk mencabut timeout.", ephemeral=True)

        try:
            await self.member.timeout(None, reason=f"Timeout removed by moderator {interaction.user.display_name} via report.")
            await interaction.followup.send(f"✅ Timeout untuk anggota {self.member.mention} berhasil dicabut.", ephemeral=True)
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)
        except discord.Forbidden:
            await interaction.followup.send("❌ Bot tidak memiliki izin untuk mencabut timeout pada anggota ini.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

    async def timeout_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.guild_permissions.moderate_members:
            return await interaction.followup.send("❌ Anda tidak memiliki izin untuk melakukan timeout.", ephemeral=True)
        
        duration = timedelta(hours=1)
        reason = f"Timeout by moderator {interaction.user.display_name} via report for a rule violation (link filter)."
        try:
            await self.member.timeout(duration, reason=reason)
            if hasattr(self.cog, "increment_timeout_counter"):
                await self.cog.increment_timeout_counter()
            await interaction.followup.send(f"✅ Anggota {self.member.mention} berhasil di-timeout lagi selama 1 jam.", ephemeral=True)
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)
        except discord.Forbidden:
            await interaction.followup.send("❌ Bot tidak memiliki izin untuk melakukan timeout pada anggota ini.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

    async def ban_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.guild_permissions.ban_members:
            return await interaction.followup.send("❌ Anda tidak memiliki izin untuk melakukan ban.", ephemeral=True)

        reason = f"Banned by moderator {interaction.user.display_name} via report for a rule violation (link filter)."
        try:
            await self.member.ban(reason=reason)
            await interaction.followup.send(f"✅ Anggota {self.member.mention} berhasil di-ban.", ephemeral=True)
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)
        except discord.Forbidden:
            await interaction.followup.send("❌ Bot tidak memiliki izin untuk melakukan ban pada anggota ini.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

    async def kick_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.guild_permissions.kick_members:
            return await interaction.followup.send("❌ Anda tidak memiliki izin untuk melakukan kick.", ephemeral=True)

        reason = f"Kicked by moderator {interaction.user.display_name} via report for a rule violation (link filter)."
        try:
            await self.member.kick(reason=reason)
            await interaction.followup.send(f"✅ Anggota {self.member.mention} berhasil di-kick.", ephemeral=True)
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)
        except discord.Forbidden:
            await interaction.followup.send("❌ Bot tidak memiliki izin untuk melakukan kick pada anggota ini.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

class UniversalMembershipVerificationButton(discord.ui.Button):
    def __init__(self, cog_instance, label: str, **kwargs):
        super().__init__(label=label, **kwargs)
        self.cog = cog_instance
        self.custom_id = f"universal_membership_check_{label.replace(' ', '_').lower()}"

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        member = interaction.user
        guild_settings = self.cog.get_guild_settings(interaction.guild_id)
        
        is_member, tier_name = await self.cog.check_membership_status(member)
        
        if is_member:
            confirm_message = guild_settings.get("membership_confirm_message", "🎉 Anda sudah menjadi anggota! Anda adalah anggota tier: **{tier_name}**.")
            
            final_message = confirm_message.format(tier_name=tier_name, member=member.mention)
            await interaction.followup.send(embed=self.cog._create_embed(description=final_message, color=self.cog.color_success), ephemeral=True)
            
        else:
            invite_message = guild_settings.get("membership_invite_message", "🥺 Anda belum menjadi anggota channel YouTube. Silakan berlangganan untuk mendapatkan role eksklusif! [LINK MEMBERSHIP]")
            
            final_message = invite_message.format(member=member.mention) 
            
            await interaction.followup.send(embed=self.cog._create_embed(description=final_message, color=self.cog.color_warning), ephemeral=True)

class UniversalMembershipView(discord.ui.View):
    def __init__(self, cog_instance, button_label: str):
        super().__init__(timeout=None)
        self.cog = cog_instance
        self.add_item(UniversalMembershipVerificationButton(
            cog_instance=self.cog,
            label=button_label,
            style=discord.ButtonStyle.primary,
            emoji="✅"
        ))

class DynamicRoleSelect(discord.ui.Select):
    def __init__(self, roles_data, custom_id, placeholder_text="✨ Pilih role yang ingin kamu ambil", rule_type="free"):
        options = []
        for role_id_str, data in roles_data.items():
            desc = data.get('description', None)
            options.append(discord.SelectOption(
                label=data['label'],
                emoji=data.get('emoji', None),
                value=role_id_str,
                description=desc
            ))
        self.rule_type = rule_type
        max_val = 1 if rule_type == "exclusive" else max(1, len(options))
        super().__init__(
            placeholder=placeholder_text,
            min_values=0,
            max_values=max_val,
            options=options,
            custom_id=custom_id
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user

        panel_role_ids = [int(r_id) for r_id in self.view.roles_data.keys()]
        selected_role_ids = [int(v) for v in self.values]

        if self.rule_type == "exclusive":
            if not selected_role_ids:
                to_remove = [guild.get_role(r_id) for r_id in panel_role_ids if guild.get_role(r_id) and guild.get_role(r_id) in member.roles]
                if to_remove:
                    await member.remove_roles(*to_remove, reason="Role Panel Copot Role")
                    result_embed = discord.Embed(
                        description="➖ Role kamu dari panel ini berhasil dilepas.",
                        color=0xFEE75C
                    )
                else:
                    result_embed = discord.Embed(
                        description="ℹ️ Tidak ada perubahan role.",
                        color=0x5865F2
                    )
            else:
                chosen_id = selected_role_ids[0]
                chosen_role = guild.get_role(chosen_id)
                if not chosen_role:
                    return await interaction.followup.send(
                        embed=discord.Embed(description="❌ Role tidak ditemukan di server.", color=0xED4245),
                        ephemeral=True
                    )
                if chosen_role in member.roles:
                    await member.remove_roles(chosen_role, reason="Role Panel Copot Role")
                    result_embed = discord.Embed(
                        description=f"➖ Role **{chosen_role.name}** berhasil dilepas.",
                        color=0xFEE75C
                    )
                else:
                    other_roles = [guild.get_role(r_id) for r_id in panel_role_ids if r_id != chosen_id and guild.get_role(r_id) and guild.get_role(r_id) in member.roles]
                    if other_roles:
                        await member.remove_roles(*other_roles, reason="Role Panel Switch (Eksklusif)")
                    await member.add_roles(chosen_role, reason="Role Panel Self-Assign (Eksklusif)")
                    if other_roles:
                        old_names = ", ".join(f"`{r.name}`" for r in other_roles)
                        result_embed = discord.Embed(
                            title="✅ Role Berhasil Dipasang",
                            description=f"➕ Role sekarang: **{chosen_role.name}**\n\n*(Role sebelumnya {old_names} otomatis dilepas sesuai aturan panel)*",
                            color=0x57F287
                        )
                    else:
                        result_embed = discord.Embed(
                            title="✅ Role Berhasil Dipasang",
                            description=f"➕ Role sekarang: **{chosen_role.name}**",
                            color=0x57F287
                        )
            result_embed.set_footer(text=f"Diperbarui untuk {member.display_name}")
            return await interaction.followup.send(embed=result_embed, ephemeral=True)

        added_roles = []
        removed_roles = []
        failed_roles = []

        if not selected_role_ids:
            result_embed = discord.Embed(
                description="ℹ️ Pilih salah satu atau beberapa role dari menu untuk memasang atau melepas.",
                color=0x5865F2
            )
            result_embed.set_footer(text=f"Diperbarui untuk {member.display_name}")
            return await interaction.followup.send(embed=result_embed, ephemeral=True)

        for role_id in selected_role_ids:
            role = guild.get_role(role_id)
            if not role:
                continue
            try:
                if role in member.roles:
                    await member.remove_roles(role, reason="Role Panel Self-Remove")
                    removed_roles.append(role.name)
                else:
                    await member.add_roles(role, reason="Role Panel Self-Assign")
                    added_roles.append(role.name)
            except discord.Forbidden:
                failed_roles.append(role.name)

        if not added_roles and not removed_roles and not failed_roles:
            result_embed = discord.Embed(
                description="ℹ️ Tidak ada perubahan role.",
                color=0x5865F2
            )
        else:
            lines = []
            if added_roles:
                lines.append(f"**➕ Berhasil Dipasang**\n" + "\n".join(f"> `{r}`" for r in added_roles))
            if removed_roles:
                lines.append(f"**➖ Berhasil Dilepas**\n" + "\n".join(f"> `{r}`" for r in removed_roles))
            if failed_roles:
                lines.append(f"**❌ Gagal (izin bot kurang tinggi)**\n" + "\n".join(f"> `{r}`" for r in failed_roles))

            result_embed = discord.Embed(
                title="✨ Pembaruan Role Selesai",
                description="\n\n".join(lines),
                color=0x57F287 if not failed_roles else 0xED4245
            )
        result_embed.set_footer(text=f"Diperbarui untuk {member.display_name}")
        await interaction.followup.send(embed=result_embed, ephemeral=True)


class DynamicRoleButton(discord.ui.Button):
    def __init__(self, role_id_str, data, message_id, rule_type="free"):
        super().__init__(
            label=data['label'],
            emoji=data.get('emoji', None),
            style=discord.ButtonStyle.secondary,
            custom_id=f"rolebtn_{message_id}_{role_id_str}"
        )
        self.role_id = int(role_id_str)
        self.message_id = str(message_id)
        self.rule_type = rule_type

    async def callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        role = interaction.guild.get_role(self.role_id)
        if not role:
            return await interaction.followup.send(
                embed=discord.Embed(description="❌ Role tidak ditemukan di server.", color=0xED4245),
                ephemeral=True
            )
        guild = interaction.guild
        member = interaction.user
        panel_role_ids = [int(r_id) for r_id in self.view.roles_data.keys()]
        try:
            if self.rule_type == "exclusive":
                if role in member.roles:
                    await member.remove_roles(role, reason="Role Panel Copot Role")
                    embed = discord.Embed(
                        description=f"➖ Role **{role.name}** berhasil dilepas.",
                        color=0xFEE75C
                    )
                else:
                    other_roles = [guild.get_role(r_id) for r_id in panel_role_ids if r_id != self.role_id and guild.get_role(r_id) and guild.get_role(r_id) in member.roles]
                    if other_roles:
                        await member.remove_roles(*other_roles, reason="Role Panel Switch (Eksklusif)")
                    await member.add_roles(role, reason="Role Panel Self-Assign (Eksklusif)")
                    if other_roles:
                        old_names = ", ".join(f"`{r.name}`" for r in other_roles)
                        embed = discord.Embed(
                            title="✅ Role Berhasil Dipasang",
                            description=f"➕ Role sekarang: **{role.name}**\n\n*(Role sebelumnya {old_names} otomatis dilepas sesuai aturan panel)*",
                            color=0x57F287
                        )
                    else:
                        embed = discord.Embed(
                            title="✅ Role Berhasil Dipasang",
                            description=f"➕ Role sekarang: **{role.name}**",
                            color=0x57F287
                        )
            else:
                if role in member.roles:
                    await member.remove_roles(role, reason="Role Panel Self-Remove")
                    embed = discord.Embed(
                        description=f"➖ Role **{role.name}** berhasil dilepas.",
                        color=0xFEE75C
                    )
                else:
                    await member.add_roles(role, reason="Role Panel Self-Assign")
                    embed = discord.Embed(
                        description=f"➕ Role **{role.name}** berhasil diberikan.",
                        color=0x57F287
                    )
            embed.set_footer(text=f"Diperbarui untuk {member.display_name}")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                embed=discord.Embed(description="❌ Bot tidak memiliki izin untuk mengatur role ini. Pastikan posisi role bot berada di atas role tersebut.", color=0xED4245),
                ephemeral=True
            )


class DynamicRoleView(discord.ui.View):
    def __init__(self, mode, roles_data, message_id, placeholder_text="✨ Pilih role yang ingin kamu ambil", rule_type="free"):
        super().__init__(timeout=None)
        self.roles_data = roles_data or {}
        self.message_id = str(message_id)
        self.mode = mode
        self.placeholder_text = placeholder_text
        self.rule_type = rule_type
        if not self.roles_data:
            empty_btn = discord.ui.Button(label="Belum ada role yang ditambahkan", disabled=True, style=discord.ButtonStyle.secondary, custom_id=f"roleempty_{message_id}")
            self.add_item(empty_btn)
            return
        if mode == "select":
            self.add_item(DynamicRoleSelect(self.roles_data, f"roleselect_{message_id}", placeholder_text, rule_type))
        elif mode == "button":
            for role_id_str, data in self.roles_data.items():
                self.add_item(DynamicRoleButton(role_id_str, data, message_id, rule_type))


class GlobalTicketButtonView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Buka Tiket Bantuan", style=discord.ButtonStyle.success, emoji="🎫", custom_id="rtm_ticket_open")
    async def open_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_ticket_open(interaction)


class GlobalTicketCloseView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Tutup Tiket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="rtm_ticket_close")
    async def close_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_ticket_close(interaction)


class BoosterMessageModal(discord.ui.Modal, title="Atur Pesan Sambutan Booster"):
    def __init__(self, cog_instance, guild_id, current_settings):
        super().__init__()
        self.cog = cog_instance
        self.guild_id = guild_id
        
        default_msg = (
            "🎉 **BOOSTER BARU!** Terima kasih banyak {user_mention} telah mem-boost **{server}**! 💜\n"
            "Berkat dukunganmu, server kita sekarang memiliki **{boost_count} Boosts** ({tier})! Nikmati role dan fasilitas eksklusifmu! 🚀"
        )
        self.message_input = discord.ui.TextInput(
            label="Isi Pesan Booster",
            placeholder="Gunakan {user}, {user_mention}, {server}, {boost_count}, {tier}",
            default=current_settings.get("boost_message") or default_msg,
            max_length=2000,
            required=True,
            style=discord.TextStyle.paragraph
        )
        self.banner_input = discord.ui.TextInput(
            label="URL Gambar Banner (Opsional)",
            placeholder="Contoh: https://example.com/nitro_banner.png",
            default=current_settings.get("boost_image_url") or "",
            max_length=1000,
            required=False
        )
        self.add_item(self.message_input)
        self.add_item(self.banner_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        banner_url = self.banner_input.value.strip() or None
        if banner_url and not (banner_url.startswith("http://") or banner_url.startswith("https://")):
            return await interaction.followup.send(embed=self.cog._create_embed(description="❌ URL Banner tidak valid. Harus dimulai dengan `http://` atau `https://`.", color=self.cog.color_error), ephemeral=True)

        guild_settings = self.cog.get_guild_settings(self.guild_id)
        guild_settings["boost_message"] = self.message_input.value.strip()
        guild_settings["boost_image_url"] = banner_url
        self.cog.save_settings()

        await interaction.followup.send(embed=self.cog._create_embed(description="✅ Format pesan booster berhasil disimpan!", color=self.cog.color_success), ephemeral=True)


class AutoRoleSetupView(discord.ui.View):
    def __init__(self, cog, guild, author):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.author = author

        role_select = discord.ui.RoleSelect(
            placeholder="Pilih role untuk member baru (Auto Role)...",
            row=0
        )
        role_select.callback = self.on_role_select
        self.add_item(role_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.author

    async def on_role_select(self, interaction: discord.Interaction):
        role_id_str = interaction.data.get("values", [None])[0]
        if role_id_str:
            role = self.guild.get_role(int(role_id_str))
            if role:
                if role >= self.guild.me.top_role:
                    return await interaction.response.send_message("❌ Role tersebut berada di atas atau sejajar dengan role bot! Pindahkan posisi role bot lebih tinggi.", ephemeral=True)
                settings = self.cog.get_guild_settings(self.guild.id)
                settings["auto_role_id"] = role.id
                self.cog.save_settings()
                await interaction.response.send_message(f"✅ Auto Role berhasil diatur ke **{role.name}** ({role.mention})!", ephemeral=True)

    @discord.ui.button(label="Hapus / Matikan Auto Role", style=discord.ButtonStyle.danger, emoji="❌", row=1)
    async def disable_auto_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.get_guild_settings(self.guild.id)
        settings["auto_role_id"] = None
        self.cog.save_settings()
        await interaction.response.send_message("🔴 Auto Role berhasil dimatikan/dihapus.", ephemeral=True)


class LogChannelSetupView(discord.ui.View):
    def __init__(self, cog, guild, author):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.author = author

        ch_select = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text],
            placeholder="Pilih kanal audit log bot...",
            row=0
        )
        ch_select.callback = self.on_channel_select
        self.add_item(ch_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.author

    async def on_channel_select(self, interaction: discord.Interaction):
        ch_id = interaction.data.get("values", [None])[0]
        if ch_id:
            ch = self.guild.get_channel(int(ch_id))
            settings = self.cog.get_guild_settings(self.guild.id)
            settings["log_channel_id"] = ch.id
            self.cog.save_settings()
            await interaction.response.send_message(f"✅ Log Channel diatur ke {ch.mention}!", ephemeral=True)

    @discord.ui.button(label="Nonaktifkan Log Channel", style=discord.ButtonStyle.danger, emoji="❌", row=1)
    async def disable_log(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.get_guild_settings(self.guild.id)
        settings["log_channel_id"] = None
        self.cog.save_settings()
        await interaction.response.send_message("🔴 Log Channel dinonaktifkan.", ephemeral=True)


class WelcomeChannelSetupView(discord.ui.View):
    def __init__(self, cog, guild, author):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.author = author

        ch_select = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text],
            placeholder="Pilih kanal pesan selamat datang...",
            row=0
        )
        ch_select.callback = self.on_channel_select
        self.add_item(ch_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.author

    async def on_channel_select(self, interaction: discord.Interaction):
        ch_id = interaction.data.get("values", [None])[0]
        if ch_id:
            ch = self.guild.get_channel(int(ch_id))
            settings = self.cog.get_guild_settings(self.guild.id)
            settings["welcome_channel_id"] = ch.id
            self.cog.save_settings()
            await interaction.response.send_message(f"✅ Welcome Channel diatur ke {ch.mention}!", ephemeral=True)

    @discord.ui.button(label="Edit Teks & Banner Welcome", style=discord.ButtonStyle.primary, emoji="✏️", row=1)
    async def edit_welcome_msg(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.get_guild_settings(self.guild.id)
        await interaction.response.send_modal(WelcomeMessageModal(self.cog, self.guild.id, settings))

    @discord.ui.button(label="Nonaktifkan Welcome", style=discord.ButtonStyle.danger, emoji="❌", row=1)
    async def disable_welcome(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.get_guild_settings(self.guild.id)
        settings["welcome_channel_id"] = None
        self.cog.save_settings()
        await interaction.response.send_message("🔴 Welcome Channel dinonaktifkan.", ephemeral=True)


class BoosterSetupView(discord.ui.View):
    def __init__(self, cog, guild, author):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.author = author

        ch_select = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text],
            placeholder="Pilih kanal untuk pengumuman booster...",
            row=0
        )
        ch_select.callback = self.on_channel_select
        self.add_item(ch_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.author

    async def on_channel_select(self, interaction: discord.Interaction):
        ch = interaction.data.get("values", [None])[0]
        if ch:
            target_ch = self.guild.get_channel(int(ch))
            settings = self.cog.get_guild_settings(self.guild.id)
            settings["boost_channel_id"] = target_ch.id
            settings["boost_enabled"] = True
            self.cog.save_settings()
            await interaction.response.send_message(f"✅ Kanal booster diatur ke {target_ch.mention}!", ephemeral=True)

    @discord.ui.button(label="Edit Teks Pesan", style=discord.ButtonStyle.primary, emoji="✏️", row=1)
    async def edit_msg_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.get_guild_settings(self.guild.id)
        await interaction.response.send_modal(BoosterMessageModal(self.cog, self.guild.id, settings))

    @discord.ui.button(label="Test Kirim Pesan", style=discord.ButtonStyle.success, emoji="🧪", row=1)
    async def test_send_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.get_guild_settings(self.guild.id)
        if not settings.get("boost_channel_id"):
            return await interaction.response.send_message("❌ Kanal booster belum diatur! Pilih kanal terlebih dahulu.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self.cog.send_booster_announcement(self.guild, interaction.user, is_test=True)
        target_ch = self.guild.get_channel(settings["boost_channel_id"])
        await interaction.followup.send(f"✅ Pesan simulasi booster berhasil dikirim ke {target_ch.mention if target_ch else 'kanal'}!", ephemeral=True)

    @discord.ui.button(label="Toggle Status Booster", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)
    async def toggle_booster_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.get_guild_settings(self.guild.id)
        current = settings.get("boost_enabled", True)
        settings["boost_enabled"] = not current
        self.cog.save_settings()
        status_str = "🟢 Diaktifkan" if settings["boost_enabled"] else "🔴 Dinonaktifkan"
        await interaction.response.send_message(f"Status pesan booster kini: **{status_str}**", ephemeral=True)


class TicketMessageModal(discord.ui.Modal, title="Atur Pesan Panel Tiket"):
    def __init__(self, cog_instance, guild_id, current_settings):
        super().__init__()
        self.cog = cog_instance
        self.guild_id = guild_id

        default_title = "🎫 Pusat Bantuan & Tiket Server"
        default_desc = (
            "Butuh bantuan, verifikasi staf, atau ingin melaporkan kendala?\n"
            "Klik tombol Buka Tiket di bawah untuk membuka kanal percakapan pribadi langsung bersama tim staf kami."
        )
        self.title_input = discord.ui.TextInput(
            label="Judul Panel Tiket",
            default=current_settings.get("ticket_panel_title") or default_title,
            max_length=100,
            required=True
        )
        self.desc_input = discord.ui.TextInput(
            label="Deskripsi / Isi Pesan Panel",
            default=current_settings.get("ticket_panel_desc") or default_desc,
            style=discord.TextStyle.paragraph,
            max_length=2000,
            required=True
        )
        self.add_item(self.title_input)
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_settings = self.cog.get_guild_settings(self.guild_id)
        guild_settings["ticket_panel_title"] = self.title_input.value.strip()
        guild_settings["ticket_panel_desc"] = self.desc_input.value.strip()
        self.cog.save_settings()
        await interaction.followup.send(
            embed=self.cog._create_embed(description="✅ Pesan panel tiket berhasil disimpan!", color=self.cog.color_success),
            ephemeral=True
        )


class TicketSetupView(discord.ui.View):
    def __init__(self, cog, guild, author):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.category_id = None
        self.support_role_id = None
        self.target_channel_id = None

        cat_select = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.category],
            placeholder="1. Pilih Kategori Kanal Tiket...",
            row=0
        )
        cat_select.callback = self.on_cat_select
        self.add_item(cat_select)

        role_select = discord.ui.RoleSelect(
            placeholder="2. Pilih Role Tim Staf Tiket...",
            row=1
        )
        role_select.callback = self.on_role_select
        self.add_item(role_select)

        target_ch_select = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text],
            placeholder="3. Pilih Kanal Penempatan Panel Tiket...",
            row=2
        )
        target_ch_select.callback = self.on_target_ch_select
        self.add_item(target_ch_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.author

    async def on_cat_select(self, interaction: discord.Interaction):
        cat_val = interaction.data.get("values", [None])[0]
        if cat_val:
            self.category_id = int(cat_val)
            settings = self.cog.get_guild_settings(self.guild.id)
            settings["ticket_category_id"] = self.category_id
            self.cog.save_settings()
            await interaction.response.send_message(f"✅ Kategori tiket disimpan!", ephemeral=True)

    async def on_role_select(self, interaction: discord.Interaction):
        role_val = interaction.data.get("values", [None])[0]
        if role_val:
            self.support_role_id = int(role_val)
            settings = self.cog.get_guild_settings(self.guild.id)
            settings["ticket_support_role_id"] = self.support_role_id
            self.cog.save_settings()
            await interaction.response.send_message(f"✅ Role staf tiket disimpan!", ephemeral=True)

    async def on_target_ch_select(self, interaction: discord.Interaction):
        ch_val = interaction.data.get("values", [None])[0]
        if ch_val:
            self.target_channel_id = int(ch_val)
            await interaction.response.send_message(f"✅ Kanal target dipilih! Klik tombol 'Pasang Panel Tiket' di bawah untuk memposting.", ephemeral=True)

    @discord.ui.button(label="Edit Teks Pesan", style=discord.ButtonStyle.primary, emoji="✏️", row=3)
    async def edit_panel_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.get_guild_settings(self.guild.id)
        await interaction.response.send_modal(TicketMessageModal(self.cog, self.guild.id, settings))

    @discord.ui.button(label="Pasang Panel Tiket", style=discord.ButtonStyle.success, emoji="🚀", row=3)
    async def deploy_ticket_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.get_guild_settings(self.guild.id)
        target_ch = self.guild.get_channel(self.target_channel_id) if self.target_channel_id else interaction.channel
        if not target_ch or not target_ch.permissions_for(self.guild.me).send_messages:
            return await interaction.response.send_message("❌ Kanal target tidak valid atau bot tidak memiliki izin mengirim pesan.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        ticket_view = GlobalTicketButtonView(self.cog)
        
        panel_title = settings.get("ticket_panel_title") or "🎫 Pusat Bantuan & Tiket Server"
        panel_desc = settings.get("ticket_panel_desc") or (
            "Butuh bantuan, verifikasi staf, atau ingin melaporkan kendala?\n"
            "Klik tombol **Buka Tiket Bantuan** di bawah ini untuk memulai percakapan pribadi langsung dengan tim staf kami."
        )
        support_role = self.guild.get_role(settings.get("ticket_support_role_id")) if settings.get("ticket_support_role_id") else None

        card = build_v2_card(
            title=panel_title,
            description=f"> {panel_desc.replace(chr(10), chr(10) + '> ')}",
            fields=[
                {"name": "⏰ Waktu Respon", "value": "`Cepat & Tanggap`"},
                {"name": "🔒 Keamanan & Privasi", "value": "`Kanal Khusus Pribadi (Terenkripsi)`"},
                {"name": "🛡️ Tim Staf Siaga", "value": support_role.mention if support_role else "`Admin & Staf`"}
            ],
            color=0x2ECC71,
            footer="Klik tombol Buka Tiket Bantuan di bawah untuk membuat kanal tiket Anda."
        )
        components = [card, *ticket_view.to_components()]
        resp = await send_v2_message(self.cog.bot, target_ch.id, components)
        if not resp or "id" not in resp:
            embed = discord.Embed(
                title=panel_title,
                description=panel_desc,
                color=0x2ECC71
            )
            embed.add_field(name="🛡️ Tim Staf Siaga", value=support_role.mention if support_role else "Admin & Staf", inline=False)
            embed.set_footer(text="Klik tombol di bawah untuk membuka tiket bantuan.")
            await target_ch.send(embed=embed, view=ticket_view)
        else:
            register_view(self.cog.bot, ticket_view, message_id=int(resp["id"]))

        await interaction.followup.send(f"✅ Panel tiket berhasil dipasang di {target_ch.mention}!", ephemeral=True)





class RolePanelDashboardView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author

        settings = self.cog.get_guild_settings(guild.id)
        panels = settings.get("role_panels", {})

        if panels:
            options = []
            for msg_id_str, pdata in list(panels.items())[:25]:
                roles = pdata.get("roles") or pdata.get("roles_data") or {}
                ch = guild.get_channel(pdata.get("channel_id"))
                ch_name = ch.name if ch else "Kanal terhapus"
                mode_str = "Dropdown" if pdata.get("mode") == "select" else "Tombol"
                rule_str = "Ketat" if pdata.get("rule_type") == "exclusive" else "Bebas"
                title_str = (pdata.get("title") or f"Panel {msg_id_str}")[:50]
                desc_str = f"{len(roles)} role | {mode_str} | {rule_str} | {ch_name}"[:100]
                options.append(discord.SelectOption(
                    label=title_str,
                    value=msg_id_str,
                    description=desc_str,
                    emoji="🎭"
                ))
            if options:
                panel_select = discord.ui.Select(
                    placeholder="Pilih panel yang ingin kamu kelola / edit...",
                    options=options,
                    row=0
                )
                panel_select.callback = self.on_select_panel
                self.add_item(panel_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Menu ini hanya dapat diakses oleh moderator yang memanggilnya.", ephemeral=True)
            return False
        return True

    async def on_select_panel(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        msg_id_str = interaction.data.get("values", [None])[0]
        if not msg_id_str:
            return
        manage_view = RolePanelManageView(self.cog, self.guild, self.author, msg_id_str)
        embed = manage_view.build_manage_embed()
        await interaction.edit_original_response(embed=embed, view=manage_view)

    @discord.ui.button(label="Buat Panel Baru", style=discord.ButtonStyle.primary, emoji="➕", row=1)
    async def create_new_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        wizard_view = RolePanelWizardChannelView(self.cog, self.guild, self.author)
        embed = discord.Embed(
            title="✨ Buat Panel Role Baru — Langkah 1/4",
            description="Pilih kanal teks tempat panel ambil role mandiri ini akan dipasang untuk anggota server:",
            color=0x5865F2
        )
        await interaction.response.edit_message(embed=embed, view=wizard_view)

    def build_dashboard_embed(self) -> discord.Embed:
        settings = self.cog.get_guild_settings(self.guild.id)
        panels = settings.get("role_panels", {})
        count = len(panels)

        desc = (
            "Selamat datang di **Studio Panel Role**!\n\n"
            "Di sini kamu bisa membuat panel ambil role baru, menambahkan atau menghapus role, "
            "mengubah teks panduan, serta mengatur aturan seleksi (**Bebas** atau **Ketat/1 Role Saja**).\n\n"
        )
        if count == 0:
            desc += "💡 *Belum ada panel aktif di server ini. Klik tombol **Buat Panel Baru** di bawah untuk memulai!*"
        else:
            desc += f"📊 Terdeteksi **{count} panel aktif** di server ini. Pilih panel pada menu dropdown di bawah untuk mengeditnya:"

        embed = discord.Embed(
            title="🎭 Studio Panel Role Mandiri",
            description=desc,
            color=0x5865F2
        )
        embed.set_footer(text=f"Server: {self.guild.name}")
        return embed


class RolePanelManageView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, message_id_str: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.message_id_str = message_id_str

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Menu ini hanya dapat diakses oleh moderator yang memanggilnya.", ephemeral=True)
            return False
        return True

    def get_panel_data(self) -> dict:
        settings = self.cog.get_guild_settings(self.guild.id)
        return settings.get("role_panels", {}).get(self.message_id_str, {})

    def build_manage_embed(self) -> discord.Embed:
        pdata = self.get_panel_data()
        if not pdata:
            return discord.Embed(description="❌ Data panel tidak ditemukan di database.", color=0xED4245)

        title = pdata.get("title", f"Panel {self.message_id_str}")
        desc = pdata.get("description", "Tidak ada deskripsi")
        ch = self.guild.get_channel(pdata.get("channel_id"))
        ch_mention = ch.mention if ch else "`Kanal Dihapus`"
        mode_str = "Dropdown Menu (Select)" if pdata.get("mode") == "select" else "Tombol Interaktif (Button)"
        rule_str = "⚖️ Ketat (Hanya 1 Role / Saling Melepas)" if pdata.get("rule_type") == "exclusive" else "✨ Bebas (Bisa Ambil / Lepas Banyak Role)"
        roles = pdata.get("roles") or pdata.get("roles_data") or {}

        role_list = []
        for r_id, r_info in roles.items():
            r_obj = self.guild.get_role(int(r_id))
            r_tag = r_obj.mention if r_obj else f"`ID:{r_id}`"
            emoji = f"{r_info.get('emoji')} " if r_info.get('emoji') else ""
            desc_text = f" — *{r_info.get('description')}*" if r_info.get('description') else ""
            role_list.append(f"> • {emoji}{r_tag}{desc_text}")

        roles_text = "\n".join(role_list) if role_list else "> *(Belum ada role)*"

        embed = discord.Embed(
            title=f"🛠️ Kelola: {title}",
            description=(
                f"**Kanal Target:** {ch_mention}\n"
                f"**ID Pesan:** `{self.message_id_str}`\n"
                f"**Tampilan:** `{mode_str}`\n"
                f"**Aturan:** `{rule_str}`\n\n"
                f"**Petunjuk Panel:**\n*{desc}*\n\n"
                f"**Daftar Role Aktif ({len(roles)}):**\n{roles_text}"
            ),
            color=0x5865F2
        )
        embed.set_footer(text="Gunakan tombol di bawah untuk mengubah setelan atau menambah/menghapus role.")
        return embed

    @discord.ui.button(label="Tambah Role", style=discord.ButtonStyle.success, emoji="➕", row=0)
    async def add_role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pdata = self.get_panel_data()
        roles = pdata.get("roles") or pdata.get("roles_data") or {}
        if len(roles) >= 25:
            return await interaction.response.send_message("❌ Panel ini sudah mencapai batas maksimal 25 role.", ephemeral=True)
        view = RolePanelAddRolePickerView(self.cog, self.guild, self.author, self.message_id_str)
        embed = discord.Embed(
            title="➕ Tambah Role Baru ke Panel",
            description="Pilih role dari menu dropdown di bawah yang ingin kamu tambahkan ke panel ini:",
            color=0x5865F2
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Hapus Role", style=discord.ButtonStyle.danger, emoji="➖", row=0)
    async def remove_role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pdata = self.get_panel_data()
        roles = pdata.get("roles") or pdata.get("roles_data") or {}
        if not roles:
            return await interaction.response.send_message("❌ Belum ada role di panel ini untuk dihapus.", ephemeral=True)
        view = RolePanelRemoveRolePickerView(self.cog, self.guild, self.author, self.message_id_str)
        embed = discord.Embed(
            title="➖ Hapus Role dari Panel",
            description="Pilih role yang ingin kamu keluarkan dari panel ini:",
            color=0xED4245
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Ubah Teks & Judul", style=discord.ButtonStyle.secondary, emoji="📝", row=1)
    async def edit_text_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pdata = self.get_panel_data()
        modal = RolePanelTextEditModal(self.cog, self.guild, self.author, self.message_id_str, pdata)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Ganti Aturan (Ketat/Bebas)", style=discord.ButtonStyle.secondary, emoji="⚖️", row=1)
    async def toggle_rule_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        settings = self.cog.get_guild_settings(self.guild.id)
        pdata = settings.get("role_panels", {}).get(self.message_id_str)
        if not pdata:
            return
        curr_rule = pdata.get("rule_type", "free")
        pdata["rule_type"] = "exclusive" if curr_rule == "free" else "free"
        self.cog.save_settings()
        await self.cog._sync_role_panel_message(self.guild, pdata, self.message_id_str)
        embed = self.build_manage_embed()
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Ganti Gaya (Menu/Tombol)", style=discord.ButtonStyle.secondary, emoji="🎨", row=1)
    async def toggle_mode_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        settings = self.cog.get_guild_settings(self.guild.id)
        pdata = settings.get("role_panels", {}).get(self.message_id_str)
        if not pdata:
            return
        curr_mode = pdata.get("mode", "select")
        pdata["mode"] = "button" if curr_mode == "select" else "select"
        self.cog.save_settings()
        await self.cog._sync_role_panel_message(self.guild, pdata, self.message_id_str)
        embed = self.build_manage_embed()
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Hapus Panel", style=discord.ButtonStyle.danger, emoji="🗑️", row=2)
    async def delete_panel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        settings = self.cog.get_guild_settings(self.guild.id)
        pdata = settings.get("role_panels", {}).pop(self.message_id_str, None)
        self.cog.save_settings()
        if pdata:
            ch = self.guild.get_channel(pdata.get("channel_id"))
            if ch:
                try:
                    msg = await ch.fetch_message(int(self.message_id_str))
                    await msg.delete()
                except Exception:
                    pass
        dash_view = RolePanelDashboardView(self.cog, self.guild, self.author)
        embed = dash_view.build_dashboard_embed()
        await interaction.edit_original_response(embed=embed, view=dash_view)

    @discord.ui.button(label="Kembali ke Studio", style=discord.ButtonStyle.secondary, emoji="◀️", row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        dash_view = RolePanelDashboardView(self.cog, self.guild, self.author)
        embed = dash_view.build_dashboard_embed()
        await interaction.edit_original_response(embed=embed, view=dash_view)


class RolePanelAddRolePickerView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, message_id_str: str):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.message_id_str = message_id_str

        role_select = discord.ui.RoleSelect(
            placeholder="Pilih role yang ingin ditambahkan ke panel...",
            min_values=1,
            max_values=1,
            row=0
        )
        role_select.callback = self.on_role_chosen
        self.add_item(role_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    async def on_role_chosen(self, interaction: discord.Interaction):
        role_id_str = interaction.data.get("values", [None])[0]
        if not role_id_str:
            return
        role = self.guild.get_role(int(role_id_str))
        if not role:
            return await interaction.response.send_message("❌ Role tidak ditemukan.", ephemeral=True)
        if role >= self.guild.me.top_role or role.managed:
            return await interaction.response.send_message("❌ Role ini tidak dapat diatur oleh bot karena posisinya di atas bot atau dikelola oleh integrasi.", ephemeral=True)
        modal = RolePanelRoleDescModal(self.cog, self.guild, self.author, self.message_id_str, role)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary, emoji="✖️", row=1)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        manage_view = RolePanelManageView(self.cog, self.guild, self.author, self.message_id_str)
        embed = manage_view.build_manage_embed()
        await interaction.response.edit_message(embed=embed, view=manage_view)


class RolePanelRoleDescModal(discord.ui.Modal, title="Detail Role untuk Panel"):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, message_id_str: str, role: discord.Role):
        super().__init__()
        self.cog = cog
        self.guild = guild
        self.author = author
        self.message_id_str = message_id_str
        self.role = role

        self.label_input = discord.ui.TextInput(
            label="Label Nama Role",
            default=role.name,
            max_length=50,
            required=True
        )
        self.emoji_input = discord.ui.TextInput(
            label="Emoji (Opsional)",
            placeholder="Contoh: 🎭 atau 🎮",
            required=False,
            max_length=10
        )
        self.desc_input = discord.ui.TextInput(
            label="Penjelasan / Deskripsi Role",
            placeholder=f"Contoh: Akses ruang obrolan dan role {role.name}",
            default=f"Role untuk {role.name}",
            max_length=100,
            required=True
        )
        self.add_item(self.label_input)
        self.add_item(self.emoji_input)
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        settings = self.cog.get_guild_settings(self.guild.id)
        pdata = settings.get("role_panels", {}).get(self.message_id_str)
        if not pdata:
            return await interaction.followup.send("❌ Data panel tidak ditemukan.", ephemeral=True)

        if "roles" not in pdata:
            pdata["roles"] = {}

        pdata["roles"][str(self.role.id)] = {
            "label": self.label_input.value.strip(),
            "emoji": self.emoji_input.value.strip() or None,
            "description": self.desc_input.value.strip()
        }
        pdata["roles_data"] = pdata["roles"]
        self.cog.save_settings()

        await self.cog._sync_role_panel_message(self.guild, pdata, self.message_id_str)

        manage_view = RolePanelManageView(self.cog, self.guild, self.author, self.message_id_str)
        embed = manage_view.build_manage_embed()
        await interaction.edit_original_response(embed=embed, view=manage_view)


class RolePanelRemoveRolePickerView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, message_id_str: str):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.message_id_str = message_id_str

        settings = self.cog.get_guild_settings(guild.id)
        pdata = settings.get("role_panels", {}).get(message_id_str, {})
        roles = pdata.get("roles") or pdata.get("roles_data") or {}

        options = []
        for r_id, r_info in roles.items():
            r_obj = guild.get_role(int(r_id))
            r_name = r_obj.name if r_obj else f"Role {r_id}"
            options.append(discord.SelectOption(
                label=r_name[:50],
                value=r_id,
                description=(r_info.get("description") or f"ID: {r_id}")[:100],
                emoji="🗑️"
            ))

        if options:
            select = discord.ui.Select(
                placeholder="Pilih role yang ingin dihapus dari panel...",
                options=options,
                row=0
            )
            select.callback = self.on_remove_selected
            self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    async def on_remove_selected(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        r_id_str = interaction.data.get("values", [None])[0]
        if not r_id_str:
            return
        settings = self.cog.get_guild_settings(self.guild.id)
        pdata = settings.get("role_panels", {}).get(self.message_id_str)
        if pdata:
            roles = pdata.get("roles") or pdata.get("roles_data") or {}
            roles.pop(r_id_str, None)
            pdata["roles"] = roles
            pdata["roles_data"] = roles
            self.cog.save_settings()
            await self.cog._sync_role_panel_message(self.guild, pdata, self.message_id_str)

        manage_view = RolePanelManageView(self.cog, self.guild, self.author, self.message_id_str)
        embed = manage_view.build_manage_embed()
        await interaction.edit_original_response(embed=embed, view=manage_view)

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary, emoji="✖️", row=1)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        manage_view = RolePanelManageView(self.cog, self.guild, self.author, self.message_id_str)
        embed = manage_view.build_manage_embed()
        await interaction.response.edit_message(embed=embed, view=manage_view)


class RolePanelTextEditModal(discord.ui.Modal, title="Ubah Teks & Judul Panel"):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, message_id_str: str, pdata: dict):
        super().__init__()
        self.cog = cog
        self.guild = guild
        self.author = author
        self.message_id_str = message_id_str

        self.title_input = discord.ui.TextInput(
            label="Judul Panel",
            default=pdata.get("title", "🎭 AMBIL ROLE MANDIRI"),
            max_length=100,
            required=True
        )
        self.desc_input = discord.ui.TextInput(
            label="Deskripsi / Petunjuk Ambil Role",
            default=pdata.get("description", "Pilih role yang kamu inginkan dari menu di bawah:"),
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True
        )
        self.placeholder_input = discord.ui.TextInput(
            label="Teks Placeholder Dropdown",
            default=pdata.get("placeholder", "✨ Pilih role yang ingin kamu ambil"),
            max_length=100,
            required=False
        )
        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        self.add_item(self.placeholder_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        settings = self.cog.get_guild_settings(self.guild.id)
        pdata = settings.get("role_panels", {}).get(self.message_id_str)
        if not pdata:
            return await interaction.followup.send("❌ Data panel tidak ditemukan.", ephemeral=True)

        pdata["title"] = self.title_input.value.strip()
        pdata["description"] = self.desc_input.value.strip()
        pdata["placeholder"] = self.placeholder_input.value.strip() or "✨ Pilih role yang ingin kamu ambil"
        self.cog.save_settings()

        await self.cog._sync_role_panel_message(self.guild, pdata, self.message_id_str)

        manage_view = RolePanelManageView(self.cog, self.guild, self.author, self.message_id_str)
        embed = manage_view.build_manage_embed()
        await interaction.edit_original_response(embed=embed, view=manage_view)


class RolePanelWizardChannelView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.author = author

        ch_select = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text],
            placeholder="Pilih kanal tujuan pemasangan panel...",
            row=0
        )
        ch_select.callback = self.on_channel_chosen
        self.add_item(ch_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    async def on_channel_chosen(self, interaction: discord.Interaction):
        ch_id = interaction.data.get("values", [None])[0]
        if not ch_id:
            return
        target_channel = self.guild.get_channel(int(ch_id))
        if not target_channel:
            return await interaction.response.send_message("❌ Kanal tidak ditemukan.", ephemeral=True)
        rule_view = RolePanelWizardRuleView(self.cog, self.guild, self.author, target_channel)
        embed = discord.Embed(
            title="⚖️ Aturan Pemilihan Role — Langkah 2/4",
            description=(
                f"Kanal Target: {target_channel.mention}\n\n"
                "Pilih aturan pemilihan role untuk panel ini:\n\n"
                "• **Mode Bebas (Multi-Role)**\n"
                "> Member bisa memilih dan mengoleksi lebih dari satu role secara fleksibel.\n\n"
                "• **Mode Ketat (Pilih 1 Saja)**\n"
                "> Cocok untuk kategori seperti Gender atau Umur. Member hanya boleh punya 1 role; jika memilih role lain, role lama langsung dilepas otomatis."
            ),
            color=0x5865F2
        )
        await interaction.response.edit_message(embed=embed, view=rule_view)

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary, emoji="✖️", row=1)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        dash_view = RolePanelDashboardView(self.cog, self.guild, self.author)
        embed = dash_view.build_dashboard_embed()
        await interaction.response.edit_message(embed=embed, view=dash_view)


class RolePanelWizardRuleView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, target_channel: discord.TextChannel):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.target_channel = target_channel

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    @discord.ui.button(label="Mode Bebas (Bisa Banyak Role)", style=discord.ButtonStyle.primary, emoji="✨", row=0)
    async def free_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        display_view = RolePanelWizardDisplayView(self.cog, self.guild, self.author, self.target_channel, "free")
        embed = discord.Embed(
            title="🎨 Gaya Tampilan Panel — Langkah 3/4",
            description=(
                f"Kanal Target: {self.target_channel.mention}\n"
                f"Aturan: `Bebas (Multi-Role)`\n\n"
                "Pilih gaya tampilan interaktif untuk member:\n\n"
                "• **Dropdown Menu**: Rapi, hemat tempat, cocok jika rolenya banyak.\n"
                "• **Tombol (Buttons)**: Visual mencolok, langsung diklik tanpa membuka menu."
            ),
            color=0x5865F2
        )
        await interaction.response.edit_message(embed=embed, view=display_view)

    @discord.ui.button(label="Mode Ketat (Hanya 1 Role)", style=discord.ButtonStyle.success, emoji="⚖️", row=0)
    async def exclusive_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        display_view = RolePanelWizardDisplayView(self.cog, self.guild, self.author, self.target_channel, "exclusive")
        embed = discord.Embed(
            title="🎨 Gaya Tampilan Panel — Langkah 3/4",
            description=(
                f"Kanal Target: {self.target_channel.mention}\n"
                f"Aturan: `Ketat (Hanya 1 Saja)`\n\n"
                "Pilih gaya tampilan interaktif untuk member:\n\n"
                "• **Dropdown Menu**: Rapi, hemat tempat, cocok jika rolenya banyak.\n"
                "• **Tombol (Buttons)**: Visual mencolok, langsung diklik tanpa membuka menu."
            ),
            color=0x5865F2
        )
        await interaction.response.edit_message(embed=embed, view=display_view)


class RolePanelWizardDisplayView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, target_channel: discord.TextChannel, rule_type: str):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.target_channel = target_channel
        self.rule_type = rule_type

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    @discord.ui.button(label="Dropdown Menu", style=discord.ButtonStyle.primary, emoji="🔽", row=0)
    async def dropdown_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RolePanelCreateModal(self.cog, self.target_channel, self.rule_type, "select")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Tombol Interaktif", style=discord.ButtonStyle.success, emoji="🔘", row=0)
    async def button_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RolePanelCreateModal(self.cog, self.target_channel, self.rule_type, "button")
        await interaction.response.send_modal(modal)


class RolePanelCreateModal(discord.ui.Modal, title="Isi Judul & Deskripsi Panel"):
    def __init__(self, cog, target_channel: discord.TextChannel, rule_type: str, mode: str):
        super().__init__()
        self.cog = cog
        self.target_channel = target_channel
        self.rule_type = rule_type
        self.mode = mode

        self.title_input = discord.ui.TextInput(
            label="Judul Panel",
            placeholder="Contoh: 🎭 Pilih Role Akses & Minat",
            default="🎭 AMBIL ROLE MANDIRI",
            max_length=100,
            required=True
        )
        self.desc_input = discord.ui.TextInput(
            label="Deskripsi / Petunjuk Ambil Role",
            placeholder="Tuliskan petunjuk untuk member...",
            default="Pilih role yang kamu inginkan untuk membuka akses channel dan notifikasi server:",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True
        )
        self.placeholder_input = discord.ui.TextInput(
            label="Placeholder Dropdown (Khusus Menu)",
            default="✨ Pilih role yang ingin kamu ambil",
            max_length=100,
            required=False
        )
        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        self.add_item(self.placeholder_input)

    async def on_submit(self, interaction: discord.Interaction):
        picker_view = RolePanelWizardRolePickerView(
            self.cog,
            self.target_channel,
            self.rule_type,
            self.mode,
            self.title_input.value.strip(),
            self.desc_input.value.strip(),
            self.placeholder_input.value.strip() or "✨ Pilih role yang ingin kamu ambil"
        )
        rule_label = "Ketat (1 Role Saja)" if self.rule_type == "exclusive" else "Bebas"
        embed = discord.Embed(
            title="🎭 Pilih Role Pertama — Langkah 4/4",
            description=(
                f"Judul: **{self.title_input.value.strip()}**\n"
                f"Kanal: {self.target_channel.mention}\n"
                f"Aturan: `{rule_label}` | Tampilan: `{self.mode.upper()}`\n\n"
                "👉 **Pilih role-role yang akan dimasukkan ke panel ini melalui menu di bawah:**\n"
                "*(Setelah selesai, kamu bisa menambah penjelasan khusus atau role tambahan kapan saja)*"
            ),
            color=0x5865F2
        )
        await interaction.response.send_message(embed=embed, view=picker_view, ephemeral=True)


class RolePanelWizardRolePickerView(discord.ui.View):
    def __init__(self, cog, target_channel: discord.TextChannel, rule_type: str, mode: str, title: str, desc: str, placeholder: str):
        super().__init__(timeout=180)
        self.cog = cog
        self.target_channel = target_channel
        self.rule_type = rule_type
        self.mode = mode
        self.panel_title = title
        self.panel_desc = desc
        self.placeholder = placeholder

        select = discord.ui.RoleSelect(
            placeholder="Pilih role-role untuk panel...",
            min_values=1,
            max_values=25
        )
        select.callback = self.on_roles_picked
        self.add_item(select)

    async def on_roles_picked(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        selected_roles = interaction.data.get("values", [])
        if not selected_roles:
            return await interaction.followup.send("❌ Tidak ada role yang dipilih.", ephemeral=True)

        guild = interaction.guild
        roles_data = {}
        for r_id_str in selected_roles:
            r = guild.get_role(int(r_id_str))
            if r and r < guild.me.top_role and not r.managed:
                roles_data[str(r.id)] = {
                    "label": r.name,
                    "emoji": None,
                    "description": f"Role akses @{r.name}"
                }

        if not roles_data:
            return await interaction.followup.send("❌ Role yang dipilih berada di atas role bot atau merupakan managed role.", ephemeral=True)

        panel_data = {
            "channel_id": self.target_channel.id,
            "mode": self.mode,
            "rule_type": self.rule_type,
            "title": self.panel_title,
            "description": self.panel_desc,
            "placeholder": self.placeholder,
            "roles": roles_data,
            "roles_data": roles_data
        }

        card, fallback_embed, initial_view = self.cog._build_role_panel_render(guild, panel_data, "temp_id")
        components = [card, *initial_view.to_components()]

        resp = await send_v2_message(self.cog.bot, self.target_channel.id, components)
        if not resp or "id" not in resp:
            msg = await self.target_channel.send(embed=fallback_embed, view=initial_view)
            msg_id = msg.id
        else:
            msg_id = int(resp["id"])

        guild_settings = self.cog.get_guild_settings(guild.id)
        if "role_panels" not in guild_settings:
            guild_settings["role_panels"] = {}
        guild_settings["role_panels"][str(msg_id)] = panel_data
        self.cog.save_settings()

        await self.cog._sync_role_panel_message(guild, panel_data, str(msg_id))

        finish_embed = discord.Embed(
            title="🎉 Panel Role Berhasil Dipasang!",
            description=(
                f"Panel **{self.panel_title}** sekarang aktif di {self.target_channel.mention}!\n\n"
                f"• **Jumlah Role:** `{len(roles_data)}` role\n"
                f"• **Aturan:** `{'Ketat (1 Role Saja)' if self.rule_type == 'exclusive' else 'Bebas'}`\n"
                f"• **Gaya:** `{self.mode.upper()}`\n\n"
                "Kamu bisa mengedit teks, menambah role baru, atau menyetel emoji dan penjelasan detail kapan saja lewat `/panelrole`."
            ),
            color=0x57F287
        )
        finish_view = RolePanelCreatedDoneView(self.cog, guild, interaction.user, str(msg_id))
        await interaction.followup.send(embed=finish_embed, view=finish_view, ephemeral=True)


class RolePanelCreatedDoneView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, message_id_str: str):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.message_id_str = message_id_str

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    @discord.ui.button(label="Kelola Panel Sekarang", style=discord.ButtonStyle.primary, emoji="🛠️")
    async def manage_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        manage_view = RolePanelManageView(self.cog, self.guild, self.author, self.message_id_str)
        embed = manage_view.build_manage_embed()
        await interaction.response.edit_message(embed=embed, view=manage_view)

    @discord.ui.button(label="Buka Studio", style=discord.ButtonStyle.secondary, emoji="🎭")
    async def studio_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        dash_view = RolePanelDashboardView(self.cog, self.guild, self.author)
        embed = dash_view.build_dashboard_embed()
        await interaction.response.edit_message(embed=embed, view=dash_view)


class BaseSettingsSubView(discord.ui.View):
    def __init__(self, cog, guild, author):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.author

    @discord.ui.button(label="Auto Role", style=discord.ButtonStyle.primary, emoji="👤")
    async def auto_role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.get_guild_settings(self.guild.id)
        current_r = self.guild.get_role(settings.get("auto_role_id")) if settings.get("auto_role_id") else None
        card = build_v2_card(
            title="👤 Atur Auto Role Member Baru",
            description="Berikan role otomatis secara instan kepada setiap anggota baru yang bergabung ke server.",
            fields=[
                {"name": "🎭 Role Saat Ini", "value": current_r.mention if current_r else "`Belum diatur`"}
            ],
            color=0x5865F2,
            footer="Pilih role dari menu di bawah atau klik tombol untuk mematikan."
        )
        await send_v2_interaction(self.cog.bot, interaction, card, AutoRoleSetupView(self.cog, self.guild, self.author), ephemeral=True)

    @discord.ui.button(label="Welcome Channel", style=discord.ButtonStyle.primary, emoji="💬")
    async def welcome_ch_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.get_guild_settings(self.guild.id)
        current_ch = self.guild.get_channel(settings.get("welcome_channel_id")) if settings.get("welcome_channel_id") else None
        card = build_v2_card(
            title="💬 Atur Kanal Selamat Datang",
            description="Kirim pesan sambutan otomatis saat ada member baru bergabung ke server.",
            fields=[
                {"name": "📢 Kanal Saat Ini", "value": current_ch.mention if current_ch else "`Belum diatur`"}
            ],
            color=self.cog.color_info,
            footer="Pilih kanal selamat datang dari dropdown di bawah."
        )
        await send_v2_interaction(self.cog.bot, interaction, card, WelcomeChannelSetupView(self.cog, self.guild, self.author), ephemeral=True)

    @discord.ui.button(label="Log Channel", style=discord.ButtonStyle.primary, emoji="📝")
    async def log_ch_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = self.cog.get_guild_settings(self.guild.id)
        current_ch = self.guild.get_channel(settings.get("log_channel_id")) if settings.get("log_channel_id") else None
        card = build_v2_card(
            title="📝 Atur Kanal Audit Log",
            description="Catat seluruh aktivitas moderasi, filter kata, dan event server secara otomatis.",
            fields=[
                {"name": "📋 Kanal Saat Ini", "value": current_ch.mention if current_ch else "`Belum diatur`"}
            ],
            color=self.cog.color_info,
            footer="Pilih kanal audit log dari dropdown di bawah."
        )
        await send_v2_interaction(self.cog.bot, interaction, card, LogChannelSetupView(self.cog, self.guild, self.author), ephemeral=True)



class AddFilterModal(discord.ui.Modal, title="Tambah Filter"):
    def __init__(self, cog_instance, filter_type):
        super().__init__()
        self.cog = cog_instance
        self.filter_type = filter_type
        self.item_to_add = discord.ui.TextInput(
            label=f"Masukkan {('kata' if filter_type == 'bad_words' else 'pola regex')} untuk ditambahkan",
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.item_to_add)

    async def on_submit(self, interaction: discord.Interaction):
        filters = self.cog.get_guild_filters(interaction.guild_id)
        item = self.item_to_add.value.lower().strip()
        if item in filters[self.filter_type]:
            await interaction.response.send_message(embed=self.cog._create_embed(description=f"❌ `{item}` sudah ada di filter.", color=self.cog.color_error), ephemeral=True)
        else:
            filters[self.filter_type].append(item)
            self.cog.save_filters()
            await interaction.response.send_message(embed=self.cog._create_embed(description=f"✅ `{item}` berhasil ditambahkan ke filter.", color=self.cog.color_success), ephemeral=True)


class RemoveFilterModal(discord.ui.Modal, title="Hapus Filter"):
    def __init__(self, cog_instance, filter_type):
        super().__init__()
        self.cog = cog_instance
        self.filter_type = filter_type
        self.item_to_remove = discord.ui.TextInput(
            label=f"Masukkan {('kata' if filter_type == 'bad_words' else 'pola')} yang akan dihapus"
        )
        self.add_item(self.item_to_remove)

    async def on_submit(self, interaction: discord.Interaction):
        filters = self.cog.get_guild_filters(interaction.guild_id)
        item = self.item_to_remove.value.lower().strip()
        if item in filters[self.filter_type]:
            filters[self.filter_type].remove(item)
            self.cog.save_filters()
            await interaction.response.send_message(embed=self.cog._create_embed(description=f"✅ `{item}` berhasil dihapus dari filter.", color=self.cog.color_success), ephemeral=True)
        else:
            await interaction.response.send_message(embed=self.cog._create_embed(description=f"❌ `{item}` tidak ditemukan di filter.", color=self.cog.color_error), ephemeral=True)


class FilterManageView(discord.ui.View):
    def __init__(self, cog_instance, author):
        super().__init__(timeout=180)
        self.cog = cog_instance
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.author

    @discord.ui.button(label="Tambah Kata Kasar", style=discord.ButtonStyle.primary, emoji="🤬")
    async def add_bad_word(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddFilterModal(self.cog, "bad_words"))

    @discord.ui.button(label="Hapus Kata Kasar", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def remove_bad_word(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RemoveFilterModal(self.cog, "bad_words"))

    @discord.ui.button(label="Tambah Pola Link", style=discord.ButtonStyle.primary, emoji="🔗")
    async def add_link_pattern(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddFilterModal(self.cog, "link_patterns"))

    @discord.ui.button(label="Hapus Pola Link", style=discord.ButtonStyle.danger, emoji="🔗")
    async def remove_link_pattern(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RemoveFilterModal(self.cog, "link_patterns"))

    @discord.ui.button(label="Lihat Semua Filter", style=discord.ButtonStyle.secondary, emoji="📋", row=2)
    async def view_filters(self, interaction: discord.Interaction, button: discord.ui.Button):
        filters = self.cog.get_guild_filters(interaction.guild_id)
        bad_words = ", ".join(f"`{w}`" for w in filters.get('bad_words', [])) or "Kosong"
        link_patterns = ", ".join(f"`{p}`" for p in filters.get('link_patterns', [])) or "Kosong"
        embed = self.cog._create_embed(title="Daftar Filter Aktif", color=self.cog.color_info)
        embed.add_field(name="🚫 Kata Kasar", value=bad_words[:1024], inline=False)
        embed.add_field(name="🔗 Pola Link", value=link_patterns[:1024], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class MasterSetupDashboardView(discord.ui.View):
    def __init__(self, cog, guild, author):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author

        menu = discord.ui.Select(
            custom_id="rtm_master_setup_dropdown",
            placeholder="Pilih Modul Pengaturan Server...",
            options=[
                discord.SelectOption(label="Pengaturan Dasar", value="base", emoji="⚙️", description="Auto Role, Welcome & Log Channel"),
                discord.SelectOption(label="Pesan Server Booster", value="booster", emoji="🚀", description="Pengumuman otomatis member yang boost"),
                discord.SelectOption(label="Sistem Tiket Bantuan", value="ticket", emoji="🎫", description="Setup kategori & pasang panel tiket"),
                discord.SelectOption(label="Panel Ambil Role (Self-Role)", value="roles", emoji="🎭", description="Wizard buat panel role dropdown / tombol"),
                discord.SelectOption(label="Keamanan & Trap", value="security", emoji="🛡️", description="Kelola filter kata kasar & trap"),
                discord.SelectOption(label="Ringkasan Konfigurasi", value="summary", emoji="📋", description="Lihat seluruh konfigurasi server aktif")
            ]
        )

        menu.callback = self.on_menu_select
        self.add_item(menu)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("Hanya pengguna yang memulai setup yang dapat berinteraksi.", ephemeral=True)
            return False
        return True

    async def on_menu_select(self, interaction: discord.Interaction):
        val = interaction.data.get("values", [""])[0]
        if val == "base":
            settings = self.cog.get_guild_settings(self.guild.id)
            auto_r = self.guild.get_role(settings.get("auto_role_id")) if settings.get("auto_role_id") else None
            welcome_c = self.guild.get_channel(settings.get("welcome_channel_id")) if settings.get("welcome_channel_id") else None
            log_c = self.guild.get_channel(settings.get("log_channel_id")) if settings.get("log_channel_id") else None
            card = build_v2_card(
                title="⚙️ Pengaturan Dasar Server",
                description="Kelola fitur otomatisasi dasar server Anda:",
                fields=[
                    {"name": "👤 Auto Role", "value": auto_r.mention if auto_r else "`Belum diatur`"},
                    {"name": "💬 Welcome Channel", "value": welcome_c.mention if welcome_c else "`Belum diatur`"},
                    {"name": "📝 Log Channel", "value": log_c.mention if log_c else "`Belum diatur`"}
                ],
                color=self.cog.color_info,
                footer="Pilih tombol di bawah untuk mengatur komponen dasar."
            )
            await send_v2_interaction(self.cog.bot, interaction, card, BaseSettingsSubView(self.cog, self.guild, self.author), ephemeral=True)
        elif val == "booster":
            settings = self.cog.get_guild_settings(self.guild.id)
            ch = self.guild.get_channel(settings.get("boost_channel_id")) if settings.get("boost_channel_id") else None
            status_txt = "🟢 Aktif" if settings.get("boost_enabled", True) else "🔴 Nonaktif"
            default_preview = "🎉 Terima kasih telah mem-boost server kami!"
            preview_msg = settings.get("boost_message") or default_preview
            if len(preview_msg) > 120:
                preview_msg = preview_msg[:117] + "..."
            card = build_v2_card(
                title="🚀 Pengaturan Pesan Sambutan Booster",
                description="Fitur pengumuman otomatis saat ada member yang melakukan Server Boost.",
                fields=[
                    {"name": "📊 Status", "value": status_txt},
                    {"name": "📢 Kanal Saat Ini", "value": ch.mention if ch else "`Belum diatur`"},
                    {"name": "💬 Cuplikan Pesan", "value": f"> {preview_msg}"}
                ],
                color=0xF47FFF,
                footer="Atur kanal, edit teks pesan, atau jalankan simulasi uji coba di bawah."
            )
            await send_v2_interaction(self.cog.bot, interaction, card, BoosterSetupView(self.cog, self.guild, self.author), ephemeral=True)
        elif val == "ticket":
            settings = self.cog.get_guild_settings(self.guild.id)
            cat = self.guild.get_channel(settings.get("ticket_category_id")) if settings.get("ticket_category_id") else None
            role = self.guild.get_role(settings.get("ticket_support_role_id")) if settings.get("ticket_support_role_id") else None
            card = build_v2_card(
                title="🎫 Pengaturan Sistem Tiket Bantuan",
                description="Sistem tiket bantuan privat untuk mempermudah anggota menghubungi tim staf.",
                fields=[
                    {"name": "📁 Kategori Kanal", "value": cat.name if cat else "`Belum diatur`"},
                    {"name": "🛡️ Role Tim Staf", "value": role.mention if role else "`Belum diatur`"}
                ],
                color=0x2ECC71,
                footer="Pilih kategori, role staf, lalu pasang panel tiket ke channel target."
            )
            await send_v2_interaction(self.cog.bot, interaction, card, TicketSetupView(self.cog, self.guild, self.author), ephemeral=True)
        elif val == "roles":
            card = build_v2_card(
                title="🎭 Wizard Panel Ambil Role Mandiri",
                description="Buat panel interaktif agar anggota dapat mengambil atau melepas role secara mandiri.",
                fields=[
                    {"name": "1️⃣ Pilih Kanal", "value": "`Tentukan kanal tempat panel dipasang`"},
                    {"name": "2️⃣ Pilih Tampilan", "value": "`Dropdown Menu (rapi) atau Tombol (interaktif)`"}
                ],
                color=0x5865F2,
                footer="Gunakan kontrol di bawah untuk memulai wizard."
            )
            await send_v2_interaction(self.cog.bot, interaction, card, RolePanelWizardMenuView(self.cog, self.guild, self.author), ephemeral=True)
        elif val == "security":
            filters = self.cog.get_guild_filters(self.guild.id)
            bad_words = filters.get('bad_words', [])
            link_patterns = filters.get('link_patterns', [])
            card = build_v2_card(
                title="🛡️ Keamanan & Filter Server",
                description="Perlindungan otomatis dari spam, kata-kata kasar, dan tautan berbahaya.",
                fields=[
                    {"name": "🚫 Sensor Kata Kasar", "value": f"`{len(bad_words)} kata dilarang`"},
                    {"name": "🔗 Proteksi Tautan", "value": f"`{len(link_patterns)} pola terdeteksi`"}
                ],
                color=self.cog.color_info,
                footer="Gunakan tombol di bawah untuk menambah atau menghapus filter."
            )
            await send_v2_interaction(self.cog.bot, interaction, card, FilterManageView(self.cog, self.author), ephemeral=True)
        elif val == "summary":
            settings = self.cog.get_guild_settings(self.guild.id)
            filters = self.cog.get_guild_filters(self.guild.id)
            auto_role = self.guild.get_role(settings.get('auto_role_id')) if settings.get('auto_role_id') else "Tidak diatur"
            welcome_ch = self.guild.get_channel(settings.get('welcome_channel_id')) if settings.get('welcome_channel_id') else "Tidak diatur"
            log_ch = self.guild.get_channel(settings.get('log_channel_id')) if settings.get('log_channel_id') else "Tidak diatur"
            boost_ch = self.guild.get_channel(settings.get('boost_channel_id')) if settings.get('boost_channel_id') else "Tidak diatur"
            boost_status = "🟢 Aktif" if settings.get("boost_enabled", True) else "🔴 Nonaktif"
            cat = self.guild.get_channel(settings.get("ticket_category_id")) if settings.get("ticket_category_id") else "Tidak diatur"
            role = self.guild.get_role(settings.get("ticket_support_role_id")) if settings.get("ticket_support_role_id") else "Tidak diatur"
            active_panels = len(settings.get("role_panels", {}))
            bad_words = filters.get('bad_words', [])
            link_patterns = filters.get('link_patterns', [])

            auto_role_str = auto_role.mention if isinstance(auto_role, discord.Role) else f"`{auto_role}`"
            welcome_str = welcome_ch.mention if isinstance(welcome_ch, discord.TextChannel) else f"`{welcome_ch}`"
            log_str = log_ch.mention if isinstance(log_ch, discord.TextChannel) else f"`{log_ch}`"
            boost_str = boost_ch.mention if isinstance(boost_ch, discord.TextChannel) else f"`{boost_ch}`"
            cat_str = cat.name if isinstance(cat, discord.CategoryChannel) else f"`{cat}`"
            role_str = role.mention if isinstance(role, discord.Role) else f"`{role}`"

            card = build_v2_card(
                title=f"📋 Ringkasan Konfigurasi • {self.guild.name}",
                description="Seluruh konfigurasi otomatisasi server yang sedang aktif saat ini:",
                fields=[
                    {
                        "name": "⚙️ Pengaturan Dasar",
                        "value": (
                            f"• **Auto Role**: {auto_role_str}\n"
                            f"• **Welcome Channel**: {welcome_str}\n"
                            f"• **Log Channel**: {log_str}"
                        )
                    },
                    {
                        "name": "🚀 Booster & Tiket",
                        "value": (
                            f"• **Booster Channel**: {boost_str} ({boost_status})\n"
                            f"• **Kategori Tiket**: {cat_str}\n"
                            f"• **Role Staf Tiket**: {role_str}\n"
                            f"• **Panel Role Aktif**: `{active_panels}` panel"
                        )
                    },
                    {
                        "name": "🛡️ Filter Keamanan",
                        "value": (
                            f"• Total Filter Kata: `{len(bad_words)}` kata\n"
                            f"• Total Filter Link: `{len(link_patterns)}` pola"
                        )
                    }
                ],
                color=self.cog.color_info,
                footer="Ringkasan Konfigurasi Server • RTM-Bot"
            )
            await send_v2_interaction(self.cog.bot, interaction, card, ephemeral=True)



class SentinelGuard(commands.Cog, name="Sentinel Moderation"):
    def __init__(self, bot):
        self.bot = bot
        self.settings_file = "data/settings.json"
        self.filters_file = "data/filters.json"
        self.warnings_file = "data/warnings.json"
        self.status_file = "data/status.json"
        self.mod_panel_message_id = None
        self.mod_panel_channel_id = None
        
        self.modpanel_buttons = [
            {"label": "Warn", "style": 2, "emoji": "⚠️", "custom_id": "modpanel_warn"},
            {"label": "Timeout", "style": 1, "emoji": "⏳", "custom_id": "modpanel_timeout"},
            {"label": "Kick", "style": 4, "emoji": "👢", "custom_id": "modpanel_kick"},
            {"label": "Ban", "style": 4, "emoji": "🔨", "custom_id": "modpanel_ban"},
            {"label": "Unwarn", "style": 3, "emoji": "🛡️", "custom_id": "modpanel_unwarn"},
            {"label": "Untimeout", "style": 3, "emoji": "⏱️", "custom_id": "modpanel_untimeout"},
            {"label": "Unban", "style": 3, "emoji": "🤝", "custom_id": "modpanel_unban"},
            {"label": "Clear Chat", "style": 4, "emoji": "🧹", "custom_id": "modpanel_clear"},
            {"label": "Lock", "style": 4, "emoji": "🔒", "custom_id": "modpanel_lock"},
            {"label": "Unlock", "style": 3, "emoji": "🔓", "custom_id": "modpanel_unlock"}
        ]
        self.spam_messages = {}
        self.spam_history = {}
        self.cross_channel_spam_history = {}
        self._recent_boosters = {}
        
        self.reminder_channel_id = int(os.getenv("REMINDER_CHANNEL_ID", 1379762287149187162)) if os.getenv("REMINDER_CHANNEL_ID") else 1379762287149187162
        self.male_role_id = int(os.getenv("MALE_ROLE_ID", 1385246612288311326)) if os.getenv("MALE_ROLE_ID") else 1385246612288311326
        self.female_role_id = int(os.getenv("FEMALE_ROLE_ID", 1379461360873898017)) if os.getenv("FEMALE_ROLE_ID") else 1379461360873898017
        
        self.common_prefixes = ('!', '.', '?', '-', '$', '%', '&', '#', '+', '=')
        self.url_regex = re.compile(r'https?://[^\s/$.?#].[^\s]*')
        
        self.color_success = 0xFFE000 
        self.color_error = 0xFFE000
        self.color_info = 0xFFE000
        self.color_warning = 0xF1C40F
        self.color_log = 0xFFE000
        self.color_welcome = 0xFFE000
        self.color_announce = 0xFFE000
        self.color_booster = 0xFFE000
        
        self.media_spam_cooldown = commands.CooldownMapping.from_cooldown(3, 30.0, commands.BucketType.user)
        self.media_spam_rapid_cooldown = commands.CooldownMapping.from_cooldown(5, 10.0, commands.BucketType.user)
        self.media_spam_heavy_cooldown = commands.CooldownMapping.from_cooldown(8, 60.0, commands.BucketType.user)
        self.link_spam_cooldown = commands.CooldownMapping.from_cooldown(2, 60.0, commands.BucketType.user)
        self.fast_spam_cooldown = commands.CooldownMapping.from_cooldown(5, 10.0, commands.BucketType.user)
        self.global_spam_cooldown = commands.CooldownMapping.from_cooldown(8, 15.0, commands.BucketType.user)
        self.multi_media_cooldown = commands.CooldownMapping.from_cooldown(1, 5.0, commands.BucketType.user)

        self.mongo_client = getattr(bot, 'mongo_client', None)
        if self.mongo_client:
            self.db = self.mongo_client["reSwan"]
            self.settings_col = self.db["moderation_settings"]
            self.filters_col = self.db["moderation_filters"]
            self.warnings_col = self.db["moderation_warnings"]
            self.status_col = self.db["moderation_status"]
        else:
            self.settings_col = None
            self.filters_col = None
            self.warnings_col = None
            self.status_col = None

        self.settings = self.load_data_from_mongo(self.settings_col, self.settings_file)
        self.filters = self.load_data_from_mongo(self.filters_col, self.filters_file)
        self.warnings = self.load_data_from_mongo(self.warnings_col, self.warnings_file)
        self.status = self.load_data_from_mongo(self.status_col, self.status_file)
        
        for guild_id_str, g_settings in self.settings.items():
            if isinstance(g_settings, dict):
                if "announcement_webhooks" not in g_settings:
                    g_settings["announcement_webhooks"] = {}
        self.save_settings()

        if "status" not in self.status:
            self.status["status"] = "online"
            self.save_status()
        
        for guild_id_str, settings in self.settings.items():
            if isinstance(settings, dict):
                if 'verification_button_label' in settings:
                    try:
                        self.bot.add_view(UniversalMembershipView(self, settings['verification_button_label']))
                    except Exception:
                        pass
                role_panels = settings.get("role_panels", {})
                for msg_id_str, pdata in role_panels.items():
                    try:
                        self.bot.add_view(DynamicRoleView(
                            pdata.get("mode", "select"),
                            pdata.get("roles") or pdata.get("roles_data") or {},
                            str(msg_id_str),
                            pdata.get("placeholder", "✨ Pilih role yang ingin kamu ambil"),
                            pdata.get("rule_type", "free")
                        ))
                    except Exception:
                        pass

        try:
            self.bot.add_view(GlobalTicketButtonView(self))
            self.bot.add_view(GlobalTicketCloseView(self))
        except Exception:
            pass

        self.update_panel_task.start()
        self.cleanup_spam_history.start()
        
    def cog_unload(self):
        self.update_panel_task.cancel()
        self.cleanup_spam_history.cancel()

    async def _create_welcome_card(self, member: discord.Member, title: str) -> io.BytesIO:
        if generate_official_member_card:
            try:
                exp = 0
                level = 0
                balance = 0
                try:
                    lvl_path = "data/level_data.json"
                    bank_path = "data/bank_data.json"
                    if os.path.exists(lvl_path):
                        with open(lvl_path, 'r', encoding='utf-8') as f:
                            l_data = json.load(f)
                            u_lvl = l_data.get(str(member.guild.id), {}).get(str(member.id), {})
                            exp = u_lvl.get("exp", 0)
                            level = u_lvl.get("level", 0)
                    if os.path.exists(bank_path):
                        with open(bank_path, 'r', encoding='utf-8') as f:
                            b_data = json.load(f)
                            balance = b_data.get(str(member.id), {}).get("balance", 0)
                except Exception:
                    pass

                serial_id = get_or_create_member_serial_id(member.guild, member) if get_or_create_member_serial_id else member.guild.member_count
                card_buffer = await generate_official_member_card(
                    bot=self.bot,
                    target=member,
                    guild=member.guild,
                    exp=exp,
                    level=level,
                    balance=balance,
                    rank_pos=serial_id,
                    custom_title=f"KARTU RESMI ANGGOTA • {member.guild.name.upper()}"
                )
                return card_buffer
            except Exception:
                pass

        width = 800
        height = 250
        background = Image.new('RGBA', (width, height), (20, 22, 26, 255))
        draw = ImageDraw.Draw(background)
        
        draw.ellipse((-150, -50, 320, 400), fill=(30, 34, 45, 255)) 
        draw.ellipse((-130, -30, 300, 380), outline=(88, 101, 242, 180), width=4) 
        
        try:
            avatar_bytes = await member.display_avatar.replace(size=128, format="png").read()
            avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            avatar_img = avatar_img.resize((150, 150))
            mask = Image.new("L", (150, 150), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 150, 150), fill=255)
            background.paste(avatar_img, (60, 50), mask)
            draw.ellipse((56, 46, 214, 214), outline=(88, 101, 242, 255), width=6)
        except Exception:
            pass

        font_bold = font_title = font_sub = font_small = ImageFont.load_default()

        safe_guild = unicodedata.normalize('NFKC', member.guild.name)
        safe_name = unicodedata.normalize('NFKC', member.display_name)
        
        text_x = 360
        draw.text((text_x, 40), title, font=font_title, fill=(114, 137, 218, 255))
        draw.text((text_x, 70), safe_name, font=font_bold, fill=(255, 255, 255, 255))
        draw.line([(text_x, 135), (750, 135)], fill=(100, 100, 100, 80), width=2)
        draw.text((text_x, 150), f"Selamat datang di {safe_guild}!", font=font_sub, fill=(200, 200, 200, 255))
        draw.text((text_x, 185), "Semoga betah dan aktif terus ya!", font=font_sub, fill=(150, 255, 150, 255))
        
        badge_text = f"Member #{member.guild.member_count}"
        draw.rounded_rectangle([(630, 20), (760, 50)], radius=15, fill=(40, 44, 52, 255), outline=(88, 101, 242, 180), width=1)
        draw.text((650, 25), badge_text, font=font_small, fill=(200, 200, 200, 255))

        buffer = io.BytesIO()
        background.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    async def _create_goodbye_card(self, member: discord.Member, title: str) -> io.BytesIO:
        width = 800
        height = 250
        background = Image.new('RGBA', (width, height), (26, 20, 20, 255))
        draw = ImageDraw.Draw(background)
        
        draw.ellipse((-150, -50, 320, 400), fill=(40, 25, 25, 255)) 
        draw.ellipse((-130, -30, 300, 380), outline=(242, 88, 88, 180), width=4)
        
        try:
            avatar_bytes = await member.display_avatar.replace(size=128, format="png").read()
            avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            avatar_img = avatar_img.resize((150, 150))
            mask = Image.new("L", (150, 150), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 150, 150), fill=255)
            
            grayscale = avatar_img.convert('L')
            grayscale_rgba = Image.new("RGBA", grayscale.size)
            grayscale_rgba.paste(grayscale, (0, 0), mask)
            
            background.paste(grayscale_rgba, (60, 50), mask)
            draw.ellipse((56, 46, 214, 214), outline=(242, 88, 88, 255), width=6)
        except Exception:
            pass

        try:
            url_bold = "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf"
            url_reg = "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf"
            async with aiohttp.ClientSession() as session:
                async with session.get(url_bold) as r1:
                    font_bold_bytes = await r1.read()
                    font_bold = ImageFont.truetype(io.BytesIO(font_bold_bytes), 42)
                    font_title = ImageFont.truetype(io.BytesIO(font_bold_bytes), 22)
                async with session.get(url_reg) as r2:
                    font_reg_bytes = await r2.read()
                    font_sub = ImageFont.truetype(io.BytesIO(font_reg_bytes), 20)
        except Exception:
            font_bold = ImageFont.load_default()
            font_title = ImageFont.load_default()
            font_sub = ImageFont.load_default()

        import unicodedata
        safe_guild = unicodedata.normalize('NFKC', member.guild.name)
        safe_name = unicodedata.normalize('NFKC', member.display_name)
        
        text_x = 360
        
        draw.text((text_x, 40), title, font=font_title, fill=(235, 100, 100, 255))
        draw.text((text_x, 70), safe_name, font=font_bold, fill=(255, 255, 255, 255))
        
        draw.line([(text_x, 135), (750, 135)], fill=(100, 100, 100, 80), width=2)
        
        draw.text((text_x, 150), f"Telah meninggalkan {safe_guild}...", font=font_sub, fill=(180, 180, 180, 255))
        draw.text((text_x, 185), "Yah, padahal lagi seru-serunya...", font=font_sub, fill=(255, 150, 150, 255))

        buffer = io.BytesIO()
        background.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    async def update_trap_display(self, current_channel_id: int = None):
        """Perbarui tampilan tombol Timeouts count pada seluruh pesan trap di server"""
        try:
            global_count = self.settings.get("global_trap_count", 30)
            from cogs.v2_layout import build_v2_card, edit_v2_message, send_v2_message
            buttons = [
                {
                    "type": 2,
                    "style": 4,
                    "label": f"Timeouts count: {global_count}",
                    "custom_id": "disabled_trap_counter",
                    "disabled": True,
                    "emoji": {"name": "🔨"}
                }
            ]
            card = build_v2_card(
                title="🚨 PERINGATAN KERAS / WARNING 🚨",
                description="**JANGAN MENGIRIM PESAN DI CHANNEL INI**\n**DO NOT SEND MESSAGES IN THIS CHANNEL**\n\nChannel ini khusus untuk mendeteksi spam & phishing. Setiap pesan yang Anda kirim di sini akan mengakibatkan sanksi **Timeout Otomatis 28 Hari**.\n\n*This channel is strictly for spam & phishing detection, any messages sent here will result in an immediate 28-day timeout.*\n\nMohon patuhi peraturan server yang ada untuk menghindari sanksi dari sistem otomatis kami.",
                color=None,
                buttons=buttons
            )

            for g_id, g_settings in self.settings.items():
                if not isinstance(g_settings, dict): continue
                trigger_channels_g = g_settings.get("trigger_channels", [])
                for ch_id in trigger_channels_g:
                    trap_msg_id = g_settings.get(f"trap_msg_{ch_id}")
                    edited = False
                    if trap_msg_id:
                        try:
                            resp = await edit_v2_message(self.bot, int(ch_id), trap_msg_id, [card])
                            if resp and isinstance(resp, dict) and "id" in resp:
                                edited = True
                        except Exception:
                            pass
                    if not edited:
                        try:
                            ch_obj = self.bot.get_channel(int(ch_id))
                            if ch_obj and ch_obj.permissions_for(ch_obj.guild.me).send_messages:
                                msg_data = await send_v2_message(self.bot, int(ch_id), [card])
                                if msg_data and isinstance(msg_data, dict) and "id" in msg_data:
                                    g_settings[f"trap_msg_{ch_id}"] = int(msg_data["id"])
                                    self.save_settings()
                        except Exception:
                            pass
        except Exception as e:
            print(f"Error in update_trap_display: {e}")

    async def increment_timeout_counter(self, current_channel_id: int = None, amount: int = 1):
        """
        Menaikkan hitungan global timeout dan memperbarui tombol peringatan di seluruh trap channel.
        Dipicu otomatis oleh trigger trap channel, anti-spam, media spam, link phising, raid escalation, atau manual timeout.
        """
        try:
            global_count = self.settings.get("global_trap_count", 30) + amount
            self.settings["global_trap_count"] = global_count
            self.save_settings()
            await self.update_trap_display(current_channel_id)
        except Exception as e:
            print(f"Error in increment_timeout_counter: {e}")

    @commands.command(name="addtrapcount", aliases=["addtimeoutcount"], help="Tambah hitungan timeout count secara manual pada kartu jebakan")
    @commands.has_permissions(administrator=True)
    async def add_trap_count(self, ctx: commands.Context, amount: int = 1):
        if amount <= 0:
            return await ctx.send("❌ Jumlah penambahan harus lebih besar dari 0.")
        await self.increment_timeout_counter(amount=amount)
        cur = self.settings.get("global_trap_count", 30)
        await ctx.send(f"✅ Hitungan timeout berhasil ditambahkan sebanyak **+{amount}**. Total saat ini: **{cur}**.")

    @commands.command(name="settrapcount", aliases=["settimeoutcount"], help="Atur angka timeout count kartu jebakan ke nilai tertentu")
    @commands.has_permissions(administrator=True)
    async def set_trap_count(self, ctx: commands.Context, new_count: int):
        if new_count < 0:
            return await ctx.send("❌ Angka hitungan timeout tidak boleh negatif.")
        self.settings["global_trap_count"] = new_count
        self.save_settings()
        await self.update_trap_display()
        await ctx.send(f"✅ Angka timeout count berhasil diatur menjadi **{new_count}**.")

    def get_guild_settings(self, guild_id: int):
        guild_id_str = str(guild_id)
        if guild_id_str not in self.settings:
            self.settings[guild_id_str] = {
                "auto_role_id": None, 
                "welcome_channel_id": None,
                "welcome_message": "Selamat datang di **{guild_name}**, {user}! 🎉",
                "welcome_embed_title": "SELAMAT DATANG!",
                "welcome_sender_name": "Admin Server",
                "welcome_banner_url": None, 
                "log_channel_id": None, 
                "reaction_roles": {},
                "channel_rules": {},
                "boost_channel_id": None,
                "boost_message": "Terima kasih banyak, {user}, telah menjadi **Server Booster** kami di {guild_name}! Kami sangat menghargai dukunganmu! ❤️",
                "boost_embed_title": "TERIMA KASIH SERVER BOOSTER!",
                "boost_sender_name": "Tim Server",
                "boost_image_url": None,
                "mod_panel_message_id": None,
                "mod_panel_channel_id": None,
                "main_membership_role_id": None, 
                "membership_roles": {}, 
                "membership_invite_message": "🥺 Anda belum menjadi anggota channel YouTube. Silakan berlangganan untuk mendapatkan role eksklusif! [LINK MEMBERSHIP]", 
                "membership_confirm_message": "🎉 Anda sudah menjadi anggota! Anda adalah anggota tier: **{tier_name}**.",
                "verification_button_label": "Verifikasi Membership",
                "spam_whitelist_roles": [],
                "goodbye_message": "Selamat tinggal, **{user}**. Sampai jumpa lagi! 👋",
                "panel_role_stats": []
                
            }
            save_data(self.settings_file, self.settings)
        if "role_panels" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["role_panels"] = {}
        if "goodbye_message" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["goodbye_message"] = "Selamat tinggal, **{user}**. Sampai jumpa lagi! 👋"
        if "welcome_embed_title" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["welcome_embed_title"] = "SELAMAT DATANG!"
        if "welcome_sender_name" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["welcome_sender_name"] = "Admin Server"
        if "welcome_banner_url" not in self.settings[guild_id_str]: 
            self.settings[guild_id_str]["welcome_banner_url"] = None
        if "channel_rules" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["channel_rules"] = {}
        if "boost_channel_id" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["boost_channel_id"] = None
        if "boost_message" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["boost_message"] = "Terima kasih banyak, {user}, telah menjadi **Server Booster** kami di {guild_name}! Kami sangat menghargai dukunganmu! ❤️"
        if "boost_embed_title" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["boost_embed_title"] = "TERIMA KASIH SERVER BOOSTER!"
        if "boost_sender_name" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["boost_sender_name"] = "Tim Server"
        if "boost_image_url" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["boost_image_url"] = None
        if "announcement_webhooks" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["announcement_webhooks"] = {}
        if "mod_panel_message_id" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["mod_panel_message_id"] = None
        if "mod_panel_channel_id" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["mod_panel_channel_id"] = None
        if "main_membership_role_id" not in self.settings[guild_id_str]: 
            self.settings[guild_id_str]["main_membership_role_id"] = None
        if "membership_roles" not in self.settings[guild_id_str]: 
            self.settings[guild_id_str]["membership_roles"] = {}
        if "membership_invite_message" not in self.settings[guild_id_str]: 
            self.settings[guild_id_str]["membership_invite_message"] = "🥺 Anda belum menjadi anggota channel YouTube. Silakan berlangganan untuk mendapatkan role eksklusif! [LINK MEMBERSHIP]"
        if "membership_confirm_message" not in self.settings[guild_id_str]: 
            self.settings[guild_id_str]["membership_confirm_message"] = "🎉 Anda sudah menjadi anggota! Anda adalah anggota tier: **{tier_name}**."
        if "verification_button_label" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["verification_button_label"] = "Verifikasi Membership" 
        if "spam_whitelist_roles" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["spam_whitelist_roles"] = []
        if "panel_role_stats" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["panel_role_stats"] = []
        if "boost_enabled" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["boost_enabled"] = True
        if "ticket_category_id" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["ticket_category_id"] = None
        if "ticket_support_role_id" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["ticket_support_role_id"] = None

        save_data(self.settings_file, self.settings)
        return self.settings[guild_id_str]
        
    def get_channel_rules(self, guild_id: int, channel_id: int) -> dict:
        guild_settings = self.get_guild_settings(guild_id)
        channel_id_str = str(channel_id)
        if channel_id_str not in guild_settings["channel_rules"]:
            guild_settings["channel_rules"][channel_id_str] = {
                "disallow_bots": False, "disallow_media": False, "disallow_prefix": False,
                "disallow_url": False, "auto_delete_seconds": 0
            }
            save_data(self.settings_file, self.settings)
        return guild_settings["channel_rules"][channel_id_str]

    async def _safe_delete_message(self, message: discord.Message, delay: int = 0):
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            if not message.guild or not message.channel:
                return
            perms = message.channel.permissions_for(message.guild.me)
            if not perms.manage_messages and message.author.id != self.bot.user.id:
                log.warning(f"⚠️ [CHANNEL RULES] Tidak memiliki izin 'Manage Messages' di #{message.channel.name} ({message.channel.id}) untuk menghapus pesan.")
                return
            await message.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            log.warning(f"⚠️ [CHANNEL RULES] Izin ditolak (Forbidden) saat menghapus pesan di #{message.channel.name} ({message.channel.id})")
        except Exception as e:
            log.debug(f"[CHANNEL RULES] Gagal menghapus pesan {message.id}: {e}")
        
    def get_guild_filters(self, guild_id: int):
        guild_id_str = str(guild_id)
        if guild_id_str not in self.filters:
            self.filters[guild_id_str] = { "bad_words": [], "link_patterns": [] }
            save_data(self.filters_file, self.filters)
        return self.filters[guild_id_str]
        
    def load_data_from_mongo(self, collection, local_path):
        if collection is not None:
            try:
                doc = collection.find_one({"_id": local_path})
                if doc and "data" in doc:
                    return doc["data"]
            except Exception:
                pass
        return load_data(local_path)

    def save_settings(self):
        save_data(self.settings_file, self.settings)
        if self.settings_col is not None:
            try:
                self.settings_col.replace_one({"_id": self.settings_file}, {"_id": self.settings_file, "data": self.settings}, upsert=True)
            except Exception:
                pass

    def save_filters(self):
        save_data(self.filters_file, self.filters)
        if self.filters_col is not None:
            try:
                self.filters_col.replace_one({"_id": self.filters_file}, {"_id": self.filters_file, "data": self.filters}, upsert=True)
            except Exception:
                pass

    def save_warnings(self):
        save_data(self.warnings_file, self.warnings)
        if self.warnings_col is not None:
            try:
                self.warnings_col.replace_one({"_id": self.warnings_file}, {"_id": self.warnings_file, "data": self.warnings}, upsert=True)
            except Exception:
                pass

    def save_status(self):
        save_data(self.status_file, self.status)
        if self.status_col is not None:
            try:
                self.status_col.replace_one({"_id": self.status_file}, {"_id": self.status_file, "data": self.status}, upsert=True)
            except Exception:
                pass

    async def check_and_escalate_warnings(self, guild, member, moderator):
        guild_id_str = str(guild.id)
        member_id_str = str(member.id)
        user_warnings = self.warnings.get(guild_id_str, {}).get(member_id_str, [])
        warn_count = len(user_warnings)

        escalation_applied = None
        duration = None

        if warn_count == 3:
            duration = timedelta(hours=1)
            escalation_applied = "Auto-Timeout (1 Hour) due to 3 warnings"
        elif warn_count >= 5:
            duration = timedelta(days=1)
            escalation_applied = "Auto-Timeout (1 Day) due to 5+ warnings"

        if duration:
            try:
                await member.timeout(duration, reason=escalation_applied)
                await self.increment_timeout_counter()
                log_embed = self._create_embed(
                    title="🚨 Auto Escalation Triggered",
                    description=f"{member.mention} has been auto-timed out because they have reached **{warn_count} warnings**.",
                    color=self.color_error
                )
                log_embed.add_field(name="Member", value=f"{member} ({member.id})", inline=True)
                log_embed.add_field(name="Action", value=escalation_applied, inline=True)

                log_channel_id = self.get_guild_settings(guild.id).get("log_channel_id")
                if log_channel_id:
                    log_channel = self.bot.get_channel(log_channel_id)
                    if log_channel:
                        await log_channel.send(embed=log_embed)
                return escalation_applied
            except Exception:
                pass
        return None

    def _create_embed(self, title: str = "", description: str = "", color: int = 0, author_name: str = "", author_icon_url: str = ""):
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(WIB))
        if author_name: embed.set_author(name=author_name, icon_url=author_icon_url)
        bot_icon_url = self.bot.user.display_avatar.url if self.bot.user.display_avatar else None
        embed.set_footer(text=f"Dijalankan oleh {self.bot.user.name}", icon_url=bot_icon_url)
        return embed

    async def log_action(self, guild: discord.Guild, title: str, fields: dict, color: int):
        if not (log_channel_id := self.get_guild_settings(guild.id).get("log_channel_id")):
            return
        if (log_channel := guild.get_channel(log_channel_id)) and log_channel.permissions_for(guild.me).send_messages:
            embed = self._create_embed(title=title, color=color, timestamp=datetime.now(WIB))
            for name, value in fields.items():
                embed.add_field(name=name, value=value, inline=False)
            try:
                await log_channel.send(embed=embed)
            except discord.Forbidden:
                pass
        else:
            pass
    async def send_spam_log_v2(
        self,
        guild: discord.Guild,
        member,
        trigger_channels: str,
        reason: str,
        detailed_reason: str,
        message_id: str,
        message_content: str = None,
        media_url: str = None,
        is_webhook: bool = False,
        media_bytes: bytes = None,
        media_filename: str = None
    ):
        spam_log_channel_id = self.get_guild_settings(guild.id).get("spam_log_channel_id")
        if not spam_log_channel_id: return
        log_channel = guild.get_channel(spam_log_channel_id)
        if not log_channel or not log_channel.permissions_for(guild.me).send_messages: return

        from cogs.v2_layout import build_v2_card, send_v2_message
        import time
        import io

        actor_str = f"🚨 Compromised Webhook: `{getattr(member, 'name', 'Webhook')}` (ID: `{getattr(member, 'id', 'Unknown')}`)" if is_webhook else f"{getattr(member, 'mention', str(member))} (`{getattr(member, 'id', 'Unknown')}`)"

        v2_fields = [
            {"name": "👤 Pelaku / Sumber", "value": actor_str},
            {"name": "📝 Reason", "value": reason},
            {"name": "🔍 Detailed Reason", "value": detailed_reason},
            {"name": "📍 Channel", "value": trigger_channels},
            {"name": "🆔 Message ID", "value": f"`{message_id}`"},
            {"name": "⏰ Waktu Kejadian", "value": f"<t:{int(time.time())}:F>"}
        ]

        if message_content and message_content.strip():
            v2_fields.append({"name": "💬 Isi Pesan Pelanggar", "value": f"```{message_content[:900]}```"})
        elif media_bytes or media_url:
            v2_fields.append({"name": "💬 Isi Pesan Pelanggar", "value": "*[Pesan hanya berupa lampiran media/gambar tanpa teks]*"})

        att_name = media_filename or "evidence.png"
        evidence_file = None
        if media_bytes:
            evidence_file = discord.File(fp=io.BytesIO(media_bytes), filename=att_name)
            v2_fields.append({"name": "🖼️ Bukti Media", "value": f"*(File bukti tersimpan permanen di channel ini: `{att_name}`)*"})
        elif media_url:
            v2_fields.append({"name": "🖼️ Bukti Media / Foto", "value": f"[Klik untuk Buka Gambar]({media_url})"})

        card = build_v2_card(
            title="⚠️ SISTEM PERTAHANAN & KEAMANAN ⚠️",
            description="Tindakan keamanan otomatis telah diambil oleh sistem pertahanan server.",
            fields=v2_fields,
            color=0xFF0000,
            footer=f"Sistem Keamanan Otomatis • {guild.name}",
            attachment_filename=att_name if media_bytes else None,
            media_url=media_url if not media_bytes else None
        )
        
        sent = False
        try:
            files_to_send = [evidence_file] if evidence_file else None
            resp = await send_v2_message(self.bot, log_channel.id, [card], files=files_to_send)
            if resp and (not isinstance(resp, dict) or "error_msg" not in resp):
                sent = True
        except Exception:
            pass

        if not sent:
            embed = discord.Embed(
                title="⚠️ SISTEM PERTAHANAN & KEAMANAN ⚠️",
                description="Tindakan keamanan otomatis telah diambil oleh sistem pertahanan server.",
                color=0xFF0000,
                timestamp=datetime.now(timezone.utc)
            )
            for f in v2_fields:
                embed.add_field(name=f["name"], value=f["value"], inline=False)
            if media_bytes:
                embed.set_image(url=f"attachment://{att_name}")
            elif media_url:
                embed.set_image(url=media_url)
            embed.set_footer(text=f"Sistem Keamanan Otomatis • {guild.name}")
            try:
                if media_bytes:
                    f_obj = discord.File(fp=io.BytesIO(media_bytes), filename=att_name)
                    await log_channel.send(embed=embed, file=f_obj)
                else:
                    await log_channel.send(embed=embed)
            except Exception:
                pass

    async def get_or_create_announcement_webhook(self, channel: discord.TextChannel, custom_name: str):
        guild_settings = self.get_guild_settings(channel.guild.id)
        webhook_url = guild_settings.get("announcement_webhooks", {}).get(str(channel.id))
        
        if webhook_url:
            try:
                webhook = discord.Webhook.from_url(webhook_url, client=self.bot)
                await webhook.fetch()
                return webhook
            except (discord.NotFound, aiohttp.ClientError):
                pass
        
        try:
            webhook_name = f"{custom_name}" if custom_name else f"Pengumuman Server"
            avatar_url = channel.guild.icon.url if channel.guild.icon else None
            
            existing_webhooks = await channel.webhooks()
            for wh in existing_webhooks:
                if wh.user.id == self.bot.user.id:
                    webhook = wh
                    break
            else:
                webhook = await channel.create_webhook(name=webhook_name, avatar=await channel.guild.icon.read() if channel.guild.icon else None, reason="For automatic announcements.")
            
            guild_settings["announcement_webhooks"][str(channel.id)] = webhook.url
            self.save_settings()
            return webhook
        except discord.Forbidden:
            raise

    async def check_membership_status(self, member: discord.Member) -> tuple[bool, Optional[str]]:
        guild_settings = self.get_guild_settings(member.guild.id)
        main_role_id = guild_settings.get("main_membership_role_id")
        
        if not main_role_id:
            return False, "ERROR: Main Role Belum Diatur" 

        main_role = member.guild.get_role(main_role_id)
        if not main_role or main_role not in member.roles:
            return False, None

        membership_roles_data = guild_settings.get("membership_roles", {})
        
        tier_roles_in_guild = []
        for role_id_str, data in membership_roles_data.items():
            if role := member.guild.get_role(int(role_id_str)):
                tier_roles_in_guild.append((role.position, role.id, data['tier_name']))

        tier_roles_in_guild.sort(key=lambda x: x[0], reverse=True)

        for position, role_id, tier_name in tier_roles_in_guild:
            if role_id in [r.id for r in member.roles]:
                return True, tier_name
        
        return True, "Base Tier / Tier Role Belum Didaftarkan"

    def detect_suspicious_links(self, content: str) -> bool:
        suspicious_patterns = [
            r'discord\.gift', r'discord\.com\/gifts', r'discordapp\.com\/gifts',
            r'free-nitro', r'steam-community', r'steamcommunity\.com',
            r'bit\.ly', r'tinyurl\.com', r'shorturl\.at', r'rb\.gy',
            r'discord-nitro', r'claim-reward', r'free-gift'
        ]
        
        clean_text = re.sub(r'[\u200B-\u200D\uFEFF\u00AD]', '', content)
        
        try:
            normalized_text = unicodedata.normalize('NFKD', clean_text).encode('ascii', 'ignore').decode('utf-8')
        except Exception:
            normalized_text = clean_text

        content_lower = normalized_text.lower()
        
        for pattern in suspicious_patterns:
            if re.search(pattern, content_lower):
                return True
        
        urls = self.url_regex.findall(normalized_text)
        for url in urls:
            if any(suspicious in url.lower() for suspicious in ['discordgift', 'nitro-free', 'steamgift']):
                return True
    
        return False

    def is_allowed_file_type(self, filename: str) -> bool:
        allowed_extensions = {
            '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp',
            '.pdf', '.txt', '.doc', '.docx', '.xls', '.xlsx',
            '.zip', '.rar', '.7z',
            '.mp3', '.wav', '.ogg',
            '.mp4', '.mov', '.avi'
        }
        
        file_ext = os.path.splitext(filename.lower())[1]
        return file_ext in allowed_extensions

    @tasks.loop(minutes=5)
    async def cleanup_spam_history(self):
        current_time = time.time()
        
        for user_id in list(self.cross_channel_spam_history.keys()):
            self.cross_channel_spam_history[user_id] = [
                entry for entry in self.cross_channel_spam_history[user_id]
                if current_time - entry['timestamp'] <= 300
            ]
            
            if not self.cross_channel_spam_history[user_id]:
                del self.cross_channel_spam_history[user_id]
    def _build_role_panel_render(self, guild: discord.Guild, panel_data: dict, message_id_str: str):
        title = panel_data.get("title", "🎭 AMBIL ROLE MANDIRI")
        desc = panel_data.get("description", "Pilih role yang kamu inginkan untuk membuka akses channel dan notifikasi:")
        rule_type = panel_data.get("rule_type", "free")
        roles = panel_data.get("roles") or panel_data.get("roles_data") or {}
        mode = panel_data.get("mode", "select")
        placeholder = panel_data.get("placeholder", "✨ Pilih role yang ingin kamu ambil")

        role_lines = []
        for r_id_str, r_info in roles.items():
            emoji_str = f"{r_info.get('emoji')} " if r_info.get("emoji") else ""
            desc_str = f" — *{r_info.get('description')}*" if r_info.get("description") else ""
            role_lines.append(f"> • {emoji_str}<@&{r_id_str}>{desc_str}")

        role_list_text = "\n".join(role_lines) if role_lines else "> *(Belum ada role yang ditambahkan)*"

        footer_text = "⚖️ Aturan Ketat: Hanya bisa memilih 1 role dalam panel ini." if rule_type == "exclusive" else "✨ Aturan Bebas: Ambil atau lepas role sesuai kebutuhanmu."

        body_text = f"{desc}\n\n**Pilihan Role Tersedia:**\n{role_list_text}"

        card = build_v2_card(
            title=title,
            description=body_text,
            color=None,
            footer=footer_text
        )

        embed = discord.Embed(
            title=title,
            description=body_text
        )
        embed.set_footer(text=footer_text)

        view = DynamicRoleView(mode, roles, message_id_str, placeholder, rule_type)
        return card, embed, view

    async def _sync_role_panel_message(self, guild: discord.Guild, panel_data: dict, message_id_str: str) -> bool:
        channel_id = panel_data.get("channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None
        if not channel:
            return False
        card, embed, view = self._build_role_panel_render(guild, panel_data, message_id_str)
        components = [card, *view.to_components()]
        edit_resp = await edit_v2_message(self.bot, channel.id, int(message_id_str), components)
        if not edit_resp:
            try:
                msg = await channel.fetch_message(int(message_id_str))
                await msg.edit(embed=embed, view=view)
            except Exception:
                pass
        register_view(self.bot, view, message_id=int(message_id_str))
        return True

    def _build_role_panel_embeds_and_view(
        self,
        guild: discord.Guild,
        panel_data: dict,
        message_id: str
    ) -> tuple[list[discord.Embed], DynamicRoleView]:
        _, embed, view = self._build_role_panel_render(guild, panel_data, message_id)
        return [embed], view

    @commands.command(name="setmainmembershiprole", aliases=["smr"])
    @commands.has_permissions(manage_guild=True)
    async def set_main_membership_role(self, ctx: commands.Context, role: discord.Role):
        guild_settings = self.get_guild_settings(ctx.guild.id)
        guild_settings["main_membership_role_id"] = role.id
        self.save_settings()
        
        await ctx.send(embed=self._create_embed(description=f"✅ Role **Pengecekan Utama Membership** berhasil diatur ke {role.mention}. Semua pengecekan akan berpatokan pada role ini.", color=self.color_success))
        await self.log_action(ctx.guild, "🔑 Role Utama Membership Diatur", {"Role": role.mention, "Moderator": ctx.author.mention}, self.color_info)

    @commands.command(name="addmembershiprole", aliases=["amr"])
    @commands.has_permissions(manage_roles=True)
    async def add_membership_role(self, ctx: commands.Context, role: discord.Role, *, tier_name: str):
        guild_settings = self.get_guild_settings(ctx.guild.id)
        role_id_str = str(role.id)
        main_role_id = guild_settings.get("main_membership_role_id")

        if not main_role_id:
            await ctx.send(embed=self._create_embed(description="❌ Role Pengecekan Utama belum diatur! Harap atur dengan `!setmainmembershiprole <@role>` terlebih dahulu.", color=self.color_error))
            return
            
        if role.id == main_role_id:
            await ctx.send(embed=self._create_embed(description="❌ Role Tier tidak boleh sama dengan Role Pengecekan Utama.", color=self.color_error))
            return

        if role_id_str in guild_settings["membership_roles"]:
            await ctx.send(embed=self._create_embed(description=f"❌ Role {role.mention} sudah terdaftar sebagai tier **{guild_settings['membership_roles'][role_id_str]['tier_name']}**.", color=self.color_error))
            return

        guild_settings["membership_roles"][role_id_str] = {
            "tier_name": tier_name.strip(),
            "emoji": "🌟" 
        }
        self.save_settings()

        await ctx.send(embed=self._create_embed(description=f"✅ Role Tier **{role.mention}** berhasil ditambahkan untuk identifikasi tier: **{tier_name.strip()}**.", color=self.color_success))
        await self.log_action(ctx.guild, "➕ Membership Tier Ditambahkan", {"Role": role.mention, "Tier Name": tier_name.strip(), "Moderator": ctx.author.mention}, self.color_info)
        
    @commands.command(name="removemembershiprole", aliases=["rmr"])
    @commands.has_permissions(manage_roles=True)
    async def remove_membership_role(self, ctx: commands.Context, role: discord.Role):
        guild_settings = self.get_guild_settings(ctx.guild.id)
        role_id_str = str(role.id)

        if role_id_str not in guild_settings["membership_roles"]:
            await ctx.send(embed=self._create_embed(description=f"❌ Role {role.mention} tidak terdaftar sebagai role tier membership YouTube.", color=self.color_error))
            return

        tier_name = guild_settings["membership_roles"].pop(role_id_str)["tier_name"]
        self.save_settings()

        await ctx.send(embed=self._create_embed(description=f"✅ Role Tier **{role.mention}** (Tier: **{tier_name}**) berhasil dihapus dari daftar identifikasi tier.", color=self.color_success))
        await self.log_action(ctx.guild, "➖ Membership Tier Dihapus", {"Role": role.mention, "Tier Name": tier_name, "Moderator": ctx.author.mention}, self.color_info)

    @commands.command(name="setmembershipmessage", aliases=["smm"])
    @commands.has_permissions(manage_guild=True)
    async def set_membership_message(self, ctx: commands.Context, type: Literal['invite', 'confirm', 'button_label'], *, message_content: str):
        guild_settings = self.get_guild_settings(ctx.guild.id)

        if type == 'invite':
            key = "membership_invite_message"
            guild_settings[key] = message_content
            self.save_settings()
            await ctx.send(embed=self._create_embed(description=f"✅ Pesan **ajakan membership** berhasil diatur.", color=self.color_success))
        elif type == 'confirm':
            key = "membership_confirm_message"
            guild_settings[key] = message_content
            self.save_settings()
            await ctx.send(embed=self._create_embed(description=f"✅ Pesan **konfirmasi membership** berhasil diatur. Gunakan `{{tier_name}}` untuk nama tier.", color=self.color_success))
        elif type == 'button_label':
            key = "verification_button_label"
            guild_settings[key] = message_content
            self.save_settings()
            await ctx.send(embed=self._create_embed(description=f"✅ Label tombol verifikasi berhasil diatur ke **'{message_content}'**.", color=self.color_success))
        else:
            await ctx.send(embed=self._create_embed(description="❌ Tipe pesan/label tidak valid. Gunakan `invite`, `confirm`, atau `button_label`.", color=self.color_error))
            return

        await self.log_action(ctx.guild, f"💬 Pesan Membership {type.capitalize()} Diatur", {"Moderator": ctx.author.mention, "Content": message_content}, self.color_info)

    @commands.command(name="sendverificationbutton", aliases=["svb"])
    @commands.has_permissions(manage_guild=True)
    async def send_verification_button(self, ctx: commands.Context, *, button_label: Optional[str] = None):
        guild_settings = self.get_guild_settings(ctx.guild.id)
        
        final_label = button_label or guild_settings.get("verification_button_label", "Verifikasi Membership")

        main_role_id = guild_settings.get("main_membership_role_id")
        main_role = ctx.guild.get_role(main_role_id) if main_role_id else None

        if not main_role:
            await ctx.send(embed=self._create_embed(description="❌ **Role Pengecekan Utama** belum diatur. Harap atur dengan `!setmainmembershiprole <@role>` terlebih dahulu.", color=self.color_error))
            return

        tier_list = []
        for role_id_str, data in guild_settings.get("membership_roles", {}).items():
            role = ctx.guild.get_role(int(role_id_str))
            tier_info = role.mention if role else f'ID: `{role_id_str}`'
            tier_list.append(f"• **{data['tier_name']}** ({tier_info})") 

        list_tiers_str = '\n'.join(tier_list) if tier_list else '— Tidak ada Tier Membership spesifik yang didaftarkan. —'
        
        embed_desc = (
            f"Tekan tombol **{final_label}** di bawah untuk memverifikasi keanggotaan YouTube Anda. "
            f"Anda harus memiliki role **{main_role.mention}** untuk lolos verifikasi.\n\n"
            f"**Tier yang Dapat Diidentifikasi (untuk pesan konfirmasi):**\n"
            f"{list_tiers_str}"
        )

        embed = self._create_embed(
            title=" Verifikasi Status Membership",
            description=embed_desc,
            color=self.color_announce
        )

        view = UniversalMembershipView(self, final_label)
        await ctx.send(embed=embed, view=view)


    async def on_member_remove(self, member: discord.Member):
        if not member.guild:
            return
        
        try:
            dm_title = f"👋 Sampai Jumpa, {member.display_name}!"
            dm_message = (
                f"Kami dari **{member.guild.name}** sangat menyayangkan kepergian Anda. "
                f"Terima kasih banyak atas waktu dan kontribusi Anda selama berada di komunitas kami. "
                f"Semoga kita bisa bertemu lagi di masa depan! "
                f"\n\nJika ada masalah yang membuat Anda keluar, kami mohon maaf dan berharap Anda baik-baik saja."
            )
            
            dm_embed = self._create_embed(
                title=dm_title,
                description=dm_message,
                color=self.color_info 
            )
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            pass
        except Exception:
            pass

        guild_settings = self.get_guild_settings(member.guild.id)
        welcome_channel_id = guild_settings.get("welcome_channel_id")
        channel = member.guild.get_channel(welcome_channel_id) if welcome_channel_id else None

        if channel and isinstance(channel, discord.TextChannel): 
            
            goodbye_message_content = guild_settings.get("goodbye_message", "Selamat tinggal, **{user}**. Sampai jumpa lagi! 👋")
            
            embed = discord.Embed(
                title="💔 Kehilangan Seorang Anggota",
                description=goodbye_message_content.format(user=member.display_name, guild_name=member.guild.name),
                color=self.color_warning,
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=member.guild.name, icon_url=member.guild.icon.url if member.guild.icon else None)
            file = None
            welcome_banner_url = guild_settings.get("welcome_banner_url")
            if welcome_banner_url:
                embed.set_image(url=welcome_banner_url)
            else:
                try:
                    card_buffer = await self._create_goodbye_card(member, "SELAMAT TINGGAL!")
                    file = discord.File(fp=card_buffer, filename="goodbye.png")
                    embed.set_image(url="attachment://goodbye.png")
                except Exception:
                    pass

            embed.set_footer(text=f"Anggota tersisa {member.guild.member_count}.")
            
            try:
                if file:
                    await channel.send(embed=embed, file=file)
                else:
                    await channel.send(embed=embed)
            except discord.Forbidden:
                pass
            except Exception:
                pass

        guild_id_str = str(member.guild.id)
        member_id_str = str(member.id)
        
        warnings_cleared = False
        if guild_id_str in self.warnings and member_id_str in self.warnings[guild_id_str]:
            del self.warnings[guild_id_str][member_id_str]
            self.save_warnings()
            warnings_cleared = True

        log_fields = {
            "Member": f"{member} ({member.id})",
            "Nama Tampilan": member.display_name,
            "Total Anggota": member.guild.member_count
        }
        if warnings_cleared:
            log_fields["Data Hapus"] = "Warning History Dihapus"
            
        await self.log_action(
            member.guild,
            "🏃 Member Left Server",
            log_fields,
            self.color_warning
        )

        await self.update_panel(member.guild)
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            embed = self._create_embed(description=f"❌ Anda tidak memiliki izin `{', '.join(error.missing_permissions)}` untuk menjalankan perintah ini.", color=self.color_error)
            await ctx.send(embed=embed, delete_after=15)
        elif isinstance(error, commands.CommandNotFound):
            pass
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(embed=self._create_embed(description=f"❌ Anggota tidak ditemukan.", color=self.color_error))
        elif isinstance(error, commands.UserNotFound):
            await ctx.send(embed=self._create_embed(description=f"❌ Pengguna tidak ditemukan.", color=self.color_error))
        elif isinstance(error, commands.BadArgument):
            await ctx.send(embed=self._create_embed(description=f"❌ Argument tidak valid: {error}", color=self.color_error), delete_after=15)
        else:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_settings = self.get_guild_settings(member.guild.id)
        
        if (welcome_channel_id := guild_settings.get("welcome_channel_id")) and (channel := member.guild.get_channel(welcome_channel_id)):
            welcome_message_content = guild_settings.get("welcome_message", "Selamat datang di **{guild_name}**, {user}! 🎉")
            welcome_embed_title = guild_settings.get("welcome_embed_title", "SELAMAT DATANG!")
            welcome_sender_name = guild_settings.get("welcome_sender_name", "Admin Server")
            welcome_banner_url = (guild_settings.get("welcome_banner_url") or "").strip() or None

            try:
                formatted_desc = welcome_message_content.format(user=member.mention, guild_name=member.guild.name)
            except Exception:
                formatted_desc = welcome_message_content

            content_text = f"Halo, {member.mention}! Selamat datang!"
            footer_text = f"Kamu adalah anggota ke-{member.guild.member_count}! • {member.guild.name}"

            card_bytes = None
            file = None
            if not welcome_banner_url:
                try:
                    card_buffer = await self._create_welcome_card(member, welcome_embed_title)
                    if card_buffer:
                        card_bytes = card_buffer.getvalue()
                        file = discord.File(fp=io.BytesIO(card_bytes), filename="welcome.png")
                except Exception:
                    pass

            card = build_v2_card(
                title=welcome_embed_title,
                description=formatted_desc,
                color=None,
                footer=footer_text,
                attachment_filename="welcome.png" if file else None,
                media_url=welcome_banner_url if (welcome_banner_url and not file) else None
            )

            v2_sent = False
            try:
                files_payload = [file] if file else None
                res = await send_v2_message(
                    bot=self.bot,
                    channel_id=channel.id,
                    components=[card],
                    files=files_payload,
                    content=content_text
                )
                if res and (getattr(res, "id", None) or (isinstance(res, dict) and "id" in res and "error_msg" not in res)):
                    v2_sent = True
                else:
                    print(f"[WELCOME] send_v2_message did not succeed: {res}")
            except Exception as e:
                print(f"[WELCOME] Exception during send_v2_message: {e}")

            if not v2_sent:
                try:
                    legacy_embed = discord.Embed(
                        description=formatted_desc,
                        color=self.color_welcome,
                        timestamp=discord.utils.utcnow()
                    )
                    if welcome_sender_name:
                        legacy_embed.set_author(name=welcome_sender_name, icon_url=member.guild.icon.url if member.guild.icon else None)
                    legacy_embed.title = welcome_embed_title
                    legacy_embed.set_thumbnail(url=member.display_avatar.url)
                    legacy_embed.set_footer(text=f"Kamu adalah anggota ke-{member.guild.member_count}!")

                    fallback_file = None
                    if welcome_banner_url:
                        legacy_embed.set_image(url=welcome_banner_url)
                    elif card_bytes:
                        fallback_file = discord.File(fp=io.BytesIO(card_bytes), filename="welcome.png")
                        legacy_embed.set_image(url="attachment://welcome.png")

                    if fallback_file:
                        await channel.send(content_text, embed=legacy_embed, file=fallback_file)
                    else:
                        await channel.send(content_text, embed=legacy_embed)
                except discord.Forbidden:
                    pass
                except Exception:
                    pass
    
        if (auto_role_id := guild_settings.get("auto_role_id")) and (role := member.guild.get_role(auto_role_id)):
            try:
                await member.add_roles(role, reason="Auto Role")
            except discord.Forbidden:
                pass
    
        await self.update_panel(member.guild)

    async def send_booster_announcement(self, guild: discord.Guild, member: discord.Member, is_test: bool = False):
        guild_settings = self.get_guild_settings(guild.id)
        if not is_test and not guild_settings.get("boost_enabled", True):
            return
        channel_id = guild_settings.get("boost_channel_id")
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not channel or not channel.permissions_for(guild.me).send_messages:
            return

        cache_key = f"{guild.id}:{member.id}"
        now = time.time()
        if not is_test:
            if cache_key in self._recent_boosters and (now - self._recent_boosters[cache_key]) < 30:
                return
            self._recent_boosters[cache_key] = now

        boost_count = guild.premium_subscription_count or 1
        tier_map = {0: "Level 0", 1: "Tier 1", 2: "Tier 2", 3: "Tier 3"}
        tier = tier_map.get(guild.premium_tier, f"Tier {guild.premium_tier}")

        default_msg = (
            "🎉 **BOOSTER BARU!** Terima kasih banyak {user_mention} telah mem-boost **{server}**! 💜\n"
            "Berkat dukunganmu, server kita sekarang memiliki **{boost_count} Boosts** ({tier})! Nikmati role dan fasilitas eksklusifmu! 🚀"
        )
        raw_template = guild_settings.get("boost_message") or default_msg
        try:
            formatted_msg = raw_template.format(
                user=member.display_name,
                user_mention=member.mention,
                server=guild.name,
                boost_count=boost_count,
                tier=tier,
                guild_name=guild.name
            )
        except Exception:
            formatted_msg = raw_template

        from cogs.v2_layout import build_v2_card, send_v2_message
        card = build_v2_card(
            title=f"🚀 Server Boosted! • {guild.name}",
            description=formatted_msg,
            fields=[
                {"name": "✨ Booster", "value": f"{member.mention} (`{member.name}`)"},
                {"name": "💎 Level Server", "value": f"**{tier}** (`{boost_count}` Boosts)"}
            ],
            color=0xF47FFF,
            media_url=guild_settings.get("boost_image_url") or None,
            footer="Server Boost Event • Terima kasih atas dukunganmu!"
        )
        await send_v2_message(self.bot, channel.id, [card])

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.premium_since is None and after.premium_since is not None:
            self.bot.loop.create_task(self.send_booster_announcement(after.guild, after))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return
            
        if message.type in (
            discord.MessageType.premium_guild_subscription,
            discord.MessageType.premium_guild_tier_1,
            discord.MessageType.premium_guild_tier_2,
            discord.MessageType.premium_guild_tier_3,
        ):
            if isinstance(message.author, discord.Member):
                self.bot.loop.create_task(self.send_booster_announcement(message.guild, message.author))
            
        channel_rules = self.get_channel_rules(message.guild.id, message.channel.id)
        auto_delete_delay = channel_rules.get("auto_delete_seconds", 0)

        if message.author.id == self.bot.user.id:
            if auto_delete_delay > 0:
                self.bot.loop.create_task(self._safe_delete_message(message, auto_delete_delay))
            return

        is_webhook = message.webhook_id is not None

        if message.author.bot or is_webhook:
            if channel_rules.get("disallow_bots"):
                self.bot.loop.create_task(self._safe_delete_message(message, 0))
                return
            
            if auto_delete_delay > 0:
                self.bot.loop.create_task(self._safe_delete_message(message, auto_delete_delay))

            if is_webhook:
                guild_settings = self.get_guild_settings(message.guild.id)
                trigger_channels = guild_settings.get("trigger_channels", [])
                first_media = message.attachments[0].url if message.attachments else None
                
                if message.channel.id in trigger_channels:
                    try: await message.delete()
                    except: pass
                    try:
                        wh = await self.bot.fetch_webhook(message.webhook_id)
                        await wh.delete(reason="Rogue Webhook: Mengirim pesan di Honeypot Channel")
                    except Exception: pass
                    await self.send_spam_log_v2(
                        message.guild, message.author, message.channel.mention,
                        "🚨 Rogue Webhook di Honeypot Channel",
                        "Webhook terdeteksi mengirim pesan di channel jebakan honeypot. Pesan dan Webhook telah dicabut otomatis.",
                        str(message.id), message_content=message.content, media_url=first_media, is_webhook=True
                    )
                    return

                wh_content_lower = message.content.lower()
                scam_keywords = ['nitro', 'gift', 'airdrop', 'free steam', 'disocrd', 'dlscord', 'discrod', 't.me/']
                urls = re.findall(r'(https?://[^\s]+)', wh_content_lower)
                if urls and any(any(kw in u for kw in scam_keywords) for u in urls):
                    try: await message.delete()
                    except: pass
                    try:
                        wh = await self.bot.fetch_webhook(message.webhook_id)
                        await wh.delete(reason="Rogue Webhook: Terdeteksi mengirim link Phishing")
                    except Exception: pass
                    await self.send_spam_log_v2(
                        message.guild, message.author, message.channel.mention,
                        "🚨 Rogue Webhook Phishing Link",
                        f"Webhook terdeteksi menyebarkan link scam/phising: `{', '.join(urls)[:150]}`. Pesan dan Webhook telah dicabut.",
                        str(message.id), message_content=message.content, media_url=first_media, is_webhook=True
                    )
                    return
                return
            return

        guild_settings = self.get_guild_settings(message.guild.id)
        whitelist_roles = guild_settings.get("spam_whitelist_roles", [])
        is_whitelisted = any(r.id in whitelist_roles for r in message.author.roles)
        user_id_str = str(message.author.id)
        is_command = message.content.startswith(tuple(await self.bot.get_prefix(message)))
        
        if auto_delete_delay > 0:
            self.bot.loop.create_task(self._safe_delete_message(message, auto_delete_delay))
        
        trigger_channels = guild_settings.get("trigger_channels", [])
        if message.channel.id in trigger_channels and not is_command:
            trap_media_bytes = None
            trap_media_filename = None
            if message.attachments:
                try:
                    trap_media_bytes = await message.attachments[0].read()
                    trap_media_filename = message.attachments[0].filename or "evidence.png"
                except Exception:
                    pass

            try:
                await message.delete()
            except discord.Forbidden:
                pass
                
            is_owner = (await self.bot.is_owner(message.author)) or str(message.author.id) == os.getenv("BOT_OWNER_ID", "1000737066822410311")
            is_immune = is_whitelisted or message.author.guild_permissions.administrator or message.author.guild_permissions.kick_members or is_owner
            if is_immune:
                return

            try:
                timeout_duration = timedelta(days=27, hours=23, minutes=59)
                timeout_reason = "Terdeteksi mengirim pesan berisi spam atau phising (Sistem Anti-Spam)"
                now_utc = datetime.now(timezone.utc)
                
                for guild_obj in self.bot.guilds:
                    member_in_guild = guild_obj.get_member(message.author.id)
                    if member_in_guild:
                        should_apply = True
                        if member_in_guild.is_timed_out() and member_in_guild.timed_out_until:
                            remaining = member_in_guild.timed_out_until - now_utc
                            if remaining >= timeout_duration:
                                should_apply = False
                        if should_apply:
                            try:
                                await member_in_guild.timeout(timeout_duration, reason=timeout_reason)
                            except Exception:
                                pass
            except Exception as e:
                print(f"Global timeout failed: {e}")
                
            if user_id_str in self.cross_channel_spam_history:
                messages_to_delete = self.cross_channel_spam_history.pop(user_id_str, [])
                delete_tasks = []
                for entry in messages_to_delete:
                    try:
                        channel_to_purge = message.guild.get_channel(entry['channel_id'])
                        if channel_to_purge and channel_to_purge.permissions_for(message.guild.me).manage_messages:
                            delete_tasks.append(channel_to_purge.delete_messages([discord.Object(id=entry['message_id'])], reason="Trigger Channel Trap Activated"))
                    except Exception:
                        continue
                if delete_tasks:
                    try:
                        await asyncio.gather(*delete_tasks, return_exceptions=True)
                    except Exception:
                        pass
                        
            await self.send_spam_log_v2(
                message.guild, message.author, message.channel.mention,
                "Terdeteksi mengirim pesan berisi spam atau phising (Sistem Anti-Spam)",
                "Pengguna terdeteksi mengirim pesan di channel jebakan (Honey-Pot). Sistem telah menjatuhkan sanksi Timeout 28 Hari secara otomatis.",
                str(message.id),
                message_content=message.content,
                media_bytes=trap_media_bytes,
                media_filename=trap_media_filename
            )
            
            await self.increment_timeout_counter(message.channel.id)
            return

        current_time = time.time()
        message_content_lower = message.content.lower()
        


        if not message.author.guild_permissions.kick_members and not is_whitelisted and not is_command:
            
            if user_id_str not in self.cross_channel_spam_history:
                self.cross_channel_spam_history[user_id_str] = []
            
            self.cross_channel_spam_history[user_id_str].append({
                'channel_id': message.channel.id,
                'message_id': message.id,
                'timestamp': current_time,
                'content': message.content[:100]
            })
            
            self.cross_channel_spam_history[user_id_str] = [
                entry for entry in self.cross_channel_spam_history[user_id_str]
                if current_time - entry['timestamp'] <= 30
            ]
            
            global_bucket = self.global_spam_cooldown.get_bucket(message)
            global_retry_after = global_bucket.update_rate_limit()
            
            if global_retry_after:
                messages_to_delete = self.cross_channel_spam_history.pop(user_id_str, [])
                
                delete_tasks = []
                for entry in messages_to_delete:
                    try:
                        channel = message.guild.get_channel(entry['channel_id'])
                        if channel and channel.permissions_for(message.guild.me).manage_messages:
                            tasks.append(channel.delete_messages([discord.Object(id=entry['message_id'])], reason="Global Cross-Channel Spam Detected"))
                    except Exception:
                        continue
                
                if delete_tasks:
                    try:
                        await asyncio.gather(*delete_tasks, return_exceptions=True)
                    except discord.Forbidden:
                       await self.log_action(message.guild, "❌ PENGHAPUSAN SPAM LINTAS CHANNEL GAGAL", 
                           {"Member": message.author.mention, "Channel Pemicu": message.channel.mention, "Error": "Gagal menghapus beberapa pesan (Forbidden/Izin)."}, self.color_error)

                if not message.author.is_timed_out():
                    duration = timedelta(minutes=30)
                    reason = "Global Cross-Channel Spam Detection (Auto-Timeout 30m)"
                    
                    try:
                        await message.author.timeout(duration, reason=reason)
                        await self.increment_timeout_counter()
                        
                        spam_count = len(messages_to_delete)
                        channels_affected = len(set(entry['channel_id'] for entry in messages_to_delete))
                        
                        await message.channel.send(
                            embed=self._create_embed(
                                description=f"🚫 {message.author.mention} telah di-**TIMEOUT 30 MENIT** karena **Spam Massal Lintas Channel** ({spam_count} pesan di {channels_affected} channel).",
                                color=self.color_error
                            ),
                            delete_after=15
                        )
                        
                        await self.log_action(
                            message.guild, 
                            "🚫 Global Cross-Channel Spam Detected",
                            {
                                "Member": message.author.mention,
                                "Total Pesan": spam_count,
                                "Channel Terlibat": channels_affected,
                                "Aksi": "Timeout (30m) + Hapus Semua Pesan"
                            },
                            self.color_error
                        )
                        
                    except discord.Forbidden:
                        await self.send_spam_log_v2(message.guild, message.author, message.channel.mention, "Spam Massal (Gagal Timeout)", "Izin bot tidak cukup.", str(message.id))
                
                return
            
            self.spam_history.setdefault(user_id_str, []).append({
                'channel_id': message.channel.id, 
                'message_id': message.id, 
                'timestamp': current_time
            })

            bucket = self.fast_spam_cooldown.get_bucket(message)
            retry_after = bucket.update_rate_limit()

            if retry_after:
                
                messages_to_delete = self.spam_history.pop(user_id_str, [])
                
                tasks = []
                for entry in messages_to_delete:
                    try:
                        channel = message.guild.get_channel(entry['channel_id'])
                        if channel and channel.permissions_for(message.guild.me).manage_messages:
                            tasks.append(channel.delete_messages([discord.Object(id=entry['message_id'])], reason="Global Spam Detected"))
                    except Exception:
                        pass
                
                if tasks:
                    try:
                        await asyncio.gather(*tasks, return_exceptions=True)
                    except discord.Forbidden:
                       await self.send_spam_log_v2(message.guild, message.author, message.channel.mention, "Gagal Menghapus Pesan Spam", "Bot kekurangan izin Manage Messages.", str(message.id))


                now_utc = datetime.now(timezone.utc)
                should_timeout = True
                if message.author.is_timed_out() and message.author.timed_out_until:
                    if (message.author.timed_out_until - now_utc) >= timedelta(minutes=10):
                        should_timeout = False

                if should_timeout:
                    duration = timedelta(minutes=10) 
                    reason = "Global Fast Spam: >5 messages in 10 seconds (Auto-Timeout 10m)."
                    try:
                        await message.author.timeout(duration, reason=reason)
                        await self.increment_timeout_counter()
                        try:
                            await message.author.send(embed=self._create_embed(description=f"⚠️ Anda telah di-timeout selama 10 Menit oleh sistem keamanan karena Spam Massal.\n\n*Anda dapat mengajukan banding atas aksi ini dengan mengirim DM ke admin/moderator server.*", color=self.color_error))
                        except: pass
                        await message.channel.send(
                            embed=self._create_embed(
                                description=f"🚫 {message.author.mention} telah di-**TIMEOUT** selama 10 menit karena **Spam Massal**.",
                                color=self.color_error
                            ),
                            delete_after=10
                        )
                        await self.send_spam_log_v2(
                            message.guild, message.author, message.channel.mention,
                            "Terdeteksi mengirim pesan berisi spam atau phising (Sistem Anti-Spam)",
                            "Pengguna terdeteksi mengirim pesan teks berisi spam secara beruntun (Fast Spam). Sistem telah menjatuhkan sanksi Timeout 10 Menit secara otomatis.",
                            str(message.id),
                            message_content=message.content
                        )
                    except discord.Forbidden:
                        await self.send_spam_log_v2(
                            message.guild, message.author, message.channel.mention,
                            "Terdeteksi mengirim pesan berisi spam atau phising (Sistem Anti-Spam)",
                            "Pengguna terdeteksi mengirim pesan teks berisi spam secara beruntun (Fast Spam). Sistem gagal menjatuhkan sanksi karena kekurangan izin.",
                            str(message.id),
                            message_content=message.content
                        )
                        
                return
            
            cooldown_duration = self.fast_spam_cooldown._cooldown.per 
            
            if user_id_str in self.spam_history:
                self.spam_history[user_id_str] = [
                    entry for entry in self.spam_history[user_id_str] 
                    if current_time - entry['timestamp'] <= cooldown_duration
                ]
                if not self.spam_history[user_id_str]:
                    del self.spam_history[user_id_str]
        
        if not message.author.guild_permissions.kick_members and not is_whitelisted:
            if self.detect_suspicious_links(message.content):
                try:
                    await message.delete()
                    
                    await message.channel.send(
                        embed=self._create_embed(
                            description=f"🛡️ {message.author.mention}, pesan Anda dihapus karena mengandung link mencurigakan yang berpotensi phising.",
                            color=self.color_warning
                        ),
                        delete_after=10
                    )
                    
                    now_utc = datetime.now(timezone.utc)
                    should_timeout = True
                    if message.author.is_timed_out() and message.author.timed_out_until:
                        if (message.author.timed_out_until - now_utc) >= timedelta(hours=1):
                            should_timeout = False

                    if should_timeout:
                        try:
                            await message.author.timeout(
                                timedelta(hours=1), 
                                reason="Automatic timeout for suspicious/phishing links"
                            )
                            await self.increment_timeout_counter()
                            try:
                                await message.author.send(embed=self._create_embed(description=f"⚠️ Anda telah di-timeout selama 1 Jam oleh sistem keamanan karena mengirim link mencurigakan/phising.\n\n*Anda dapat mengajukan banding atas aksi ini dengan mengirim DM ke admin/moderator server.*", color=self.color_error))
                            except: pass
                        except discord.Forbidden:
                            pass
                    
                    await self.log_action(
                        message.guild,
                        "🛡️ Suspicious Link Detected & Blocked",
                        {
                            "Member": message.author.mention,
                            "Channel": message.channel.mention,
                            "Content Preview": message.content[:100] + "..." if len(message.content) > 100 else message.content,
                            "Action": "Message Deleted + Auto-Timeout"
                        },
                        self.color_warning
                    )
                    
                except discord.Forbidden:
                    pass
                
                return

        if message.attachments and not message.author.guild_permissions.kick_members and not is_whitelisted:
            total_size = sum(att.size for att in message.attachments)
            media_count = len(message.attachments)

            for attachment in message.attachments:
                if not self.is_allowed_file_type(attachment.filename):
                    try:
                        await message.delete()
                        await message.channel.send(
                            embed=self._create_embed(
                                description=f"🚫 {message.author.mention}, tipe file `{attachment.filename}` tidak diizinkan.",
                                color=self.color_error
                            ),
                            delete_after=10
                        )
                        return
                    except discord.Forbidden:
                        pass
                    return

            heavy_bucket = self.media_spam_heavy_cooldown.get_bucket(message)
            heavy_retry_after = heavy_bucket.update_rate_limit()
            
            if heavy_retry_after:
                try:
                    ev_bytes = None
                    ev_filename = None
                    if message.attachments:
                        try:
                            ev_bytes = await message.attachments[0].read()
                            ev_filename = message.attachments[0].filename or "evidence.png"
                        except Exception: pass

                    await message.delete()

                    now_utc = datetime.now(timezone.utc)
                    should_timeout = True
                    if message.author.is_timed_out() and message.author.timed_out_until:
                        if (message.author.timed_out_until - now_utc) >= timedelta(minutes=30):
                            should_timeout = False

                    if should_timeout:
                        await message.author.timeout(timedelta(minutes=30), reason="Heavy media spam (8+ media in 60 seconds)")
                        await self.increment_timeout_counter()
                        try:
                            await message.author.send(embed=self._create_embed(description=f"⚠️ Anda telah di-timeout selama 30 Menit oleh sistem keamanan karena spam media berat.\n\n*Anda dapat mengajukan banding atas aksi ini dengan mengirim DM ke admin/moderator server.*", color=self.color_error))
                        except: pass
                        await self.send_spam_log_v2(
                            message.guild, message.author, message.channel.mention,
                            "Terdeteksi mengirim pesan berisi spam atau phising (Sistem Anti-Spam)",
                            "Pengguna terdeteksi mengirim pesan gambar berisi spam secara massal (Heavy Spam). Sistem telah menjatuhkan sanksi Timeout 30 Menit secara otomatis.",
                            str(message.id),
                            message_content=message.content,
                            media_bytes=ev_bytes,
                            media_filename=ev_filename
                        )
                        
                        await message.channel.send(
                            embed=self._create_embed(
                                description=f"🚫 {message.author.mention} di-**TIMEOUT 30 MENIT** karena spam media berat.",
                                color=self.color_error
                            ),
                            delete_after=10
                        )
                    return
                except discord.Forbidden:
                    pass

            if len(message.attachments) > 5 or total_size > 50 * 1024 * 1024:
                try:
                    await message.delete()
                    await message.channel.send(
                        embed=self._create_embed(
                            description=f"📁 {message.author.mention}, batas maksimal: 5 file atau total 50MB per pesan.",
                            color=self.color_warning
                        ),
                        delete_after=10
                    )
                    return
                except discord.Forbidden:
                    pass

        if is_command:
            return 
        
        rules = channel_rules

        if rules.get("disallow_media") and message.attachments:
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            await message.channel.send(
                embed=self._create_embed(description=f"🖼️ {message.author.mention}, media/files are not allowed in this channel.", color=self.color_warning),
                delete_after=10
            )
            return

        if rules.get("disallow_url") and self.url_regex.search(message.content):
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            await message.channel.send(
                embed=self._create_embed(description=f"🔗 {message.author.mention}, links are not allowed in this channel.", color=self.color_warning),
                delete_after=10
            )
            return

        if rules.get("disallow_prefix") and message.content.startswith(self.common_prefixes):
            command_prefixes = await self.bot.get_prefix(message)
            if not isinstance(command_prefixes, list):
                command_prefixes = [command_prefixes]
            is_actual_command = any(
                message.content.startswith(prefix) and self.bot.get_command(message.content[len(prefix):].split(' ')[0])
                for prefix in command_prefixes
            )
            if not is_actual_command:
                try:
                    await message.delete()
                except discord.Forbidden:
                    pass
                await message.channel.send(
                    embed=self._create_embed(description=f"❗ {message.author.mention}, bot commands are not allowed in this channel.", color=self.color_warning),
                    delete_after=10
                )
                return

        guild_filters = self.get_guild_filters(message.guild.id)
        for bad_word in guild_filters.get("bad_words", []):
            if bad_word.lower() in message_content_lower:
                try:
                    await message.delete()
                except discord.Forbidden:
                    pass
                await message.channel.send(
                    embed=self._create_embed(description=f"🤬 Pesan dari {message.author.mention} dihapus karena mengandung kata kasar.", color=self.color_warning),
                    delete_after=10
                )
                return
        
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None or payload.member is None or payload.member.bot: return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        
        guild_settings = self.get_guild_settings(payload.guild_id)
        role_map = guild_settings.get("reaction_roles", {}).get(str(payload.message_id))
        
        if role_map and (role_id := role_map.get(str(payload.emoji))):
            if (role := guild.get_role(role_id)):
                try:
                    await payload.member.add_roles(role, reason="Reaction Role")
                except discord.Forbidden:
                    pass
                except Exception as e:
                    pass
            else:
                pass
        else:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None: return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild or not (member := guild.get_member(payload.user_id)) or member.bot: return

        guild_settings = self.get_guild_settings(payload.guild_id)
        role_map = guild_settings.get("reaction_roles", {}).get(str(payload.message_id))
        
        if role_map and (role_id := role_map.get(str(payload.emoji))):
            if (role := guild.get_role(role_id)):
                if role in member.roles:
                    try:
                        await member.remove_roles(role, reason="Reaction Role Removed")
                    except discord.Forbidden:
                        pass
                    except Exception as e:
                        pass
                else:
                    pass
            else:
                pass
        else:
            pass



    @commands.hybrid_command(name="kick", description="Keluarkan member dari server")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(member="Member yang ingin di-kick", reason="Alasan mengeluarkan member")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: Optional[str] = "No reason provided."):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send(embed=self._create_embed(description="❌ You cannot kick a member with an equal or higher role.", color=self.color_error)); return
        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak dapat menendang anggota ini karena peran mereka sama atau lebih tinggi dari peran bot.", color=self.color_error)); return
        if member.id == ctx.guild.owner.id:
            await ctx.send(embed=self._create_embed(description="❌ You cannot kick the server owner.", color=self.color_error)); return
        if member.id == self.bot.user.id:
            await ctx.send(embed=self._create_embed(description="❌ You cannot kick this bot itself.", color=self.color_error)); return

        try:
            await member.kick(reason=reason)
            await ctx.send(embed=self._create_embed(description=f"✅ **{member.display_name}** has been kicked.", color=self.color_success))
            await self.log_action(ctx.guild, "👢 Member Kicked", {"Member": f"{member} ({member.id})", "Moderator": ctx.author.mention, "Reason": reason}, self.color_warning)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot does not have sufficient permissions to kick this member. Ensure the bot's role is higher.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ An error occurred while kicking the member: {e}", color=self.color_error))

    @commands.hybrid_command(name="ban", description="Blokir member dari server")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.describe(member="Member target", reason="Alasan pemblokiran")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = "No reason provided."):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner: await ctx.send(embed=self._create_embed(description="❌ You cannot ban a member with an equal or higher role.", color=self.color_error)); return
        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak dapat memblokir anggota ini karena peran mereka sama atau lebih tinggi dari peran bot.", color=self.color_error)); return
        if member.id == ctx.guild.owner.id: await ctx.send(embed=self._create_embed(description="❌ You cannot ban the server owner.", color=self.color_error)); return
        if member.id == self.bot.user.id: await ctx.send(embed=self._create_embed(description="❌ You cannot ban this bot itself.", color=self.color_error)); return

        try:
            await member.ban(reason=reason)
            await ctx.send(embed=self._create_embed(description=f"✅ **{member.display_name}** has been banned.", color=self.color_success))
            await self.log_action(ctx.guild, "🔨 Member Banned", {"Member": f"{member} ({member.id})", "Moderator": ctx.author.mention, "Reason": reason}, self.color_error)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot does not have sufficient permissions to ban this member. Ensure the bot's role is higher.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ An error occurred while banning the member: {e}", color=self.color_error))

    @commands.hybrid_command(name="softban", description="Ban member dan langsung unban untuk bersihkan pesan dalam 7 hari")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.describe(member="Member target", reason="Alasan softban")
    @commands.has_permissions(ban_members=True)
    async def softban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided."):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send(embed=self._create_embed(description="❌ You cannot softban a member with an equal or higher role.", color=self.color_error))
            return
        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak dapat memblokir anggota ini karena peran mereka sama atau lebih tinggi dari peran bot.", color=self.color_error)); return
        if member.id == ctx.guild.owner.id:
            await ctx.send(embed=self._create_embed(description="❌ You cannot softban the server owner.", color=self.color_error)); return
        if member.id == self.bot.user.id:
            await ctx.send(embed=self._create_embed(description="❌ You cannot softban this bot itself.", color=self.color_error)); return

        try:
            dm_embed = self._create_embed(title=f"🚨 You Were Softbanned from {ctx.guild.name}", color=self.color_error)
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        try:
            await member.ban(reason=f"Softban: {reason}", delete_message_seconds=604800)
            await ctx.guild.unban(member, reason="Softban cleanup complete")

            await ctx.send(embed=self._create_embed(description=f"✅ **{member.display_name}** has been softbanned (messages from the last 7 days cleared).", color=self.color_success))
            await self.log_action(ctx.guild, "🔨 Member Softbanned", {"Member": f"{member} ({member.id})", "Moderator": ctx.author.mention, "Reason": reason}, self.color_error)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot does not have sufficient permissions to ban/unban this member.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ An error occurred during softban: {e}", color=self.color_error))

    @commands.hybrid_command(name="unban", description="Cabut blokir member")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.describe(user_identifier="ID atau Username target", reason="Alasan pencabutan")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, *, user_identifier: str, reason: Optional[str] = "No reason provided."):
        user_to_unban = None
        try:
            user_id = int(user_identifier)
            temp_user = await self.bot.fetch_user(user_id)
            user_to_unban = temp_user
        except ValueError:
            for entry in [entry async for entry in ctx.guild.bans()]:
                if str(entry.user).lower() == user_identifier.lower():
                    user_to_unban = entry.user
                    break
        except discord.NotFound:
            pass

        if user_to_unban is None:
            await ctx.send(embed=self._create_embed(description=f"❌ User `{user_identifier}` not found in ban list or invalid ID/Name#Tag.", color=self.color_error))
            return

        try:
            await ctx.guild.unban(user_to_unban, reason=reason)
            await ctx.send(embed=self._create_embed(description=f"✅ Ban for **{user_to_unban}** has been lifted.", color=self.color_success))
            await self.log_action(ctx.guild, "🤝 Ban Lifted", {"User": f"{user_to_unban} ({user_to_unban.id})", "Moderator": ctx.author.mention, "Reason": reason}, self.color_success)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot does not have sufficient permissions to unban this member. Ensure the bot's role is higher.", color=self.color_error))
        except discord.NotFound:
            await ctx.send(embed=self._create_embed(description=f"❌ User `{user_to_unban}` not found in ban list.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ An error occurred while unbanning: {e}", color=self.color_error))

    @commands.hybrid_command(name="warn", description="Beri peringatan tercatat pada member")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(member="Member target", reason="Alasan peringatan")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send(embed=self._create_embed(description="❌ You cannot warn a member with an equal or higher role.", color=self.color_error))
            return
        if member.bot:
            await ctx.send(embed=self._create_embed(description="❌ You cannot warn a bot.", color=self.color_error)); return
        if member.id == ctx.guild.owner.id:
            await ctx.send(embed=self._create_embed(description="❌ You cannot warn the server owner.", color=self.color_error)); return

        timestamp = int(time.time())
        warning_data = {
            "moderator_id": ctx.author.id,
            "timestamp": timestamp,
            "reason": reason
        }
        guild_id_str = str(ctx.guild.id)
        member_id_str = str(member.id)
        
        self.warnings.setdefault(guild_id_str, {}).setdefault(member_id_str, []).append(warning_data)
        self.save_warnings()

        try:
            dm_embed = self._create_embed(title=f"🚨 You Received a Warning in {ctx.guild.name}", color=self.color_warning)
            dm_embed.add_field(name="Warning Reason", value=reason, inline=False)
            dm_embed.set_footer(text=f"Warning issued by {ctx.author.display_name}")
            await member.send(embed=dm_embed)
            dm_sent = True
        except discord.Forbidden:
            dm_sent = False

        confirm_desc = f"✅ **{member.display_name}** has been warned."
        if not dm_sent:
            confirm_desc += "\n*(Warning message could not be sent to user's DMs.)*"
            
        await ctx.send(embed=self._create_embed(description=confirm_desc, color=self.color_success))
        await self.log_action(ctx.guild, "⚠️ Member Warned", {"Member": f"{member} ({member.id})", "Moderator": ctx.author.mention, "Reason": reason}, self.color_warning)
        await self.check_and_escalate_warnings(ctx.guild, member, ctx.author)

    @commands.hybrid_command(name="unwarn", description="Hapus peringatan member")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(member="Member target", warning_index="Nomor urut peringatan", reason="Alasan penghapusan")
    @commands.has_permissions(kick_members=True)
    async def unwarn(self, ctx: commands.Context, member: discord.Member, warning_index: int, *, reason: Optional[str] = "Admin error."):
        guild_id_str = str(ctx.guild.id)
        member_id_str = str(member.id)
        
        user_warnings = self.warnings.get(guild_id_str, {}).get(member_id_str, [])
        
        if not user_warnings:
            await ctx.send(embed=self._create_embed(description=f"❌ **{member.display_name}** has no warnings.", color=self.color_error))
            return

        if not (0 < warning_index <= len(user_warnings)):
            await ctx.send(embed=self._create_embed(description=f"❌ Invalid warning index. Use `!warnings {member.mention}` to see the warning list.", color=self.color_error))
            return
        
        removed_warning = self.warnings[guild_id_str][member_id_str].pop(warning_index - 1)
        self.save_warnings()
        
        await ctx.send(embed=self._create_embed(description=f"✅ Warning #{warning_index} for **{member.display_name}** has been removed.", color=self.color_success))
        
        log_fields = {
            "Member": f"{member} ({member.id})",
            "Moderator": ctx.author.mention,
            "Reason for Removal": reason,
            "Removed Warning": f"`{removed_warning['reason']}`"
        }
        await self.log_action(ctx.guild, "👍 Warning Removed", log_fields, self.color_success)

    @commands.command(name="warnings", aliases=["history"])
    @commands.has_permissions(kick_members=True)
    async def warnings(self, ctx, member: discord.Member):
        guild_id_str = str(ctx.guild.id)
        member_id_str = str(member.id)
        
        user_warnings = self.warnings.get(guild_id_str, {}).get(member_id_str, [])
        
        if not user_warnings:
            await ctx.send(embed=self._create_embed(description=f"✅ **{member.display_name}** has no warning history.", color=self.color_success))
            return

        embed = self._create_embed(title=f"Warning History for {member.display_name}", color=self.color_info)
        embed.set_thumbnail(url=member.display_avatar.url)

        for idx, warn_data in enumerate(user_warnings, 1):
            moderator = await self.bot.fetch_user(warn_data.get('moderator_id', 0))
            timestamp = warn_data.get('timestamp', 0)
            reason = warn_data.get('reason', 'N/A')
            field_value = f"**Reason:** {reason}\n**Moderator:** {moderator.mention if moderator else 'Unknown'}\n**Date:** <t:{timestamp}:F>"
            embed.add_field(name=f"Warning #{idx}", value=field_value, inline=False)
            
        await ctx.send(embed=embed)

    @commands.command(name="setgoodbye", aliases=["sbm"])
    @commands.has_permissions(manage_guild=True)
    async def set_goodbye_message(self, ctx, *, message_content: str):
        guild_settings = self.get_guild_settings(ctx.guild.id)
        
        if len(message_content) > 4000:
            return await ctx.send(embed=self._create_embed(description="❌ Isi pesan terlalu panjang (maksimal 4000 karakter).", color=self.color_error))
        
        guild_settings["goodbye_message"] = message_content
        self.save_settings()
        
        embed = self._create_embed(
            description=f"✅ Pesan selamat tinggal berhasil diatur:\n```{message_content}```",
            color=self.color_success
        )
        await ctx.send(embed=embed)
        await self.log_action(ctx.guild, "💬 Pesan Selamat Tinggal Diatur", {"Moderator": ctx.author.mention, "Isi Pesan": message_content}, self.color_info)

    @commands.hybrid_command(name="timeout", aliases=["mute"], description="Bungkam member sementara")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="Member target", duration="Durasi (misal: 10m, 1h)", reason="Alasan timeout")
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx: commands.Context, member: discord.Member, duration: str, *, reason: Optional[str] = "No reason provided."):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send(embed=self._create_embed(description="❌ You cannot timeout a member with an equal or higher role.", color=self.color_error)); return
        if member.id == ctx.guild.owner.id:
            await ctx.send(embed=self._create_embed(description="❌ You cannot timeout the server owner.", color=self.color_error)); return
        if member.id == self.bot.user.id:
            await ctx.send(embed=self._create_embed(description="❌ You cannot timeout this bot itself.", color=self.color_error)); return
        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak dapat memberi timeout anggota ini karena peran mereka sama atau lebih tinggi dari peran bot.", color=self.color_error)); return

        delta = parse_duration(duration)
        if not delta: await ctx.send(embed=self._create_embed(description="❌ Invalid duration format. Use `s` (seconds), `m` (minutes), `h` (hours), `d` (days). Example: `10m`.", color=self.color_error)); return
        if delta.total_seconds() > 2419200:
            await ctx.send(embed=self._create_embed(description="❌ Timeout duration cannot exceed 28 days.", color=self.color_error)); return

        try:
            await member.timeout(delta, reason=reason)
            await self.increment_timeout_counter()
            await ctx.send(embed=self._create_embed(description=f"✅ **{member.display_name}** has been timed out for `{duration}`.", color=self.color_success))
            await self.log_action(ctx.guild, "🤫 Member Timeout", {"Member": f"{member} ({member.id})", "Duration": duration, "Moderator": ctx.author.mention, "Reason": reason}, self.color_warning)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot does not have sufficient permissions to timeout this member. Ensure the bot's role is higher.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ An error occurred while timing out: {e}", color=self.color_error))

    @commands.hybrid_command(name="removetimeout", aliases=["unmute"], description="Cabut status bungkam member")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="Member target")
    @commands.has_permissions(moderate_members=True)
    async def remove_timeout(self, ctx: commands.Context, member: discord.Member):
        if member.id == ctx.guild.owner.id: await ctx.send(embed=self._create_embed(description="❌ You cannot remove timeout for the server owner.", color=self.color_error)); return
        if member.id == self.bot.user.id: await ctx.send(embed=self._create_embed(description="❌ You cannot remove timeout for this bot itself.", color=self.color_error)); return
        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak dapat menghapus timeout anggota ini karena peran mereka sama atau lebih tinggi dari peran bot.", color=self.color_error)); return

        if not member.is_timed_out():
            await ctx.send(embed=self._create_embed(description=f"❌ {member.display_name} is not currently timed out.", color=self.color_error))
            return

        try:
            await member.timeout(None, reason=f"Timeout removed by {ctx.author}")
            await ctx.send(embed=self._create_embed(description=f"✅ Timeout for **{member.display_name}** has been removed.", color=self.color_success))
            await self.log_action(ctx.guild, "😊 Timeout Removed", {"Member": f"{member} ({member.id})", "Moderator": ctx.author.mention}, self.color_success)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot does not have sufficient permissions to remove timeout for this member. Ensure the bot's role is higher.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ An error occurred while removing timeout: {e}", color=self.color_error))

    @commands.hybrid_command(name="disconnect", aliases=["voicedisconnect", "vkick"], description="Keluarkan member dari Voice Channel")
    @app_commands.describe(member="Member yang ingin dikeluarkan dari Voice Channel", reason="Alasan disconnect")
    async def voice_disconnect(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Tidak ada alasan."):
        if member.id == ctx.guild.owner.id: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengeluarkan pemilik server.", color=self.color_error)); return
        if member.id == self.bot.user.id: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengeluarkan bot ini.", color=self.color_error)); return
        if member.guild_permissions.administrator: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengeluarkan Administrator.", color=self.color_error)); return
        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak dapat mengeluarkan anggota ini karena peran mereka lebih tinggi dari peran bot.", color=self.color_error)); return

        if not member.voice or not member.voice.channel:
            await ctx.send(embed=self._create_embed(description=f"❌ {member.display_name} sedang tidak berada di dalam Voice Channel mana pun.", color=self.color_error))
            return

        vc_name = member.voice.channel.name
        try:
            await member.move_to(None, reason=f"Disconnected by {ctx.author}: {reason}")
            
            if not ctx.author.guild_permissions.administrator:
                try:
                    dm_embed = discord.Embed(title=f"⚠️ Disconnected dari Voice Channel - {ctx.guild.name}", description=f"Anda telah dikeluarkan dari Voice Channel **{vc_name}** atas permintaan dari **{ctx.author.display_name}**.\n\n**Alasan:** {reason}\n\n*Anda dapat mengajukan banding atas aksi ini dengan mengirim DM ke admin/moderator server.*", color=0xFF0000)
                    await member.send(embed=dm_embed)
                except: pass

            await ctx.send(embed=self._create_embed(description=f"✅ **{member.display_name}** telah dikeluarkan dari Voice Channel **{vc_name}** oleh **{ctx.author.display_name}**.\n**Alasan:** {reason}", color=self.color_success))
            await self.log_action(ctx.guild, "📞 Voice Disconnect", {"Member": f"{member} ({member.id})", "Channel": vc_name, "Requester": ctx.author.mention, "Reason": reason}, self.color_warning)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin (Move Members) untuk mengeluarkan member ini dari Voice Channel.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan: {e}", color=self.color_error))
        
    @commands.hybrid_command(name="clear", aliases=["purge", "bersihkan"], description="Menghapus pesan dalam jumlah tertentu di channel teks atau voice.")
    @commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(amount="Jumlah pesan yang akan dihapus (1-100)", channel="Channel target (opsional, bisa Text/Voice/Thread)")
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx: commands.Context, amount: int, channel: Optional[discord.abc.GuildChannel] = None):
        if amount <= 0: await ctx.send(embed=self._create_embed(description="❌ Amount must be greater than 0.", color=self.color_error)); return
        if amount > 100: await ctx.send(embed=self._create_embed(description="❌ You can only delete a maximum of 100 messages at once.", color=self.color_error)); return

        target_channel = channel or ctx.channel
        if not hasattr(target_channel, "purge"):
            return await ctx.send(embed=self._create_embed(description="❌ Channel yang dipilih tidak mendukung fitur hapus pesan.", color=self.color_error), ephemeral=True)

        await ctx.defer(ephemeral=True)
        try:
            limit = amount if ctx.interaction else amount + 1
            deleted = await target_channel.purge(limit=limit)
            actual_deleted = len(deleted) if ctx.interaction else max(0, len(deleted) - 1)
            embed = self._create_embed(description=f"🗑️ Berhasil menghapus **{actual_deleted}** pesan di {target_channel.mention}.", color=self.color_success)
            await ctx.send(embed=embed, delete_after=5 if not ctx.interaction else None)
            
            if actual_deleted > 0:
                await self.log_action(ctx.guild, "🗑️ Messages Deleted", {"Channel": target_channel.mention, "Amount": f"{actual_deleted} messages", "Moderator": ctx.author.mention}, self.color_info)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin `Manage Messages` untuk menghapus pesan di channel ini.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat menghapus pesan: {e}", color=self.color_error))
        
    @commands.hybrid_command(name="slowmode", description="Atur batas waktu kirim pesan channel")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.describe(seconds="Waktu jeda dalam detik (0 untuk mematikan)")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, seconds: int):
        if seconds < 0: await ctx.send(embed=self._create_embed(description="❌ Slowmode duration cannot be negative.", color=self.color_error)); return
        if seconds > 21600: await ctx.send(embed=self._create_embed(description="❌ Slowmode duration cannot exceed 6 hours (21600 seconds).", color=self.color_error)); return

        try:
            await ctx.channel.edit(slowmode_delay=seconds)
            status = f"set to `{seconds}` seconds" if seconds > 0 else "disabled"
            await ctx.send(embed=self._create_embed(description=f"✅ Slowmode in this channel has been {status}.", color=self.color_success))
            await self.log_action(ctx.guild, "⏳ Slowmode Changed", {"Channel": ctx.channel.mention, "Duration": f"{seconds} seconds", "Moderator": ctx.author.mention}, self.color_info)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot does not have `Manage Channels` permission to set slowmode.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ An error occurred while setting slowmode: {e}", color=self.color_error))

    @commands.hybrid_command(name="lock", description="Kunci channel dari member biasa")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.describe(channel="Channel target (opsional)")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        target_channel = channel or ctx.channel
        current_perms = target_channel.permissions_for(ctx.guild.default_role)
        if not current_perms.send_messages is False:
            try:
                await target_channel.set_permissions(ctx.guild.default_role, send_messages=False)
                await ctx.send(embed=self._create_embed(description=f"🔒 Channel {target_channel.mention} has been locked.", color=self.color_success))
                await self.log_action(ctx.guild, "🔒 Channel Locked", {"Channel": target_channel.mention, "Moderator": ctx.author.mention}, self.color_warning)
            except discord.Forbidden:
                await ctx.send(embed=self._create_embed(description="❌ Bot does not have `Manage Channels` permission to lock the channel.", color=self.color_error))
            except Exception as e:
                await ctx.send(embed=self._create_embed(description=f"❌ An error occurred while locking the channel: {e}", color=self.color_error))
        else:
            await ctx.send(embed=self._create_embed(description=f"❌ Channel {target_channel.mention} is already locked.", color=self.color_error))

    @commands.hybrid_command(name="unlock", description="Buka kembali kunci channel")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.describe(channel="Channel target (opsional)")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        target_channel = channel or ctx.channel
        current_perms = target_channel.permissions_for(ctx.guild.default_role)
        if not current_perms.send_messages is True:
            try:
                await target_channel.set_permissions(ctx.guild.default_role, send_messages=None)
                await ctx.send(embed=self._create_embed(description=f"🔓 Channel {target_channel.mention} has been unlocked.", color=self.color_success))
                await self.log_action(ctx.guild, "🔓 Channel Unlocked", {"Channel": target_channel.mention, "Moderator": ctx.author.mention}, self.color_success)
            except discord.Forbidden:
                await ctx.send(embed=self._create_embed(description="❌ Bot does not have `Manage Channels` permission to unlock the channel.", color=self.color_error))
            except Exception as e:
                await ctx.send(embed=self._create_embed(description=f"❌ An error occurred while unlocking the channel: {e}", color=self.color_error))
        else:
            await ctx.send(embed=self._create_embed(description=f"❌ Channel {target_channel.mention} is already unlocked.", color=self.color_error))

    @commands.command(name="addrole")
    @commands.has_permissions(manage_roles=True)
    async def add_role(self, ctx, member: discord.Member, role: discord.Role):
        if ctx.author.top_role <= role:
            await ctx.send(embed=self._create_embed(description="❌ You cannot assign a role that is higher than or equal to your own role.", color=self.color_error))
            return
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send(embed=self._create_embed(description="❌ You cannot modify roles for a member with a higher or equal position.", color=self.color_error))
            return
        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak dapat menambahkan peran anggota ini karena peran mereka sama atau lebih tinggi dari peran bot.", color=self.color_error)); return
        if role in member.roles:
            await ctx.send(embed=self._create_embed(description=f"❌ {member.display_name} already has the role {role.mention}.", color=self.color_error))
            return
            
        try:
            await member.add_roles(role, reason=f"Assigned by {ctx.author}")
            await ctx.send(embed=self._create_embed(description=f"✅ Role {role.mention} has been given to {member.mention}.", color=self.color_success))
            await self.log_action(ctx.guild, "➕ Role Assigned", {"Member": member.mention, "Role": role.mention, "Moderator": ctx.author.mention}, self.color_info)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot does not have sufficient permissions to assign this role. Ensure the bot's role is higher than the role to be assigned.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ An error occurred while assigning the role: {e}", color=self.color_error))

    @commands.command(name="removerole")
    @commands.has_permissions(manage_roles=True)
    async def remove_role(self, ctx, member: discord.Member, role: discord.Role):
        if ctx.author.top_role <= role:
            await ctx.send(embed=self._create_embed(description="❌ You cannot remove a role that is higher than or equal to your own role.", color=self.color_error))
            return
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send(embed=self._create_embed(description="❌ You cannot modify roles for a member with a higher or equal position.", color=self.color_error))
            return
        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak dapat menghapus peran anggota ini karena peran mereka sama atau lebih tinggi dari peran bot.", color=self.color_error)); return
        if role not in member.roles:
            await ctx.send(embed=self._create_embed(description=f"❌ {member.display_name} does not have the role {role.mention}.", color=self.color_error))
            return
            
        try:
            await member.remove_roles(role, reason=f"Removed by {ctx.author}")
            await ctx.send(embed=self._create_embed(description=f"✅ Role {role.mention} has been removed from {member.mention}.", color=self.color_success))
            await self.log_action(ctx.guild, "➖ Role Removed", {"Member": member.mention, "Role": role.mention, "Moderator": ctx.author.mention}, self.color_info)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot does not have sufficient permissions to remove this role. Ensure the bot's role is higher than the role to be removed.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ An error occurred while removing the role: {e}", color=self.color_error))

    @commands.command(name="nick")
    @commands.has_permissions(manage_nicknames=True)
    async def nick(self, ctx, member: discord.Member, *, new_nickname: Optional[str] = None):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send(embed=self._create_embed(description="❌ You cannot change the nickname of a member with an equal or higher role.", color=self.color_error))
            return
        if member.id == ctx.guild.owner.id:
            await ctx.send(embed=self._create_embed(description="❌ You cannot change the nickname of the server owner.", color=self.color_error)); return
        if member.id == self.bot.user.id:
            await ctx.send(embed=self._create_embed(description="❌ You cannot change the nickname of this bot itself.", color=self.color_error)); return
        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak dapat mengubah nickname anggota ini karena peran mereka sama atau lebih tinggi dari peran bot.", color=self.color_error)); return

        old_nickname = member.display_name
        try:
            await member.edit(nick=new_nickname, reason=f"Changed by {ctx.author}")
            if new_nickname:
                await ctx.send(embed=self._create_embed(description=f"✅ Nickname **{old_nickname}** has been changed to **{new_nickname}**.", color=self.color_success))
                await self.log_action(ctx.guild, "👤 Nickname Changed", {"Member": member.mention, "From": old_nickname, "To": new_nickname, "Moderator": ctx.author.mention}, self.color_info)
            else:
                await ctx.send(embed=self._create_embed(description=f"✅ Nickname for **{old_nickname}** has been reset.", color=self.color_success))
                await self.log_action(ctx.guild, "👤 Nickname Reset", {"Member": member.mention, "Moderator": ctx.author.mention}, self.color_info)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot does not have sufficient permissions to change this nickname. Ensure the bot's role is higher than this member.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ An error occurred while changing nickname: {e}", color=self.color_error))

    @commands.command(name="channelrules", aliases=["cr"])
    @commands.has_permissions(manage_channels=True)
    async def channel_rules(self, ctx, channel: Optional[discord.TextChannel] = None):
        target_channel = channel or ctx.channel
        class ChannelRuleView(discord.ui.View):
            def __init__(self, cog_instance, author, target_channel):
                super().__init__(timeout=300)
                self.cog, self.author, self.target_channel = cog_instance, author, target_channel
                self.guild_id, self.channel_id = target_channel.guild.id, target_channel.id
                self.message = None
                self.update_buttons()

            def update_buttons(self):
                rules = self.cog.get_channel_rules(self.guild_id, self.channel_id)
                def set_button_state(button, label_text, is_active):
                    button.label = f"{label_text}: {'Aktif' if is_active else 'Nonaktif'}"
                    button.style = discord.ButtonStyle.green if is_active else discord.ButtonStyle.red
                
                self.clear_items()
                
                self.toggle_bots = discord.ui.Button(emoji="🛡️", row=0)
                self.toggle_bots.callback = lambda i: self.toggle_rule(i, "disallow_bots")
                set_button_state(self.toggle_bots, "Dilarang Bot", rules.get("disallow_bots", False))
                self.add_item(self.toggle_bots)

                self.toggle_media = discord.ui.Button(emoji="🖼️", row=0)
                self.toggle_media.callback = lambda i: self.toggle_rule(i, "disallow_media")
                set_button_state(self.toggle_media, "Dilarang Media", rules.get("disallow_media", False))
                self.add_item(self.toggle_media)

                self.toggle_prefix = discord.ui.Button(emoji="❗", row=0)
                self.toggle_prefix.callback = lambda i: self.toggle_rule(i, "disallow_prefix")
                set_button_state(self.toggle_prefix, "Dilarang Prefix", rules.get("disallow_prefix", False))
                self.add_item(self.toggle_prefix)

                self.toggle_url = discord.ui.Button(emoji="🔗", row=1)
                self.toggle_url.callback = lambda i: self.toggle_rule(i, "disallow_url")
                set_button_state(self.toggle_url, "Dilarang URL", rules.get("disallow_url", False))
                self.add_item(self.toggle_url)
                
                self.toggle_auto_delete = discord.ui.Button(emoji="⏳", row=1)
                self.toggle_auto_delete.callback = lambda i: self.set_auto_delete(i)
                delay = rules.get("auto_delete_seconds", 0)
                self.toggle_auto_delete.label = f"Hapus Otomatis: {delay}s" if delay > 0 else "Hapus Otomatis: Nonaktif"
                self.toggle_auto_delete.style = discord.ButtonStyle.green if delay > 0 else discord.ButtonStyle.red
                self.add_item(self.toggle_auto_delete)

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                if interaction.user != self.author:
                    await interaction.response.send_message("Hanya pengguna yang memulai perintah yang dapat berinteraksi.", ephemeral=True)
                    return False
                if not interaction.user.guild_permissions.manage_channels:
                    await interaction.response.send_message("Anda tidak memiliki izin `Manage Channels` untuk mengubah aturan ini.", ephemeral=True)
                    return False
                return True

            async def toggle_rule(self, interaction: discord.Interaction, rule_name: str):
                rules = self.cog.get_channel_rules(self.guild_id, self.channel_id)
                rules[rule_name] = not rules.get(rule_name, False)
                self.cog.save_settings()
                self.update_buttons()
                await interaction.response.edit_message(view=self)
                await self.cog.log_action(
                    self.target_channel.guild,
                    "🔧 Channel Rule Changed",
                    {"Channel": self.target_channel.mention, f"Rule '{rule_name}'": "Enabled" if rules[rule_name] else "Disabled", "Moderator": interaction.user.mention},
                    self.cog.color_info
                )

            async def set_auto_delete(self, interaction: discord.Interaction):
                class AutoDeleteModal(discord.ui.Modal, title="Set Auto-Delete"):
                    def __init__(self, current_delay, parent_view_instance):
                        super().__init__()
                        self.cog = parent_view_instance.cog
                        self.guild_id = parent_view_instance.guild_id
                        self.channel_id = parent_view_instance.channel_id
                        self.parent_view = parent_view_instance

                        self.delay_input = discord.ui.TextInput(
                            label="Duration (seconds, 0 to disable)",
                            placeholder="Example: 30 (max 3600)",
                            default=str(current_delay),
                            max_length=4
                        )
                        self.add_item(self.delay_input)

                    async def on_submit(self, modal_interaction: discord.Interaction):
                        await modal_interaction.response.defer(ephemeral=True)
                        try:
                            delay = int(self.delay_input.value)
                            if not (0 <= delay <= 3600):
                                await modal_interaction.followup.send(embed=self.cog._create_embed(description="❌ Duration must be between 0 and 3600 seconds (1 hour).", color=self.cog.color_error), ephemeral=True)
                                return
                            
                            rules = self.cog.get_channel_rules(self.guild_id, self.channel_id)
                            rules["auto_delete_seconds"] = delay
                            self.cog.save_settings()
                            
                            self.parent_view.update_buttons()
                            await modal_interaction.message.edit(view=self.parent_view)
                            
                            await self.cog.log_action(
                                self.parent_view.target_channel.guild,
                                "⏳ Auto-Delete Changed",
                                {"Channel": self.parent_view.target_channel.mention, "Duration": f"{delay} seconds" if delay > 0 else "Disabled", "Moderator": modal_interaction.user.mention},
                                self.cog.color_info
                            )
                        except ValueError:
                            await modal_interaction.followup.send(embed=self.cog._create_embed(description="❌ Duration must be a number.", color=self.cog.color_error), ephemeral=True)
                        except Exception as e:
                            await modal_interaction.followup.send(embed=self.cog._create_embed(description=f"❌ An error occurred: {e}", color=self.cog.color_error), ephemeral=True)
                
                rules = self.cog.get_channel_rules(self.guild_id, self.channel_id)
                current_delay = rules.get("auto_delete_seconds", 0)
                await interaction.response.send_modal(AutoDeleteModal(current_delay, self))

        embed = self._create_embed(title=f"🔧 Rules for Channel: #{target_channel.name}", description="Press buttons to enable (green) or disable (red) rules for this channel. Press the auto-delete button to set its duration (default 30s).", color=self.color_info)
        view_instance = ChannelRuleView(self, ctx.author, target_channel)
        view_instance.message = await ctx.send(embed=embed, view=view_instance)

    @commands.hybrid_command(name="setwelcomechannel", description="Atur channel untuk ucapan selamat datang")
    @app_commands.describe(channel="Channel text untuk welcome message")
    @commands.has_permissions(manage_guild=True)
    async def set_welcome_channel(self, ctx, channel: discord.TextChannel):
        guild_settings = self.get_guild_settings(ctx.guild.id)
        guild_settings["welcome_channel_id"] = channel.id
        self.save_settings()
        embed = self._create_embed(
            description=f"✅ Welcome channel successfully set to {channel.mention}.",
            color=self.color_success
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="setspamlog", description="Atur channel log khusus untuk sistem anti-spam & jebakan")
    @app_commands.describe(channel="Channel text untuk log anti-spam")
    @commands.has_permissions(manage_guild=True)
    async def set_spamlog_channel(self, ctx, channel: discord.TextChannel):
        guild_settings = self.get_guild_settings(ctx.guild.id)
        guild_settings["spam_log_channel_id"] = channel.id
        self.save_settings()
        embed = self._create_embed(
            description=f"✅ Channel Log Anti-Spam berhasil diatur ke {channel.mention}.",
            color=self.color_success
        )
        await ctx.send(embed=embed)
        
    @commands.command(name="addwhitelistrole")
    @commands.has_permissions(manage_roles=True)
    async def add_whitelist_role(self, ctx, role_id: int):
        guild_settings = self.get_guild_settings(ctx.guild.id)
        if "spam_whitelist_roles" not in guild_settings:
            guild_settings["spam_whitelist_roles"] = []
        if role_id in guild_settings["spam_whitelist_roles"]:
            await ctx.send(embed=self._create_embed(description="❌ Peran ini sudah ada di daftar whitelist.", color=self.color_error))
            return
        
        role = ctx.guild.get_role(role_id)
        if not role:
            await ctx.send(embed=self._create_embed(description="❌ ID peran tidak valid.", color=self.color_error))
            return
            
        guild_settings["spam_whitelist_roles"].append(role_id)
        self.save_settings()
        await ctx.send(embed=self._create_embed(description=f"✅ Peran {role.mention} telah ditambahkan ke whitelist spam.", color=self.color_success))

    @commands.command(name="removewhitelistrole")
    @commands.has_permissions(manage_roles=True)
    async def remove_whitelist_role(self, ctx, role_id: int):
        guild_settings = self.get_guild_settings(ctx.guild.id)
        if "spam_whitelist_roles" not in guild_settings or role_id not in guild_settings["spam_whitelist_roles"]:
            await ctx.send(embed=self._create_embed(description="❌ Peran ini tidak ada di daftar whitelist.", color=self.color_error))
            return
            
        guild_settings["spam_whitelist_roles"].remove(role_id)
        self.save_settings()
        role = ctx.guild.get_role(role_id)
        role_mention = role.mention if role else str(role_id)
        await ctx.send(embed=self._create_embed(description=f"✅ Peran {role_mention} telah dihapus dari whitelist spam.", color=self.color_success))

    @commands.command(name="setreactionrole")
    @commands.has_permissions(manage_roles=True)
    async def set_reaction_role(self, ctx, message: discord.Message, emoji: str, role: discord.Role):
        if ctx.author.top_role <= role:
            return await ctx.send(embed=self._create_embed(description="❌ You cannot set a reaction role for a role higher than or equal to your own.", color=self.color_error))
        
        guild_settings = self.get_guild_settings(ctx.guild.id)
        message_id_str = str(message.id)
        if message_id_str not in guild_settings["reaction_roles"]: guild_settings["reaction_roles"][message_id_str] = {}
        guild_settings["reaction_roles"][message_id_str][emoji] = role.id
        self.save_settings()
        try:
            await message.add_reaction(emoji)
            await ctx.send(embed=self._create_embed(description=f"✅ Role **{role.mention}** will be given for {emoji} reaction on [that message]({message.jump_url}).", color=self.color_success))
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot does not have permission to add reactions or set roles. Ensure all permissions are complete.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ An error occurred: {e}", color=self.color_error))

    async def handle_ticket_open(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user
        guild_settings = self.get_guild_settings(guild.id)
        
        existing = discord.utils.get(guild.text_channels, name=f"ticket-{user.name.lower()}")
        if existing:
            return await interaction.followup.send(f"❌ Anda sudah memiliki tiket yang aktif: {existing.mention}", ephemeral=True)
            
        cat_id = guild_settings.get("ticket_category_id")
        category = guild.get_channel(cat_id) if cat_id else None
        
        support_role_id = guild_settings.get("ticket_support_role_id")
        if support_role_id:
            support_role = guild.get_role(support_role_id)
        else:
            env_role_id = int(os.getenv("TICKET_SUPPORT_ROLE_ID", 1264935423184998422))
            support_role = guild.get_role(env_role_id)
            
        if not support_role:
            support_role = next((r for r in guild.roles if r.permissions.manage_channels or r.permissions.administrator), None)
            
        ow = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True)
        }
        if support_role:
            ow[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            
        try:
            tc = await guild.create_text_channel(
                f"ticket-{user.name.lower()}",
                overwrites=ow,
                category=category,
                topic=f"Tiket Bantuan untuk {user.name} (ID: {user.id})"
            )
        except Exception as e:
            return await interaction.followup.send(f"❌ Gagal membuat kanal tiket: {e}", ephemeral=True)
            
        from cogs.v2_layout import build_v2_card, send_v2_message
        close_view = GlobalTicketCloseView(self)
        card = build_v2_card(
            title=f"🎫 Tiket Bantuan • {user.display_name}",
            description=(
                f"Halo {user.mention}, selamat datang di kanal dukungan pribadi Anda!\n\n"
                "Silakan sampaikan pertanyaan, kendala, atau kebutuhan Anda dengan jelas dan lengkap.\n"
                "Tim staf kami telah diberi tahu dan akan segera merespons Anda secepatnya."
            ),
            fields=[
                {"name": "👤 Pembuat Tiket", "value": f"{user.mention} (`{user.id}`)"},
                {"name": "🛡️ Tim Staf Siaga", "value": support_role.mention if support_role else "`Staf / Admin`"},
                {"name": "💡 Panduan Penggunaan Tiket", "value": "• Sampaikan kronologi atau pertanyaan secara detail.\n• Lampirkan tangkapan layar/bukti pendukung jika ada.\n• Jangan melakukan spam tag staf.\n• Klik tombol **Tutup Tiket** di bawah jika urusan telah selesai."}
            ],
            color=0x2ECC71,
            footer="RTM-Bot Ticket System • Klik tombol Tutup Tiket di bawah jika urusan telah selesai"
        )
        
        staff_ping = support_role.mention if support_role else ""
        components = [card, *close_view.to_components()]
        resp = await send_v2_message(self.bot, tc.id, components)
        if not resp or "id" not in resp:
            embed = discord.Embed(
                title=f"🎫 Tiket Bantuan • {user.display_name}",
                description=(
                    f"Halo {user.mention}! Silakan jelaskan kebutuhan Anda di sini.\n"
                    "Tim staf kami akan segera membantu Anda."
                ),
                color=0x2ECC71
            )
            embed.add_field(name="👤 Pembuat Tiket", value=f"{user.mention} (`{user.id}`)", inline=True)
            embed.add_field(name="🛡️ Tim Staf", value=support_role.mention if support_role else "`Staf / Admin`", inline=True)
            embed.add_field(name="💡 Panduan", value="Sampaikan keluhan dengan jelas, lalu klik Tutup Tiket jika selesai.", inline=False)
            embed.set_footer(text="Klik tombol Tutup Tiket di bawah jika urusan telah selesai.")
            await tc.send(content=f"{user.mention} {staff_ping}", embed=embed, view=close_view)

        else:
            register_view(self.bot, close_view, message_id=int(resp["id"]))
            if staff_ping:
                await tc.send(f"{user.mention} {staff_ping}", delete_after=5)
                
        await interaction.followup.send(f"✅ Tiket Anda berhasil dibuka di {tc.mention}!", ephemeral=True)

    async def handle_ticket_close(self, interaction: discord.Interaction):
        channel = interaction.channel
        guild = interaction.guild
        user = interaction.user
        
        is_staff = user.guild_permissions.manage_channels or user.guild_permissions.administrator
        is_creator = False
        if channel.topic and str(user.id) in channel.topic:
            is_creator = True
        elif channel.name.startswith("ticket-") and user.name.lower() in channel.name:
            is_creator = True
            
        if not is_creator and not is_staff:
            return await interaction.response.send_message("❌ Anda tidak memiliki izin untuk menutup tiket ini.", ephemeral=True)
            
        await interaction.response.send_message("🔒 Tiket akan ditutup dan dihapus dalam 5 detik...")
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Tiket ditutup oleh {user.display_name}")
        except Exception:
            pass

    @commands.hybrid_command(name="setup", aliases=["settings", "setupserver"], description="Buka Master Server Control Center untuk konfigurasi terpadu")
    @commands.has_permissions(manage_guild=True)
    async def setup(self, ctx: commands.Context):
        view_instance = MasterSetupDashboardView(self, ctx.guild, ctx.author)
        settings = self.get_guild_settings(ctx.guild.id)
        auto_r = ctx.guild.get_role(settings.get("auto_role_id")) if settings.get("auto_role_id") else None
        welcome_c = ctx.guild.get_channel(settings.get("welcome_channel_id")) if settings.get("welcome_channel_id") else None
        boost_c = ctx.guild.get_channel(settings.get("boost_channel_id")) if settings.get("boost_channel_id") else None
        ticket_cat = ctx.guild.get_channel(settings.get("ticket_category_id")) if settings.get("ticket_category_id") else None
        ticket_role = ctx.guild.get_role(settings.get("ticket_support_role_id")) if settings.get("ticket_support_role_id") else None

        role_txt = auto_r.name if auto_r else "Belum diatur"
        welcome_txt = f"#{welcome_c.name}" if welcome_c else "Belum diatur"
        boost_status = "Aktif" if settings.get("boost_enabled", True) else "Nonaktif"
        boost_txt = f"#{boost_c.name} ({boost_status})" if boost_c else "Belum diatur"

        ticket_parts = []
        if ticket_cat:
            ticket_parts.append(f"Kategori: {ticket_cat.name}")
        if ticket_role:
            ticket_parts.append(f"Staf: @{ticket_role.name}")
        ticket_txt = " • ".join(ticket_parts) if ticket_parts else "Belum diatur"

        card = build_v2_card(
            title=f"⚙️ Master Server Control Center • {ctx.guild.name}",
            description=(
                "**Pusat Kendali Administrasi & Otomatisasi Komunitas**\n\n"
                "Pilih modul konfigurasi pada menu di bawah untuk mengelola sistem server secara langsung. "
                "Seluruh perubahan disimpan dan diterapkan secara instan."
            ),
            fields=[
                {"name": "👤 Auto Role & Sambutan", "value": f"`Role: {role_txt}` • `Kanal: {welcome_txt}`"},
                {"name": "🚀 Notifikasi Server Booster", "value": f"`{boost_txt}`"},
                {"name": "🎫 Sistem Layanan Tiket", "value": f"`{ticket_txt}`"},
                {"name": "🎭 Pengambilan Peran Mandiri", "value": "`Konfigurasi Panel Self-Role Interaktif`"}
            ],
            color=self.color_info,
            footer="RTM-Bot • Pilih modul pengaturan pada menu di bawah ini"
        )
        components = [card, *view_instance.to_components()]
        resp = await send_v2_message(self.bot, ctx.channel.id, components)
        if not resp or "id" not in resp:
            embed = self._create_embed(
                title=f"⚙️ Master Server Control Center • {ctx.guild.name}",
                description="Pilih modul yang ingin Anda konfigurasi dari menu dropdown di bawah ini:",
                color=self.color_info,
                author_name=ctx.guild.name,
                author_icon_url=ctx.guild.icon.url if ctx.guild.icon else ""
            )
            await ctx.send(embed=embed, view=view_instance)
        else:
            register_view(self.bot, view_instance, message_id=int(resp["id"]))


    @commands.hybrid_command(name="panelrole", description="Studio panel ambil role mandiri: buat baru, kelola role & atur seleksi")
    @commands.has_permissions(manage_guild=True)
    async def panelrole(self, ctx: commands.Context):
        view = RolePanelDashboardView(self, ctx.guild, ctx.author)
        embed = view.build_dashboard_embed()
        await ctx.send(embed=embed, view=view, ephemeral=True)

    @commands.hybrid_command(name="ticket", aliases=["tiket", "setupticket"], description="Buka panel konfigurasi atau pasang panel tiket bantuan")
    @commands.has_permissions(manage_guild=True)
    async def ticket(self, ctx: commands.Context):
        view = TicketSetupView(self, ctx.guild, ctx.author)
        embed = self._create_embed(
            title="🎫 Pengaturan Sistem Tiket Bantuan Server",
            description=(
                "Atur sistem tiket bantuan server dengan 3 langkah mudah:\n\n"
                "1. **Pilih Kategori Kanal** tempat kanal tiket privat akan dibuat.\n"
                "2. **Pilih Role Staf / Support** yang dapat melihat dan menjawab tiket.\n"
                "3. **Pilih Kanal Target** dan klik **Pasang Panel Tiket**."
            ),
            color=0x2ECC71
        )
        await ctx.send(embed=embed, view=view, ephemeral=True)


    @commands.hybrid_command(name="announce", aliases=["pengumuman", "broadcast"], description="Kirim pengumuman langsung via modal (Mendukung Webhook, Polling & Voice Channel)")
    @app_commands.describe(channel_identifier="Tag channel, ID, atau nama channel (Teks / Voice)")
    @commands.has_permissions(manage_guild=True)
    async def announce(self, ctx, channel_identifier: str):
        target_channel = None

        if channel_identifier.startswith('<#') and channel_identifier.endswith('>'):
            try:
                channel_id = int(channel_identifier[2:-1])
                target_channel = ctx.guild.get_channel(channel_id) or self.bot.get_channel(channel_id)
            except ValueError:
                pass
        
        if not target_channel and channel_identifier.isdigit():
            try:
                channel_id = int(channel_identifier)
                target_channel = ctx.guild.get_channel(channel_id) or self.bot.get_channel(channel_id)
            except ValueError:
                pass
        
        if not target_channel:
            target_channel = discord.utils.get(ctx.guild.channels, name=channel_identifier.lower().replace('#', ''))

        valid_channel_types = (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread)
        if not target_channel or not isinstance(target_channel, valid_channel_types):
            await ctx.send(embed=self._create_embed(
                description=f"❌ Channel '{channel_identifier}' tidak ditemukan atau tidak mendukung pesan. Mohon gunakan mention channel (`#general` atau channel voice) atau ID channel yang benar.",
                color=self.color_error
            ))
            return
        
        view_instance = AnnounceButtonView(self.bot, self, ctx, target_channel)
        initial_msg = await ctx.send(embed=self._create_embed(
            title="🔔 Siap Membuat Pengumuman?",
            description=f"Anda akan membuat pengumuman di channel {target_channel.mention}.\nTekan tombol di bawah untuk mengaktifkan mention `@everyone`, Polling, dan membuka formulir untuk mengisi teks pengumuman langsung. Anda memiliki **60 detik**.",
            color=self.color_info),
            view=view_instance
        )
        view_instance.message = initial_msg
        
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        try:
            if interaction.type == discord.InteractionType.component and interaction.data:
                custom_id = interaction.data.get("custom_id", "")
                if custom_id == "disabled_trap_counter":
                    await interaction.response.send_message("🔨 Fitur ini berjalan otomatis. Anda tidak perlu mengklik tombol ini.", ephemeral=True)
                    return
                if custom_id.startswith("roleselect_") or custom_id.startswith("rolebtn_"):
                    if not interaction.response.is_done():
                        await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
    
    @tasks.loop(minutes=1)
    async def update_panel_task(self):
        for guild in self.bot.guilds:
            await self.update_panel(guild)
    
    async def update_panel(self, guild: discord.Guild):
        guild_settings = self.get_guild_settings(guild.id)
        panel_id = guild_settings.get('mod_panel_message_id')
        channel_id = guild_settings.get('mod_panel_channel_id')

        if not panel_id or not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            return

        try:
            panel_message = await channel.fetch_message(panel_id)
        except discord.NotFound:
            guild_settings['mod_panel_message_id'] = None
            self.save_settings()
            
            await self.create_mod_panel_if_needed(guild)
            return
        
        except (discord.Forbidden, discord.errors.DiscordServerError, aiohttp.ClientError, asyncio.TimeoutError) as e:
            return
        except Exception as e:
            return

        total_members = len(guild.members)
        bot_members = sum(1 for member in guild.members if member.bot)
        human_members = total_members - bot_members
        total_channels = len(guild.channels)
        
        status_data = load_data(self.status_file)
        current_status = status_data.get("status", "online")
        
        if current_status == "online":
            status_emoji = '🟢'
            status_text = 'Online & Berjalan'
        else:
            status_emoji = '🔴'
            status_text = 'Offline / DnD'

        from cogs.v2_layout import build_v2_card, edit_v2_message
        
        v2_fields = self._build_modpanel_fields(guild, guild_settings, total_members, human_members, bot_members, total_channels, status_emoji, status_text)
                
        card = build_v2_card(
            title=f"🛡️ Moderator Control Panel - {guild.name}",
            description="Statistik real-time mengenai status server dan anggota.",
            fields=v2_fields,
            color=None,
            buttons=self.modpanel_buttons,
            footer=f"Terakhir diperbarui: {datetime.now(WIB).strftime('%d/%m/%Y %H:%M:%S')} WIB"
        )
        
        try:
            from cogs.v2_layout import edit_v2_message
            resp = await edit_v2_message(self.bot, channel.id, panel_message.id, [card])
            if resp is None:
                try: await panel_message.delete()
                except: pass
                guild_settings['mod_panel_message_id'] = None
                self.save_settings()
                await self.create_mod_panel_if_needed(guild)
        except discord.Forbidden:
            pass
        except Exception as e:
            print(f"Error updating mod panel V2: {e}")

    def _build_modpanel_fields(self, guild: discord.Guild, guild_settings: dict, total_members: int, human_members: int, bot_members: int, total_channels: int, status_emoji: str, status_text: str) -> list:
        fields = [
            {
                "name": "📊 Statistik Server", 
                "value": f"👥 **Member:** `{total_members}` (🧍 `{human_members}` | 🤖 `{bot_members}`)\n📁 **Channel:** `{total_channels}`"
            },
            {
                "name": "🌐 Status Sistem", 
                "value": f"{status_emoji} **{status_text}**"
            }
        ]
        
        voice_members_count = sum(len(vc.members) for vc in guild.voice_channels)
        busy_vc = max(guild.voice_channels, key=lambda vc: len(vc.members), default=None) if guild.voice_channels else None
        busy_text = f"Teramai: **{busy_vc.name}** (`{len(busy_vc.members)}` member)" if (busy_vc and len(busy_vc.members) > 0) else "Status: *Hening*"
        fields.append({
            "name": "🎙️ Voice Pulse",
            "value": f"🔊 **Aktif di Voice:** `{voice_members_count}` member\n📍 {busy_text}"
        })
        
        now_utc = datetime.now(timezone.utc)
        timed_out_count = sum(1 for m in guild.members if m.timed_out_until and m.timed_out_until > now_utc)
        trap_count = len(guild_settings.get("trigger_channels", []))
        trap_status = f"`{trap_count}` aktif" if trap_count > 0 else "Nonaktif"
        fields.append({
            "name": "🛡️ Keamanan & Moderasi",
            "value": f"⏳ **Timeout Aktif:** `{timed_out_count}` member\n🪤 **Honeypot Trap:** {trap_status}"
        })
        
        return fields

    async def create_mod_panel_if_needed(self, guild: discord.Guild):
        guild_settings = self.get_guild_settings(guild.id)
        panel_id = guild_settings.get('mod_panel_message_id')
        channel_id = guild_settings.get('mod_panel_channel_id')
        
        if not panel_id and channel_id:
            channel = guild.get_channel(channel_id)
            if channel and channel.permissions_for(guild.me).send_messages:
                total_members = len(guild.members)
                bot_members = sum(1 for member in guild.members if member.bot)
                human_members = total_members - bot_members
                total_channels = len(guild.channels)

                status_data = load_data(self.status_file)
                current_status = status_data.get("status", "online")
                
                if current_status == "online":
                    status_emoji = '🟢'
                    status_text = 'Online & Berjalan'
                else:
                    status_emoji = '🔴'
                    status_text = 'Offline / DnD'

                from cogs.v2_layout import build_v2_card, send_v2_message
                
                v2_fields = self._build_modpanel_fields(guild, guild_settings, total_members, human_members, bot_members, total_channels, status_emoji, status_text)
                
                card = build_v2_card(
                    title=f"🛡️ Moderator Control Panel - {guild.name}",
                    description="Statistik real-time mengenai status server dan anggota.",
                    fields=v2_fields,
                    color=None,
                    buttons=self.modpanel_buttons,
                    footer=f"Terakhir diperbarui: {datetime.now(WIB).strftime('%d/%m/%Y %H:%M:%S')} WIB"
                )
                
                response = await send_v2_message(self.bot, channel.id, [card])
                if not response: return
                
                guild_settings['mod_panel_message_id'] = int(response['id'])
                guild_settings['mod_panel_channel_id'] = channel.id
                self.save_settings()

    @commands.hybrid_command(name="modpanel", description="Membuat panel statistik dan moderasi server.")
    @commands.has_permissions(manage_guild=True)
    async def modpanel(self, ctx: commands.Context):
        try:
            guild_settings = self.get_guild_settings(ctx.guild.id)
            panel_id = guild_settings.get('mod_panel_message_id')
            channel_id = guild_settings.get('mod_panel_channel_id')

            if panel_id and channel_id:
                try:
                    channel = ctx.guild.get_channel(channel_id)
                    if channel:
                        await channel.fetch_message(panel_id)
                        await ctx.send(embed=self._create_embed(description="❌ Panel moderasi sudah ada. Hapus pesan panel lama untuk membuat yang baru.", color=self.color_error), ephemeral=True)
                        return
                except discord.NotFound:
                    guild_settings['mod_panel_message_id'] = None
                    guild_settings['mod_panel_channel_id'] = None
                    self.save_settings()
                except discord.Forbidden:
                    await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin untuk mengakses channel panel lama. Silakan minta admin server untuk mengatasinya.", color=self.color_error), ephemeral=True)
                    return

            total_members = len(ctx.guild.members)
            bot_members = sum(1 for member in ctx.guild.members if member.bot)
            human_members = total_members - bot_members
            total_channels = len(ctx.guild.channels)
            
            status_data = load_data(self.status_file)
            current_status = status_data.get("status", "online")
            
            if current_status == "online":
                status_emoji = '🟢'
                status_text = 'Online & Berjalan'
            else:
                status_emoji = '🔴'
                status_text = 'Offline / DnD'
            
            from cogs.v2_layout import build_v2_card, send_v2_message
            
            v2_fields = self._build_modpanel_fields(ctx.guild, guild_settings, total_members, human_members, bot_members, total_channels, status_emoji, status_text)
            
            card = build_v2_card(
                title=f"🛡️ Moderator Control Panel - {ctx.guild.name}",
                description="Statistik real-time mengenai status server dan anggota.",
                fields=v2_fields,
                color=self.color_info,
                buttons=self.modpanel_buttons,
                footer=f"Terakhir diperbarui: {datetime.now(WIB).strftime('%d/%m/%Y %H:%M:%S')} WIB"
            )
            
            response = await send_v2_message(self.bot, ctx.channel.id, [card])
            if response:
                guild_settings['mod_panel_message_id'] = int(response['id'])
                guild_settings['mod_panel_channel_id'] = ctx.channel.id
                self.save_settings()
            

        except discord.Forbidden:
            await ctx.author.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin `Send Messages` dan `Embed Links` di channel tersebut. Silakan minta admin server untuk memberikan izin yang sesuai.", color=self.color_error))

        except Exception as e:
            await ctx.author.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan tak terduga: {e}", color=self.color_error))

    @commands.command(name="toggle_status")
    @commands.has_permissions(manage_guild=True)
    async def toggle_status(self, ctx):
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
            
        status_data = load_data(self.status_file)
        current_status = status_data.get("status", "online")

        if current_status == "online":
            status_data["status"] = "dnd"
            self.status["status"] = "dnd"
            self.save_status()
            await ctx.send(embed=self._create_embed(description="✅ Status panel bot berhasil diubah menjadi **Offline/Do Not Disturb**.", color=self.color_success), ephemeral=True)
        else:
            status_data["status"] = "online"
            self.status["status"] = "online"
            self.save_status()
            await ctx.send(embed=self._create_embed(description="✅ Status panel bot berhasil diubah menjadi **Online**.", color=self.color_success), ephemeral=True)
        
        await self.update_panel(ctx.guild)
    
    class ModPanelModal(discord.ui.Modal):
        def __init__(self, cog_instance, title):
            super().__init__(title=title)
            self.cog = cog_instance

    class WarnModal(ModPanelModal):
        def __init__(self, cog_instance):
            super().__init__(cog_instance, title="Peringatkan Pengguna")
            self.user_id = discord.ui.TextInput(
                label="ID atau username#tag",
                placeholder="Contoh: 123456789012345678 atau John#1234",
                required=True
            )
            self.reason = discord.ui.TextInput(
                label="Alasan Peringatan",
                placeholder="Contoh: Spam link di channel #general",
                style=discord.TextStyle.paragraph,
                required=True
            )
            self.add_item(self.user_id)
            self.add_item(self.reason)

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                member_id_or_name = self.user_id.value.strip()
                reason = self.reason.value.strip()
                member = await self.cog.fetch_member_from_id_or_name(interaction.guild, member_id_or_name)
                
                if member is None:
                    return await interaction.followup.send("❌ Pengguna tidak ditemukan.", ephemeral=True)
                
                warnings_list = self.cog.warnings.get(str(member.guild.id), {}).get(str(member.id), [])
                warning_count = len(warnings_list)
                
                await self.cog.warn_from_modal(interaction, member, reason)
                
                if warning_count > 0:
                     await interaction.followup.send(f"✅ {member.display_name} telah diberi peringatan. Total peringatan: **{warning_count + 1}**.", ephemeral=True)
                else:
                    await interaction.followup.send(f"✅ {member.display_name} telah diberi peringatan. Ini adalah peringatan pertama mereka.", ephemeral=True)
                
            except Exception as e:
                await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

    class TimeoutModal(ModPanelModal):
        def __init__(self, cog_instance):
            super().__init__(cog_instance, title="Beri Timeout Pengguna")
            self.user_id = discord.ui.TextInput(
                label="ID atau username#tag",
                placeholder="Contoh: 123456789012345678 atau John#1234",
                required=True
            )
            self.duration = discord.ui.TextInput(
                label="Durasi (misal: 10m, 1h, 2d)",
                placeholder="Contoh: 30m (30 menit)",
                required=True
            )
            self.reason = discord.ui.TextInput(
                label="Alasan Timeout",
                placeholder="Contoh: Pelanggaran peraturan",
                required=False,
                style=discord.TextStyle.paragraph
            )
            self.add_item(self.user_id)
            self.add_item(self.duration)
            self.add_item(self.reason)
        
        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                member_id_or_name = self.user_id.value.strip()
                duration = self.duration.value.strip()
                reason = self.reason.value.strip() or "No reason provided."

                member = await self.cog.fetch_member_from_id_or_name(interaction.guild, member_id_or_name)

                if member is None:
                    return await interaction.followup.send("❌ Pengguna tidak ditemukan.", ephemeral=True)
                
                await self.cog.timeout_from_modal(interaction, member, duration, reason)
            except Exception as e:
                await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

    class KickModal(ModPanelModal):
        def __init__(self, cog_instance):
            super().__init__(cog_instance, title="Tendang Pengguna")
            self.user_id = discord.ui.TextInput(
                label="ID atau username#tag",
                placeholder="Contoh: 123456789012345678 atau John#1234",
                required=True
            )
            self.reason = discord.ui.TextInput(
                label="Alasan Kick",
                placeholder="Contoh: Melanggar peraturan berulang kali",
                required=False,
                style=discord.TextStyle.paragraph
            )
            self.add_item(self.user_id)
            self.add_item(self.reason)
        
        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                member_id_or_name = self.user_id.value.strip()
                reason = self.reason.value.strip() or "No reason provided."
                
                member = await self.cog.fetch_member_from_id_or_name(interaction.guild, member_id_or_name)
                
                if member is None:
                    return await interaction.followup.send("❌ Pengguna tidak ditemukan.", ephemeral=True)

                await self.cog.kick_from_modal(interaction, member, reason)
            except Exception as e:
                await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

    class BanModal(ModPanelModal):
        def __init__(self, cog_instance):
            super().__init__(cog_instance, title="Blokir Pengguna")
            self.user_id = discord.ui.TextInput(
                label="ID atau username#tag",
                placeholder="Contoh: 123456789012345678 atau John#1234",
                required=True
            )
            self.reason = discord.ui.TextInput(
                label="Alasan Ban",
                placeholder="Contoh: Pelanggaran berat",
                required=False,
                style=discord.TextStyle.paragraph
            )
            self.add_item(self.user_id)
            self.add_item(self.reason)
        
        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                member_id_or_name = self.user_id.value.strip()
                reason = self.reason.value.strip() or "No reason provided."

                member = await self.cog.fetch_member_from_id_or_name(interaction.guild, member_id_or_name)

                if member is None:
                    return await interaction.followup.send("❌ Pengguna tidak ditemukan.", ephemeral=True)
                
                await self.cog.ban_from_modal(interaction, member, reason)
            except Exception as e:
                await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

    class ClearModal(ModPanelModal):
        def __init__(self, cog_instance):
            super().__init__(cog_instance, title="Hapus Pesan")
            self.amount = discord.ui.TextInput(
                label="Jumlah Pesan (1-100)",
                placeholder="Contoh: 10",
                required=True
            )
            self.channel_id = discord.ui.TextInput(
                label="Channel ID (Opsional)",
                placeholder="ID channel target (kosongkan untuk channel ini)",
                required=False
            )
            self.add_item(self.amount)
            self.add_item(self.channel_id)
        
        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                amount = int(self.amount.value.strip())
                if amount <= 0 or amount > 100:
                    return await interaction.followup.send("❌ Jumlah harus antara 1 dan 100.", ephemeral=True)

                channel_id_str = self.channel_id.value.strip()
                target_channel = interaction.channel
                if channel_id_str:
                    target_channel = interaction.guild.get_channel(int(channel_id_str))
                    if not target_channel or not hasattr(target_channel, 'purge'):
                        return await interaction.followup.send("❌ Channel ID tidak valid atau tidak mendukung fitur hapus pesan.", ephemeral=True)
                
                if not hasattr(target_channel, 'purge'):
                    return await interaction.followup.send("❌ Channel ini tidak mendukung fitur hapus pesan.", ephemeral=True)

                deleted = await target_channel.purge(limit=amount)
                
                await self.cog.clear_from_modal(interaction, target_channel, len(deleted))
            except ValueError:
                await interaction.followup.send("❌ Masukkan angka yang valid.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

    class UnbanModal(ModPanelModal):
        def __init__(self, cog_instance):
            super().__init__(cog_instance, title="Cabut Ban Pengguna")
            self.user_identifier = discord.ui.TextInput(
                label="ID atau username#tag",
                placeholder="Contoh: 123456789012345678 atau John#1234",
                required=True
            )
            self.reason = discord.ui.TextInput(
                label="Alasan Pencabutan Ban",
                placeholder="Contoh: Kesalahan administrasi",
                required=False,
                style=discord.TextStyle.paragraph
            )
            self.add_item(self.user_identifier)
            self.add_item(self.reason)

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                user_identifier = self.user_identifier.value.strip()
                reason = self.reason.value.strip() or "No reason provided."

                user_to_unban = None
                try:
                    user_id = int(user_identifier)
                    temp_user = await self.cog.bot.fetch_user(user_id)
                    user_to_unban = temp_user
                except ValueError:
                    for entry in [entry async for entry in interaction.guild.bans()]:
                        if str(entry.user).lower() == user_identifier.lower():
                            user_to_unban = entry.user
                            break
                except discord.NotFound:
                    pass

                if user_to_unban is None:
                    return await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ User `{user_identifier}` not found in ban list or invalid ID/Name#Tag.", color=self.cog.color_error), ephemeral=True)
                
                await self.cog.unban_from_modal(interaction, user_to_unban, reason)
            except Exception as e:
                await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

    class UnwarnModal(ModPanelModal):
        def __init__(self, cog_instance):
            super().__init__(cog_instance, title="Cabut Peringatan Pengguna")
            self.user_id = discord.ui.TextInput(
                label="ID atau username#tag",
                placeholder="Contoh: 123456789012345678 atau John#1234",
                required=True
            )
            self.warning_index = discord.ui.TextInput(
                label="Nomor Peringatan",
                placeholder="Contoh: 1 (Gunakan !warnings untuk melihat nomor)",
                required=True
            )
            self.reason = discord.ui.TextInput(
                label="Alasan Pencabutan Peringatan",
                placeholder="Contoh: Kesalahan administrasi",
                required=False,
                style=discord.TextStyle.paragraph
            )
            self.add_item(self.user_id)
            self.add_item(self.warning_index)
            self.add_item(self.reason)

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                member_id_or_name = self.user_id.value.strip()
                warning_index = int(self.warning_index.value.strip())
                reason = self.reason.value.strip() or "Admin error."

                member = await self.cog.fetch_member_from_id_or_name(interaction.guild, member_id_or_name)
                
                if member is None:
                    return await interaction.followup.send("❌ Pengguna tidak ditemukan.", ephemeral=True)
                
                await self.cog.unwarn_from_modal(interaction, member, warning_index, reason)
            except ValueError:
                await interaction.followup.send("❌ Nomor peringatan harus berupa angka.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)
    
    class RemoveTimeoutModal(ModPanelModal):
        def __init__(self, cog_instance):
            super().__init__(cog_instance, title="Cabut Timeout Pengguna")
            self.user_id = discord.ui.TextInput(
                label="ID atau username#tag",
                placeholder="Contoh: 123456789012345678 atau John#1234",
                required=True
            )
            self.add_item(self.user_id)
        
        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                member_id_or_name = self.user_id.value.strip()
                member = await self.cog.fetch_member_from_id_or_name(interaction.guild, member_id_or_name)
                
                if member is None:
                    return await interaction.followup.send("❌ Pengguna tidak ditemukan.", ephemeral=True)

                await self.cog.remove_timeout_from_modal(interaction, member)
            except Exception as e:
                await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

    class LockModal(ModPanelModal):
        def __init__(self, cog_instance):
            super().__init__(cog_instance, title="Kunci Channel")
            self.channel_id = discord.ui.TextInput(
                label="Channel ID (Opsional)",
                placeholder="ID channel target (kosongkan untuk channel ini)",
                required=False
            )
            self.add_item(self.channel_id)
        
        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                channel_id_str = self.channel_id.value.strip()
                target_channel = interaction.channel
                if channel_id_str:
                    target_channel = interaction.guild.get_channel(int(channel_id_str))
                    if not target_channel or not isinstance(target_channel, discord.TextChannel):
                        return await interaction.followup.send("❌ Channel ID tidak valid.", ephemeral=True)

                current_perms = target_channel.permissions_for(interaction.guild.default_role)
                if not current_perms.send_messages is False:
                    await target_channel.set_permissions(interaction.guild.default_role, send_messages=False)
                    await interaction.followup.send(embed=self.cog._create_embed(description=f"🔒 Channel {target_channel.mention} telah dikunci.", color=self.cog.color_success), ephemeral=True)
                    await self.cog.log_action(interaction.guild, "🔒 Channel Locked", {"Channel": target_channel.mention, "Moderator": interaction.user.mention}, self.cog.color_warning)
                else:
                    await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Channel {target_channel.mention} sudah terkunci.", color=self.cog.color_error), ephemeral=True)

            except Exception as e:
                await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

    class UnlockModal(ModPanelModal):
        def __init__(self, cog_instance):
            super().__init__(cog_instance, title="Buka Kunci Channel")
            self.channel_id = discord.ui.TextInput(
                label="Channel ID (Opsional)",
                placeholder="ID channel target (kosongkan untuk channel ini)",
                required=False
            )
            self.add_item(self.channel_id)
        
        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                channel_id_str = self.channel_id.value.strip()
                target_channel = interaction.channel
                if channel_id_str:
                    target_channel = interaction.guild.get_channel(int(channel_id_str))
                    if not target_channel or not isinstance(target_channel, discord.TextChannel):
                        return await interaction.followup.send("❌ Channel ID tidak valid.", ephemeral=True)

                current_perms = target_channel.permissions_for(interaction.guild.default_role)
                if not current_perms.send_messages is True:
                    await target_channel.set_permissions(interaction.guild.default_role, send_messages=None)
                    await interaction.followup.send(embed=self.cog._create_embed(description=f"🔓 Channel {target_channel.mention} telah dibuka kuncinya.", color=self.cog.color_success), ephemeral=True)
                    await self.cog.log_action(interaction.guild, "🔓 Channel Unlocked", {"Channel": target_channel.mention, "Moderator": interaction.user.mention}, self.cog.color_success)
                else:
                    await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Channel {target_channel.mention} sudah tidak terkunci.", color=self.cog.color_error), ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)


    async def fetch_member_from_id_or_name(self, guild, identifier):
        try:
            return await guild.fetch_member(int(identifier))
        except (ValueError, discord.NotFound):
            return guild.get_member_named(identifier)

    @commands.hybrid_command(name="remove_modpanel", description="Menghapus panel moderasi saat ini dari channel.")
    @commands.has_permissions(manage_guild=True)
    async def remove_modpanel(self, ctx: commands.Context):
        guild_settings = self.get_guild_settings(ctx.guild.id)
        panel_id = guild_settings.get('mod_panel_message_id')
        channel_id = guild_settings.get('mod_panel_channel_id')
        
        if panel_id and channel_id:
            try:
                channel = ctx.guild.get_channel(channel_id)
                if channel:
                    message = await channel.fetch_message(panel_id)
                    await message.delete()
            except Exception:
                pass
            
            guild_settings['mod_panel_message_id'] = None
            guild_settings['mod_panel_channel_id'] = None
            self.save_settings()
            await ctx.send("✅ Panel moderasi berhasil dihapus dan dinonaktifkan.", ephemeral=True)
        else:
            await ctx.send("⚠️ Tidak ada panel moderasi aktif di server ini.", ephemeral=True)

    class RealtimeModPanelView(discord.ui.View):
        def __init__(self, cog_instance):
            super().__init__(timeout=None)
            self.cog = cog_instance
            self.add_buttons()

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message("❌ Anda harus memiliki izin `Manage Server` untuk menggunakan tombol moderasi ini.", ephemeral=True)
                return False
            return True

        def add_buttons(self):
            warn_button = discord.ui.Button(label="Warn", style=discord.ButtonStyle.secondary, emoji="⚠️", row=0, custom_id="modpanel_warn")
            warn_button.callback = self.warn_user_callback
            self.add_item(warn_button)

            timeout_button = discord.ui.Button(label="Timeout", style=discord.ButtonStyle.primary, emoji="⏳", row=0, custom_id="modpanel_timeout")
            timeout_button.callback = self.timeout_user_callback
            self.add_item(timeout_button)

            kick_button = discord.ui.Button(label="Kick", style=discord.ButtonStyle.danger, emoji="👢", row=0, custom_id="modpanel_kick")
            kick_button.callback = self.kick_user_callback
            self.add_item(kick_button)

            ban_button = discord.ui.Button(label="Ban", style=discord.ButtonStyle.danger, emoji="🔨", row=0, custom_id="modpanel_ban")
            ban_button.callback = self.ban_user_callback
            self.add_item(ban_button)
            
            unwarn_button = discord.ui.Button(label="Unwarn", style=discord.ButtonStyle.success, emoji="🛡️", row=1, custom_id="modpanel_unwarn")
            unwarn_button.callback = self.unwarn_user_callback
            self.add_item(unwarn_button)

            remove_timeout_button = discord.ui.Button(label="Untimeout", style=discord.ButtonStyle.success, emoji="⏱️", row=1, custom_id="modpanel_untimeout")
            remove_timeout_button.callback = self.remove_timeout_callback
            self.add_item(remove_timeout_button)

            unban_button = discord.ui.Button(label="Unban", style=discord.ButtonStyle.success, emoji="🤝", row=1, custom_id="modpanel_unban")
            unban_button.callback = self.unban_user_callback
            self.add_item(unban_button)

            clear_button = discord.ui.Button(label="Clear Chat", style=discord.ButtonStyle.danger, emoji="🧹", row=2, custom_id="modpanel_clear")
            clear_button.callback = self.clear_messages_callback
            self.add_item(clear_button)

            self.lock_button = discord.ui.Button(label="Lock", style=discord.ButtonStyle.danger, emoji="🔒", row=2, custom_id="modpanel_lock")
            self.lock_button.callback = self.lock_channel_callback
            self.add_item(self.lock_button)

            self.unlock_button = discord.ui.Button(label="Unlock", style=discord.ButtonStyle.success, emoji="🔓", row=2, custom_id="modpanel_unlock")
            self.unlock_button.callback = self.unlock_channel_callback
            self.add_item(self.unlock_button)

        async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
            await interaction.response.send_message(f"❌ Terjadi kesalahan: {error}", ephemeral=True)

        async def warn_user_callback(self, interaction: discord.Interaction):
            if not interaction.user.guild_permissions.kick_members:
                return await interaction.response.send_message("❌ Anda tidak memiliki izin `Kick Members`.", ephemeral=True)
            await interaction.response.send_modal(self.cog.WarnModal(self.cog))

        async def timeout_user_callback(self, interaction: discord.Interaction):
            if not interaction.user.guild_permissions.moderate_members:
                return await interaction.response.send_message("❌ Anda tidak memiliki izin `Moderate Members`.", ephemeral=True)
            await interaction.response.send_modal(self.cog.TimeoutModal(self.cog))

        async def kick_user_callback(self, interaction: discord.Interaction):
            if not interaction.user.guild_permissions.kick_members:
                return await interaction.response.send_message("❌ Anda tidak memiliki izin `Kick Members`.", ephemeral=True)
            await interaction.response.send_modal(self.cog.KickModal(self.cog))

        async def ban_user_callback(self, interaction: discord.Interaction):
            if not interaction.user.guild_permissions.ban_members:
                return await interaction.response.send_message("❌ Anda tidak memiliki izin `Ban Members`.", ephemeral=True)
            await interaction.response.send_modal(self.cog.BanModal(self.cog))

        async def unban_user_callback(self, interaction: discord.Interaction):
            if not interaction.user.guild_permissions.ban_members:
                return await interaction.response.send_message("❌ Anda tidak memiliki izin `Ban Members`.", ephemeral=True)
            await interaction.response.send_modal(self.cog.UnbanModal(self.cog))

        async def unwarn_user_callback(self, interaction: discord.Interaction):
            if not interaction.user.guild_permissions.kick_members:
                return await interaction.response.send_message("❌ Anda tidak memiliki izin `Kick Members`.", ephemeral=True)
            await interaction.response.send_modal(self.cog.UnwarnModal(self.cog))
        
        async def remove_timeout_callback(self, interaction: discord.Interaction):
            if not interaction.user.guild_permissions.moderate_members:
                return await interaction.response.send_message("❌ Anda tidak memiliki izin `Moderate Members`.", ephemeral=True)
            await interaction.response.send_modal(self.cog.RemoveTimeoutModal(self.cog))

        async def clear_messages_callback(self, interaction: discord.Interaction):
            if not interaction.user.guild_permissions.manage_messages:
                return await interaction.response.send_message("❌ Anda tidak memiliki izin `Manage Messages`.", ephemeral=True)
            await interaction.response.send_modal(self.cog.ClearModal(self.cog))

        async def lock_channel_callback(self, interaction: discord.Interaction):
            if not interaction.user.guild_permissions.manage_channels:
                return await interaction.response.send_message("❌ Anda tidak memiliki izin `Manage Channels`.", ephemeral=True)
            
            target_channel = interaction.channel
            modal = self.cog.LockModal(self.cog)
            await interaction.response.send_modal(modal)

        async def unlock_channel_callback(self, interaction: discord.Interaction):
            if not interaction.user.guild_permissions.manage_channels:
                return await interaction.response.send_message("❌ Anda tidak memiliki izin `Manage Channels`.", ephemeral=True)
            
            target_channel = interaction.channel
            modal = self.cog.UnlockModal(self.cog)
            await interaction.response.send_modal(modal)
    
    async def warn_from_modal(self, interaction, member, reason):
        timestamp = int(time.time())
        warning_data = {
            "moderator_id": interaction.user.id,
            "timestamp": timestamp,
            "reason": reason
        }
        guild_id_str = str(interaction.guild.id)
        member_id_str = str(member.id)

        self.warnings.setdefault(guild_id_str, {}).setdefault(member_id_str, []).append(warning_data)
        self.save_warnings()

        try:
            dm_embed = self._create_embed(title=f"🚨 You Received a Warning in {interaction.guild.name}", color=self.color_warning)
            dm_embed.add_field(name="Warning Reason", value=reason, inline=False)
            dm_embed.set_footer(text=f"Warning issued by {interaction.user.display_name}")
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        await self.check_and_escalate_warnings(interaction.guild, member, interaction.user)
    
    async def timeout_from_modal(self, interaction, member, duration, reason):
        delta = parse_duration(duration)
        if not delta: 
            await interaction.followup.send(embed=self._create_embed(description="❌ Invalid duration format. Use `s`, `m`, `h`, `d`. Example: `10m`.", color=self.color_error), ephemeral=True)
            return
        if delta.total_seconds() > 2419200:
            await interaction.followup.send(embed=self._create_embed(description="❌ Timeout duration cannot exceed 28 days.", color=self.color_error), ephemeral=True)
            return
        
        try:
            await member.timeout(delta, reason=reason)
            await self.increment_timeout_counter()
            await interaction.followup.send(embed=self._create_embed(description=f"✅ **{member.display_name}** has been timed out for `{duration}`.", color=self.color_success), ephemeral=True)
            await self.log_action(interaction.guild, "🤫 Member Timeout", {"Member": f"{member} ({member.id})", "Duration": duration, "Moderator": interaction.user.mention, "Reason": reason}, self.color_warning)
        except discord.Forbidden:
            await interaction.followup.send(embed=self._create_embed(description="❌ Bot does not have sufficient permissions to timeout this member. Ensure the bot's role is higher.", color=self.color_error), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=self._create_embed(description=f"❌ An error occurred while timing out: {e}", color=self.color_error), ephemeral=True)
            
    async def kick_from_modal(self, interaction, member, reason):
        try:
            await member.kick(reason=reason)
            await interaction.followup.send(embed=self._create_embed(description=f"✅ **{member.display_name}** has been kicked.", color=self.color_success), ephemeral=True)
            await self.log_action(interaction.guild, "👢 Member Kicked", {"Member": f"{member} ({member.id})", "Moderator": interaction.user.mention, "Reason": reason}, self.color_warning)
        except discord.Forbidden:
            await interaction.followup.send(embed=self._create_embed(description="❌ Bot does not have sufficient permissions to kick this member. Ensure the bot's role is higher.", color=self.color_error), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=self._create_embed(description=f"❌ An error occurred while kicking the member: {e}", color=self.color_error), ephemeral=True)
            
    async def ban_from_modal(self, interaction, member, reason):
        try:
            await member.ban(reason=reason)
            await interaction.followup.send(embed=self._create_embed(description=f"✅ **{member.display_name}** has been banned.", color=self.color_success), ephemeral=True)
            await self.log_action(interaction.guild, "🔨 Member Banned", {"Member": f"{member} ({member.id})", "Moderator": interaction.user.mention, "Reason": reason}, self.color_error)
        except discord.Forbidden:
            await interaction.followup.send(embed=self._create_embed(description="❌ Bot does not have sufficient permissions to ban this member. Ensure the bot's role is higher.", color=self.color_error), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=self._create_embed(description=f"❌ An error occurred while banning the member: {e}", color=self.color_error), ephemeral=True)
            
    async def unban_from_modal(self, interaction, user, reason):
        try:
            await interaction.guild.unban(user, reason=reason)
            await interaction.followup.send(embed=self._create_embed(description=f"✅ Ban for **{user}** has been lifted.", color=self.color_success), ephemeral=True)
            await self.log_action(interaction.guild, "🤝 Ban Lifted", {"User": f"{user} ({user.id})", "Moderator": interaction.user.mention, "Reason": reason}, self.color_success)
        except discord.Forbidden:
            await interaction.followup.send(embed=self._create_embed(description="❌ Bot does not have sufficient permissions to unban this member.", color=self.color_error), ephemeral=True)
        except discord.NotFound:
            await interaction.followup.send(embed=self._create_embed(description=f"❌ User `{user}` not found in ban list.", color=self.color_error), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=self._create_embed(description=f"❌ An error occurred while unbanning: {e}", color=self.color_error), ephemeral=True)

    async def unwarn_from_modal(self, interaction, member, warning_index, reason):
        guild_id_str = str(interaction.guild.id)
        member_id_str = str(member.id)
        
        user_warnings = self.warnings.get(guild_id_str, {}).get(member_id_str, [])
        
        if not user_warnings:
            await interaction.followup.send(embed=self._create_embed(description=f"❌ **{member.display_name}** has no warnings.", color=self.color_error), ephemeral=True)
            return

        if not (0 < warning_index <= len(user_warnings)):
            await interaction.followup.send(embed=self._create_embed(description=f"❌ Invalid warning index. Use `!warnings {member.display_name}` to see the warning list.", color=self.color_error), ephemeral=True)
            return
        
        removed_warning = self.warnings[guild_id_str][member_id_str].pop(warning_index - 1)
        self.save_warnings()
        
        await interaction.followup.send(embed=self._create_embed(description=f"✅ Warning #{warning_index} for **{member.display_name}** has been removed.", color=self.color_success), ephemeral=True)
        
        log_fields = {
            "Member": f"{member} ({member.id})",
            "Moderator": interaction.user.mention,
            "Reason for Removal": reason,
            "Removed Warning": f"`{removed_warning['reason']}`"
        }
        await self.log_action(interaction.guild, "👍 Warning Removed", log_fields, self.color_success)

    async def remove_timeout_from_modal(self, interaction, member):
        if not member.is_timed_out():
            await interaction.followup.send(embed=self._create_embed(description=f"❌ {member.display_name} is not currently timed out.", color=self.color_error), ephemeral=True)
            return

        try:
            await member.timeout(None, reason=f"Timeout removed by {interaction.user.display_name}")
            await interaction.followup.send(embed=self._create_embed(description=f"✅ Timeout for **{member.display_name}** has been removed.", color=self.color_success), ephemeral=True)
            await self.log_action(interaction.guild, "😊 Timeout Removed", {"Member": f"{member} ({member.id})", "Moderator": interaction.user.mention}, self.color_success)
        except discord.Forbidden:
            await interaction.followup.send(embed=self._create_embed(description="❌ Bot does not have sufficient permissions to remove timeout for this member. Ensure the bot's role is higher.", color=self.color_error), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=self._create_embed(description=f"❌ An error occurred while removing timeout: {e}", color=self.color_error), ephemeral=True)


    async def clear_from_modal(self, interaction, target_channel, deleted_count):
        embed = self._create_embed(description=f"🗑️ Successfully deleted **{deleted_count}** messages from {target_channel.mention}.", color=self.color_success)
        await interaction.followup.send(embed=embed, ephemeral=True)
        await self.log_action(interaction.guild, "🗑️ Messages Deleted", {"Channel": target_channel.mention, "Amount": f"{deleted_count} messages", "Moderator": interaction.user.mention}, self.color_info)
    
    @commands.hybrid_command(name="trap", aliases=["setjebakan", "triggerchannel"], description="Set atau hapus channel sebagai jebakan anti-spam (Honey-pot).")
    @app_commands.describe(action="Pilih 'add' untuk tambah, 'remove' untuk hapus jebakan", channel="Channel target")
    @commands.has_permissions(manage_guild=True)
    async def trap(self, ctx: commands.Context, action: str, channel: discord.TextChannel = None):
        action = action.lower()
        if action not in ["add", "remove"]:
            return await ctx.send("❌ Opsi tidak valid. Gunakan `add` atau `remove`.", ephemeral=True)
            
        target_channel = channel or ctx.channel
        guild_settings = self.get_guild_settings(ctx.guild.id)
        trigger_channels = guild_settings.get("trigger_channels", [])
        
        if action == "add":
            if target_channel.id in trigger_channels:
                return await ctx.send(f"⚠️ Channel {target_channel.mention} sudah menjadi Trigger Channel.", ephemeral=True)
            trigger_channels.append(target_channel.id)
            guild_settings["trigger_channels"] = trigger_channels
            self.save_settings()
            await ctx.send(embed=self._create_embed(description=f"✅ Channel {target_channel.mention} telah berhasil diatur sebagai jebakan anti-spam (Trap Channel).", color=self.color_success))
            
            from cogs.v2_layout import build_v2_card, send_v2_message
            
            global_count = self.settings.get("global_trap_count", 30)
            buttons = [
                {
                    "type": 2,
                    "style": 4,
                    "label": f"Timeouts count: {global_count}",
                    "custom_id": "disabled_trap_counter",
                    "disabled": True,
                    "emoji": {"name": "🔨"}
                }
            ]
            
            card = build_v2_card(
                title="🚨 PERINGATAN KERAS / WARNING 🚨",
                description="**JANGAN MENGIRIM PESAN DI CHANNEL INI**\n**DO NOT SEND MESSAGES IN THIS CHANNEL**\n\nChannel ini khusus untuk mendeteksi spam & phishing. Setiap pesan yang Anda kirim di sini akan mengakibatkan sanksi **Timeout Otomatis 28 Hari**.\n\n*This channel is strictly for spam & phishing detection, any messages sent here will result in an immediate 28-day timeout.*\n\nMohon patuhi peraturan server yang ada untuk menghindari sanksi dari sistem otomatis kami.",
                color=None,
                buttons=buttons
            )
            
            try:
                msg_data = await send_v2_message(self.bot, target_channel.id, [card])
                if msg_data and "id" in msg_data:
                    guild_settings[f"trap_msg_{target_channel.id}"] = int(msg_data["id"])
                    
                    if "global_trap_count" not in self.settings:
                        self.settings["global_trap_count"] = 30
                    self.save_settings()
            except Exception as e:
                print(f"Failed to send trap message: {e}")
            
        elif action == "remove":
            if target_channel.id not in trigger_channels:
                return await ctx.send(f"⚠️ Channel {target_channel.mention} bukan Trigger Channel.", ephemeral=True)
            trigger_channels.remove(target_channel.id)
            guild_settings["trigger_channels"] = trigger_channels
            self.save_settings()
            await ctx.send(embed=self._create_embed(description=f"✅ Channel {target_channel.mention} telah dihapus dari daftar jebakan anti-spam.", color=self.color_success))

async def setup(bot):
    cog = SentinelGuard(bot)
    await bot.add_cog(cog)
    bot.add_view(cog.RealtimeModPanelView(cog))
