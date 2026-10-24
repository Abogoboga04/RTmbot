import discord
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, Literal
import json
import re
import os
import asyncio
import urllib.parse
import yt_dlp
import functools
import uuid
import aiohttp
import datetime
from functools import partial
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

from dotenv import load_dotenv 
import base64
import tempfile

load_dotenv()

API_KEYS = []
default_key = os.getenv("GOOGLE_API_KEY")
if default_key:
    API_KEYS.append(default_key)

for i in range(1, 10):
    extra_key = os.getenv(f"GOOGLE_API_KEY_{i}")
    if extra_key and extra_key not in API_KEYS:
        API_KEYS.append(extra_key)

current_key_idx = 0

def configure_genai():
    global current_key_idx
    if API_KEYS:
        genai.configure(api_key=API_KEYS[current_key_idx])

def rotate_api_key():
    global current_key_idx
    if len(API_KEYS) > 1:
        current_key_idx = (current_key_idx + 1) % len(API_KEYS)
        configure_genai()
        return True
    return False

configure_genai()

def _get_youtube_video_id(url):
    if not url: return None
    url = url.replace('\\', '')
    youtube_regex = r'(?:https?:\/\/)?(?:[a-zA-Z0-9-]+\.)?(?:youtube(?:-nocookie)?\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=|watch\?.*&v=|live\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(youtube_regex, url)
    return match.group(1) if match else None

import pytubefix
import emoji

def _extract_youtube_info(url, cookiefile_path=None):
    clean_url = url.replace('\\', '').strip()
    video_id = _get_youtube_video_id(clean_url)
    default_thumb = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg" if video_id else None

    title = None
    description = ""
    thumbnail_url = default_thumb
    channel_name = None

    import requests
    import json
    import re

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        r_html = requests.get(clean_url, headers=headers, timeout=6)
        if r_html.status_code == 200:
            html = r_html.text
            match = re.search(r'ytInitialPlayerResponse\s*=\s*({.+?});', html)
            if not match:
                match = re.search(r'var ytInitialPlayerResponse\s*=\s*({.+?});(?:var|</script>)', html)
            if match:
                try:
                    data = json.loads(match.group(1))
                    details = data.get('videoDetails', {})
                    raw_title = details.get('title')
                    if raw_title:
                        title = " ".join(emoji.replace_emoji(raw_title, replace='').split())
                    desc = details.get('shortDescription')
                    if desc:
                        description = desc
                    if details.get('author'):
                        channel_name = details.get('author')
                    thumbs = details.get('thumbnail', {}).get('thumbnails', [])
                    if thumbs:
                        thumbnail_url = thumbs[-1].get('url', thumbnail_url)
                except Exception:
                    pass
    except Exception:
        pass

    if not title or not channel_name:
        try:
            r = requests.get(f"https://www.youtube.com/oembed?url={clean_url}&format=json", timeout=5)
            if r.status_code == 200:
                data = r.json()
                raw_title = data.get('title', '')
                if not raw_title and "html" in data:
                    t_match = re.search(r'title=["\'](.*?)["\']', data["html"])
                    if t_match:
                        raw_title = t_match.group(1)
                if raw_title and not title:
                    title = " ".join(emoji.replace_emoji(raw_title, replace='').split())
                if data.get('author_name') and not channel_name:
                    channel_name = data.get('author_name')
                if data.get('thumbnail_url') and not thumbnail_url:
                    thumbnail_url = data.get('thumbnail_url')
        except Exception:
            pass

    if not title:
        try:
            yt = pytubefix.YouTube(clean_url, client='WEB')
            raw_title = yt.title if yt.title else ""
            if raw_title:
                title = " ".join(emoji.replace_emoji(raw_title, replace='').split())
            if yt.description and not description:
                description = yt.description
            if yt.thumbnail_url and not thumbnail_url:
                thumbnail_url = yt.thumbnail_url
            if yt.author and not channel_name:
                channel_name = yt.author
        except Exception:
            pass

    if not title:
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'cachedir': '.yt-dlp-cache',
                'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(clean_url, download=False)
                raw_title = info.get('title', '')
                if raw_title:
                    title = " ".join(emoji.replace_emoji(raw_title, replace='').split())
                if info.get('description') and not description:
                    description = info.get('description')
                if info.get('uploader') and not channel_name:
                    channel_name = info.get('uploader')
                if info.get('thumbnail') and not thumbnail_url:
                    thumbnail_url = info.get('thumbnail')
        except Exception:
            pass

    return title, description, thumbnail_url, clean_url, channel_name


def _extract_tiktok_info(url):
    clean_url = url.replace('\\', '').strip()
    title = None
    description = ""
    thumbnail_url = None
    creator = None
    video_id = None

    import requests

    try:
        encoded_url = urllib.parse.quote(clean_url, safe="")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        r = requests.get(f"https://www.tikwm.com/api/?url={encoded_url}", headers=headers, timeout=8)
        if r.status_code == 200:
            res_json = r.json()
            if res_json.get("code") == 0 and res_json.get("data"):
                d = res_json["data"]
                video_id = str(d.get("id") or "")
                raw_title = d.get("title") or ""
                if raw_title:
                    title = " ".join(emoji.replace_emoji(raw_title, replace='').split())
                    description = title
                creator = d.get("author", {}).get("unique_id") or d.get("author", {}).get("nickname") or ""
                thumbnail_url = d.get("cover") or d.get("origin_cover")
    except Exception:
        pass

    if not title or not thumbnail_url:
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'socket_timeout': 8,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(clean_url, download=False)
                if info:
                    if not title:
                        raw_title = info.get("title") or ""
                        if raw_title:
                            title = " ".join(emoji.replace_emoji(raw_title, replace='').split())
                            description = title
                    if not creator:
                        creator = info.get("uploader") or info.get("creator") or ""
                    if not thumbnail_url:
                        thumbnail_url = info.get("thumbnail")
                    if not video_id:
                        video_id = str(info.get("id") or "")
        except Exception:
            pass

    return title, description, thumbnail_url, clean_url, creator


def _extract_instagram_info(url):
    clean_url = url.replace('\\', '').strip()
    title = None
    description = ""
    thumbnail_url = None
    creator = None
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'socket_timeout': 8,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            if info:
                raw_title = info.get("title") or info.get("description") or ""
                if raw_title:
                    title = " ".join(emoji.replace_emoji(raw_title, replace='').split())
                    description = title
                creator = info.get("uploader") or info.get("channel") or ""
                thumbnail_url = info.get("thumbnail")
    except Exception:
        pass
    return title, description, thumbnail_url, clean_url, creator



TYPE_LABELS = {
    "live": "Live Streaming YouTube",
    "upload": "Video Baru YouTube",
    "premier": "Premiere YouTube",
    "tiktok": "Video TikTok",
    "tiktok_live": "TikTok Live",
    "instagram": "Post atau Reels Instagram",
    "instagram_live": "Instagram Live",
}

class NotifFormatEditorModal(discord.ui.Modal, title="Format Notifikasi Jalur"):
    def __init__(self, cog, path_id: str, type_key: str, parent_view):
        super().__init__()
        self.cog = cog
        self.path_id = path_id
        self.type_key = type_key
        self.parent_view = parent_view

        path_data = cog.config.get("notification_paths", {}).get(path_id, {})
        custom_msgs = path_data.get("custom_messages", {})
        msg_cfg = custom_msgs.get(type_key) or cog.default_messages.get(type_key, {})

        current_content = msg_cfg.get("content") or "@everyone {ai_hype}"
        current_title = msg_cfg.get("title") or "[{judul}]({url})"
        current_desc = msg_cfg.get("description") or "{deskripsi} {url}"
        current_btn = msg_cfg.get("button_label") or "Tonton Konten"

        self.content_input = discord.ui.TextInput(
            label="Isi Pesan Biasa (Gunakan {ai_hype} untuk AI)",
            style=discord.TextStyle.paragraph,
            default=current_content,
            required=False,
            max_length=2000
        )
        self.title_input = discord.ui.TextInput(
            label="Judul Utama [{judul}]({url})",
            style=discord.TextStyle.short,
            default=current_title,
            required=False,
            max_length=256
        )
        self.desc_input = discord.ui.TextInput(
            label="Deskripsi Utama ({deskripsi})",
            style=discord.TextStyle.paragraph,
            default=current_desc,
            required=False,
            max_length=2000
        )
        self.btn_input = discord.ui.TextInput(
            label="Label Tombol Tautan",
            style=discord.TextStyle.short,
            default=current_btn,
            required=False,
            max_length=80
        )

        self.add_item(self.content_input)
        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        self.add_item(self.btn_input)

    async def on_submit(self, interaction: discord.Interaction):
        path_data = self.cog.config.get("notification_paths", {}).get(self.path_id)
        if not path_data:
            return await interaction.response.send_message("Jalur notifikasi tidak ditemukan.", ephemeral=True)
        if "custom_messages" not in path_data:
            path_data["custom_messages"] = {}
        if self.type_key not in path_data["custom_messages"]:
            path_data["custom_messages"][self.type_key] = self.cog.default_messages.get(self.type_key, {}).copy()

        cfg = path_data["custom_messages"][self.type_key]
        cfg["content"] = self.content_input.value.strip() or "@everyone {ai_hype}"

        raw_title = self.title_input.value.strip() or "[{judul}]({url})"
        clean_title = emoji.replace_emoji(raw_title, replace="").strip()
        clean_title = re.sub(r"\[\s+", "[", clean_title)
        clean_title = re.sub(r"\s+\]", "]", clean_title)
        cfg["title"] = clean_title

        cfg["description"] = self.desc_input.value.strip() or "{deskripsi}"
        cfg["button_label"] = self.btn_input.value.strip() or "Tonton Konten"

        self.cog.save_config()
        self.parent_view._update_items()
        await interaction.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view)


class ContentRadarStudioView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, initial_path_id: Optional[str] = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.selected_path_id = initial_path_id
        self.selected_type_key = "live"

        available_paths = self._get_guild_paths()
        if not self.selected_path_id and available_paths:
            self.selected_path_id = available_paths[0][0]

        self._update_items()

    def _get_guild_paths(self):
        result = []
        paths = self.cog.config.get("notification_paths", {})
        for pid, pdata in paths.items():
            src = self.cog.bot.get_channel(pdata.get("source_id"))
            tgt = self.cog.bot.get_channel(pdata.get("target_id"))
            if src and src.guild.id == self.guild.id:
                result.append((pid, src, tgt))
            elif tgt and tgt.guild.id == self.guild.id:
                result.append((pid, src, tgt))
        return result

    def _get_current_msg_config(self):
        if not self.selected_path_id:
            return self.cog.default_messages.get(self.selected_type_key, {})
        pdata = self.cog.config.get("notification_paths", {}).get(self.selected_path_id, {})
        customs = pdata.get("custom_messages", {})
        return customs.get(self.selected_type_key) or self.cog.default_messages.get(self.selected_type_key, {})

    def build_embed(self) -> discord.Embed:
        paths = self._get_guild_paths()
        if not paths:
            embed = discord.Embed(
                title="Studio Jalur Notifikasi",
                description="Belum ada jalur notifikasi yang terdaftar di server ini.\nGunakan perintah `!addpath <sumber> <tujuan>` untuk membuat jalur baru.",
                color=0xED4245
            )
            return embed

        current_path_tuple = None
        for p in paths:
            if p[0] == self.selected_path_id:
                current_path_tuple = p
                break
        if not current_path_tuple:
            current_path_tuple = paths[0]
            self.selected_path_id = current_path_tuple[0]

        pid, src_ch, tgt_ch = current_path_tuple
        src_name = f"<#{src_ch.id}>" if src_ch else f"`ID: {pid}`"
        tgt_name = f"<#{tgt_ch.id}>" if tgt_ch else "Belum diatur"

        msg_cfg = self._get_current_msg_config()
        type_name = TYPE_LABELS.get(self.selected_type_key, self.selected_type_key.upper())

        content_val = msg_cfg.get("content") or "@everyone {ai_hype}"
        title_val = msg_cfg.get("title") or "[{judul}]({url})"
        desc_val = msg_cfg.get("description") or "{deskripsi}"
        btn_val = msg_cfg.get("button_label") or "Tonton Konten"
        use_card = msg_cfg.get("use_embed", True)
        format_str = "Kartu Visual" if use_card else "Pesan Teks"

        embed = discord.Embed(
            title=f"Pengaturan Notifikasi: {type_name}",
            color=0xED4245
        )
        embed.description = (
            f"**ID Jalur:** `{pid}`\n"
            f"**Kanal Sumber:** {src_name}\n"
            f"**Kanal Tujuan:** {tgt_name}\n"
            f"**Format Tampilan:** `{format_str}`\n\n"
            f"**Isi Pesan Biasa:**\n> {content_val}\n\n"
            f"**Judul Utama:**\n> {title_val}\n\n"
            f"**Deskripsi Utama:**\n> {desc_val}\n\n"
            f"**Label Tombol:** `{btn_val}`\n\n"
            f"*Gunakan tombol di bawah untuk mengubah setelan atau menguji pengiriman.*"
        )
        return embed

    def _update_items(self):
        self.clear_items()
        paths = self._get_guild_paths()

        if not paths:
            return

        path_options = []
        for pid, src, tgt in paths[:25]:
            s_name = f"#{src.name}" if src else f"ID {pid[:8]}"
            t_name = f"#{tgt.name}" if tgt else "Target"
            label = f"{s_name} → {t_name}"
            is_def = (pid == self.selected_path_id)
            path_options.append(discord.SelectOption(label=label[:100], value=pid, default=is_def))

        path_select = discord.ui.Select(
            placeholder="Pilih Jalur Notifikasi...",
            options=path_options,
            row=0
        )

        async def path_callback(interaction: discord.Interaction):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("Anda tidak memiliki akses ke panel ini.", ephemeral=True)
            self.selected_path_id = path_select.values[0]
            self._update_items()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

        path_select.callback = path_callback
        self.add_item(path_select)

        type_options = []
        for tkey, tlbl in TYPE_LABELS.items():
            is_def = (tkey == self.selected_type_key)
            type_options.append(discord.SelectOption(label=tlbl, value=tkey, default=is_def))

        type_select = discord.ui.Select(
            placeholder="Pilih Tipe Konten...",
            options=type_options,
            row=1
        )

        async def type_callback(interaction: discord.Interaction):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("Anda tidak memiliki akses ke panel ini.", ephemeral=True)
            self.selected_type_key = type_select.values[0]
            self._update_items()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

        type_select.callback = type_callback
        self.add_item(type_select)

        edit_btn = discord.ui.Button(label="Ubah Teks", style=discord.ButtonStyle.primary, row=2)
        async def edit_callback(interaction: discord.Interaction):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("Anda tidak memiliki akses.", ephemeral=True)
            if not self.selected_path_id:
                return await interaction.response.send_message("Pilih jalur notifikasi terlebih dahulu.", ephemeral=True)
            await interaction.response.send_modal(NotifFormatEditorModal(self.cog, self.selected_path_id, self.selected_type_key, self))
        edit_btn.callback = edit_callback
        self.add_item(edit_btn)

        format_btn = discord.ui.Button(label="Ganti Format", style=discord.ButtonStyle.secondary, row=2)
        async def format_callback(interaction: discord.Interaction):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("Anda tidak memiliki akses.", ephemeral=True)
            if not self.selected_path_id:
                return await interaction.response.send_message("Pilih jalur notifikasi terlebih dahulu.", ephemeral=True)
            pdata = self.cog.config.get("notification_paths", {}).get(self.selected_path_id, {})
            if "custom_messages" not in pdata:
                pdata["custom_messages"] = self.cog.default_messages.copy()
            if self.selected_type_key not in pdata["custom_messages"]:
                pdata["custom_messages"][self.selected_type_key] = self.cog.default_messages.get(self.selected_type_key, {}).copy()
            curr = pdata["custom_messages"][self.selected_type_key].get("use_embed", True)
            pdata["custom_messages"][self.selected_type_key]["use_embed"] = not curr
            pdata["custom_messages"][self.selected_type_key]["_format_explicitly_set"] = True
            self.cog.save_config()
            self._update_items()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        format_btn.callback = format_callback
        self.add_item(format_btn)

        test_btn = discord.ui.Button(label="Tes Kirim", style=discord.ButtonStyle.success, row=2)
        async def test_callback(interaction: discord.Interaction):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("Anda tidak memiliki akses.", ephemeral=True)
            await self._run_test_send(interaction)
        test_btn.callback = test_callback
        self.add_item(test_btn)

        del_btn = discord.ui.Button(label="Hapus Jalur", style=discord.ButtonStyle.danger, row=2)
        async def del_callback(interaction: discord.Interaction):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("Anda tidak memiliki akses.", ephemeral=True)
            if self.selected_path_id in self.cog.config.get("notification_paths", {}):
                del self.cog.config["notification_paths"][self.selected_path_id]
                self.cog.save_config()
                self.selected_path_id = None
                self._update_items()
                await interaction.response.edit_message(embed=self.build_embed(), view=self)
            else:
                await interaction.response.send_message("Jalur tidak ditemukan.", ephemeral=True)
        del_btn.callback = del_callback
        self.add_item(del_btn)

        close_btn = discord.ui.Button(label="Tutup", style=discord.ButtonStyle.secondary, row=2)
        async def close_callback(interaction: discord.Interaction):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("Anda tidak memiliki akses.", ephemeral=True)
            await interaction.response.defer()
            await interaction.delete_original_response()
            self.stop()
        close_btn.callback = close_callback
        self.add_item(close_btn)

    async def _run_test_send(self, interaction: discord.Interaction):
        pdata = self.cog.config.get("notification_paths", {}).get(self.selected_path_id)
        if not pdata:
            return await interaction.response.send_message("Jalur notifikasi tidak ditemukan.", ephemeral=True)

        target_ch_id = pdata.get("target_id")
        target_ch = self.cog.bot.get_channel(target_ch_id)
        if not target_ch:
            return await interaction.response.send_message(f"Kanal tujuan (ID: {target_ch_id}) tidak ditemukan.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        msg_cfg = self._get_current_msg_config()
        if "tiktok" in self.selected_type_key:
            sample_creator = "TikTok Creator"
            if self.selected_type_key == "tiktok_live":
                sample_title = "Live Streaming TikTok - Sesi Ngobrol & Mabar"
                sample_url = "https://www.tiktok.com/@tiktok/live"
                sample_desc = "Sedang siaran langsung di TikTok! Yuk tonton keseruannya sekarang!"
            else:
                sample_title = "Video TikTok Terbaru Hari Ini"
                sample_url = "https://www.tiktok.com/@tiktok"
                sample_desc = "Cek video TikTok terbaru dan jangan lewatkan keseruannya!"
            sample_thumb = "https://images.unsplash.com/photo-1611162618071-b39a2ec055fb?w=800"
        elif "instagram" in self.selected_type_key:
            sample_creator = "Instagram Creator"
            if self.selected_type_key == "instagram_live":
                sample_title = "Live Streaming Instagram"
                sample_url = "https://www.instagram.com"
                sample_desc = "Yuk join Instagram Live sekarang juga!"
            else:
                sample_title = "Postingan & Reels Terbaru Instagram"
                sample_url = "https://www.instagram.com"
                sample_desc = "Ada postingan atau Reels baru di Instagram, cek sekarang!"
            sample_thumb = "https://images.unsplash.com/photo-1611162616305-c69b3fa7fbe0?w=800"
        else:
            sample_creator = "Luthfi Halimawan"
            sample_title = "SAFARI TV - UJI COBA LIVE STREAMING"
            sample_url = "https://www.youtube.com/watch?v=5dv55fcY9JI"
            sample_desc = "Ini adalah deskripsi uji coba format notifikasi."
            sample_thumb = "https://img.youtube.com/vi/5dv55fcY9JI/maxresdefault.jpg"

        intro_template = msg_cfg.get("content") or "@everyone {ai_hype}"
        if "{ai_hype}" in intro_template:
            ai_text = await self.cog._generate_jarkasih_hype(self.selected_type_key, channel_name=sample_creator, video_title=sample_title, video_desc=sample_desc)
            intro = intro_template.replace("{ai_hype}", ai_text)
        else:
            intro = intro_template

        intro = intro.replace("{judul}", sample_title).replace("{url}", sample_url).replace("{channel}", sample_creator).strip()

        card_title_template = msg_cfg.get("title") or "[{judul}]({url})"
        card_desc_template = msg_cfg.get("description") or "{deskripsi}"
        btn_label = msg_cfg.get("button_label") or "Tonton Konten"
        use_card = msg_cfg.get("use_embed", True)

        final_card_title = card_title_template.replace("{judul}", sample_title).replace("{url}", sample_url).replace("{channel}", sample_creator)
        try:
            final_card_title = emoji.replace_emoji(final_card_title, replace="").strip()
            final_card_title = re.sub(r"\[\s+", "[", final_card_title)
            final_card_title = re.sub(r"\s+\]", "]", final_card_title)
        except Exception:
            pass

        final_card_desc = card_desc_template.replace("{deskripsi}", sample_desc).replace("{judul}", sample_title).replace("{url}", sample_url).replace("{channel}", sample_creator)

        if not use_card:
            fallback_view = discord.ui.View()
            fallback_btn = discord.ui.Button(label=btn_label, style=discord.ButtonStyle.primary, url=sample_url)
            fallback_view.add_item(fallback_btn)
            text_to_send = f"{intro}\n{sample_url}" if sample_url not in intro else intro
            try:
                await target_ch.send(content=text_to_send, view=fallback_view)
                return await interaction.followup.send(f"Berhasil mengirim uji coba notifikasi teks biasa ke {target_ch.mention}.", ephemeral=True)
            except Exception as e:
                return await interaction.followup.send(f"Gagal mengirim notifikasi teks: {e}", ephemeral=True)

        from cogs.v2_layout import build_v2_card, send_v2_message
        buttons = [{
            "style": 5,
            "label": btn_label,
            "url": sample_url
        }]

        files = None
        attachment_fn = None
        try:
            import io
            dl_headers = {"User-Agent": "Mozilla/5.0"}
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout, headers=dl_headers) as sess:
                async with sess.get(sample_thumb) as r:
                    if r.status == 200:
                        img_bytes = await r.read()
                        if img_bytes:
                            files = [discord.File(io.BytesIO(img_bytes), filename="thumbnail.jpg")]
                            attachment_fn = "thumbnail.jpg"
        except Exception:
            files = None
            attachment_fn = None

        card = build_v2_card(
            title=final_card_title,
            description=final_card_desc,
            buttons=buttons,
            attachment_filename=attachment_fn,
            media_url=sample_thumb if not attachment_fn else None
        )

        res = await send_v2_message(self.cog.bot, target_ch.id, [card], files=files, content=intro)
        if res and not (isinstance(res, dict) and "error_msg" in res):
            await interaction.followup.send(f"Berhasil mengirim uji coba notifikasi kartu ke {target_ch.mention}.", ephemeral=True)
        else:
            await interaction.followup.send(f"Gagal mengirim kartu uji coba: {res}", ephemeral=True)

class ContentRadar(commands.Cog, name="Content Radar & Feed"):
    def __init__(self, bot):
        self.bot = bot
        self.config_file = "data/notif.json"

        self.mongo_client = getattr(bot, 'mongo_client', None)
        if self.mongo_client:
            self.db = self.mongo_client["reSwan"]
            self.collection = self.db["notif_config"]
        else:
            self.collection = None

        self.default_messages = self._get_default_messages()
        self.config = self._load_config()
        self.daily_reset_task.start()

    def cog_unload(self):
        self.daily_reset_task.cancel()

    async def _extract_url_from_message(self, message):
        content_clean = message.content.replace('\\', '') if message.content else ''
        
        markdown_url_pattern = r'\[.*?\]\((https?://[^\)]+)\)'
        markdown_match = re.search(markdown_url_pattern, content_clean)
        if markdown_match:
            return markdown_match.group(1)
        
        general_url_pattern = re.compile(r'https?://[^\s<>"]+|www\.[^\s<>"]+')
        match = general_url_pattern.search(content_clean)
        if match:
            return match.group(0).rstrip(').,!')
            
        youtu_pattern = re.compile(r'youtu\.be/[a-zA-Z0-9_-]{11}')
        match2 = youtu_pattern.search(content_clean)
        if match2:
            return "https://" + match2.group(0)

        if message.embeds:
            for emb in message.embeds:
                if emb.url:
                    return emb.url
                if emb.description:
                    emb_match = general_url_pattern.search(emb.description)
                    if emb_match:
                        return emb_match.group(0).rstrip(').,!')
                if emb.fields:
                    for field in emb.fields:
                        f_match = general_url_pattern.search(field.value or "")
                        if f_match:
                            return f_match.group(0).rstrip(').,!')
        
        return None

    async def _detect_youtube_link(self, url, message_content):
        url = url.replace('\\', '')
        content_clean = message_content.replace('\\', '').lower()
        youtube_regex = r'(?:https?:\/\/)?(?:[a-zA-Z0-9-]+\.)?(?:youtube(?:-nocookie)?\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=|watch\?.*&v=|live\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
        
        if re.search(youtube_regex, url):
            if "live" in content_clean or "/live/" in url or "youtube.com/live/" in url:
                return "live", url
            elif "premier" in content_clean or "premiere" in content_clean:
                return "premier", url
            else:
                return "upload", url
        
        return None, url

    async def _detect_tiktok_link(self, url):
        url = url.replace('\\', '')
        
        live_match = re.search(r'tiktok\.com/@([\w.-]+)/live', url, re.IGNORECASE)
        if live_match:
            return "tiktok_live", url

        tiktok_patterns = [
            r'(?:https?:\/\/)?(?:[\w-]+\.)?tiktok\.com/(?:@[\w.-]+\/)?video/(\d+)',
            r'(?:https?:\/\/)?(?:[\w-]+\.)?tiktok\.com/(?:@[\w.-]+\/)?t/(\w+)',
            r'(?:https?:\/\/)?(?:[\w-]+\.)?tiktok\.com/t/(\w+)',
            r'(?:https?:\/\/)?(?:vm|vt|m)\.tiktok\.com/(\w+)'
        ]

        for pattern in tiktok_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                if "vm.tiktok.com" in url or "vt.tiktok.com" in url:
                    try:
                        timeout = aiohttp.ClientTimeout(total=10)
                        async with aiohttp.ClientSession(timeout=timeout) as session:
                            async with session.get(url, allow_redirects=True) as response:
                                final_url = str(response.url)
                                if "tiktok.com" in final_url:
                                    url = final_url
                    except Exception:
                        pass

                    resolved_live_match = re.search(r'tiktok\.com/@([\w.-]+)/live', url, re.IGNORECASE)
                    if resolved_live_match:
                        return "tiktok_live", url
                
                if "www.tiktok.com" not in url and "tiktok.com" in url:
                    url = url.replace("tiktok.com", "www.tiktok.com")
                
                return "tiktok", url
        
        return None, url

    async def _detect_instagram_link(self, url):
        url = url.replace('\\', '')
        
        live_match = re.search(r'instagram\.com/([A-Za-z0-9_.]+)/live', url, re.IGNORECASE)
        if live_match:
            return "instagram_live", url
        
        ig_patterns = [
            r'instagram\.com/p/([A-Za-z0-9_-]+)',
            r'instagram\.com/reel/([A-Za-z0-9_-]+)',
            r'instagram\.com/tv/([A-Za-z0-9_-]+)'
        ]
        
        for pattern in ig_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return "instagram", url
                
        return None, url

    async def _get_link_from_url(self, message):
        url = await self._extract_url_from_message(message)
        if not url:
            return None, None
        
        link_type, final_url = await self._detect_youtube_link(url, message.content)
        if link_type:
            return link_type, final_url
        
        link_type, final_url = await self._detect_tiktok_link(url)
        if link_type:
            return link_type, final_url
            
        link_type, final_url = await self._detect_instagram_link(url)
        if link_type:
            return link_type, final_url
        
        return None, None
    
    def _get_unique_video_id(self, url):
        if not url: return None
        url = url.replace('\\', '')
        
        youtube_regex = r'(?:https?:\/\/)?(?:[a-zA-Z0-9-]+\.)?(?:youtube(?:-nocookie)?\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=|watch\?.*&v=|live\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
        match = re.search(youtube_regex, url)
        if match:
            return f"yt_{match.group(1)}"

        tk_live_match = re.search(r'tiktok\.com/@([\w.-]+)/live', url, re.IGNORECASE)
        if tk_live_match:
            return None

        tiktok_patterns = [
            r'(?:https?:\/\/)?(?:[\w-]+\.)?tiktok\.com/(?:@[\w.-]+\/)?video/(\d+)',
            r'(?:https?:\/\/)?(?:[\w-]+\.)?tiktok\.com/(?:@[\w.-]+\/)?t/(\w+)',
            r'(?:https?:\/\/)?(?:[\w-]+\.)?tiktok\.com/t/(\w+)',
            r'(?:https?:\/\/)?(?:vm|vt|m)\.tiktok\.com/(\w+)'
        ]
        
        for pattern in tiktok_patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return f"tk_{match.group(1)}"

        ig_live_match = re.search(r'instagram\.com/([A-Za-z0-9_.]+)/live', url, re.IGNORECASE)
        if ig_live_match:
            return f"ig_live_{ig_live_match.group(1)}"

        ig_match = re.search(r'instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)', url, re.IGNORECASE)
        if ig_match:
            return f"ig_{ig_match.group(1)}"

        return None

    def _get_default_messages(self):
        return {
            "live": {
                "title": "[{judul}]({url})",
                "description": "{deskripsi} {url}",
                "content": "@everyone {ai_hype}",
                "button_label": "Tonton Live",
                "button_style": discord.ButtonStyle.danger.value,
                "button_color": "#ed4245",
                "embed_color": "#e74c3c",
                "use_embed": True,
                "embed_thumbnail": True
            },
            "upload": {
                "title": "[{judul}]({url})",
                "description": "{deskripsi} {url}",
                "content": "@everyone {ai_hype}",
                "button_label": "Tonton Video",
                "button_style": discord.ButtonStyle.primary.value,
                "button_color": "#5865f2",
                "embed_color": "#2ecc71",
                "use_embed": True,
                "embed_thumbnail": True
            },
            "premier": {
                "title": "[{judul}]({url})",
                "description": "{deskripsi} {url}",
                "content": "@everyone {ai_hype}",
                "button_label": "Tonton Premiere",
                "button_style": discord.ButtonStyle.success.value,
                "button_color": "#57f287",
                "embed_color": "#9b59b6",
                "use_embed": True,
                "embed_thumbnail": True
            },
            "tiktok": {
                "title": "[{judul}]({url})",
                "description": "Cek video TikTok terbaru!\n\n{url}",
                "content": "@everyone {ai_hype}",
                "button_label": "Tonton di TikTok",
                "button_style": discord.ButtonStyle.primary.value,
                "button_color": "#000000",
                "embed_color": "#000000",
                "use_embed": True,
                "embed_thumbnail": True
            },
            "tiktok_live": {
                "title": "[TikTok Live]({url})",
                "description": "Ada yang lagi live di TikTok nih!\n\n{url}",
                "content": "@everyone {ai_hype}",
                "button_label": "Tonton Live TikTok",
                "button_style": discord.ButtonStyle.danger.value,
                "button_color": "#ed4245",
                "embed_color": "#e74c3c",
                "use_embed": True,
                "embed_thumbnail": True
            },
            "instagram": {
                "title": "[Instagram Post]({url})",
                "description": "Ada postingan atau Reels baru di Instagram!\n\n{url}",
                "content": "@everyone {ai_hype}",
                "button_label": "Buka Instagram",
                "button_style": discord.ButtonStyle.primary.value,
                "button_color": "#E1306C",
                "embed_color": "#E1306C",
                "use_embed": True,
                "embed_thumbnail": True
            },
            "instagram_live": {
                "title": "[Instagram Live]({url})",
                "description": "Yuk join Instagram Live sekarang!\n\n{url}",
                "content": "@everyone {ai_hype}",
                "button_label": "Tonton IG Live",
                "button_style": discord.ButtonStyle.danger.value,
                "button_color": "#ed4245",
                "embed_color": "#e74c3c",
                "use_embed": True,
                "embed_thumbnail": True
            }
        }

    def _load_config(self):
        default_config = {
            "notification_paths": {},
            "recent_video_ids": [],
            "next_daily_reset_timestamp": None
        }
        config = {}
        if self.collection is not None:
            try:
                doc = self.collection.find_one({"_id": "notif_config"})
                if doc and "data" in doc:
                    config = doc["data"]
            except Exception:
                pass

        if not config:
            try:
                with open(self.config_file, "r") as f:
                    config = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                pass

        final_config = {**default_config, **config}

        keys_to_remove = ["mirrored_users", "last_daily_reset_timestamp", "last_link_after_reset"]
        for key in keys_to_remove:
            if key in final_config:
                del final_config[key]

        for path_id, path_data in final_config["notification_paths"].items():
            if "custom_messages" in path_data:
                for message_type in self.default_messages.keys():
                    if message_type not in path_data["custom_messages"]:
                        path_data["custom_messages"][message_type] = self.default_messages[message_type].copy()
                    else:
                        m_cfg = path_data["custom_messages"][message_type]
                        if "title" in m_cfg and isinstance(m_cfg["title"], str):
                            clean_t = m_cfg["title"]
                            try:
                                if any(c in clean_t for c in ['\u00f0', '\u0178', '\u201d', '\u00b4']):
                                    clean_t = clean_t.encode('cp1252', errors='ignore').decode('utf-8', errors='ignore')
                            except Exception:
                                pass
                            clean_t = emoji.replace_emoji(clean_t, replace="").strip()
                            clean_t = re.sub(r"\[\s+", "[", clean_t)
                            clean_t = re.sub(r"\s+\]", "]", clean_t)
                            m_cfg["title"] = clean_t
                        if "use_embed" not in m_cfg:
                            m_cfg["use_embed"] = True
                        elif message_type in ["tiktok", "tiktok_live", "instagram", "instagram_live"] and not m_cfg.get("_format_explicitly_set", False):
                            m_cfg["use_embed"] = True

        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, "w") as f:
                json.dump(final_config, f, indent=4)
        except Exception:
            pass
        return final_config

    def save_config(self):
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception:
            pass

        if self.collection is not None:
            try:
                self.collection.replace_one({"_id": "notif_config"}, {"_id": "notif_config", "data": self.config}, upsert=True)
            except Exception:
                pass
            
    async def _perform_daily_reset(self):
        now = datetime.datetime.now(datetime.UTC) 
        self.config["recent_video_ids"] = []
        
        next_reset_time = now + datetime.timedelta(hours=24)
        self.config["next_daily_reset_timestamp"] = next_reset_time.isoformat()
        
        self.save_config()

    @tasks.loop(hours=24)
    async def daily_reset_task(self):
        await self._perform_daily_reset()

    @daily_reset_task.before_loop
    async def before_daily_reset_task(self):
        await self.bot.wait_until_ready()
        
        next_reset_ts = self.config.get("next_daily_reset_timestamp")
        
        if next_reset_ts:
            try:
                next_reset_time = datetime.datetime.fromisoformat(next_reset_ts)
                now = datetime.datetime.now(datetime.UTC)
                
                delay = (next_reset_time - now).total_seconds()
                
                if delay > 0:
                    await asyncio.sleep(delay)
                else:
                    await self._perform_daily_reset()

            except Exception:
                await self._perform_daily_reset()
        else:
            await self._perform_daily_reset()

    @commands.command(name="resetcache")
    @commands.has_permissions(administrator=True)
    async def reset_cache(self, ctx):
        self.config["recent_video_ids"] = []
        self.save_config()
        await ctx.send("Cache ID video yang baru saja dikirim berhasil dibersihkan.")

    @commands.command(name="addpath")
    @commands.has_permissions(administrator=True)
    async def add_notification_path(self, ctx, source_channel_id: int, target_channel_id: int):
        if not ctx.guild:
            await ctx.send("Perintah ini hanya dapat digunakan di dalam server.")
            return
        
        for path_id, data in self.config["notification_paths"].items():
            if data["source_id"] == source_channel_id and data["target_id"] == target_channel_id:
                return await ctx.send(f"Jalur notifikasi tersebut sudah ada dengan ID Jalur `{path_id}`.")
        
        new_path_id = str(uuid.uuid4())
        self.config["notification_paths"][new_path_id] = {
            "source_id": source_channel_id,
            "target_id": target_channel_id,
            "custom_messages": self._get_default_messages()
        }
        self.save_config()
        
        source_channel = self.bot.get_channel(source_channel_id)
        target_channel = self.bot.get_channel(target_channel_id)
        source_info = f"#{source_channel.name}" if source_channel else f"ID: {source_channel_id}"
        target_info = f"#{target_channel.name}" if target_channel else f"ID: {target_channel_id}"
        
        msg = f"Jalur notifikasi baru berhasil dibuat!\n"
        msg += f"Sumber: **{source_info}**\n"
        msg += f"Tujuan: **{target_info}**\n"
        msg += f"ID Jalur: `{new_path_id}`"
        await ctx.send(msg)

    @commands.command(name="removepath")
    @commands.has_permissions(administrator=True)
    async def remove_notification_path(self, ctx, path_id: str):
        if path_id in self.config["notification_paths"]:
            del self.config["notification_paths"][path_id]
            self.save_config()
            await ctx.send(f"Jalur notifikasi dengan ID `{path_id}` berhasil dihapus.")
        else:
            await ctx.send(f"Jalur notifikasi dengan ID `{path_id}` tidak ditemukan.")

    @commands.hybrid_command(name="notif", aliases=["notifstudio", "contentradar"], description="Buka studio pengaturan jalur notifikasi Discord")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def notif_studio(self, ctx: commands.Context):
        if not ctx.guild:
            return await ctx.send("Perintah ini hanya dapat digunakan di server.", ephemeral=True)
        view = ContentRadarStudioView(self, ctx.guild, ctx.author)
        await ctx.send(embed=view.build_embed(), view=view, ephemeral=True)

    @commands.command(name="config")
    @commands.has_permissions(administrator=True)
    async def start_config(self, ctx):
        if not ctx.guild:
            return await ctx.send("Perintah ini hanya dapat digunakan di dalam server.")
        view = ContentRadarStudioView(self, ctx.guild, ctx.author)
        await ctx.send(embed=view.build_embed(), view=view)

    @commands.command(name="checkcache")
    @commands.has_permissions(administrator=True)
    async def check_cache(self, ctx):
        recent_ids = self.config.get("recent_video_ids", [])
        
        if not recent_ids:
            await ctx.send("Cache saat ini kosong.")
            return
        
        embed = discord.Embed(
            title="📦 Isi Cache Video",
            description=f"Total {len(recent_ids)} video dalam cache:",
            color=0x00ff00
        )
        
        cache_list = []
        for i, video_id in enumerate(recent_ids[-20:], 1):
            cache_list.append(f"{i}. `{video_id}`")
        
        embed.add_field(
            name="Video Terbaru (max 20)",
            value="\n".join(cache_list) if cache_list else "Tidak ada video",
            inline=False
        )
        
        embed.set_footer(text=f"Total video dalam cache: {len(recent_ids)}")
        
        await ctx.send(embed=embed)

    async def _generate_jarkasih_hype(self, link_type, channel_name=None, video_title=None, video_desc=None):
        tipe_konten_map = {
            "live": "Live Streaming YouTube",
            "upload": "Video Baru YouTube",
            "premier": "Premiere YouTube",
            "tiktok": "Video TikTok",
            "tiktok_live": "Live Streaming TikTok",
            "instagram": "Postingan/Reel Instagram",
            "instagram_live": "Live Streaming Instagram"
        }
        tipe_konten = tipe_konten_map.get(link_type, "Konten Terbaru")
        
        info_lines = []
        if channel_name:
            info_lines.append(f"- Channel/Kreator: {channel_name}")
        if video_title:
            info_lines.append(f"- Judul: {video_title}")
        if video_desc:
            short_desc = video_desc.strip()[:300].replace("\n", " ")
            info_lines.append(f"- Ringkasan/Deskripsi: {short_desc}")
            
        context_str = "\n".join(info_lines) if info_lines else "Belum ada detail khusus."

        prompt = f"""Kamu adalah bot Discord server RTMxBadut.
Tugas kamu membuat 1 kalimat notifikasi/sapaan santai dan asik buat warga server tentang {tipe_konten} yang baru rilis/dimulai.

Informasi konten:
{context_str}

Panduan gaya:
1. Hubungkan sapaan kamu secara alami dengan judul atau topik kontennya di atas. Jangan buat pujian kosong yang tidak nyambung dengan isi videonya.
2. Gunakan bahasa obrolan Discord/tongkrongan Indonesia yang asik, santai, dan luwes.
3. Sesuaikan dengan situasinya:
   - Kalau video santai/keseharian/vlog, sapa warga server dengan santai dan ajak nonton.
   - Kalau live streaming, ajak warga server langsung merapat ke live chat.
   - Kalau premiere, ingatkan buat standby sebelum mulai.
4. Singkat, padat (cukup 1-2 kalimat). Jangan pakai hashtag (#) dan jangan tulis URL link di dalam teks karena link sudah disediakan di tombol.

Berikan teks pengumuman kamu sekarang:"""
        
        if channel_name and video_title:
            if link_type == "live":
                fallback_text = f"Ada live streaming baru nih dari {channel_name} dengan judul '{video_title}'. Yuk langsung gabung ke live chat!"
            elif link_type == "premier":
                fallback_text = f"{channel_name} mau premiere video baru '{video_title}'. Jangan sampai kelewatan ya!"
            else:
                fallback_text = f"{channel_name} baru aja upload video baru: '{video_title}'. Yuk langsung tonton sekarang!"
        elif channel_name:
            fallback_text = f"Ada konten baru dari {channel_name}. Yuk langsung dicek dan tonton!"
        else:
            fallback_text = f"Ada {tipe_konten} baru nih. Yuk langsung cek dan tonton sekarang!"
        
        models_to_try = ['gemini-2.5-flash', 'gemini-3-flash-preview', 'gemini-2.5-flash-lite']
        
        for model_name in models_to_try:
            attempts = max(1, len(API_KEYS))
            for _ in range(attempts):
                try:
                    model = genai.GenerativeModel(model_name)
                    response = await asyncio.wait_for(model.generate_content_async(prompt), timeout=60.0)
                    if response.text:
                        return response.text.strip().replace('"', '')
                except asyncio.TimeoutError:
                    return fallback_text
                except google_exceptions.ResourceExhausted:
                    if rotate_api_key():
                        await asyncio.sleep(1)
                        continue
                    else:
                        break 
                except Exception:
                    break 
                    
        return fallback_text

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.id == self.bot.user.id or not message.guild:
            return
        
        paths_to_send = [data for data in self.config["notification_paths"].values() if data["source_id"] == message.channel.id]
        if not paths_to_send:
            return

        link_type, link_for_send = await self._get_link_from_url(message)
        if not link_type:
            return

        unique_id = self._get_unique_video_id(link_for_send)
        
        if unique_id:
            recent_ids = self.config.get("recent_video_ids", [])
            if unique_id in recent_ids:
                try:
                    await message.reply("⚠️ Tautan ini sudah pernah dikirim sebelumnya dan ada dalam cache. Tidak akan dikirim ulang untuk menghindari duplikasi.")
                except Exception:
                    pass
                return
                
            if "recent_video_ids" not in self.config:
                self.config["recent_video_ids"] = []
                
            self.config["recent_video_ids"].append(unique_id)
            if len(self.config["recent_video_ids"]) > 999:
                self.config["recent_video_ids"].pop(0)
            self.save_config()

        source_embed = message.embeds[0] if message.embeds else None

        youtube_title = None
        youtube_description = None
        youtube_thumbnail = None
        video_url = link_for_send
        youtube_channel = None

        if source_embed:
            if source_embed.title:
                youtube_title = source_embed.title
            if source_embed.description:
                youtube_description = source_embed.description
            if source_embed.thumbnail and source_embed.thumbnail.url:
                youtube_thumbnail = source_embed.thumbnail.url
            elif source_embed.image and source_embed.image.url:
                youtube_thumbnail = source_embed.image.url
            if source_embed.author and source_embed.author.name:
                youtube_channel = source_embed.author.name

        if link_type in ["live", "upload", "premier"]:
            if not youtube_title or not youtube_thumbnail:
                import asyncio
                yt_t, yt_d, yt_th, yt_u, yt_c = await asyncio.to_thread(_extract_youtube_info, link_for_send)
                if not youtube_title and yt_t:
                    youtube_title = yt_t
                if not youtube_description and yt_d:
                    youtube_description = yt_d
                if not youtube_thumbnail and yt_th:
                    youtube_thumbnail = yt_th
                if not youtube_channel and yt_c:
                    youtube_channel = yt_c
        elif link_type in ["tiktok", "tiktok_live"]:
            if not youtube_title or not youtube_thumbnail:
                import asyncio
                tt_t, tt_d, tt_th, tt_u, tt_c = await asyncio.to_thread(_extract_tiktok_info, link_for_send)
                if not youtube_title and tt_t:
                    youtube_title = tt_t
                if not youtube_description and tt_d:
                    youtube_description = tt_d
                if not youtube_thumbnail and tt_th:
                    youtube_thumbnail = tt_th
                if not youtube_channel and tt_c:
                    youtube_channel = tt_c
        elif link_type in ["instagram", "instagram_live"]:
            if not youtube_title or not youtube_thumbnail:
                import asyncio
                ig_t, ig_d, ig_th, ig_u, ig_c = await asyncio.to_thread(_extract_instagram_info, link_for_send)
                if not youtube_title and ig_t:
                    youtube_title = ig_t
                if not youtube_description and ig_d:
                    youtube_description = ig_d
                if not youtube_thumbnail and ig_th:
                    youtube_thumbnail = ig_th
                if not youtube_channel and ig_c:
                    youtube_channel = ig_c

        clean_title = youtube_title if youtube_title else None
        if youtube_title:
            date_patterns = [
                r'\d{4}-\d{2}-\d{2}',
                r'\d{2}:\d{2}',
                r'\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}'
            ]
            for pattern in date_patterns:
                clean_title = re.sub(pattern, '', clean_title).strip()

        ai_hype_text = await self._generate_jarkasih_hype(
            link_type,
            channel_name=youtube_channel,
            video_title=clean_title,
            video_desc=youtube_description
        )

        for path_data in paths_to_send:
            target_channel_id = path_data["target_id"]
            config_msg = path_data["custom_messages"].get(link_type, self.default_messages.get(link_type))
            if not config_msg: continue

            try:
                target_channel = self.bot.get_channel(target_channel_id)
                if not target_channel: continue 

                final_content = config_msg.get('content')
                final_embed_title = config_msg.get('title')
                final_embed_description = config_msg.get('description')
                use_embed = config_msg.get('use_embed', True)

                if final_content and "{ai_hype}" in final_content:
                    final_content = final_content.replace("{ai_hype}", ai_hype_text)

                if link_type in ["live", "upload", "premier", "tiktok", "tiktok_live"]:
                    default_title_fallback = "Video TikTok" if "tiktok" in link_type else "Video YouTube"
                    clean_title = youtube_title if youtube_title else default_title_fallback
                    if clean_title:
                        date_patterns = [
                            r'\d{4}-\d{2}-\d{2}',
                            r'\d{2}:\d{2}',
                            r'\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}'
                        ]
                        for pattern in date_patterns:
                            clean_title = re.sub(pattern, '', clean_title).strip()
                        clean_title = re.sub(r'[\[\]]', '', clean_title)
                        try:
                            clean_title = emoji.replace_emoji(clean_title, replace='')
                        except Exception:
                            pass
                        clean_title = " ".join(clean_title.split())
                    
                    if not final_content or final_content.strip() == "Ada video TikTok baru nih!":
                        final_content = "{ai_hype}"
                    if "{ai_hype}" in final_content:
                        final_content = final_content.replace("{ai_hype}", ai_hype_text)

                    if final_content:
                        final_content = final_content.replace("{judul}", clean_title)
                        final_content = final_content.replace("{url}", video_url if self._is_valid_url(video_url) else "")
                    
                    if final_embed_title:
                        fallback_title = clean_title if clean_title else default_title_fallback
                        fallback_channel = youtube_channel if youtube_channel else ("Kreator TikTok" if "tiktok" in link_type else "Channel YouTube")
                        final_embed_title = final_embed_title.replace("{judul}", fallback_title).replace("$judul", fallback_title)
                        final_embed_title = final_embed_title.replace("{channel}", fallback_channel).replace("$channel", fallback_channel)
                        final_embed_title = final_embed_title.replace("{url}", video_url if self._is_valid_url(video_url) else "").replace("$url", video_url if self._is_valid_url(video_url) else "")
                        final_embed_title = final_embed_title.replace("{ai_hype}", ai_hype_text).replace("$ai_hype", ai_hype_text)
                    else:
                        final_embed_title = f"[{clean_title}]({video_url})" if self._is_valid_url(video_url) else clean_title

                    if final_embed_description:
                        fallback_title = clean_title if clean_title else default_title_fallback
                        fallback_channel = youtube_channel if youtube_channel else ("Kreator TikTok" if "tiktok" in link_type else "Channel YouTube")
                        fallback_desc = youtube_description if youtube_description else ""
                        desc_sub = fallback_desc[:1900] + ('...' if len(fallback_desc) > 1900 else '')
                        final_embed_description = final_embed_description.replace("{deskripsi}", desc_sub).replace("$deskripsi", desc_sub)
                        final_embed_description = final_embed_description.replace("{judul}", fallback_title).replace("$judul", fallback_title)
                        final_embed_description = final_embed_description.replace("{channel}", fallback_channel).replace("$channel", fallback_channel)
                        final_embed_description = final_embed_description.replace("{url}", video_url if self._is_valid_url(video_url) else "").replace("$url", video_url if self._is_valid_url(video_url) else "")
                        final_embed_description = final_embed_description.replace("{ai_hype}", ai_hype_text).replace("$ai_hype", ai_hype_text)
                    else:
                        final_embed_description = youtube_description[:1900] if youtube_description else link_for_send

                elif link_type in ["instagram", "instagram_live"]:
                    tipe_str = "Postingan Instagram"
                    if link_type == "instagram_live": tipe_str = "Instagram Live"
                    clean_title = youtube_title if youtube_title else tipe_str
                    clean_title = re.sub(r'[\[\]]', '', clean_title)
                    try:
                        clean_title = emoji.replace_emoji(clean_title, replace='')
                    except Exception:
                        pass
                    clean_title = " ".join(clean_title.split())

                    if not final_content:
                        final_content = "{ai_hype}"
                    if "{ai_hype}" in final_content:
                        final_content = final_content.replace("{ai_hype}", ai_hype_text)

                    if final_content:
                        final_content = final_content.replace("{judul}", clean_title)
                        if self._is_valid_url(link_for_send):
                            final_content = final_content.replace("{url}", link_for_send)
                    
                    if final_embed_title:
                        fallback_channel = youtube_channel if youtube_channel else "Akun Instagram"
                        final_embed_title = final_embed_title.replace("{judul}", clean_title).replace("$judul", clean_title)
                        final_embed_title = final_embed_title.replace("{channel}", fallback_channel).replace("$channel", fallback_channel)
                        final_embed_title = final_embed_title.replace("{url}", video_url if self._is_valid_url(video_url) else "").replace("$url", video_url if self._is_valid_url(video_url) else "")
                        final_embed_title = final_embed_title.replace("{ai_hype}", ai_hype_text).replace("$ai_hype", ai_hype_text)
                    else:
                        final_embed_title = f"[{clean_title}]({link_for_send})" if self._is_valid_url(link_for_send) else clean_title

                    if final_embed_description:
                        fallback_desc = youtube_description if youtube_description else ""
                        desc_sub = fallback_desc[:1900] + ('...' if len(fallback_desc) > 1900 else '')
                        final_embed_description = final_embed_description.replace("{deskripsi}", desc_sub).replace("$deskripsi", desc_sub)
                        final_embed_description = final_embed_description.replace("{judul}", clean_title).replace("$judul", clean_title)
                        final_embed_description = final_embed_description.replace("{url}", video_url if self._is_valid_url(video_url) else "").replace("$url", video_url if self._is_valid_url(video_url) else "")
                    else:
                        final_embed_description = youtube_description[:1900] if youtube_description else link_for_send

                if use_embed:
                    message_content = final_content if final_content else ai_hype_text
                else:
                    if final_content and "{url}" not in final_content:
                        message_content = f"{final_content}\n{link_for_send}"
                    elif not final_content:
                        message_content = f"{ai_hype_text}\n{link_for_send}"
                    else:
                        message_content = final_content

                button_label = config_msg.get('button_label', 'Tonton Konten')
                button_style_value = config_msg.get('button_style', discord.ButtonStyle.primary.value)
                try: 
                    button_style = discord.ButtonStyle(button_style_value)
                except ValueError: 
                    button_style = discord.ButtonStyle.primary

                if link_type in ["live", "upload", "premier", "tiktok", "tiktok_live", "instagram", "instagram_live"] and use_embed:
                    from cogs.v2_layout import build_v2_card, send_v2_message
                    
                    desc_text = ""
                    if final_embed_description:
                        desc_text += f"{final_embed_description}"
                        
                    desc_text = desc_text.strip()
                    if not desc_text:
                        desc_text = link_for_send
                    
                    if "tiktok" in link_type:
                        default_btn_label = "Tonton di TikTok"
                    elif "instagram" in link_type:
                        default_btn_label = "Lihat di Instagram"
                    else:
                        default_btn_label = "Tonton di YouTube" if link_type in ["live", "upload", "premier"] else "Tonton Konten"
                    actual_button_label = config_msg.get('button_label') or default_btn_label

                    buttons = [{
                        "style": 5, 
                        "label": actual_button_label,
                        "url": link_for_send
                    }]
                    
                    if link_type in ["live", "upload", "premier"]:
                        vid_id = _get_youtube_video_id(link_for_send)
                        if vid_id and not youtube_thumbnail and config_msg.get('embed_thumbnail', True):
                            youtube_thumbnail = f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg"

                    files = None
                    attachment_fn = None
                    if youtube_thumbnail and config_msg.get('embed_thumbnail', True):
                        try:
                            import io
                            dl_headers = {
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                            }
                            if "tiktok" in link_type:
                                dl_headers["Referer"] = "https://www.tiktok.com/"
                            elif "instagram" in link_type:
                                dl_headers["Referer"] = "https://www.instagram.com/"
                            timeout = aiohttp.ClientTimeout(total=10)
                            async with aiohttp.ClientSession(timeout=timeout, headers=dl_headers) as session:
                                async with session.get(youtube_thumbnail) as img_resp:
                                    if img_resp.status == 200:
                                        img_bytes = await img_resp.read()
                                        if img_bytes:
                                            files = [discord.File(io.BytesIO(img_bytes), filename="thumbnail.jpg")]
                                            attachment_fn = "thumbnail.jpg"
                        except Exception:
                            files = None
                            attachment_fn = None

                    try:
                        final_embed_title = emoji.replace_emoji(final_embed_title, replace="").strip()
                        final_embed_title = re.sub(r"\[\s+", "[", final_embed_title)
                        final_embed_title = re.sub(r"\s+\]", "]", final_embed_title)
                    except Exception:
                        pass

                    card = build_v2_card(
                        title=final_embed_title,
                        description=desc_text,
                        fields=None,
                        color=None,
                        buttons=buttons,
                        attachment_filename=attachment_fn,
                        media_url=youtube_thumbnail if not attachment_fn else None
                    )
                    v2_sent = False
                    try:
                        resp = await send_v2_message(self.bot, target_channel.id, [card], files=files, content=message_content)
                        if resp and not (isinstance(resp, dict) and "error_msg" in resp):
                            v2_sent = True
                    except Exception as err:
                        with open("notif_v2_error.txt", "a") as f:
                            f.write(f"V2 Error: {err}\n")

                    if not v2_sent:
                        fallback_view = discord.ui.View()
                        fallback_btn = discord.ui.Button(label=actual_button_label, style=button_style, url=link_for_send)
                        fallback_view.add_item(fallback_btn)
                        send_text = message_content if message_content else ai_hype_text
                        if link_for_send not in send_text:
                            send_text = f"{send_text}\n{link_for_send}"
                        await target_channel.send(content=send_text, view=fallback_view)
                else:
                    embed = None
                    if use_embed:
                        embed_color_hex = config_msg.get('embed_color', '#3498db')
                        try: 
                            embed_color = discord.Color(int(embed_color_hex.strip("#"), 16))
                        except: 
                            embed_color = discord.Color.blue()
                        
                        if final_embed_title or final_embed_description:
                             embed = discord.Embed(title=final_embed_title, description=final_embed_description, color=embed_color)
                             
                             if link_type in ["live", "upload", "premier"] and config_msg.get('embed_thumbnail', True) and youtube_thumbnail:
                                  embed.set_image(url=youtube_thumbnail)
                             
                             if message_content is None: 
                                 message_content = None
                        else:
                             message_content = final_content if final_content else link_for_send
                             if not final_content:
                                  message_content = link_for_send
                             embed = None
                    
                    view = discord.ui.View()
                    button = discord.ui.Button(label=button_label, style=button_style, url=link_for_send)
                    view.add_item(button)
    
                    await target_channel.send(content=message_content, embed=embed, view=view)
                
            except Exception as e:
                import traceback
                print(f"[NOTIF ERROR] {e}")
                traceback.print_exc()

    def _is_valid_url(self, url):
        try:
            result = urllib.parse.urlparse(url)
            return all([result.scheme in ['http', 'https'], result.netloc])
        except Exception:
            return False

async def setup(bot):
    os.makedirs('data', exist_ok=True)
    await bot.add_cog(ContentRadar(bot))
