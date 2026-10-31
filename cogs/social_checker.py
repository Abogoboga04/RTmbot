import asyncio
import json
import os
import re
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional, Literal
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
import yt_dlp
from dotenv import load_dotenv
from cogs.v2_layout import build_v2_card, send_v2_message


class _SilentYDLLogger:
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


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

def clean_ai_hype_text(text: str) -> str:
    if not text:
        return ""
    text = text.strip().strip('"\'`')
    preamble_patterns = [
        r'^(?:[\*_~`\s]*(?:siap|tentu|oke|baik|halo|berikut(?:\sadalah)?|ini(?:\sdia)?|teks|pengumuman|notifikasi)[^\n:]*:[ \t\r\f\v\*_~`]*\n*)+',
    ]
    for pattern in preamble_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()
    if '\n' in text:
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if len(lines) > 1:
            first_line_clean = lines[0].strip().strip('*_~`')
            first_line_lower = first_line_clean.lower()
            is_filler = (
                ':' in lines[0] or
                'teks pengumuman' in first_line_lower or
                'ini dia' in first_line_lower or
                first_line_lower in ['siap!', 'tentu!', 'oke!', 'baik!']
            )
            if is_filler and any(w in first_line_lower for w in ['siap', 'tentu', 'oke', 'baik', 'berikut', 'ini dia', 'pengumuman', 'notifikasi']):
                text = '\n\n'.join(lines[1:]).strip()
    return text.strip('"\'`').strip()


def clean_hyperlink_title(raw_title: str) -> str:
    if not raw_title:
        return ""
    try:
        import emoji
        cleaned = emoji.replace_emoji(str(raw_title), replace='')
    except Exception:
        cleaned = str(raw_title)
    cleaned = re.sub(r'[\[\]]', '', cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned

def normalize_tiktok_username(raw: str) -> str:
    if not raw:
        return ""
    text = str(raw).strip()
    if "?" in text:
        text = text.split("?")[0]
    m = re.search(r'@([a-zA-Z0-9_.-]+)', text)
    if m:
        return m.group(1).lower().rstrip("/")
    if "tiktok.com" in text:
        parts = [p for p in text.rstrip("/").split("/") if p]
        if parts:
            candidate = parts[-1].lstrip("@")
            if candidate and not candidate.startswith("http") and "tiktok.com" not in candidate:
                return candidate.lower()
    clean = text.lstrip("@").strip().lower()
    clean = clean.split("/")[0]
    return clean

async def async_resolve_tiktok_username(raw: str) -> str:
    if not raw:
        return ""
    text = str(raw).strip()
    clean = normalize_tiktok_username(text)
    if clean and ("tiktok.com" not in clean and not clean.startswith("http")):
        return clean
    if "tiktok.com" in text:
        try:
            from curl_cffi import requests as cffi_requests
            def _resolve_url(target_url: str):
                s = cffi_requests.Session(impersonate="chrome")
                resp = s.head(target_url, allow_redirects=True, timeout=8)
                return resp.url
            final_url = await asyncio.to_thread(_resolve_url, text)
            resolved_clean = normalize_tiktok_username(final_url)
            if resolved_clean:
                return resolved_clean
        except Exception:
            pass
    return clean

def _get_proxy_for_platform(platform: str) -> Optional[str]:
    if platform == "instagram":
        return os.getenv("IG_PROXY") or os.getenv("SOCIAL_PROXY") or os.getenv("HTTPS_PROXY")
    elif platform == "tiktok":
        return os.getenv("TT_PROXY") or os.getenv("SOCIAL_PROXY") or os.getenv("HTTPS_PROXY")
    elif platform == "youtube":
        return os.getenv("YT_PROXY") or os.getenv("SOCIAL_PROXY") or os.getenv("HTTPS_PROXY")
    return os.getenv("SOCIAL_PROXY") or os.getenv("HTTPS_PROXY")


def _ig_pk_to_shortcode(pk_val) -> str:
    try:
        pk = int(str(pk_val).replace("POLARIS_", "").strip())
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        shortcode = ""
        while pk > 0:
            pk, rem = divmod(pk, 64)
            shortcode = alphabet[rem] + shortcode
        return shortcode
    except Exception:
        return str(pk_val)


def normalize_instagram_username(raw: str) -> str:
    if not raw:
        return ""
    text = str(raw).strip()
    if "?" in text:
        text = text.split("?")[0]
    m = re.search(r'@([a-zA-Z0-9_.-]+)', text)
    if m:
        return m.group(1).lower().rstrip("/")
    if "instagram.com" in text:
        clean_url = text.rstrip("/")
        parts = [p for p in clean_url.split("/") if p]
        if parts:
            cand = parts[-1].lstrip("@")
            if cand and not cand.startswith("http") and "instagram.com" not in cand and cand not in ("p", "reel", "reels", "tv", "stories"):
                return cand.lower()
    clean = text.lstrip("@").strip().lower()
    clean = clean.split("/")[0]
    return clean

async def async_resolve_instagram_username(raw: str) -> str:
    if not raw:
        return ""
    text = str(raw).strip()
    norm = normalize_instagram_username(text)
    if norm and ("instagram.com" not in norm and not norm.startswith("http")):
        return norm
    if "instagram.com" in text:
        m_post = re.search(r'instagram\.com\/(?:p|reel|reels|tv)\/([A-Za-z0-9_-]+)', text)
        if m_post:
            shortcode = m_post.group(1)
            try:
                import instaloader
                def _get_owner(sc: str):
                    L = instaloader.Instaloader(quiet=True)
                    post = instaloader.Post.from_shortcode(L.context, sc)
                    return post.owner_username
                owner = await asyncio.to_thread(_get_owner, shortcode)
                if owner:
                    return owner.lower()
            except Exception:
                pass
        try:
            from curl_cffi import requests as cffi_requests
            def _resolve_ig_url(target_url: str):
                s = cffi_requests.Session(impersonate="chrome")
                resp = s.head(target_url, allow_redirects=True, timeout=8)
                return resp.url
            final_url = await asyncio.to_thread(_resolve_ig_url, text)
            resolved_clean = normalize_instagram_username(final_url)
            if resolved_clean:
                return resolved_clean
        except Exception:
            pass
    return norm


class SocialFormatEditorModal(discord.ui.Modal, title="Edit Pesan Notifikasi"):
    def __init__(self, cog, target: dict, author: discord.Member, parent_view):
        super().__init__()
        self.cog = cog
        self.target = target
        self.author = author
        self.parent_view = parent_view

        current_content = target.get("content") or target.get("custom_template") or "@everyone {ai_hype}"
        current_title = target.get("card_title") or "[{judul}]({url})"
        current_desc = target.get("card_desc") or "{deskripsi}"
        current_btn = target.get("button_label") or ""

        self.content_input = discord.ui.TextInput(
            label="Pesan Notifikasi & Mention",
            default=current_content,
            placeholder="Contoh: @everyone {ai_hype}\nBisa isi: @everyone, @here, @Role, {ai_hype}, {judul}, {url}",
            style=discord.TextStyle.paragraph,
            max_length=1500,
            required=True
        )
        self.title_input = discord.ui.TextInput(
            label="Pola Judul Kartu",
            default=current_title,
            placeholder="Variabel: {judul}, {channel}, {creator}, {url}",
            max_length=256,
            required=True
        )
        self.desc_input = discord.ui.TextInput(
            label="Deskripsi Konten",
            default=current_desc,
            placeholder="Variabel: {deskripsi}, {judul}, {url}",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=False
        )
        self.btn_input = discord.ui.TextInput(
            label="Label Tombol (Opsional)",
            default=current_btn,
            placeholder="Kosongkan untuk otomatis platform (cth: Tonton di YouTube)",
            max_length=80,
            required=False
        )

        self.add_item(self.content_input)
        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        self.add_item(self.btn_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.target["content"] = self.content_input.value.strip()
        self.target["custom_template"] = self.target["content"]
        self.target["card_title"] = self.title_input.value.strip()
        self.target["card_desc"] = self.desc_input.value.strip()
        val_btn = self.btn_input.value.strip()
        self.target["button_label"] = val_btn if val_btn else None

        self.cog._save_config()
        self.parent_view.update_components()
        await interaction.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view)


class SocialCheckerStudioView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, platform_filter: Optional[str] = None, initial_target: Optional[dict] = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.platform_filter = platform_filter
        self.target = initial_target
        self.update_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Menu ini hanya dapat diakses oleh moderator yang memanggilnya.", ephemeral=True)
            return False
        return True

    def get_targets(self) -> list:
        targets = self.cog.config.get("targets", [])
        if self.platform_filter:
            targets = [t for t in targets if t.get("platform") == self.platform_filter]
        if self.guild:
            guild_targets = [t for t in targets if t.get("target_guild_id") == self.guild.id]
            if guild_targets:
                return guild_targets
        return targets

    def update_components(self):
        self.clear_items()
        targets = self.get_targets()

        if targets:
            if not self.target or self.target not in targets:
                self.target = targets[0]

            options = []
            for t in targets[:25]:
                plat_code = t.get("platform", "youtube")
                p_name = "YouTube" if plat_code == "youtube" else ("TikTok" if plat_code == "tiktok" else "Instagram")
                d_name = t.get("display_name", t.get("identifier"))
                is_selected = (self.target and self.target.get("id") == t.get("id"))
                options.append(discord.SelectOption(
                    label=d_name[:80],
                    description=f"{p_name} ({t.get('identifier')[:40]})",
                    value=t.get("id", t.get("identifier")),
                    default=is_selected
                ))

            target_select = discord.ui.Select(
                placeholder="Pilih target yang ingin diatur",
                options=options,
                row=0
            )
            target_select.callback = self.target_select_callback
            self.add_item(target_select)

        if self.target:
            channel_select = discord.ui.ChannelSelect(
                channel_types=[discord.ChannelType.text],
                placeholder="Pilih kanal tujuan di Discord",
                min_values=1,
                max_values=1,
                row=1
            )
            channel_select.callback = self.channel_select_callback
            self.add_item(channel_select)

            btn_format = discord.ui.Button(label="Ubah Teks", style=discord.ButtonStyle.primary, row=2)
            btn_format.callback = self.btn_format_callback
            self.add_item(btn_format)

            use_card = self.target.get("use_card", True)
            card_lbl = "Gaya: Kartu" if use_card else "Gaya: Teks"
            btn_card = discord.ui.Button(label=card_lbl, style=discord.ButtonStyle.secondary, row=2)
            btn_card.callback = self.btn_card_callback
            self.add_item(btn_card)

            btn_test = discord.ui.Button(label="Tes Kirim", style=discord.ButtonStyle.success, row=2)
            btn_test.callback = self.btn_test_callback
            self.add_item(btn_test)

            is_active = self.target.get("enabled", True)
            status_lbl = "Status: Aktif" if is_active else "Status: Dijeda"
            btn_status = discord.ui.Button(label=status_lbl, style=discord.ButtonStyle.secondary, row=2)
            btn_status.callback = self.btn_status_callback
            self.add_item(btn_status)

            btn_delete = discord.ui.Button(label="Hapus", style=discord.ButtonStyle.danger, row=2)
            btn_delete.callback = self.btn_delete_callback
            self.add_item(btn_delete)

            btn_clearcache = discord.ui.Button(label="🧹 Bersihkan Cache", style=discord.ButtonStyle.secondary, row=3)
            btn_clearcache.callback = self.btn_clearcache_callback
            self.add_item(btn_clearcache)

    def build_embed(self) -> discord.Embed:
        if not self.target:
            embed = discord.Embed(
                title="Pengaturan Notifikasi Media Sosial",
                description="Belum ada channel atau akun yang dipantau.\nGunakan `/social add` untuk menambahkan pemantauan baru.",
                color=0x5865F2
            )
            return embed

        platform = self.target.get("platform", "youtube").capitalize()
        name = self.target.get("display_name", self.target.get("identifier"))
        ident = self.target.get("identifier")
        ch_id = self.target.get("target_channel_id")
        ch_str = f"<#{ch_id}>" if ch_id else "Belum diatur"

        content_val = self.target.get("content") or self.target.get("custom_template") or "@everyone {ai_hype}"
        title_tmpl = self.target.get("card_title") or "[{judul}]({url})"
        desc_tmpl = self.target.get("card_desc") or "{deskripsi}"
        target_plat = self.target.get("platform")
        if target_plat == "tiktok":
            default_btn = "Buka di TikTok"
        elif target_plat == "instagram":
            default_btn = "Buka di Instagram"
        else:
            default_btn = "Tonton di YouTube"
        btn_label = self.target.get("button_label") or default_btn
        use_card = self.target.get("use_card", True)
        card_status = "Kartu" if use_card else "Teks biasa"
        is_enabled = self.target.get("enabled", True)
        status_str = "Aktif" if is_enabled else "Dijeda"

        embed = discord.Embed(
            title=f"Pengaturan Notifikasi {platform}: {name}",
            description=(
                f"**ID Target:** `{ident}`\n"
                f"**Status:** {status_str}\n"
                f"**Kanal Tujuan:** {ch_str}\n"
                f"**Gaya Tampilan:** `{card_status}`\n\n"
                f"**Isi Pesan Biasa:**\n> {content_val}\n\n"
                f"**Judul Utama:**\n> `{title_tmpl}`\n"
                f"**Deskripsi Utama:**\n> `{desc_tmpl}`\n"
                f"**Label Tombol:** `{btn_label}`"
            ),
            color=0x00F2FE if self.target.get("platform") == "tiktok" else 0xFF0000
        )
        embed.set_footer(text="Gunakan tombol di bawah untuk mengubah setelan.")
        return embed

    async def target_select_callback(self, interaction: discord.Interaction):
        selected_val = interaction.data["values"][0]
        targets = self.get_targets()
        found = next((t for t in targets if t.get("id") == selected_val or t.get("identifier") == selected_val), None)
        if found:
            self.target = found
            self.update_components()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def channel_select_callback(self, interaction: discord.Interaction):
        selected_channel_id = int(interaction.data["values"][0])
        self.target["target_channel_id"] = selected_channel_id
        if interaction.guild:
            self.target["target_guild_id"] = interaction.guild.id
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_format_callback(self, interaction: discord.Interaction):
        modal = SocialFormatEditorModal(self.cog, self.target, self.author, self)
        await interaction.response.send_modal(modal)

    async def btn_card_callback(self, interaction: discord.Interaction):
        curr = self.target.get("use_card", True)
        self.target["use_card"] = not curr
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_status_callback(self, interaction: discord.Interaction):
        curr = self.target.get("enabled", True)
        self.target["enabled"] = not curr
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_test_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ch_id = self.target.get("target_channel_id")
        ch = interaction.guild.get_channel(ch_id) if ch_id and interaction.guild else None
        if not ch:
            return await interaction.followup.send("Kanal tujuan belum diatur atau tidak ditemukan.", ephemeral=True)

        plat = self.target.get("platform", "youtube")
        d_name = self.target.get("display_name", self.target.get("identifier"))
        if plat == "tiktok":
            target_ident = normalize_tiktok_username(self.target.get("identifier"))
            sample_url = f"https://www.tiktok.com/@{target_ident}"
            sample_thumb = "https://images.unsplash.com/photo-1611162618071-b39a2ec055fb?w=800"
        elif plat == "instagram":
            target_ident = normalize_instagram_username(self.target.get("identifier"))
            sample_url = f"https://www.instagram.com/{target_ident}/"
            sample_thumb = "https://images.unsplash.com/photo-1611262588024-d12430b98920?w=800"
        else:
            sample_url = "https://www.youtube.com"
            sample_thumb = "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800"
        sample_item = {
            "video_id": "test_sample_" + str(uuid.uuid4())[:6],
            "title": f"Uji Coba Konten {d_name}",
            "description": "Pesan uji coba notifikasi otomatis. Pengaturan berhasil disimpan.",
            "url": sample_url,
            "thumbnail": sample_thumb,
            "published": datetime.now(timezone.utc).isoformat(),
            "uploader": d_name,
            "duration": "01:00",
            "is_live": False
        }

        success = await self.cog._send_content_card(self.target, sample_item)
        if success:
            await interaction.followup.send(f"Notifikasi uji coba berhasil dikirim ke {ch.mention}.", ephemeral=True)
        else:
            await interaction.followup.send(f"Gagal mengirim notifikasi uji coba ke {ch.mention}.", ephemeral=True)

    async def btn_delete_callback(self, interaction: discord.Interaction):
        t_id = self.target.get("id") or self.target.get("identifier")
        d_name = self.target.get("display_name", self.target.get("identifier"))
        self.cog.config["targets"] = [t for t in self.cog.config.get("targets", []) if (t.get("id") != t_id and t.get("identifier") != t_id)]
        self.cog._save_config()
        self.target = None
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        await interaction.followup.send(f"Pemantauan untuk {d_name} berhasil dihapus.", ephemeral=True)

    async def btn_clearcache_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        plat = self.target.get("platform")
        ident = self.target.get("identifier")
        d_name = self.target.get("display_name", ident)
        count = await self.cog._clear_target_cache(plat, ident)
        await interaction.followup.send(
            f"🧹 Berhasil membersihkan **{count}** cache riwayat untuk **{d_name}** ({plat.capitalize()})!\n"
            f"Pemeriksaan berikutnya akan mendeteksi ulang postingan/konten terbaru.",
            ephemeral=True
        )


class InstagramAddAccountModal(discord.ui.Modal, title="Tambah Akun Instagram"):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, parent_view):
        super().__init__()
        self.cog = cog
        self.guild = guild
        self.author = author
        self.parent_view = parent_view

        self.username_input = discord.ui.TextInput(
            label="Username Akun Instagram",
            placeholder="Contoh: coretan_recehhh (tanpa @ atau link)",
            max_length=60,
            required=True
        )
        self.add_item(self.username_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        raw_user = self.username_input.value.strip()
        clean_user = await async_resolve_instagram_username(raw_user)
        if not clean_user:
            return await interaction.followup.send("Nama pengguna Instagram tidak valid atau tidak ditemukan.", ephemeral=True)

        found_existing = None
        for t in self.cog.config.get("targets", []):
            if t.get("platform") == "instagram" and t.get("identifier", "").lower() == clean_user.lower():
                found_existing = t
                break

        if found_existing:
            self.parent_view.target = found_existing
            self.parent_view.update_components()
            await interaction.followup.send(f"Akun **@{clean_user}** sudah terdaftar dalam pemantauan.", ephemeral=True)
            return

        new_target = {
            "id": str(uuid.uuid4())[:8],
            "platform": "instagram",
            "identifier": clean_user,
            "display_name": clean_user,
            "target_guild_id": self.guild.id if self.guild else None,
            "target_channel_id": interaction.channel_id,
            "content": "@everyone {ai_hype}",
            "custom_template": "@everyone {ai_hype}",
            "card_title": "[{judul}]({url})",
            "card_desc": "{deskripsi}",
            "button_label": None,
            "use_card": True,
            "enabled": True,
            "feed_enabled": True,
            "reels_enabled": True,
            "stories_enabled": True,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        self.cog.config["targets"].append(new_target)
        self.cog._save_config()

        current_items = await self.cog._fetch_instagram_content(clean_user)
        for it in current_items:
            if it.get("creator") and new_target.get("display_name") == clean_user:
                new_target["display_name"] = it["creator"]
            if not it.get("is_story") and it["video_id"] not in self.cog.cache["posted_ids"]:
                self.cog.cache["posted_ids"].append(it["video_id"])
        self.cog._save_config()
        self.cog._save_cache()

        self.parent_view.target = new_target
        self.parent_view.update_components()
        await interaction.edit_original_response(embed=self.parent_view.build_embed(), view=self.parent_view)
        await interaction.followup.send(f"Berhasil menambahkan akun Instagram **@{clean_user}**!", ephemeral=True)


class InstagramStudioView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, initial_target: Optional[dict] = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.target = initial_target
        self.update_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Menu konfigurasi ini hanya dapat diakses oleh pemanggil.", ephemeral=True)
            return False
        return True

    def get_targets(self) -> list:
        targets = [t for t in self.cog.config.get("targets", []) if t.get("platform") == "instagram"]
        if self.guild:
            g_targets = [t for t in targets if t.get("target_guild_id") == self.guild.id]
            if g_targets:
                return g_targets
        return targets

    def update_components(self):
        self.clear_items()
        targets = self.get_targets()

        if targets:
            if not self.target or self.target not in targets:
                self.target = targets[0]

            options = []
            for t in targets[:25]:
                d_name = t.get("display_name", t.get("identifier"))
                ident = t.get("identifier")
                feed_st = "F:ON" if t.get("feed_enabled", True) else "F:OFF"
                reel_st = "R:ON" if t.get("reels_enabled", True) else "R:OFF"
                story_st = "S:ON" if t.get("stories_enabled", True) else "S:OFF"
                desc = f"@{ident} ({feed_st} | {reel_st} | {story_st})"
                is_selected = (self.target and self.target.get("id") == t.get("id"))
                options.append(discord.SelectOption(
                    label=d_name[:80],
                    description=desc[:100],
                    value=t.get("id", ident),
                    default=is_selected,
                    emoji="📸"
                ))

            target_select = discord.ui.Select(
                placeholder="Pilih Akun Instagram yang Ingin Diatur",
                options=options,
                row=0
            )
            target_select.callback = self.target_select_callback
            self.add_item(target_select)

        if self.target:
            channel_select = discord.ui.ChannelSelect(
                channel_types=[discord.ChannelType.text],
                placeholder="Pilih Kanal Discord untuk Notifikasi",
                min_values=1,
                max_values=1,
                row=1
            )
            channel_select.callback = self.channel_select_callback
            self.add_item(channel_select)

            feed_active = self.target.get("feed_enabled", True)
            btn_feed = discord.ui.Button(
                label=f"📸 Feed: {'AKTIF' if feed_active else 'MATI'}",
                style=discord.ButtonStyle.success if feed_active else discord.ButtonStyle.secondary,
                row=2
            )
            btn_feed.callback = self.btn_feed_callback
            self.add_item(btn_feed)

            reels_active = self.target.get("reels_enabled", True)
            btn_reels = discord.ui.Button(
                label=f"🎬 Reels: {'AKTIF' if reels_active else 'MATI'}",
                style=discord.ButtonStyle.success if reels_active else discord.ButtonStyle.secondary,
                row=2
            )
            btn_reels.callback = self.btn_reels_callback
            self.add_item(btn_reels)

            stories_active = self.target.get("stories_enabled", True)
            btn_stories = discord.ui.Button(
                label=f"⏳ Story: {'AKTIF' if stories_active else 'MATI'}",
                style=discord.ButtonStyle.success if stories_active else discord.ButtonStyle.secondary,
                row=2
            )
            btn_stories.callback = self.btn_stories_callback
            self.add_item(btn_stories)

            use_card = self.target.get("use_card", True)
            btn_card = discord.ui.Button(
                label=f"🎨 Gaya: {'Kartu' if use_card else 'Teks'}",
                style=discord.ButtonStyle.secondary,
                row=3
            )
            btn_card.callback = self.btn_card_callback
            self.add_item(btn_card)

            btn_format = discord.ui.Button(
                label="✏️ Edit Pesan",
                style=discord.ButtonStyle.secondary,
                row=3
            )
            btn_format.callback = self.btn_format_callback
            self.add_item(btn_format)

            is_active = self.target.get("enabled", True)
            btn_status = discord.ui.Button(
                label=f"⏸️ {'Status: Aktif' if is_active else 'Status: Dijeda'}",
                style=discord.ButtonStyle.success if is_active else discord.ButtonStyle.secondary,
                row=3
            )
            btn_status.callback = self.btn_status_callback
            self.add_item(btn_status)

            btn_test = discord.ui.Button(
                label="🧪 Tes Kirim",
                style=discord.ButtonStyle.primary,
                row=3
            )
            btn_test.callback = self.btn_test_callback
            self.add_item(btn_test)

            btn_add = discord.ui.Button(
                label="➕ Tambah Akun",
                style=discord.ButtonStyle.success,
                row=4
            )
            btn_add.callback = self.btn_add_callback
            self.add_item(btn_add)

            btn_delete = discord.ui.Button(
                label="🗑️ Hapus Akun",
                style=discord.ButtonStyle.danger,
                row=4
            )
            btn_delete.callback = self.btn_delete_callback
            self.add_item(btn_delete)

            btn_clearcache = discord.ui.Button(
                label="🧹 Bersihkan Cache",
                style=discord.ButtonStyle.secondary,
                row=4
            )
            btn_clearcache.callback = self.btn_clearcache_callback
            self.add_item(btn_clearcache)
        else:
            btn_add = discord.ui.Button(
                label="➕ Tambah Akun Instagram Baru",
                style=discord.ButtonStyle.success,
                row=0
            )
            btn_add.callback = self.btn_add_callback
            self.add_item(btn_add)

    def build_embed(self) -> discord.Embed:
        if not self.target:
            embed = discord.Embed(
                title="📸 Studio Konfigurasi Instagram",
                description="Belum ada akun Instagram yang dipantau di server ini.\nKlik tombol **➕ Tambah Akun Instagram Baru** di bawah untuk mulai memantau.",
                color=0xE1306C
            )
            return embed

        name = self.target.get("display_name", self.target.get("identifier"))
        ident = self.target.get("identifier")
        ch_id = self.target.get("target_channel_id")
        ch_str = f"<#{ch_id}>" if ch_id else "*(Belum diatur)*"

        feed_st = "🟢 Aktif" if self.target.get("feed_enabled", True) else "🔴 Mati"
        reels_st = "🟢 Aktif" if self.target.get("reels_enabled", True) else "🔴 Mati"
        stories_st = "🟢 Aktif" if self.target.get("stories_enabled", True) else "🔴 Mati"

        content_val = self.target.get("content") or self.target.get("custom_template") or "@everyone {ai_hype}"
        card_st = "Kartu" if self.target.get("use_card", True) else "Teks Biasa"
        is_active = self.target.get("enabled", True)
        status_st = "🟢 Berjalan (Aktif)" if is_active else "⏸️ Dijeda"
        card_title = self.target.get("card_title", "[{judul}]({url})")
        card_desc = self.target.get("card_desc", "{deskripsi}")

        embed = discord.Embed(
            title=f"📸 All-in-One Studio Instagram: @{ident}",
            description=(
                f"**Nama Akun:** **{name}**\n"
                f"**Status Pemantauan:** {status_st}\n"
                f"**Kanal Tujuan Discord:** {ch_str}\n"
                f"**Gaya Tampilan Pesan:** `{card_st}`\n\n"
                f"**Filter Konten:**\n"
                f"• 📸 Postingan Feed (Foto/Album): **{feed_st}**\n"
                f"• 🎬 Reels Video: **{reels_st}**\n"
                f"• ⏳ Story (24 Jam): **{stories_st}**\n\n"
                f"**Pesan Notifikasi:**\n"
                f"• 💬 Format Pesan: `{content_val}`\n"
                f"• 🏷️ Pola Judul: `{card_title}`\n"
                f"• 📝 Pola Deskripsi: `{card_desc}`"
            ),
            color=0xE1306C
        )
        embed.set_footer(text="Gunakan tombol di bawah. Klik 'Edit Pesan' untuk mengatur teks, mention, dan AI Hype.")
        return embed

    async def target_select_callback(self, interaction: discord.Interaction):
        selected_val = interaction.data["values"][0]
        targets = self.get_targets()
        found = next((t for t in targets if t.get("id") == selected_val or t.get("identifier") == selected_val), None)
        if found:
            self.target = found
            self.update_components()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def channel_select_callback(self, interaction: discord.Interaction):
        selected_channel_id = int(interaction.data["values"][0])
        self.target["target_channel_id"] = selected_channel_id
        if interaction.guild:
            self.target["target_guild_id"] = interaction.guild.id
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_feed_callback(self, interaction: discord.Interaction):
        curr = self.target.get("feed_enabled", True)
        self.target["feed_enabled"] = not curr
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_reels_callback(self, interaction: discord.Interaction):
        curr = self.target.get("reels_enabled", True)
        self.target["reels_enabled"] = not curr
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_stories_callback(self, interaction: discord.Interaction):
        curr = self.target.get("stories_enabled", True)
        self.target["stories_enabled"] = not curr
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_card_callback(self, interaction: discord.Interaction):
        curr = self.target.get("use_card", True)
        self.target["use_card"] = not curr
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_status_callback(self, interaction: discord.Interaction):
        curr = self.target.get("enabled", True)
        self.target["enabled"] = not curr
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_format_callback(self, interaction: discord.Interaction):
        modal = SocialFormatEditorModal(self.cog, self.target, self.author, self)
        await interaction.response.send_modal(modal)

    async def btn_add_callback(self, interaction: discord.Interaction):
        modal = InstagramAddAccountModal(self.cog, self.guild, self.author, self)
        await interaction.response.send_modal(modal)

    async def btn_delete_callback(self, interaction: discord.Interaction):
        t_id = self.target.get("id") or self.target.get("identifier")
        d_name = self.target.get("display_name", self.target.get("identifier"))
        self.cog.config["targets"] = [t for t in self.cog.config.get("targets", []) if (t.get("id") != t_id and t.get("identifier") != t_id)]
        self.cog._save_config()
        self.target = None
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        await interaction.followup.send(f"Akun Instagram **{d_name}** berhasil dihapus dari pemantauan.", ephemeral=True)

    async def btn_test_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ch_id = self.target.get("target_channel_id")
        ch = interaction.guild.get_channel(ch_id) if ch_id and interaction.guild else None
        if not ch:
            return await interaction.followup.send("Kanal tujuan belum diatur atau tidak ditemukan di server ini.", ephemeral=True)

        clean_user = self.target.get("identifier")
        items = await self.cog._fetch_instagram_content(clean_user)
        test_item = items[0] if items else None
        if not test_item:
            test_item = {
                "video_id": f"test_ig_{clean_user}",
                "shortcode": "test",
                "title": f"Postingan Terbaru @{clean_user}",
                "creator": self.target.get("display_name", clean_user),
                "url": f"https://www.instagram.com/{clean_user}/",
                "thumbnail": "https://images.unsplash.com/photo-1611162616305-c69b3fa7fbe0?w=800",
                "description": f"Halo semua! Ini adalah simulasi uji coba notifikasi Instagram untuk akun @{clean_user}.",
                "is_live": False,
                "is_story": False,
                "is_reel": False,
                "force_test": True,
            }
        else:
            test_item = dict(test_item)
            test_item["force_test"] = True

        sent = await self.cog._send_content_card(self.target, test_item)
        if sent:
            await interaction.followup.send(f"Berhasil mengirimkan preview notifikasi ke {ch.mention}!", ephemeral=True)
        else:
            await interaction.followup.send(f"Gagal mengirim preview ke {ch.mention}. Pastikan izin bot mencukupi.", ephemeral=True)

    async def btn_clearcache_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ident = self.target.get("identifier")
        d_name = self.target.get("display_name", ident)
        count = await self.cog._clear_target_cache("instagram", ident)
        await interaction.followup.send(
            f"🧹 Berhasil membersihkan **{count}** cache riwayat untuk Instagram **@{d_name}**!\n"
            f"Pemeriksaan berikutnya akan otomatis mendeteksi ulang postingan/story terbaru.",
            ephemeral=True
        )


class TikTokAddAccountModal(discord.ui.Modal, title="Tambah Akun TikTok"):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, parent_view):
        super().__init__()
        self.cog = cog
        self.guild = guild
        self.author = author
        self.parent_view = parent_view

        self.username_input = discord.ui.TextInput(
            label="Username / Link Akun TikTok",
            placeholder="Contoh: @khaby.lame atau https://www.tiktok.com/@khaby.lame",
            max_length=100,
            required=True
        )
        self.add_item(self.username_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        raw_user = self.username_input.value.strip()
        clean_user = await async_resolve_tiktok_username(raw_user)
        if not clean_user:
            return await interaction.followup.send("Nama pengguna atau tautan akun TikTok tidak valid.", ephemeral=True)

        found_existing = None
        for t in self.cog.config.get("targets", []):
            if t.get("platform") == "tiktok" and t.get("identifier", "").lower() == clean_user.lower():
                found_existing = t
                break

        if found_existing:
            self.parent_view.target = found_existing
            self.parent_view.update_components()
            await interaction.followup.send(f"Akun TikTok **@{clean_user}** sudah terdaftar dalam pemantauan.", ephemeral=True)
            return

        new_target = {
            "id": str(uuid.uuid4())[:8],
            "platform": "tiktok",
            "identifier": clean_user,
            "display_name": clean_user,
            "sec_uid": None,
            "target_guild_id": self.guild.id if self.guild else None,
            "target_channel_id": interaction.channel_id,
            "content": "@everyone {ai_hype}",
            "custom_template": "@everyone {ai_hype}",
            "card_title": "[{judul}]({url})",
            "card_desc": "{deskripsi}",
            "button_label": None,
            "use_card": True,
            "enabled": True,
            "video_enabled": True,
            "live_enabled": True,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        self.cog.config["targets"].append(new_target)
        self.cog._save_config()

        current_items = await self.cog._fetch_tiktok_content(clean_user)
        for it in current_items:
            if it.get("sec_uid") and not new_target.get("sec_uid"):
                new_target["sec_uid"] = it["sec_uid"]
            if it.get("creator") and new_target.get("display_name") == clean_user:
                new_target["display_name"] = it["creator"]
            if not it.get("is_live") and it["video_id"] not in self.cog.cache["posted_ids"]:
                self.cog.cache["posted_ids"].append(it["video_id"])
        self.cog._save_config()
        self.cog._save_cache()

        self.parent_view.target = new_target
        self.parent_view.update_components()
        await interaction.edit_original_response(embed=self.parent_view.build_embed(), view=self.parent_view)
        await interaction.followup.send(f"Berhasil menambahkan akun TikTok **@{clean_user}**!", ephemeral=True)


class TikTokStudioView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, initial_target: Optional[dict] = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.target = initial_target
        self.update_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Menu konfigurasi ini hanya dapat diakses oleh pemanggil.", ephemeral=True)
            return False
        return True

    def get_targets(self) -> list:
        targets = [t for t in self.cog.config.get("targets", []) if t.get("platform") == "tiktok"]
        if self.guild:
            g_targets = [t for t in targets if t.get("target_guild_id") == self.guild.id]
            if g_targets:
                return g_targets
        return targets

    def update_components(self):
        self.clear_items()
        targets = self.get_targets()

        if targets:
            if not self.target or self.target not in targets:
                self.target = targets[0]

            options = []
            for t in targets[:25]:
                d_name = t.get("display_name", t.get("identifier"))
                ident = t.get("identifier")
                vid_st = "V:ON" if t.get("video_enabled", True) else "V:OFF"
                live_st = "L:ON" if t.get("live_enabled", True) else "L:OFF"
                desc = f"@{ident} ({vid_st} | {live_st})"
                is_selected = (self.target and self.target.get("id") == t.get("id"))
                options.append(discord.SelectOption(
                    label=d_name[:80],
                    description=desc[:100],
                    value=t.get("id", ident),
                    default=is_selected,
                    emoji="🎵"
                ))

            target_select = discord.ui.Select(
                placeholder="Pilih Akun TikTok yang Ingin Diatur",
                options=options,
                row=0
            )
            target_select.callback = self.target_select_callback
            self.add_item(target_select)

        if self.target:
            channel_select = discord.ui.ChannelSelect(
                channel_types=[discord.ChannelType.text],
                placeholder="Pilih Kanal Discord untuk Notifikasi",
                min_values=1,
                max_values=1,
                row=1
            )
            channel_select.callback = self.channel_select_callback
            self.add_item(channel_select)

            video_active = self.target.get("video_enabled", True)
            btn_video = discord.ui.Button(
                label=f"🎬 Video: {'AKTIF' if video_active else 'MATI'}",
                style=discord.ButtonStyle.success if video_active else discord.ButtonStyle.secondary,
                row=2
            )
            btn_video.callback = self.btn_video_callback
            self.add_item(btn_video)

            live_active = self.target.get("live_enabled", True)
            btn_live = discord.ui.Button(
                label=f"🔴 Live: {'AKTIF' if live_active else 'MATI'}",
                style=discord.ButtonStyle.success if live_active else discord.ButtonStyle.secondary,
                row=2
            )
            btn_live.callback = self.btn_live_callback
            self.add_item(btn_live)

            use_card = self.target.get("use_card", True)
            btn_card = discord.ui.Button(
                label=f"🎨 Gaya: {'Kartu' if use_card else 'Teks'}",
                style=discord.ButtonStyle.secondary,
                row=3
            )
            btn_card.callback = self.btn_card_callback
            self.add_item(btn_card)

            btn_format = discord.ui.Button(
                label="✏️ Edit Pesan",
                style=discord.ButtonStyle.secondary,
                row=3
            )
            btn_format.callback = self.btn_format_callback
            self.add_item(btn_format)

            is_active = self.target.get("enabled", True)
            btn_status = discord.ui.Button(
                label=f"⏸️ {'Status: Aktif' if is_active else 'Status: Dijeda'}",
                style=discord.ButtonStyle.success if is_active else discord.ButtonStyle.secondary,
                row=3
            )
            btn_status.callback = self.btn_status_callback
            self.add_item(btn_status)

            btn_test = discord.ui.Button(
                label="🧪 Tes Kirim",
                style=discord.ButtonStyle.primary,
                row=3
            )
            btn_test.callback = self.btn_test_callback
            self.add_item(btn_test)

            btn_add = discord.ui.Button(
                label="➕ Tambah Akun",
                style=discord.ButtonStyle.success,
                row=4
            )
            btn_add.callback = self.btn_add_callback
            self.add_item(btn_add)

            btn_delete = discord.ui.Button(
                label="🗑️ Hapus Akun",
                style=discord.ButtonStyle.danger,
                row=4
            )
            btn_delete.callback = self.btn_delete_callback
            self.add_item(btn_delete)

            btn_clearcache = discord.ui.Button(
                label="🧹 Bersihkan Cache",
                style=discord.ButtonStyle.secondary,
                row=4
            )
            btn_clearcache.callback = self.btn_clearcache_callback
            self.add_item(btn_clearcache)
        else:
            btn_add = discord.ui.Button(
                label="➕ Tambah Akun TikTok Baru",
                style=discord.ButtonStyle.success,
                row=0
            )
            btn_add.callback = self.btn_add_callback
            self.add_item(btn_add)

    def build_embed(self) -> discord.Embed:
        if not self.target:
            embed = discord.Embed(
                title="🎵 Studio Konfigurasi TikTok",
                description="Belum ada akun TikTok yang dipantau di server ini.\nKlik tombol **➕ Tambah Akun TikTok Baru** di bawah untuk mulai memantau.",
                color=0x00F2FE
            )
            return embed

        name = self.target.get("display_name", self.target.get("identifier"))
        ident = self.target.get("identifier")
        ch_id = self.target.get("target_channel_id")
        ch_str = f"<#{ch_id}>" if ch_id else "*(Belum diatur)*"

        video_st = "🟢 Aktif" if self.target.get("video_enabled", True) else "🔴 Mati"
        live_st = "🟢 Aktif" if self.target.get("live_enabled", True) else "🔴 Mati"

        content_val = self.target.get("content") or self.target.get("custom_template") or "@everyone {ai_hype}"
        card_st = "Kartu" if self.target.get("use_card", True) else "Teks Biasa"
        is_active = self.target.get("enabled", True)
        status_st = "🟢 Berjalan (Aktif)" if is_active else "⏸️ Dijeda"
        card_title = self.target.get("card_title", "[{judul}]({url})")
        card_desc = self.target.get("card_desc", "{deskripsi}")

        embed = discord.Embed(
            title=f"🎵 All-in-One Studio TikTok: @{ident}",
            description=(
                f"**Nama Akun:** **{name}**\n"
                f"**Status Pemantauan:** {status_st}\n"
                f"**Kanal Tujuan Discord:** {ch_str}\n"
                f"**Gaya Tampilan Pesan:** `{card_st}`\n\n"
                f"**Filter Konten:**\n"
                f"• 🎬 Video Feed: **{video_st}**\n"
                f"• 🔴 Live Streaming: **{live_st}**\n\n"
                f"**Pesan Notifikasi:**\n"
                f"• 💬 Format Pesan: `{content_val}`\n"
                f"• 🏷️ Pola Judul: `{card_title}`\n"
                f"• 📝 Pola Deskripsi: `{card_desc}`"
            ),
            color=0x00F2FE
        )
        embed.set_footer(text="Gunakan tombol di bawah. Klik 'Edit Pesan' untuk mengatur teks, mention, dan AI Hype.")
        return embed

    async def target_select_callback(self, interaction: discord.Interaction):
        selected_val = interaction.data["values"][0]
        targets = self.get_targets()
        found = next((t for t in targets if t.get("id") == selected_val or t.get("identifier") == selected_val), None)
        if found:
            self.target = found
            self.update_components()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def channel_select_callback(self, interaction: discord.Interaction):
        selected_channel_id = int(interaction.data["values"][0])
        self.target["target_channel_id"] = selected_channel_id
        if interaction.guild:
            self.target["target_guild_id"] = interaction.guild.id
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_video_callback(self, interaction: discord.Interaction):
        curr = self.target.get("video_enabled", True)
        self.target["video_enabled"] = not curr
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_live_callback(self, interaction: discord.Interaction):
        curr = self.target.get("live_enabled", True)
        self.target["live_enabled"] = not curr
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_card_callback(self, interaction: discord.Interaction):
        curr = self.target.get("use_card", True)
        self.target["use_card"] = not curr
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_status_callback(self, interaction: discord.Interaction):
        curr = self.target.get("enabled", True)
        self.target["enabled"] = not curr
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_format_callback(self, interaction: discord.Interaction):
        modal = SocialFormatEditorModal(self.cog, self.target, self.author, self)
        await interaction.response.send_modal(modal)

    async def btn_add_callback(self, interaction: discord.Interaction):
        modal = TikTokAddAccountModal(self.cog, self.guild, self.author, self)
        await interaction.response.send_modal(modal)

    async def btn_delete_callback(self, interaction: discord.Interaction):
        t_id = self.target.get("id") or self.target.get("identifier")
        d_name = self.target.get("display_name", self.target.get("identifier"))
        self.cog.config["targets"] = [t for t in self.cog.config.get("targets", []) if (t.get("id") != t_id and t.get("identifier") != t_id)]
        self.cog._save_config()
        self.target = None
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        await interaction.followup.send(f"Akun TikTok **{d_name}** berhasil dihapus dari pemantauan.", ephemeral=True)

    async def btn_test_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ch_id = self.target.get("target_channel_id")
        ch = interaction.guild.get_channel(ch_id) if ch_id and interaction.guild else None
        if not ch:
            return await interaction.followup.send("Kanal tujuan belum diatur atau tidak ditemukan di server ini.", ephemeral=True)

        clean_user = self.target.get("identifier")
        items = await self.cog._fetch_tiktok_content(clean_user, self.target.get("sec_uid"))
        test_item = items[0] if items else None
        if not test_item:
            test_item = {
                "video_id": f"test_tt_{clean_user}",
                "title": f"Video Terbaru @{clean_user}",
                "description": f"Halo semua! Ini adalah simulasi uji coba notifikasi TikTok untuk akun @{clean_user}.",
                "creator": self.target.get("display_name", clean_user),
                "url": f"https://www.tiktok.com/@{clean_user}",
                "thumbnail": "https://images.unsplash.com/photo-1611162618071-b39a2ec055fb?w=800",
                "is_live": False,
                "force_test": True,
            }
        else:
            test_item = dict(test_item)
            test_item["force_test"] = True

        sent = await self.cog._send_content_card(self.target, test_item)
        if sent:
            await interaction.followup.send(f"Berhasil mengirimkan preview notifikasi ke {ch.mention}!", ephemeral=True)
        else:
            await interaction.followup.send(f"Gagal mengirim preview ke {ch.mention}. Pastikan izin bot mencukupi.", ephemeral=True)

    async def btn_clearcache_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ident = self.target.get("identifier")
        d_name = self.target.get("display_name", ident)
        count = await self.cog._clear_target_cache("tiktok", ident)
        await interaction.followup.send(
            f"🧹 Berhasil membersihkan **{count}** cache riwayat untuk TikTok **@{d_name}**!\n"
            f"Pemeriksaan berikutnya akan otomatis mendeteksi ulang video/live terbaru.",
            ephemeral=True
        )


class YouTubeAddAccountModal(discord.ui.Modal, title="Tambah Channel YouTube"):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, parent_view):
        super().__init__()
        self.cog = cog
        self.guild = guild
        self.author = author
        self.parent_view = parent_view

        self.channel_input = discord.ui.TextInput(
            label="Channel ID / Handle / Link YouTube",
            placeholder="Contoh: @MrBeast, UCX6OQ3DkcsbYNE6H8uQQuVA, atau link channel",
            max_length=150,
            required=True
        )
        self.add_item(self.channel_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        raw_ident = self.channel_input.value.strip()
        cid, name = await self.cog._resolve_youtube_channel(raw_ident)
        if not cid:
            return await interaction.followup.send("Channel YouTube tidak valid atau tidak ditemukan.", ephemeral=True)

        found_existing = None
        for t in self.cog.config.get("targets", []):
            if t.get("platform") == "youtube" and t.get("identifier") == cid:
                found_existing = t
                break

        if found_existing:
            self.parent_view.target = found_existing
            self.parent_view.update_components()
            await interaction.followup.send(f"Channel **{name}** (`{cid}`) sudah terdaftar dalam pemantauan.", ephemeral=True)
            return

        new_target = {
            "id": str(uuid.uuid4())[:8],
            "platform": "youtube",
            "identifier": cid,
            "display_name": name,
            "target_guild_id": self.guild.id if self.guild else None,
            "target_channel_id": interaction.channel_id,
            "content": "@everyone {ai_hype}",
            "custom_template": "@everyone {ai_hype}",
            "card_title": "[{judul}]({url})",
            "card_desc": "{deskripsi}",
            "button_label": None,
            "use_card": True,
            "enabled": True,
            "video_enabled": True,
            "live_enabled": True,
            "shorts_enabled": True,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        self.cog.config["targets"].append(new_target)
        self.cog._save_config()

        current_items = await self.cog._fetch_youtube_content(cid)
        for it in current_items:
            if not it.get("is_live") and it["video_id"] not in self.cog.cache["posted_ids"]:
                self.cog.cache["posted_ids"].append(it["video_id"])
        self.cog._save_cache()

        self.parent_view.target = new_target
        self.parent_view.update_components()
        await interaction.edit_original_response(embed=self.parent_view.build_embed(), view=self.parent_view)
        await interaction.followup.send(f"Berhasil menambahkan channel YouTube **{name}**!", ephemeral=True)


class YouTubeStudioView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, initial_target: Optional[dict] = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.target = initial_target
        self.update_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Menu konfigurasi ini hanya dapat diakses oleh pemanggil.", ephemeral=True)
            return False
        return True

    def get_targets(self) -> list:
        targets = [t for t in self.cog.config.get("targets", []) if t.get("platform") == "youtube"]
        if self.guild:
            g_targets = [t for t in targets if t.get("target_guild_id") == self.guild.id]
            if g_targets:
                return g_targets
        return targets

    def update_components(self):
        self.clear_items()
        targets = self.get_targets()

        if targets:
            if not self.target or self.target not in targets:
                self.target = targets[0]

            options = []
            for t in targets[:25]:
                d_name = t.get("display_name", t.get("identifier"))
                ident = t.get("identifier")
                vid_st = "V:ON" if t.get("video_enabled", True) else "V:OFF"
                live_st = "L:ON" if t.get("live_enabled", True) else "L:OFF"
                short_st = "S:ON" if t.get("shorts_enabled", True) else "S:OFF"
                desc = f"{ident[:30]} ({vid_st} | {live_st} | {short_st})"
                is_selected = (self.target and self.target.get("id") == t.get("id"))
                options.append(discord.SelectOption(
                    label=d_name[:80],
                    description=desc[:100],
                    value=t.get("id", ident),
                    default=is_selected,
                    emoji="▶️"
                ))

            target_select = discord.ui.Select(
                placeholder="Pilih Channel YouTube yang Ingin Diatur",
                options=options,
                row=0
            )
            target_select.callback = self.target_select_callback
            self.add_item(target_select)

        if self.target:
            channel_select = discord.ui.ChannelSelect(
                channel_types=[discord.ChannelType.text],
                placeholder="Pilih Kanal Discord untuk Notifikasi",
                min_values=1,
                max_values=1,
                row=1
            )
            channel_select.callback = self.channel_select_callback
            self.add_item(channel_select)

            video_active = self.target.get("video_enabled", True)
            btn_video = discord.ui.Button(
                label=f"📹 Video: {'AKTIF' if video_active else 'MATI'}",
                style=discord.ButtonStyle.success if video_active else discord.ButtonStyle.secondary,
                row=2
            )
            btn_video.callback = self.btn_video_callback
            self.add_item(btn_video)

            live_active = self.target.get("live_enabled", True)
            btn_live = discord.ui.Button(
                label=f"🔴 Live: {'AKTIF' if live_active else 'MATI'}",
                style=discord.ButtonStyle.success if live_active else discord.ButtonStyle.secondary,
                row=2
            )
            btn_live.callback = self.btn_live_callback
            self.add_item(btn_live)

            shorts_active = self.target.get("shorts_enabled", True)
            btn_shorts = discord.ui.Button(
                label=f"⚡ Shorts: {'AKTIF' if shorts_active else 'MATI'}",
                style=discord.ButtonStyle.success if shorts_active else discord.ButtonStyle.secondary,
                row=2
            )
            btn_shorts.callback = self.btn_shorts_callback
            self.add_item(btn_shorts)

            use_card = self.target.get("use_card", True)
            btn_card = discord.ui.Button(
                label=f"🎨 Gaya: {'Kartu' if use_card else 'Teks'}",
                style=discord.ButtonStyle.secondary,
                row=3
            )
            btn_card.callback = self.btn_card_callback
            self.add_item(btn_card)

            btn_format = discord.ui.Button(
                label="✏️ Edit Pesan",
                style=discord.ButtonStyle.secondary,
                row=3
            )
            btn_format.callback = self.btn_format_callback
            self.add_item(btn_format)

            is_active = self.target.get("enabled", True)
            btn_status = discord.ui.Button(
                label=f"⏸️ {'Status: Aktif' if is_active else 'Status: Dijeda'}",
                style=discord.ButtonStyle.success if is_active else discord.ButtonStyle.secondary,
                row=3
            )
            btn_status.callback = self.btn_status_callback
            self.add_item(btn_status)

            btn_test = discord.ui.Button(
                label="🧪 Tes Kirim",
                style=discord.ButtonStyle.primary,
                row=3
            )
            btn_test.callback = self.btn_test_callback
            self.add_item(btn_test)

            btn_add = discord.ui.Button(
                label="➕ Tambah Channel",
                style=discord.ButtonStyle.success,
                row=4
            )
            btn_add.callback = self.btn_add_callback
            self.add_item(btn_add)

            btn_delete = discord.ui.Button(
                label="🗑️ Hapus Channel",
                style=discord.ButtonStyle.danger,
                row=4
            )
            btn_delete.callback = self.btn_delete_callback
            self.add_item(btn_delete)

            btn_clearcache = discord.ui.Button(
                label="🧹 Bersihkan Cache",
                style=discord.ButtonStyle.secondary,
                row=4
            )
            btn_clearcache.callback = self.btn_clearcache_callback
            self.add_item(btn_clearcache)
        else:
            btn_add = discord.ui.Button(
                label="➕ Tambah Channel YouTube Baru",
                style=discord.ButtonStyle.success,
                row=0
            )
            btn_add.callback = self.btn_add_callback
            self.add_item(btn_add)

    def build_embed(self) -> discord.Embed:
        if not self.target:
            embed = discord.Embed(
                title="▶️ Studio Konfigurasi YouTube",
                description="Belum ada channel YouTube yang dipantau di server ini.\nKlik tombol **➕ Tambah Channel YouTube Baru** di bawah untuk mulai memantau.",
                color=0xFF0000
            )
            return embed

        name = self.target.get("display_name", self.target.get("identifier"))
        ident = self.target.get("identifier")
        ch_id = self.target.get("target_channel_id")
        ch_str = f"<#{ch_id}>" if ch_id else "*(Belum diatur)*"

        video_st = "🟢 Aktif" if self.target.get("video_enabled", True) else "🔴 Mati"
        live_st = "🟢 Aktif" if self.target.get("live_enabled", True) else "🔴 Mati"
        shorts_st = "🟢 Aktif" if self.target.get("shorts_enabled", True) else "🔴 Mati"

        content_val = self.target.get("content") or self.target.get("custom_template") or "@everyone {ai_hype}"
        card_st = "Kartu" if self.target.get("use_card", True) else "Teks Biasa"
        is_active = self.target.get("enabled", True)
        status_st = "🟢 Berjalan (Aktif)" if is_active else "⏸️ Dijeda"
        card_title = self.target.get("card_title", "[{judul}]({url})")
        card_desc = self.target.get("card_desc", "{deskripsi}")

        embed = discord.Embed(
            title=f"▶️ All-in-One Studio YouTube: {name}",
            description=(
                f"**Nama Channel:** **{name}** (`{ident}`)\n"
                f"**Status Pemantauan:** {status_st}\n"
                f"**Kanal Tujuan Discord:** {ch_str}\n"
                f"**Gaya Tampilan Pesan:** `{card_st}`\n\n"
                f"**Filter Konten:**\n"
                f"• 📹 Video Reguler: **{video_st}**\n"
                f"• 🔴 Live Streaming: **{live_st}**\n"
                f"• ⚡ Shorts: **{shorts_st}**\n\n"
                f"**Pesan Notifikasi:**\n"
                f"• 💬 Format Pesan: `{content_val}`\n"
                f"• 🏷️ Pola Judul: `{card_title}`\n"
                f"• 📝 Pola Deskripsi: `{card_desc}`"
            ),
            color=0xFF0000
        )
        embed.set_footer(text="Gunakan tombol di bawah. Klik 'Edit Pesan' untuk mengatur teks, mention, dan AI Hype.")
        return embed

    async def target_select_callback(self, interaction: discord.Interaction):
        selected_val = interaction.data["values"][0]
        targets = self.get_targets()
        found = next((t for t in targets if t.get("id") == selected_val or t.get("identifier") == selected_val), None)
        if found:
            self.target = found
            self.update_components()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def channel_select_callback(self, interaction: discord.Interaction):
        selected_channel_id = int(interaction.data["values"][0])
        self.target["target_channel_id"] = selected_channel_id
        if interaction.guild:
            self.target["target_guild_id"] = interaction.guild.id
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_video_callback(self, interaction: discord.Interaction):
        curr = self.target.get("video_enabled", True)
        self.target["video_enabled"] = not curr
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_live_callback(self, interaction: discord.Interaction):
        curr = self.target.get("live_enabled", True)
        self.target["live_enabled"] = not curr
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_shorts_callback(self, interaction: discord.Interaction):
        curr = self.target.get("shorts_enabled", True)
        self.target["shorts_enabled"] = not curr
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_card_callback(self, interaction: discord.Interaction):
        curr = self.target.get("use_card", True)
        self.target["use_card"] = not curr
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_status_callback(self, interaction: discord.Interaction):
        curr = self.target.get("enabled", True)
        self.target["enabled"] = not curr
        self.cog._save_config()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def btn_format_callback(self, interaction: discord.Interaction):
        modal = SocialFormatEditorModal(self.cog, self.target, self.author, self)
        await interaction.response.send_modal(modal)

    async def btn_add_callback(self, interaction: discord.Interaction):
        modal = YouTubeAddAccountModal(self.cog, self.guild, self.author, self)
        await interaction.response.send_modal(modal)

    async def btn_delete_callback(self, interaction: discord.Interaction):
        t_id = self.target.get("id") or self.target.get("identifier")
        d_name = self.target.get("display_name", self.target.get("identifier"))
        self.cog.config["targets"] = [t for t in self.cog.config.get("targets", []) if (t.get("id") != t_id and t.get("identifier") != t_id)]
        self.cog._save_config()
        self.target = None
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        await interaction.followup.send(f"Channel YouTube **{d_name}** berhasil dihapus dari pemantauan.", ephemeral=True)

    async def btn_test_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ch_id = self.target.get("target_channel_id")
        ch = interaction.guild.get_channel(ch_id) if ch_id and interaction.guild else None
        if not ch:
            return await interaction.followup.send("Kanal tujuan belum diatur atau tidak ditemukan di server ini.", ephemeral=True)

        cid = self.target.get("identifier")
        d_name = self.target.get("display_name", cid)
        items = await self.cog._fetch_youtube_content(cid)
        test_item = items[0] if items else None
        if not test_item:
            test_item = {
                "video_id": f"test_yt_{cid[:8]}",
                "title": f"Video Terbaru {d_name}",
                "description": f"Halo semua! Ini adalah simulasi uji coba notifikasi YouTube untuk channel {d_name}.",
                "url": f"https://www.youtube.com/channel/{cid}",
                "thumbnail": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800",
                "is_live": False,
                "is_short": False,
                "creator": d_name,
                "force_test": True,
            }
        else:
            meta = await self.cog._fetch_youtube_metadata(test_item["video_id"], test_item.get("is_live", False))
            if meta:
                test_item = dict(meta)
            else:
                test_item = dict(test_item)
            test_item["force_test"] = True

        sent = await self.cog._send_content_card(self.target, test_item)
        if sent:
            await interaction.followup.send(f"Berhasil mengirimkan preview notifikasi ke {ch.mention}!", ephemeral=True)
        else:
            await interaction.followup.send(f"Gagal mengirim preview ke {ch.mention}. Pastikan izin bot mencukupi.", ephemeral=True)

    async def btn_clearcache_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ident = self.target.get("identifier")
        d_name = self.target.get("display_name", ident)
        count = await self.cog._clear_target_cache("youtube", ident)
        await interaction.followup.send(
            f"🧹 Berhasil membersihkan **{count}** cache riwayat untuk channel **{d_name}**!\n"
            f"Pemeriksaan berikutnya akan otomatis mendeteksi ulang video terbaru.",
            ephemeral=True
        )


class SocialChecker(commands.Cog, name="Social Media Checker"):
    def __init__(self, bot):
        self.bot = bot
        self.config_file = "data/social_checker_config.json"
        self.cache_file = "data/social_checker_cache.json"

        self.mongo_client = getattr(bot, "mongo_client", None)
        self.config_col = None
        self.cache_col = None
        self._ensure_mongo()

        self.config = self._load_config()
        self.cache = self._load_cache()
        self.live_states = {}
        self.ig_story_states = {}

        self.http_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        interval = self.config.get("check_interval", 30)
        self.checker_loop.change_interval(seconds=interval)
        self.checker_loop.start()

    def cog_unload(self):
        self.checker_loop.cancel()

    def _ensure_mongo(self):
        if not self.mongo_client:
            self.mongo_client = getattr(self.bot, "mongo_client", None)
        if not self.mongo_client:
            mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
            if mongo_uri:
                try:
                    import pymongo
                    self.mongo_client = pymongo.MongoClient(mongo_uri)
                except Exception:
                    pass
        if self.mongo_client and self.config_col is None:
            try:
                db = self.mongo_client["reSwan"]
                self.config_col = db["social_checker_config"]
                self.cache_col = db["social_checker_cache"]
            except Exception:
                pass

    def _load_config(self):
        default_config = {
            "check_interval": 30,
            "targets": [],
        }
        self._ensure_mongo()
        loaded = None
        if self.config_col is not None:
            try:
                doc = self.config_col.find_one({"_id": "social_checker_config"})
                if doc and "data" in doc and doc["data"].get("targets"):
                    loaded = {**default_config, **doc["data"]}
            except Exception:
                pass

        if not loaded and os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("targets"):
                        loaded = {**default_config, **data}
            except Exception:
                pass

        if not loaded:
            loaded = default_config

        if not loaded.get("targets") and self.mongo_client:
            try:
                db = self.mongo_client["reSwan"]
                old_doc = db["yt_test_config"].find_one({"_id": "yt_test_config"})
                if old_doc and "data" in old_doc and "channels" in old_doc["data"]:
                    migrated_targets = []
                    for ch in old_doc["data"]["channels"]:
                        migrated_targets.append({
                            "id": str(uuid.uuid4())[:8],
                            "platform": "youtube",
                            "identifier": ch.get("channel_id"),
                            "display_name": ch.get("channel_name", "YouTube Channel"),
                            "target_guild_id": None,
                            "target_channel_id": ch.get("target_discord_channel_id"),
                            "mention_role": ch.get("mention_role", "@everyone"),
                            "message_mode": "ai",
                            "custom_template": None,
                            "enabled": ch.get("enabled", True),
                            "added_at": ch.get("added_at") or datetime.now(timezone.utc).isoformat(),
                        })
                    if migrated_targets:
                        loaded["targets"] = migrated_targets
                        self.config = loaded
                        self._save_config()
            except Exception:
                pass

        return loaded

    def _save_config(self):
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
        except Exception:
            pass

        self._ensure_mongo()
        if self.config_col is not None:
            try:
                self.config_col.replace_one(
                    {"_id": "social_checker_config"},
                    {"_id": "social_checker_config", "data": self.config},
                    upsert=True,
                )
            except Exception:
                pass

    def _load_cache(self):
        default_cache = {"posted_ids": []}
        self._ensure_mongo()
        if self.cache_col is not None:
            try:
                doc = self.cache_col.find_one({"_id": "social_checker_cache"})
                if doc and "data" in doc:
                    merged = list(set(default_cache["posted_ids"] + doc["data"].get("posted_ids", [])))
                    return {"posted_ids": merged}
            except Exception:
                pass

        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {**default_cache, **data}
            except Exception:
                pass

        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(default_cache, f, indent=4)
        return default_cache

    def _is_id_posted(self, vid: str) -> bool:
        if not vid:
            return False
        if vid in self.cache.get("posted_ids", []):
            return True
        self._ensure_mongo()
        if self.cache_col is not None:
            try:
                doc = self.cache_col.find_one({"_id": "social_checker_cache", "data.posted_ids": vid})
                if doc:
                    if vid not in self.cache["posted_ids"]:
                        self.cache["posted_ids"].append(vid)
                    return True
            except Exception:
                pass
        return False

    def _record_posted_id(self, vid: str):
        if not vid:
            return
        if vid not in self.cache.get("posted_ids", []):
            self.cache["posted_ids"].append(vid)
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=4)
        except Exception:
            pass
        self._ensure_mongo()
        if self.cache_col is not None:
            try:
                self.cache_col.update_one(
                    {"_id": "social_checker_cache"},
                    {"$addToSet": {"data.posted_ids": vid}},
                    upsert=True
                )
            except Exception:
                pass

    def _save_cache(self):
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=4)
        except Exception:
            pass

        self._ensure_mongo()
        if self.cache_col is not None:
            try:
                self.cache_col.update_one(
                    {"_id": "social_checker_cache"},
                    {"$addToSet": {"data.posted_ids": {"$each": self.cache["posted_ids"]}}},
                    upsert=True,
                )
            except Exception:
                pass

    async def _clear_target_cache(self, platform: Optional[str] = None, identifier: Optional[str] = None) -> int:
        removals = set()

        if platform == "instagram":
            if identifier:
                clean_user = normalize_instagram_username(identifier)
                if clean_user in self.ig_story_states:
                    self.ig_story_states.pop(clean_user, None)
                for vid in list(self.cache.get("posted_ids", [])):
                    if vid.startswith(f"ig_story_{clean_user}_"):
                        removals.add(vid)
                try:
                    items = await self._fetch_instagram_content(clean_user)
                    for item in items:
                        vid = item.get("video_id")
                        if vid and vid in self.cache.get("posted_ids", []):
                            removals.add(vid)
                except Exception:
                    pass
                if not removals:
                    ig_targets = [t for t in self.config.get("targets", []) if t.get("platform") == "instagram"]
                    if len(ig_targets) <= 1:
                        for vid in list(self.cache.get("posted_ids", [])):
                            if vid.startswith("ig_"):
                                removals.add(vid)
            else:
                for vid in list(self.cache.get("posted_ids", [])):
                    if vid.startswith("ig_"):
                        removals.add(vid)
                self.ig_story_states.clear()

        elif platform == "tiktok":
            if identifier:
                clean_user = normalize_tiktok_username(identifier)
                if clean_user in self.live_states:
                    self.live_states.pop(clean_user, None)
                for vid in list(self.cache.get("posted_ids", [])):
                    if vid.startswith(f"tt_{clean_user}_"):
                        removals.add(vid)
                try:
                    items = await self._fetch_tiktok_content(clean_user)
                    for item in items:
                        vid = item.get("video_id")
                        if vid and vid in self.cache.get("posted_ids", []):
                            removals.add(vid)
                except Exception:
                    pass
                if not removals:
                    tt_targets = [t for t in self.config.get("targets", []) if t.get("platform") == "tiktok"]
                    if len(tt_targets) <= 1:
                        for vid in list(self.cache.get("posted_ids", [])):
                            if vid.startswith("tt_") or (vid.isdigit() and len(vid) >= 15):
                                removals.add(vid)
            else:
                for vid in list(self.cache.get("posted_ids", [])):
                    if vid.startswith("tt_") or (vid.isdigit() and len(vid) >= 15):
                        removals.add(vid)
                self.live_states.clear()

        elif platform == "youtube":
            if identifier:
                clean_user = identifier.strip()
                if clean_user in self.live_states:
                    self.live_states.pop(clean_user, None)
                try:
                    items = await self._fetch_youtube_content(clean_user)
                    for item in items:
                        vid = item.get("video_id")
                        if vid and vid in self.cache.get("posted_ids", []):
                            removals.add(vid)
                except Exception:
                    pass
                if not removals:
                    yt_targets = [t for t in self.config.get("targets", []) if t.get("platform") == "youtube"]
                    if len(yt_targets) <= 1:
                        for vid in list(self.cache.get("posted_ids", [])):
                            if not vid.startswith("ig_") and not vid.startswith("tt_") and not (vid.isdigit() and len(vid) >= 15):
                                removals.add(vid)
            else:
                for vid in list(self.cache.get("posted_ids", [])):
                    if not vid.startswith("ig_") and not vid.startswith("tt_") and not (vid.isdigit() and len(vid) >= 15):
                        removals.add(vid)
                self.live_states.clear()

        else:
            for vid in list(self.cache.get("posted_ids", [])):
                removals.add(vid)
            self.ig_story_states.clear()
            self.live_states.clear()

        removed_count = len(removals)
        if removals:
            self.cache["posted_ids"] = [x for x in self.cache.get("posted_ids", []) if x not in removals]
            try:
                os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    json.dump(self.cache, f, indent=4)
            except Exception:
                pass

            self._ensure_mongo()
            if self.cache_col is not None:
                try:
                    self.cache_col.update_one(
                        {"_id": "social_checker_cache"},
                        {"$pull": {"data.posted_ids": {"$in": list(removals)}}}
                    )
                except Exception:
                    pass

        return removed_count

    async def _generate_ai_hype(self, creator: str, title: str, platform: str, is_live: bool = False, is_story: bool = False, is_reel: bool = False, image_bytes: Optional[bytes] = None, description: Optional[str] = None) -> str:
        if not API_KEYS:
            return self._fallback_hype(creator, platform, is_live, is_story, is_reel)

        if platform == "tiktok":
            tipe_konten = "Live Streaming TikTok" if is_live else "Video TikTok"
        elif platform == "instagram":
            tipe_konten = "Story Instagram" if is_story else ("Reels Instagram" if is_reel else "Postingan Foto/Video Instagram")
        else:
            tipe_konten = "Live Streaming YouTube" if is_live else "Video Baru YouTube"

        info_lines = []
        if creator:
            info_lines.append(f"- Channel/Kreator: {creator}")
        if title:
            info_lines.append(f"- Judul/Topik: {title}")
        if description and description != title:
            info_lines.append(f"- Teks Deskripsi/Caption: {description[:300]}")

        context_str = "\n".join(info_lines) if info_lines else "Belum ada detail khusus."

        prompt = f"""Kamu adalah bot Discord server RTMxBadut.
Tugas kamu membuat 1 kalimat notifikasi/sapaan santai dan asik buat warga server tentang {tipe_konten} yang baru rilis/dimulai.

Informasi konten:
{context_str}

Panduan gaya & aturan mutlak:
1. Hubungkan sapaan kamu secara alami dengan isi kontennya di atas. Jika ada foto/meme/teks pada gambar yang dilampirkan, BACA dan cermati teks meme, tweet, suasana, atau objek utama pada gambar tersebut agar sapaan kamu sangat relevan dan nyambung dengan apa yang terlihat di gambar!
2. Gunakan bahasa obrolan Discord/tongkrongan Indonesia yang asik, santai, dan luwes.
3. Sesuaikan dengan situasinya:
   - Kalau postingan meme/relate/santai, sapa warga server dengan santai dan ajak bahas isi gambarnya.
   - Kalau story Instagram, ingatkan warga server untuk intip story sebelum hilang dalam 24 jam.
   - Kalau live streaming, ajak warga server langsung merapat ke live chat.
4. Singkat, padat (cukup 1-2 kalimat). Jangan pakai hashtag dan jangan tulis URL link di dalam teks karena link sudah disediakan di tombol.
5. PENTING: DILARANG KERAS menyertakan kalimat pembuka/basa-basi apapun seperti "Siap!", "Berikut adalah...", "Ini dia pengumumannya:", "Tentu!", atau tanda kutip pembuka/penutup.
6. LANGSUNG tulis isi kalimat notifikasinya dari kata pertama tanpa kata pengantar atau judul sama sekali.

Tulis LANGSUNG teks pengumumannya sekarang:"""

        contents = []
        if image_bytes:
            contents.append({"mime_type": "image/jpeg", "data": image_bytes})
        contents.append(prompt)

        models_to_try = ['gemini-2.5-flash', 'gemini-3-flash-preview', 'gemini-2.5-flash-lite']

        for model_name in models_to_try:
            attempts = max(1, len(API_KEYS))
            for _ in range(attempts):
                try:
                    model = genai.GenerativeModel(model_name)
                    response = await asyncio.wait_for(model.generate_content_async(contents), timeout=30.0)
                    if response and response.text:
                        cleaned = clean_ai_hype_text(response.text)
                        if cleaned:
                            return cleaned
                except asyncio.TimeoutError:
                    return self._fallback_hype(creator, platform, is_live, is_story, is_reel)
                except google_exceptions.ResourceExhausted:
                    if rotate_api_key():
                        await asyncio.sleep(1)
                        continue
                    else:
                        break
                except Exception:
                    break

        return self._fallback_hype(creator, platform, is_live, is_story, is_reel)

    def _fallback_hype(self, creator: str, platform: str, is_live: bool, is_story: bool = False, is_reel: bool = False) -> str:
        if platform == "tiktok":
            if is_live:
                return f"**{creator}** sedang live streaming di TikTok sekarang! Yuk tonton keseruannya!"
            return f"Video TikTok terbaru dari **{creator}** sudah tayang!"
        elif platform == "instagram":
            if is_story:
                return f"**{creator}** baru saja membagikan Instagram Story baru! Yuk intip sebelum 24 jam!"
            if is_reel:
                return f"Reel terbaru dari **{creator}** sudah rilis di Instagram! Tonton sekarang yuk!"
            return f"Postingan terbaru dari **{creator}** sudah tayang di Instagram!"
        if is_live:
            return f"**{creator}** sedang melangsungkan live streaming sekarang!"
        return f"Video terbaru dari **{creator}** sudah rilis!"

    def _extract_youtube_id(self, url: str):
        if not url:
            return None
        clean_url = url.replace("\\", "")
        pattern = r"(?:https?:\/\/)?(?:[a-zA-Z0-9-]+\.)?(?:youtube(?:-nocookie)?\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=|watch\?.*&v=|live\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
        match = re.search(pattern, clean_url)
        return match.group(1) if match else None

    async def _resolve_youtube_channel(self, identifier: str):
        clean_id = identifier.strip().rstrip("/")
        if re.match(r"^UC[a-zA-Z0-9_-]{22}$", clean_id):
            name = await self._fetch_yt_name_from_rss(clean_id)
            return clean_id, name or "YouTube Channel"

        match = re.search(r"youtube\.com\/channel\/(UC[a-zA-Z0-9_-]{22})", clean_id)
        if match:
            cid = match.group(1)
            name = await self._fetch_yt_name_from_rss(cid)
            return cid, name or "YouTube Channel"

        handle_match = re.search(r"@([a-zA-Z0-9_.-]+)", clean_id)
        if handle_match:
            target_url = f"https://www.youtube.com/@{handle_match.group(1)}"
        elif not clean_id.startswith("http"):
            target_url = f"https://www.youtube.com/@{clean_id}"
        else:
            target_url = clean_id

        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(target_url, headers=self.http_headers) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        cid_match = re.search(r'\"browseId\":\"(UC[a-zA-Z0-9_-]{22})\"', html)
                        if not cid_match:
                            cid_match = re.search(r'<meta itemprop=\"identifier\" content=\"(UC[a-zA-Z0-9_-]{22})\"', html)
                        name_match = re.search(r'<meta property=\"og:title\" content=\"(.*?)\"', html)
                        name = name_match.group(1) if name_match else "YouTube Creator"
                        if cid_match:
                            return cid_match.group(1), name
        except Exception:
            pass
        return None, None

    async def _fetch_yt_name_from_rss(self, channel_id: str):
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        try:
            timeout = aiohttp.ClientTimeout(total=6)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=self.http_headers) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        root = ET.fromstring(content)
                        elem = root.find("{http://www.w3.org/2005/Atom}title")
                        if elem is not None and elem.text:
                            return elem.text.strip()
        except Exception:
            pass
        return None

    async def _fetch_youtube_content(self, channel_id: str):
        results = []
        seen_ids = set()

        direct_live_id = await self._check_youtube_direct_live(channel_id)
        if direct_live_id:
            seen_ids.add(direct_live_id)
            results.append({"video_id": direct_live_id, "is_live": True})

        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        try:
            timeout = aiohttp.ClientTimeout(total=6)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(rss_url, headers=self.http_headers) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        root = ET.fromstring(content)
                        ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
                        for entry in root.findall("atom:entry", ns):
                            elem = entry.find("yt:videoId", ns)
                            if elem is not None and elem.text:
                                vid = elem.text.strip()
                                if vid not in seen_ids:
                                    seen_ids.add(vid)
                                    results.append({"video_id": vid, "is_live": False})
        except Exception:
            pass

        return results[:10]

    async def _check_youtube_direct_live(self, channel_id: str):
        ts = int(datetime.now(timezone.utc).timestamp())
        url = f"https://www.youtube.com/channel/{channel_id}/live?t={ts}"
        headers = {
            **self.http_headers,
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache"
        }
        try:
            timeout = aiohttp.ClientTimeout(total=7)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers, allow_redirects=True) as resp:
                    final_url = str(resp.url)
                    if "/watch?v=" not in final_url:
                        return None

                    vid = self._extract_youtube_id(final_url)
                    if not vid:
                        return None

                    html = await resp.text()
                    is_live_now = '"isLive":true' in html or '"isLiveNow":true' in html or 'THUMBNAIL_OVERLAY_BADGE_STYLE_LIVE' in html
                    if not is_live_now:
                        return None

                    cid_match = re.search(r'\"channelId\":\"(UC[a-zA-Z0-9_-]{22})\"', html)
                    if cid_match and cid_match.group(1) != channel_id:
                        return None

                    return vid
        except Exception:
            pass
        return None

    async def _fetch_youtube_metadata(self, video_id: str, is_live_hint: bool = False):
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        oembed_url = f"https://www.youtube.com/oembed?url={watch_url}&format=json"

        meta = {
            "title": f"Video #{video_id}",
            "creator": "YouTube Creator",
            "channel_id": None,
            "url": watch_url,
            "thumbnail": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            "is_live": is_live_hint,
            "description": "",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(oembed_url, headers=self.http_headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        raw_title = data.get("title", "")
                        if not raw_title and "html" in data:
                            t_match = re.search(r'title=["\'](.*?)["\']', data["html"])
                            if t_match:
                                raw_title = t_match.group(1)
                        if raw_title:
                            meta["title"] = clean_hyperlink_title(raw_title)
                        if data.get("author_name"):
                            meta["creator"] = data["author_name"]
                        if data.get("thumbnail_url"):
                            meta["thumbnail"] = data["thumbnail_url"]
        except Exception:
            pass

        try:
            timeout_html = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout_html) as session:
                async with session.get(watch_url, headers=self.http_headers) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        cid_match = re.search(r'\"channelId\":\"(UC[a-zA-Z0-9_-]{22})\"', html)
                        if cid_match:
                            meta["channel_id"] = cid_match.group(1)

                        if not meta["is_live"]:
                            if '"isLive":true' in html or '"isLiveNow":true' in html or 'THUMBNAIL_OVERLAY_BADGE_STYLE_LIVE' in html:
                                meta["is_live"] = True

                        desc_match = re.search(r'<meta property=\"og:description\" content=\"(.*?)\"', html)
                        if desc_match:
                            meta["description"] = desc_match.group(1)
        except Exception:
            pass

        return meta

    def _sync_tiktok_web_profile(self, username: str):
        clean_user = normalize_tiktok_username(username)
        if not clean_user:
            return None, None, None, None
        url = f"https://www.tiktok.com/@{clean_user}"
        try:
            from curl_cffi import requests as cffi_requests
            s = cffi_requests.Session(impersonate="chrome")
            proxy = _get_proxy_for_platform("tiktok")
            if proxy:
                s.proxies = {"http": proxy, "https": proxy}
            mobile_headers = {
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.tiktok.com/",
            }
            r = s.get(url, headers=mobile_headers, timeout=10)
            if r.status_code == 200:
                text = r.text
                idx = text.find("__UNIVERSAL_DATA_FOR_REHYDRATION__")
                if idx != -1:
                    c_start = text.find(">", idx) + 1
                    c_end = text.find("</script>", c_start)
                    if c_start > 0 and c_end != -1:
                        data = json.loads(text[c_start:c_end])
                        scope = data.get("__DEFAULT_SCOPE__", {})
                        user_detail = scope.get("webapp.user-detail", {})
                        u_info = user_detail.get("userInfo", {})
                        user = u_info.get("user", {})
                        sec_uid = user.get("secUid")
                        display_name = user.get("nickname") or clean_user
                        avatar = user.get("avatarLarger") or user.get("avatarMedium") or user.get("avatarThumb")
                        room_id = str(user.get("roomId") or "").strip()
                        live_item = None
                        if room_id and room_id != "0":
                            signature = user.get("signature") or f"Sedang live streaming di TikTok: @{clean_user}"
                            live_item = {
                                "video_id": f"live_{clean_user}_{room_id}",
                                "title": f"Live Streaming TikTok - @{clean_user}",
                                "creator": display_name,
                                "url": f"https://www.tiktok.com/@{clean_user}/live",
                                "thumbnail": avatar,
                                "description": clean_hyperlink_title(signature) or f"Sedang siaran langsung di TikTok: @{clean_user}",
                                "is_live": True,
                                "sec_uid": sec_uid,
                            }
                        return live_item, sec_uid, display_name, avatar
        except Exception:
            pass
        return None, None, None, None

    def _sync_tiktok_live(self, username: str):
        clean_user = normalize_tiktok_username(username)
        if not clean_user:
            return None
        live_item, _, _, _ = self._sync_tiktok_web_profile(clean_user)
        if live_item:
            return live_item

        try:
            live_url = f"https://www.tiktok.com/@{clean_user}/live"
            ydl_opts = {
                "extract_flat": True,
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": 8,
                "logger": _SilentYDLLogger(),
            }
            try:
                from yt_dlp.networking.impersonate import ImpersonateTarget
                ydl_opts["impersonate"] = ImpersonateTarget.from_str("chrome")
            except Exception:
                pass
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(live_url, download=False)
                if info and info.get("is_live"):
                    room_id = str(info.get("id") or "active")
                    display_name = info.get("creator") or info.get("uploader") or clean_user
                    title = clean_hyperlink_title(info.get("title")) or f"Live Streaming TikTok - @{clean_user}"
                    return {
                        "video_id": f"live_{clean_user}_{room_id}",
                        "title": title,
                        "creator": display_name,
                        "url": live_url,
                        "thumbnail": info.get("thumbnail"),
                        "description": title,
                        "is_live": True,
                    }
        except Exception:
            pass
        return None

    def _sync_tiktok_secuid_videos(self, sec_uid: str, username: str, display_name: Optional[str] = None):
        if not sec_uid:
            return []
        clean_user = normalize_tiktok_username(username)
        creator_name = display_name or clean_user
        ydl_opts = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 10,
            "logger": _SilentYDLLogger(),
        }
        try:
            from yt_dlp.networking.impersonate import ImpersonateTarget
            ydl_opts["impersonate"] = ImpersonateTarget.from_str("chrome")
        except Exception:
            pass
        proxy = _get_proxy_for_platform("tiktok")
        if proxy:
            ydl_opts["proxy"] = proxy
        try:
            import itertools
            from yt_dlp.extractor.tiktok import TikTokUserIE
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ie = TikTokUserIE(ydl)
                entries = list(itertools.islice(ie._entries(sec_uid, clean_user), 5))
                if not entries:
                    return []
                results = []
                for entry in entries:
                    if not entry:
                        continue
                    vid = str(entry.get("id") or "")
                    if not vid:
                        continue
                    url = f"https://www.tiktok.com/@{clean_user}/video/{vid}"
                    uploader = entry.get("uploader") or entry.get("channel") or creator_name
                    raw_title = entry.get("title") or entry.get("description") or ""
                    cleaned_title = clean_hyperlink_title(raw_title) or f"TikTok Video by @{clean_user}"
                    t_url = entry.get("thumbnail")
                    if not t_url and entry.get("thumbnails"):
                        t_url = entry["thumbnails"][0].get("url")
                    results.append({
                        "video_id": vid,
                        "title": cleaned_title,
                        "creator": uploader,
                        "url": url,
                        "thumbnail": t_url,
                        "description": raw_title or cleaned_title,
                        "is_live": False,
                        "sec_uid": sec_uid,
                    })
                return results
        except Exception:
            return []

    def _sync_tiktok_embed(self, username: str):
        clean_user = normalize_tiktok_username(username)
        if not clean_user:
            return []
        url = f"https://www.tiktok.com/embed/@{clean_user}"
        try:
            from curl_cffi import requests as cffi_requests
            s = cffi_requests.Session(impersonate="chrome")
            proxy = _get_proxy_for_platform("tiktok")
            if proxy:
                s.proxies = {"http": proxy, "https": proxy}
            s.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.tiktok.com/",
                "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
            })
            r = s.get(url, timeout=10)
            if r.status_code != 200:
                return []
            text = r.text
            idx = text.find("__FRONTITY_CONNECT_STATE__")
            if idx == -1:
                return []
            content_start = text.find(">", idx) + 1
            content_end = text.find("</script>", content_start)
            if content_start == 0 or content_end == -1:
                return []
            raw_json = text[content_start:content_end]
            data = json.loads(raw_json)
            src = data.get("source", {}).get("data", {})
            results = []
            for k, v in src.items():
                if isinstance(v, dict) and "videoList" in v:
                    u_info = v.get("userInfo") or {}
                    display_name = u_info.get("nickname") or clean_user
                    for item in v.get("videoList", []):
                        vid = str(item.get("id") or "")
                        if not vid:
                            continue
                        desc = item.get("desc") or ""
                        cover = item.get("coverUrl") or item.get("originCoverUrl") or item.get("dynamicCoverUrl")
                        results.append({
                            "video_id": vid,
                            "title": clean_hyperlink_title(desc) or f"TikTok Video by @{clean_user}",
                            "creator": display_name,
                            "url": f"https://www.tiktok.com/@{clean_user}/video/{vid}",
                            "thumbnail": cover,
                            "description": desc or f"TikTok Video by @{clean_user}",
                            "is_live": False,
                        })
            results.sort(key=lambda x: int(x["video_id"]) if x["video_id"].isdigit() else 0, reverse=True)
            return results
        except Exception:
            return []

    def _sync_tiktok_profile(self, username: str):
        clean_user = normalize_tiktok_username(username)
        if not clean_user:
            return None
        url = f"https://www.tiktok.com/@{clean_user}/"

        ydl_opts = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "playlist_items": "1:5",
            "socket_timeout": 10,
            "logger": _SilentYDLLogger(),
        }
        try:
            from yt_dlp.networking.impersonate import ImpersonateTarget
            ydl_opts["impersonate"] = ImpersonateTarget.from_str("chrome")
        except Exception:
            pass
        proxy = _get_proxy_for_platform("tiktok")
        if proxy:
            ydl_opts["proxy"] = proxy
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception:
            return None

    def _sync_tiktok_tikwm_feed(self, clean_user: str, display_name: Optional[str] = None):
        try:
            from curl_cffi import requests as cffi_requests
            s = cffi_requests.Session(impersonate="chrome")
            proxy = _get_proxy_for_platform("tiktok")
            if proxy:
                s.proxies = {"http": proxy, "https": proxy}
            url = f"https://www.tiktok.com/@{clean_user}"
            mobile_headers = {
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.tiktok.com/",
            }
            r = s.get(url, headers=mobile_headers, timeout=10)
            if r.status_code != 200:
                return []
            raw_vids = re.findall(r"/video/(\d{19})", r.text) + re.findall(r"(\d{19})", r.text)
            found_vids = list(dict.fromkeys(raw_vids))
            results = []
            creator_name = display_name or clean_user
            for vid in found_vids[:5]:
                post_url = f"https://www.tiktok.com/@{clean_user}/video/{vid}"
                results.append({
                    "video_id": vid,
                    "title": f"TikTok Video by @{clean_user}",
                    "creator": creator_name,
                    "url": post_url,
                    "thumbnail": None,
                    "description": f"TikTok Video by @{clean_user}",
                    "is_live": False,
                })
            return results
        except Exception:
            return []

    async def _fetch_tiktok_content(self, username: str, sec_uid: Optional[str] = None):
        clean_user = normalize_tiktok_username(username)
        if not clean_user:
            return []

        results = []
        known_sec_uid = sec_uid
        display_name = clean_user

        if known_sec_uid:
            try:
                sec_videos = await asyncio.to_thread(self._sync_tiktok_secuid_videos, known_sec_uid, clean_user, display_name)
                if sec_videos:
                    results.extend(sec_videos)
            except Exception:
                pass

        live_item = None
        try:
            live_item, fetched_sec_uid, nick, avatar = await asyncio.to_thread(self._sync_tiktok_web_profile, clean_user)
            if fetched_sec_uid and not known_sec_uid:
                known_sec_uid = fetched_sec_uid
            if nick:
                display_name = nick
        except Exception:
            pass

        if not results and known_sec_uid:
            try:
                sec_videos = await asyncio.to_thread(self._sync_tiktok_secuid_videos, known_sec_uid, clean_user, display_name)
                if sec_videos:
                    results.extend(sec_videos)
            except Exception:
                pass

        if not results:
            try:
                embed_results = await asyncio.to_thread(self._sync_tiktok_embed, clean_user)
                if embed_results:
                    if known_sec_uid:
                        for er in embed_results:
                            er["sec_uid"] = known_sec_uid
                    results.extend(embed_results)
            except Exception:
                pass

        if not results:
            try:
                data = await asyncio.to_thread(self._sync_tiktok_profile, clean_user)
                if data and "entries" in data:
                    for entry in data.get("entries", []):
                        if not entry:
                            continue
                        vid = str(entry.get("id") or "")
                        if not vid:
                            continue

                        url = entry.get("url")
                        if not url or not url.startswith("http"):
                            url = f"https://www.tiktok.com/@{clean_user}/video/{vid}"

                        t_url = entry.get("thumbnail")
                        if not t_url and entry.get("thumbnails"):
                            t_url = entry["thumbnails"][0].get("url")

                        results.append({
                            "video_id": vid,
                            "title": clean_hyperlink_title(entry.get("title")) or f"TikTok Video by @{clean_user}",
                            "creator": entry.get("uploader") or display_name,
                            "url": url,
                            "thumbnail": t_url,
                            "description": entry.get("title") or "",
                            "is_live": False,
                            "sec_uid": known_sec_uid,
                        })
            except Exception:
                pass

        if not results:
            try:
                tt_fallback = await asyncio.to_thread(self._sync_tiktok_tikwm_feed, clean_user, display_name)
                if tt_fallback:
                    results.extend(tt_fallback)
            except Exception:
                pass

        if known_sec_uid:
            for item in results:
                if not item.get("sec_uid"):
                    item["sec_uid"] = known_sec_uid

        was_live = self.live_states.get(clean_user, False)
        if live_item:
            if not was_live:
                self.live_states[clean_user] = True
                results.insert(0, live_item)
        else:
            if was_live:
                self.live_states[clean_user] = False

        return results

    async def _fetch_single_tiktok_metadata(self, url: str) -> dict:
        meta = None
        canonical_url = url.strip()
        if "vt.tiktok.com" in canonical_url or "vm.tiktok.com" in canonical_url or "/t/" in canonical_url:
            try:
                dl_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                async with aiohttp.ClientSession(headers=dl_headers) as s:
                    async with s.get(canonical_url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=8)) as r:
                        canonical_url = str(r.url)
            except Exception:
                canonical_url = url

        class _SilentYDLLogger:
            def debug(self, msg):
                pass
            def info(self, msg):
                pass
            def warning(self, msg):
                pass
            def error(self, msg):
                pass

        ydl_opts = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 10,
            "logger": _SilentYDLLogger(),
        }
        try:
            from yt_dlp.networking.impersonate import ImpersonateTarget
            ydl_opts["impersonate"] = ImpersonateTarget.from_str("chrome")
        except Exception:
            pass

        try:
            data = await asyncio.to_thread(lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(canonical_url, download=False))
            if data and data.get("id"):
                meta = {
                    "video_id": str(data.get("id")),
                    "title": clean_hyperlink_title(data.get("title")) or "TikTok Video",
                    "creator": data.get("uploader") or data.get("creator") or "TikTok Creator",
                    "url": data.get("webpage_url") or canonical_url,
                    "thumbnail": data.get("thumbnail"),
                    "description": data.get("title") or "",
                    "is_live": False,
                }
        except Exception:
            pass

        if not meta or not meta.get("thumbnail"):
            try:
                clean_url = urllib.parse.quote(canonical_url, safe="")
                tikwm_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://www.tiktok.com/"
                }
                async with aiohttp.ClientSession(headers=tikwm_headers) as session:
                    async with session.get(f"https://www.tikwm.com/api/?url={clean_url}", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            res_json = await resp.json()
                            if res_json.get("code") == 0 and res_json.get("data"):
                                d = res_json["data"]
                                meta = {
                                    "video_id": str(d.get("id") or (meta.get("video_id") if meta else "")),
                                    "title": d.get("title") or (meta.get("title") if meta else "TikTok Video"),
                                    "creator": d.get("author", {}).get("unique_id") or d.get("author", {}).get("nickname") or (meta.get("creator") if meta else "TikTok Creator"),
                                    "url": canonical_url,
                                    "thumbnail": d.get("cover") or d.get("origin_cover") or (meta.get("thumbnail") if meta else None),
                                    "description": d.get("title") or "",
                                    "is_live": False,
                                }
            except Exception:
                pass

        return meta

    def _sync_instagram_web_profile(self, username: str):
        clean_user = normalize_instagram_username(username)
        if not clean_user:
            return None, [], None
        url = f"https://www.instagram.com/{clean_user}/"
        try:
            from curl_cffi import requests as cffi_requests
            s = cffi_requests.Session(impersonate="chrome")
            proxy = _get_proxy_for_platform("instagram")
            if proxy:
                s.proxies = {"http": proxy, "https": proxy}
            session_id = os.getenv("IG_SESSION_ID") or self.config.get("instagram_session_id")
            if session_id:
                s.cookies.set("sessionid", session_id, domain=".instagram.com")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
            r = s.get(url, headers=headers, timeout=6)
            if r.status_code != 200:
                return None, [], None

            matches = re.findall(r'<script type="application/json"[^>]*data-sjs[^>]*>(.*?)</script>', r.text, re.DOTALL)
            user_info = None
            timeline_items = []
            latest_reel_media = 0

            for m in matches:
                if not user_info and "latest_reel_media" in m:
                    try:
                        d = json.loads(m)
                        def _find_user(obj):
                            nonlocal user_info, latest_reel_media
                            if isinstance(obj, dict):
                                if "latest_reel_media" in obj:
                                    user_info = obj
                                    latest_reel_media = int(obj.get("latest_reel_media") or 0)
                                    return
                                for v in obj.values():
                                    if user_info:
                                        break
                                    _find_user(v)
                            elif isinstance(obj, list):
                                for it in obj:
                                    if user_info:
                                        break
                                    _find_user(it)
                        _find_user(d)
                    except Exception:
                        pass

                if not timeline_items and "polaris_ordered_timeline_connection" in m:
                    try:
                        d = json.loads(m)
                        def _find_timeline(obj):
                            nonlocal timeline_items
                            if isinstance(obj, dict):
                                if "polaris_ordered_timeline_connection" in obj:
                                    conn = obj.get("polaris_ordered_timeline_connection") or {}
                                    edges = conn.get("edges") or []
                                    timeline_items = edges
                                    return
                                for v in obj.values():
                                    if timeline_items:
                                        break
                                    _find_timeline(v)
                            elif isinstance(obj, list):
                                for it in obj:
                                    if timeline_items:
                                        break
                                    _find_timeline(it)
                        _find_timeline(d)
                    except Exception:
                        pass

                if user_info and timeline_items:
                    break

            parsed_posts = []
            display_name = user_info.get("full_name") or user_info.get("username") or clean_user if user_info else clean_user
            avatar_url = user_info.get("profile_pic_url_hd") or user_info.get("profile_pic_url") if user_info else None

            for edge in timeline_items:
                node = edge.get("node") if isinstance(edge, dict) else None
                if not node or not isinstance(node, dict):
                    continue
                code = node.get("code")
                if not code:
                    continue
                pk = str(node.get("pk") or code)
                prod_type = node.get("product_type") or ""
                is_reel = (prod_type == "clips" or node.get("media_type") == 2)
                caption_obj = node.get("caption") or {}
                raw_caption = caption_obj.get("text", "") if isinstance(caption_obj, dict) else str(caption_obj or "")
                clean_caption = clean_hyperlink_title(raw_caption) or (f"Instagram Reel by @{clean_user}" if is_reel else f"Instagram Post by @{clean_user}")
                thumb = node.get("display_uri")
                post_url = f"https://www.instagram.com/reel/{code}/" if is_reel else f"https://www.instagram.com/p/{code}/"

                carousel_list = []
                if "carousel_media" in node and isinstance(node["carousel_media"], list):
                    for cm in node["carousel_media"]:
                        if isinstance(cm, dict):
                            is_v = bool(cm.get("is_video") or cm.get("media_type") == 2)
                            u = cm.get("video_url") if is_v else (cm.get("display_uri") or cm.get("display_url"))
                            if u:
                                carousel_list.append({"url": u, "is_video": is_v})
                elif "edge_sidecar_to_children" in node:
                    edges = (node.get("edge_sidecar_to_children") or {}).get("edges") or []
                    for ed in edges:
                        s_n = ed.get("node") if isinstance(ed, dict) else None
                        if s_n and isinstance(s_n, dict):
                            is_v = bool(s_n.get("is_video") or s_n.get("media_type") == 2)
                            u = s_n.get("video_url") if is_v else (s_n.get("display_url") or s_n.get("display_uri"))
                            if u:
                                carousel_list.append({"url": u, "is_video": is_v})

                post_ts = int(node.get("taken_at_timestamp") or node.get("taken_at") or 0)
                if not post_ts and pk.isdigit():
                    try:
                        post_ts = int(((int(pk) >> 23) + 1314220021721) / 1000)
                    except Exception:
                        post_ts = 0

                parsed_posts.append({
                    "video_id": f"ig_{code}",
                    "shortcode": code,
                    "pk": pk,
                    "title": clean_caption,
                    "creator": display_name,
                    "url": post_url,
                    "thumbnail": thumb,
                    "description": raw_caption or clean_caption,
                    "is_live": False,
                    "is_story": False,
                    "is_reel": is_reel,
                    "media_list": carousel_list,
                    "timestamp": post_ts,
                })

            story_item = None
            if latest_reel_media and latest_reel_media > 0:
                story_item = {
                    "video_id": f"ig_story_{clean_user}_{latest_reel_media}",
                    "latest_reel_media": latest_reel_media,
                    "timestamp": int(latest_reel_media),
                    "title": f"Story Instagram Baru - @{clean_user}",
                    "creator": display_name,
                    "url": f"https://www.instagram.com/stories/{clean_user}/",
                    "thumbnail": avatar_url,
                    "description": f"Kreator @{clean_user} baru saja mengunggah Instagram Story baru!",
                    "is_live": False,
                    "is_story": True,
                    "is_reel": False,
                }

            return user_info, parsed_posts, story_item
        except Exception:
            return None, [], None

    def _sync_instagram_mirror_profile(self, username: str):
        clean_user = normalize_instagram_username(username)
        if not clean_user:
            return []
        url = f"https://www.instagram.com/{clean_user}/"
        try:
            from curl_cffi import requests as cffi_requests
            s = cffi_requests.Session(impersonate="chrome")
            proxy = _get_proxy_for_platform("instagram")
            if proxy:
                s.proxies = {"http": proxy, "https": proxy}
            session_id = os.getenv("IG_SESSION_ID") or self.config.get("instagram_session_id")
            if session_id:
                s.cookies.set("sessionid", session_id, domain=".instagram.com")
            headers = {
                "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            r = s.get(url, headers=headers, timeout=6)
            if r.status_code != 200:
                return []
            matches = re.findall(r'<script type="application/json"[^>]*data-sjs[^>]*>(.*?)</script>', r.text, re.DOTALL)
            parsed_posts = []
            display_name = clean_user
            for m in matches:
                if "display_uri" in m and ("seo_canonical_url" in m or "pk" in m or "id" in m):
                    try:
                        d = json.loads(m)
                        found_items = []
                        def _scan_posts(obj):
                            if isinstance(obj, dict):
                                if "display_uri" in obj and ("pk" in obj or "id" in obj):
                                    found_items.append(obj)
                                for v in obj.values():
                                    _scan_posts(v)
                            elif isinstance(obj, list):
                                for it in obj:
                                    _scan_posts(it)
                        _scan_posts(d)
                        for item in found_items:
                            pk = str(item.get("pk") or item.get("id") or "").replace("POLARIS_", "")
                            if not pk or not pk.isdigit():
                                continue
                            code = _ig_pk_to_shortcode(pk)
                            if not code:
                                continue
                            prod_type = str(item.get("product_type") or "")
                            is_reel = (prod_type == "clips" or item.get("media_type") == 2)
                            caption_obj = item.get("caption") or {}
                            raw_caption = caption_obj.get("text", "") if isinstance(caption_obj, dict) else str(caption_obj or "")
                            clean_caption = clean_hyperlink_title(raw_caption) or (f"Instagram Reel by @{clean_user}" if is_reel else f"Instagram Post by @{clean_user}")
                            thumb = item.get("display_uri")
                            post_url = f"https://www.instagram.com/reel/{code}/" if is_reel else f"https://www.instagram.com/p/{code}/"
                            item_id = f"ig_{code}"
                            if item_id in [p["video_id"] for p in parsed_posts]:
                                continue

                            post_ts = int(item.get("taken_at_timestamp") or item.get("taken_at") or 0)
                            if not post_ts and pk.isdigit():
                                try:
                                    post_ts = int(((int(pk) >> 23) + 1314220021721) / 1000)
                                except Exception:
                                    post_ts = 0

                            parsed_posts.append({
                                "video_id": item_id,
                                "shortcode": code,
                                "pk": pk,
                                "title": clean_caption,
                                "creator": display_name,
                                "url": post_url,
                                "thumbnail": thumb,
                                "description": raw_caption or clean_caption,
                                "is_live": False,
                                "is_story": False,
                                "is_reel": is_reel,
                                "media_list": [],
                                "timestamp": post_ts,
                            })
                        if parsed_posts:
                            break
                    except Exception:
                        pass
            return parsed_posts
        except Exception:
            return []

    async def _fetch_single_instagram_metadata(self, url: str) -> dict:
        canonical_url = url.strip()
        m_code = re.search(r'instagram\.com\/(?:p|reel|reels|tv)\/([A-Za-z0-9_-]+)', canonical_url)
        if not m_code:
            return None
        shortcode = m_code.group(1)
        meta = None
        try:
            import instaloader
            def _get_instaloader_post(sc: str):
                L = instaloader.Instaloader(quiet=True)
                p = instaloader.Post.from_shortcode(L.context, sc)
                return {
                    "video_id": f"ig_{sc}",
                    "shortcode": sc,
                    "title": clean_hyperlink_title(p.caption) or f"Instagram Post by @{p.owner_username}",
                    "creator": p.owner_username,
                    "url": f"https://www.instagram.com/reel/{sc}/" if p.is_video else f"https://www.instagram.com/p/{sc}/",
                    "thumbnail": p.url,
                    "description": p.caption or "",
                    "is_live": False,
                    "is_story": False,
                    "is_reel": p.is_video,
                }
            meta = await asyncio.to_thread(_get_instaloader_post, shortcode)
        except Exception:
            pass

        if not meta or not meta.get("thumbnail"):
            try:
                from curl_cffi import requests as cffi_requests
                def _get_html_meta(target_url: str):
                    s = cffi_requests.Session(impersonate="chrome")
                    r = s.get(target_url, timeout=10)
                    if r.status_code == 200:
                        m_img = re.search(r'property="og:image"\s+content="([^"]+)"', r.text)
                        m_title = re.search(r'property="og:title"\s+content="([^"]+)"', r.text)
                        m_desc = re.search(r'property="og:description"\s+content="([^"]+)"', r.text)
                        img_url = m_img.group(1).replace("&amp;", "&") if m_img else None
                        title_text = m_title.group(1) if m_title else "Instagram Post"
                        desc_text = m_desc.group(1) if m_desc else ""
                        return {
                            "video_id": f"ig_{shortcode}",
                            "shortcode": shortcode,
                            "title": clean_hyperlink_title(title_text) or "Instagram Post",
                            "creator": "Instagram Creator",
                            "url": target_url,
                            "thumbnail": img_url,
                            "description": desc_text,
                            "is_live": False,
                            "is_story": False,
                            "is_reel": "reel" in target_url,
                        }
                    return None
                meta = await asyncio.to_thread(_get_html_meta, canonical_url)
            except Exception:
                pass
        return meta

    async def _fetch_instagram_content(self, username: str):
        clean_user = normalize_instagram_username(username)
        if not clean_user:
            return []

        user_info, parsed_posts, story_item = await asyncio.to_thread(self._sync_instagram_web_profile, clean_user)
        results = []

        if story_item:
            story_ts = story_item.get("latest_reel_media", 0)
            last_ts = self.ig_story_states.get(clean_user, 0)
            if story_ts > last_ts:
                self.ig_story_states[clean_user] = story_ts
                results.append(story_item)
        else:
            self.ig_story_states[clean_user] = 0

        if parsed_posts:
            results.extend(parsed_posts)

        if not results:
            mirror_posts = await asyncio.to_thread(self._sync_instagram_mirror_profile, clean_user)
            if mirror_posts:
                results.extend(mirror_posts)

        return results

    async def _enrich_instagram_media(self, content_data: dict) -> dict:
        sc = content_data.get("shortcode")
        url = content_data.get("url") or ""
        if not sc and url:
            m = re.search(r'instagram\.com\/(?:p|reel|reels|tv)\/([A-Za-z0-9_-]+)', url)
            if m:
                sc = m.group(1)
        if not sc:
            return {}

        def _fetch_instaloader():
            try:
                import instaloader
                L = instaloader.Instaloader(quiet=True)
                p = instaloader.Post.from_shortcode(L.context, sc)
                v_url = p.video_url if p.is_video else None
                m_list = []
                if p.typename == "GraphSidecar":
                    for s_node in p.get_sidecar_nodes():
                        m_list.append({
                            "url": s_node.video_url if s_node.is_video else s_node.display_url,
                            "is_video": s_node.is_video
                        })
                return {
                    "video_url": v_url,
                    "media_list": m_list,
                    "is_reel": p.is_video or content_data.get("is_reel", False),
                    "thumbnail": p.url or content_data.get("thumbnail")
                }
            except Exception:
                return None

        try:
            enriched = await asyncio.wait_for(asyncio.to_thread(_fetch_instaloader), timeout=10.0)
            if enriched and (enriched.get("video_url") or enriched.get("media_list")):
                return enriched
        except Exception:
            pass

        def _fetch_curl_cffi():
            try:
                from curl_cffi import requests as cffi_requests
                s = cffi_requests.Session(impersonate="chrome")
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                }
                target_url = f"https://www.instagram.com/p/{sc}/"
                r = s.get(target_url, headers=headers, timeout=8)
                if r.status_code != 200:
                    return None
                scripts = re.findall(r'<script type="application/json"[^>]*data-sjs[^>]*>(.*?)</script>', r.text, re.DOTALL)
                c_items = []
                for scr in scripts:
                    if any(k in scr for k in ["carousel_media", "edge_sidecar_to_children", "display_uri", "display_url"]):
                        try:
                            d = json.loads(scr)
                            def _scan(obj):
                                if isinstance(obj, dict):
                                    if "carousel_media" in obj and isinstance(obj["carousel_media"], list):
                                        for cm in obj["carousel_media"]:
                                            c_items.append(cm)
                                    if "edge_sidecar_to_children" in obj:
                                        edges = (obj.get("edge_sidecar_to_children") or {}).get("edges") or []
                                        for ed in edges:
                                            c_items.append(ed.get("node"))
                                    for v in obj.values():
                                        _scan(v)
                                elif isinstance(obj, list):
                                    for it in obj:
                                        _scan(it)
                            _scan(d)
                        except Exception:
                            pass
                if c_items:
                    m_list = []
                    for item in c_items:
                        if not item or not isinstance(item, dict):
                            continue
                        is_v = bool(item.get("is_video") or item.get("media_type") == 2)
                        v_u = item.get("video_url")
                        d_u = item.get("display_uri") or item.get("display_url") or item.get("url")
                        u = v_u if (is_v and v_u) else d_u
                        if u and u not in [x.get("url") for x in m_list]:
                            m_list.append({"url": u, "is_video": is_v})
                    if m_list:
                        return {
                            "video_url": None,
                            "media_list": m_list,
                            "is_reel": content_data.get("is_reel", False),
                            "thumbnail": m_list[0].get("url") or content_data.get("thumbnail")
                        }
                return None
            except Exception:
                return None

        cffi_res = await asyncio.to_thread(_fetch_curl_cffi)
        if cffi_res and (cffi_res.get("media_list") and len(cffi_res.get("media_list")) > 0):
            return cffi_res

        def _fetch_ytdlp():
            try:
                import yt_dlp
                ydl_opts = {
                    "quiet": True,
                    "skip_download": True,
                    "extract_flat": False,
                    "no_warnings": True
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        return None
                    entries = info.get("entries")
                    if entries:
                        m_list = []
                        for entry in entries:
                            m_list.append({
                                "url": entry.get("url"),
                                "is_video": entry.get("ext") == "mp4" or entry.get("vcodec") != "none"
                            })
                        return {"media_list": m_list, "video_url": None}
                    v_url = info.get("url") if (info.get("ext") == "mp4" or info.get("vcodec") != "none") else None
                    return {"video_url": v_url, "media_list": []}
            except Exception:
                return None

        if url:
            ytdlp_res = await asyncio.to_thread(_fetch_ytdlp)
            if ytdlp_res:
                return ytdlp_res

        return {}

    async def _try_fetch_story_media(self, username: str) -> tuple:
        session_id = os.getenv("IG_SESSION_ID") or self.config.get("instagram_session_id")
        if not session_id or not username:
            return None, False

        clean_user = normalize_instagram_username(username)

        def _fetch_story():
            try:
                import instaloader
                L = instaloader.Instaloader(quiet=True)
                L.context._session.cookies.set("sessionid", session_id, domain=".instagram.com")
                profile = instaloader.Profile.from_username(L.context, clean_user)
                for story in L.get_stories(userids=[profile.userid]):
                    for item in story.get_items():
                        return (item.video_url if item.is_video else item.url), item.is_video
                return None, False
            except Exception:
                return None, False

        return await asyncio.to_thread(_fetch_story)

    async def _send_content_card(self, target: dict, content_data: dict):
        channel = self.bot.get_channel(target["target_channel_id"])
        if not channel:
            try:
                channel = await self.bot.fetch_channel(target["target_channel_id"])
            except Exception:
                return False

        creator = content_data.get("creator") or target.get("display_name", "Creator")
        title = content_data.get("title", "")
        url = content_data.get("url", "")
        platform = target.get("platform", "youtube")
        is_live = content_data.get("is_live", False)
        is_story = content_data.get("is_story", False)
        is_reel = content_data.get("is_reel", False)
        thumbnail = content_data.get("thumbnail")

        if not content_data.get("force_test", False):
            if platform == "instagram":
                if is_story and not target.get("stories_enabled", True):
                    return False
                if is_reel and not target.get("reels_enabled", True):
                    return False
                if not is_story and not is_reel and not target.get("feed_enabled", True):
                    return False
            elif platform == "tiktok":
                if is_live and not target.get("live_enabled", True):
                    return False
                if not is_live and not target.get("video_enabled", True):
                    return False
            elif platform == "youtube":
                is_short = content_data.get("is_short", False) or "/shorts/" in url
                if is_live and not target.get("live_enabled", True):
                    return False
                if is_short and not target.get("shorts_enabled", True):
                    return False
                if not is_live and not is_short and not target.get("video_enabled", True):
                    return False

        if platform == "instagram" and not is_story:
            enriched = await self._enrich_instagram_media(content_data)
            if enriched:
                content_data.update(enriched)
                thumbnail = content_data.get("thumbnail") or thumbnail
                is_reel = content_data.get("is_reel", is_reel)

        if platform == "instagram" and is_story:
            story_media_url, is_v = await self._try_fetch_story_media(creator or target.get("identifier"))
            if story_media_url:
                if is_v:
                    content_data["video_url"] = story_media_url
                else:
                    content_data["thumbnail"] = story_media_url
                    thumbnail = story_media_url

        desc = content_data.get("description") or title or url
        desc = clean_hyperlink_title(desc) if desc else ""

        if platform == "instagram":
            if is_story:
                clean_card_title = f"⏳ Story Baru @{creator}"
            elif is_reel:
                clean_card_title = f"🎬 Reels Baru @{creator}"
            else:
                clean_card_title = f"📸 Postingan Baru @{creator}"
        elif platform == "tiktok":
            clean_card_title = f"🔴 Live Streaming @{creator}" if is_live else f"🎵 Video TikTok @{creator}"
        else:
            clean_card_title = clean_hyperlink_title(title) or f"Video YouTube {creator}"

        preview_img_bytes = None
        target_img_url = thumbnail
        if not target_img_url and media_list:
            first_m = media_list[0]
            target_img_url = first_m.get("url") if isinstance(first_m, dict) else str(first_m)

        if target_img_url:
            try:
                import io
                dl_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                if "tiktok" in str(target_img_url):
                    dl_headers["Referer"] = "https://www.tiktok.com/"
                elif "instagram" in str(target_img_url) or "cdninstagram" in str(target_img_url):
                    dl_headers["Referer"] = "https://www.instagram.com/"
                timeout = aiohttp.ClientTimeout(total=8)
                async with aiohttp.ClientSession(timeout=timeout, headers=dl_headers) as session:
                    async with session.get(target_img_url) as img_resp:
                        if img_resp.status == 200:
                            b = await img_resp.read()
                            if b and len(b) <= 8 * 1024 * 1024:
                                preview_img_bytes = b
            except Exception:
                preview_img_bytes = None

        raw_content = target.get("content") or target.get("custom_template")
        if not raw_content:
            raw_content = "@everyone {ai_hype}"

        intro_text = raw_content
        if "{ai_hype}" in intro_text or "{aihype}" in intro_text:
            ai_text = await self._generate_ai_hype(
                creator=creator,
                title=clean_card_title,
                platform=platform,
                is_live=is_live,
                is_story=is_story,
                is_reel=is_reel,
                image_bytes=preview_img_bytes,
                description=desc
            )
            intro_text = intro_text.replace("{ai_hype}", ai_text).replace("{aihype}", ai_text)

        intro_text = (
            intro_text
            .replace("{judul}", clean_card_title)
            .replace("{creator}", creator)
            .replace("{username}", creator)
            .replace("{uploader}", creator)
            .replace("{channel}", creator)
            .replace("{url}", url)
            .strip()
        )

        if platform == "tiktok":
            default_btn = "Tonton Live TikTok" if is_live else "Tonton di TikTok"
        elif platform == "instagram":
            if is_story:
                default_btn = "Buka Story di Instagram"
            elif is_reel:
                default_btn = "Tonton Reel di Instagram"
            else:
                default_btn = "Buka di Instagram"
        else:
            default_btn = "Tonton Live" if is_live else "Tonton Video"
        btn_label = target.get("button_label") or default_btn
        card_title_template = target.get("card_title") or "[{judul}]({url})"
        card_desc_template = target.get("card_desc") or "{deskripsi}"
        use_card = target.get("use_card", True)

        final_card_title = (
            card_title_template
            .replace("{judul}", clean_card_title)
            .replace("{creator}", creator)
            .replace("{username}", creator)
            .replace("{uploader}", creator)
            .replace("{channel}", creator)
            .replace("{url}", url)
        )
        final_card_desc = (
            card_desc_template
            .replace("{deskripsi}", desc if desc else url)
            .replace("{judul}", clean_card_title)
            .replace("{creator}", creator)
            .replace("{username}", creator)
            .replace("{uploader}", creator)
            .replace("{channel}", creator)
            .replace("{url}", url)
            .strip()
        )
        if not final_card_desc:
            final_card_desc = url

        buttons = [{
            "label": btn_label,
            "style": 5,
            "url": url,
        }]

        files = None
        attachment_fn = None
        attachment_fns = None

        video_url = content_data.get("video_url")
        media_list = content_data.get("media_list") or []

        if video_url:
            try:
                import io
                timeout = aiohttp.ClientTimeout(total=25)
                dl_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://www.instagram.com/"
                }
                async with aiohttp.ClientSession(timeout=timeout, headers=dl_headers) as session:
                    async with session.get(video_url) as v_resp:
                        if v_resp.status == 200:
                            c_len = v_resp.content_length
                            if c_len is None or c_len <= 24 * 1024 * 1024:
                                v_bytes = await v_resp.read()
                                if len(v_bytes) <= 24 * 1024 * 1024:
                                    files = [discord.File(io.BytesIO(v_bytes), filename="instagram_video.mp4")]
                                    attachment_fn = "instagram_video.mp4"
            except Exception:
                files = None
                attachment_fn = None

        if not files and media_list and len(media_list) > 1:
            try:
                import io
                timeout = aiohttp.ClientTimeout(total=20)
                dl_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://www.instagram.com/"
                }
                c_files = []
                async with aiohttp.ClientSession(timeout=timeout, headers=dl_headers) as session:
                    for idx, m_item in enumerate(media_list[:10]):
                        m_u = m_item.get("url") if isinstance(m_item, dict) else str(m_item)
                        is_v = m_item.get("is_video") if isinstance(m_item, dict) else False
                        ext = "mp4" if is_v else "jpg"
                        try:
                            async with session.get(m_u) as m_resp:
                                if m_resp.status == 200:
                                    b = await m_resp.read()
                                    if len(b) <= 24 * 1024 * 1024:
                                        c_files.append(discord.File(io.BytesIO(b), filename=f"slide_{idx+1}.{ext}"))
                        except Exception:
                            pass
                if c_files:
                    files = c_files
                    attachment_fns = [f.filename for f in c_files]
                    attachment_fn = files[0].filename
            except Exception:
                pass

        if not files and preview_img_bytes:
            import io
            files = [discord.File(io.BytesIO(preview_img_bytes), filename="thumbnail.jpg")]
            attachment_fn = "thumbnail.jpg"

        if use_card:
            card = build_v2_card(
                title=final_card_title,
                description=final_card_desc,
                color=None,
                buttons=buttons,
                attachment_filename=attachment_fn if not attachment_fns else None,
                attachment_filenames=attachment_fns,
                media_url=thumbnail if not (attachment_fn or attachment_fns) else None,
            )
            res = await send_v2_message(self.bot, channel.id, [card], files=files, content=intro_text)
            if not (isinstance(res, dict) and "error_msg" in res):
                return True

        fallback_view = discord.ui.View()
        fallback_btn = discord.ui.Button(label=btn_label, style=discord.ButtonStyle.link, url=url)
        fallback_view.add_item(fallback_btn)
        send_content = intro_text
        if url not in send_content:
            send_content = f"{send_content}\n{url}"
        await channel.send(content=send_content, files=files, view=fallback_view)
        return True

    async def _process_single_target(self, target: dict):
        platform = target.get("platform")
        identifier = target.get("identifier")
        new_count = 0

        try:
            if platform == "youtube":
                items = await self._fetch_youtube_content(identifier)
                unposted_items = [it for it in items if not self._is_id_posted(it["video_id"])]
                if len(unposted_items) > 1:
                    live_vids = [x for x in unposted_items if x.get("is_live")]
                    vod_vids = [x for x in unposted_items if not x.get("is_live")]
                    if vod_vids:
                        candidate_vod = vod_vids[0]
                        for older_it in vod_vids[1:]:
                            self._record_posted_id(older_it["video_id"])
                        items_to_process = live_vids + [candidate_vod]
                    else:
                        items_to_process = live_vids
                else:
                    items_to_process = unposted_items

                for item in items_to_process:
                    vid = item["video_id"]
                    meta = await self._fetch_youtube_metadata(vid, item.get("is_live", False))
                    if meta.get("channel_id") and meta["channel_id"] != identifier:
                        continue

                    is_live = meta.get("is_live", False)
                    is_short = meta.get("is_short", False) or "/shorts/" in meta.get("url", "")
                    if is_live and not target.get("live_enabled", True):
                        self._record_posted_id(vid)
                        continue
                    if is_short and not target.get("shorts_enabled", True):
                        self._record_posted_id(vid)
                        continue
                    if not is_live and not is_short and not target.get("video_enabled", True):
                        self._record_posted_id(vid)
                        continue

                    success = await self._send_content_card(target, meta)
                    if success:
                        self._record_posted_id(vid)
                        new_count += 1
                        print(f"[SocialChecker] [youtube] Channel: {identifier} | Sent NEW video: {vid}")
                        await asyncio.sleep(2)

                if new_count == 0 and items:
                    print(f"[SocialChecker] [youtube] Channel: {identifier} | {len(items)} items checked (all in cache / idle)")

            elif platform == "tiktok":
                items = await self._fetch_tiktok_content(identifier, target.get("sec_uid"))
                now_ts = datetime.now(timezone.utc).timestamp()
                max_age_seconds = 48 * 3600
                unposted_items = []
                for item in items:
                    if item.get("sec_uid") and not target.get("sec_uid"):
                        target["sec_uid"] = item["sec_uid"]
                        self._save_config()
                    vid = item["video_id"]
                    if self._is_id_posted(vid):
                        continue

                    is_live = item.get("is_live", False)
                    if not is_live:
                        ts = item.get("timestamp") or 0
                        if not ts and vid.isdigit() and len(vid) >= 15:
                            try:
                                ts = int(vid) >> 32
                                item["timestamp"] = ts
                            except Exception:
                                pass
                        if ts and (now_ts - ts) > max_age_seconds:
                            self._record_posted_id(vid)
                            continue

                    unposted_items.append(item)

                if len(unposted_items) > 1:
                    live_items = [x for x in unposted_items if x.get("is_live")]
                    vod_items = [x for x in unposted_items if not x.get("is_live")]
                    if vod_items:
                        vod_items.sort(key=lambda x: x.get("timestamp") or 0, reverse=True)
                        candidate_vod = vod_items[0]
                        for older_item in vod_items[1:]:
                            self._record_posted_id(older_item["video_id"])
                        items_to_process = live_items + [candidate_vod]
                    else:
                        items_to_process = live_items
                else:
                    items_to_process = unposted_items

                for item in items_to_process:
                    vid = item["video_id"]
                    is_live = item.get("is_live", False)
                    if is_live and not target.get("live_enabled", True):
                        continue
                    if not is_live and not target.get("video_enabled", True):
                        self._record_posted_id(vid)
                        continue

                    success = await self._send_content_card(target, item)
                    if success:
                        if not item.get("is_live"):
                            self._record_posted_id(vid)
                        new_count += 1
                        print(f"[SocialChecker] [tiktok] User: @{identifier} | Sent NEW {'live' if is_live else 'video'}: {vid}")
                        await asyncio.sleep(2)

                if new_count == 0 and items:
                    print(f"[SocialChecker] [tiktok] User: @{identifier} | {len(items)} items checked (all in cache / idle)")

            elif platform == "instagram":
                items = await self._fetch_instagram_content(identifier)
                now_ts = datetime.now(timezone.utc).timestamp()
                max_age_seconds = 48 * 3600
                unposted_items = []
                for item in items:
                    vid = item["video_id"]
                    if self._is_id_posted(vid):
                        continue

                    ts = item.get("timestamp") or 0
                    if not ts and item.get("pk") and str(item["pk"]).isdigit():
                        try:
                            pk_int = int(item["pk"])
                            ts = int(((pk_int >> 23) + 1314220021721) / 1000)
                            item["timestamp"] = ts
                        except Exception:
                            pass

                    if ts and (now_ts - ts) > max_age_seconds:
                        self._record_posted_id(vid)
                        continue

                    unposted_items.append(item)

                if len(unposted_items) > 1:
                    story_items = [x for x in unposted_items if x.get("is_story")]
                    post_items = [x for x in unposted_items if not x.get("is_story")]
                    items_to_process = []
                    if story_items:
                        items_to_process.append(story_items[0])
                        for older_story in story_items[1:]:
                            self._record_posted_id(older_story["video_id"])
                    if post_items:
                        post_items.sort(key=lambda x: x.get("timestamp") or 0, reverse=True)
                        items_to_process.append(post_items[0])
                        for older_post in post_items[1:]:
                            self._record_posted_id(older_post["video_id"])
                else:
                    items_to_process = unposted_items

                for item in items_to_process:
                    vid = item["video_id"]
                    is_story = item.get("is_story", False)
                    is_reel = item.get("is_reel", False)
                    if is_story and not target.get("stories_enabled", True):
                        self._record_posted_id(vid)
                        continue
                    if is_reel and not target.get("reels_enabled", True):
                        self._record_posted_id(vid)
                        continue
                    if not is_story and not is_reel and not target.get("feed_enabled", True):
                        self._record_posted_id(vid)
                        continue

                    success = await self._send_content_card(target, item)
                    if success:
                        self._record_posted_id(vid)
                        new_count += 1
                        print(f"[SocialChecker] [instagram] User: @{identifier} | Sent NEW post/reel/story: {vid}")
                        await asyncio.sleep(2)

                if new_count == 0 and items:
                    print(f"[SocialChecker] [instagram] User: @{identifier} | {len(items)} items checked (all in cache / idle)")

        except Exception as e:
            print(f"[SocialChecker] [{platform}] Target: {identifier} | Error: {e}")

    @tasks.loop(seconds=30)
    async def checker_loop(self):
        targets = [t for t in self.config.get("targets", []) if t.get("enabled", True)]
        if not targets:
            return

        tasks = [asyncio.wait_for(self._process_single_target(t), timeout=120.0) for t in targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res, t in zip(results, targets):
            if isinstance(res, Exception):
                print(f"[SocialChecker] Error processing {t.get('platform')} {t.get('identifier')}: {res}")

    @checker_loop.before_loop
    async def before_checker_loop(self):
        await self.bot.wait_until_ready()

    @checker_loop.error
    async def on_checker_loop_error(self, error):
        print(f"[SocialChecker] Error in checker loop: {error}")


    @commands.hybrid_group(name="yt", description="Manajemen pemantauan YouTube")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def yt_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await self.yt_setup(ctx)

    @yt_group.command(name="setup", description="Dashboard All-in-One konfigurasi pemantauan YouTube")
    @app_commands.describe(target="Nama channel atau ID YouTube yang ingin diatur (opsional)")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def yt_setup(self, ctx: commands.Context, target: Optional[str] = None):
        found = None
        if target:
            clean = target.strip().lower()
            for t in self.config.get("targets", []):
                if t.get("platform") == "youtube" and (t.get("identifier", "").lower() == clean or clean in t.get("display_name", "").lower() or t.get("id") == clean):
                    found = t
                    break
            if not found:
                return await ctx.send(f"Channel `{target}` tidak ditemukan.", ephemeral=True)

        view = YouTubeStudioView(self, ctx.guild, ctx.author, initial_target=found)
        await ctx.send(embed=view.build_embed(), view=view, ephemeral=True)

    @yt_group.command(name="studio", description="Buka panel All-in-One Studio YouTube")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def yt_studio(self, ctx: commands.Context, target: Optional[str] = None):
        await self.yt_setup(ctx, target)

    @yt_group.command(name="add", description="Tambah channel YouTube untuk dipantau")
    @commands.is_owner()
    async def yt_add(self, ctx: commands.Context, identifier: str, target_channel: discord.TextChannel = None):
        channel_to_use = target_channel or ctx.channel
        cid, name = await self._resolve_youtube_channel(identifier)
        if not cid:
            return await ctx.send(f"Channel YouTube `{identifier}` tidak ditemukan.", ephemeral=True)

        for t in self.config["targets"]:
            if t.get("platform") == "youtube" and t.get("identifier") == cid:
                t["target_channel_id"] = channel_to_use.id
                t["target_guild_id"] = ctx.guild.id if ctx.guild else None
                t["display_name"] = name
                self._save_config()
                return await ctx.send(f"Channel **{name}** (`{cid}`) sudah terdaftar, target diperbarui ke {channel_to_use.mention}.", ephemeral=True)

        new_target = {
            "id": str(uuid.uuid4())[:8],
            "platform": "youtube",
            "identifier": cid,
            "display_name": name,
            "target_guild_id": ctx.guild.id if ctx.guild else None,
            "target_channel_id": channel_to_use.id,
            "content": "@everyone {ai_hype}",
            "custom_template": "@everyone {ai_hype}",
            "card_title": "[{judul}]({url})",
            "card_desc": "{deskripsi}",
            "button_label": None,
            "use_card": True,
            "enabled": True,
            "video_enabled": True,
            "live_enabled": True,
            "shorts_enabled": True,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        self.config["targets"].append(new_target)
        self._save_config()

        current_items = await self._fetch_youtube_content(cid)
        for it in current_items:
            if not it.get("is_live"):
                if it["video_id"] not in self.cache["posted_ids"]:
                    self.cache["posted_ids"].append(it["video_id"])
        self._save_cache()

        await ctx.send(f"Berhasil menambahkan channel **{name}** (`{cid}`) ke pemantauan di {channel_to_use.mention}.", ephemeral=True)

    @yt_group.command(name="remove", description="Hapus channel YouTube dari pemantauan")
    @commands.is_owner()
    async def yt_remove(self, ctx: commands.Context, identifier: str):
        before_count = len(self.config["targets"])
        self.config["targets"] = [
            t for t in self.config["targets"]
            if not (t.get("platform") == "youtube" and (t.get("identifier") == identifier or identifier in t.get("display_name", "")))
        ]
        if len(self.config["targets"]) < before_count:
            self._save_config()
            return await ctx.send(f"Channel YouTube `{identifier}` berhasil dihapus dari pemantauan.", ephemeral=True)
        await ctx.send(f"Channel `{identifier}` tidak ditemukan di daftar pemantauan.", ephemeral=True)

    @yt_group.command(name="config", description="Buka panel pengaturan untuk channel YouTube")
    @app_commands.describe(target="Nama channel atau ID YouTube yang ingin diatur (opsional)")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def yt_config(self, ctx: commands.Context, target: Optional[str] = None):
        await self.yt_setup(ctx, target)

    @yt_group.command(name="clearcache", description="Bersihkan cache riwayat video YouTube agar bot mendeteksi ulang")
    @app_commands.describe(target="Channel ID atau nama channel yang ingin dibersihkan cachenya (opsional)")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def yt_clearcache(self, ctx: commands.Context, target: Optional[str] = None):
        await ctx.defer(ephemeral=True)
        count = await self._clear_target_cache("youtube", target)
        if target:
            await ctx.send(f"🧹 Berhasil membersihkan **{count}** cache riwayat untuk YouTube target `{target}`! Video berikutnya akan dianggap baru.", ephemeral=True)
        else:
            await ctx.send(f"🧹 Berhasil membersihkan seluruh cache YouTube (**{count}** video)! Seluruh channel YouTube akan diperiksa ulang.", ephemeral=True)


    @yt_group.command(name="list", description="Daftar channel YouTube yang dipantau")
    @commands.is_owner()
    async def yt_list(self, ctx: commands.Context):
        yt_targets = [t for t in self.config["targets"] if t.get("platform") == "youtube"]
        if not yt_targets:
            return await ctx.send("Belum ada channel YouTube yang dipantau.", ephemeral=True)

        lines = ["**Daftar Pemantauan YouTube:**"]
        for idx, t in enumerate(yt_targets, 1):
            status = "AKTIF" if t.get("enabled", True) else "NONAKTIF"
            ch_mention = f"<#{t['target_channel_id']}>"
            lines.append(f"{idx}. **{t['display_name']}** (`{t['identifier']}`) - {ch_mention} [{status}] Mode: `{t.get('message_mode', 'ai')}` Mention: `{t.get('mention_role')}`")
        await ctx.send("\n".join(lines), ephemeral=True)

    @yt_group.command(name="test", description="Kirim uji coba notifikasi untuk URL YouTube")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def yt_test(self, ctx: commands.Context, url: str, channel: discord.TextChannel = None):
        target_channel = channel or ctx.channel
        await ctx.defer(ephemeral=True)
        vid = self._extract_youtube_id(url)
        if not vid:
            return await ctx.send("URL YouTube tidak valid.", ephemeral=True)

        meta = await self._fetch_youtube_metadata(vid)
        existing_target = None
        cid = meta.get("channel_id")
        for t in self.config.get("targets", []):
            if t.get("platform") == "youtube" and (t.get("identifier") == cid or (cid and cid in t.get("identifier"))):
                existing_target = t
                break

        dummy_target = {
            "platform": "youtube",
            "identifier": meta.get("channel_id") or "test",
            "display_name": meta.get("creator", "Creator"),
            "target_channel_id": target_channel.id,
            "mention_role": existing_target.get("mention_role", "none") if existing_target else "none",
            "message_mode": existing_target.get("message_mode", "ai") if existing_target else "ai",
            "custom_template": existing_target.get("custom_template") if existing_target else None,
            "card_title": existing_target.get("card_title") if existing_target else None,
            "card_desc": existing_target.get("card_desc") if existing_target else None,
            "button_label": existing_target.get("button_label") if existing_target else None,
            "use_card": existing_target.get("use_card", True) if existing_target else True,
        }
        card_sent = await self._send_content_card(dummy_target, meta)
        embed = discord.Embed(
            title="🎬 Preview Pengujian Notifikasi YouTube",
            description="Pengujian notifikasi berhasil diproses dengan detail konten di bawah ini:",
            color=0xFF0000
        )
        embed.add_field(name="👤 Channel / Kreator", value=f"**{meta.get('creator', 'Creator')}**", inline=True)
        embed.add_field(name="🆔 ID Video", value=f"`{meta.get('video_id', vid)}`", inline=True)
        embed.add_field(name="📢 Saluran Target", value=target_channel.mention, inline=True)
        embed.add_field(name="📝 Judul Video", value=meta.get('title', 'Video')[:250], inline=False)
        embed.add_field(name="🔗 Tautan Video", value=f"[Buka Video YouTube]({meta.get('url', url)})", inline=False)
        status_text = f"✅ Notifikasi berhasil dikirim ke {target_channel.mention}." if card_sent else f"⚠️ Gagal mengirim notifikasi ke {target_channel.mention}."
        embed.add_field(name="⚡ Status Pengiriman", value=status_text, inline=False)
        if meta.get("thumbnail"):
            embed.set_thumbnail(url=meta["thumbnail"])
        embed.set_footer(text="Gunakan link video YouTube siapapun untuk preview format notifikasi.")
        await ctx.send(embed=embed, ephemeral=True)

    @yt_group.command(name="check", description="Paksa cek pembaruan YouTube sekarang")
    @commands.is_owner()
    async def yt_check(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        targets = [t for t in self.config["targets"] if t.get("platform") == "youtube" and t.get("enabled", True)]
        found_any = 0
        for t in targets:
            items = await self._fetch_youtube_content(t["identifier"])
            for it in items:
                vid = it["video_id"]
                if self._is_id_posted(vid):
                    continue
                meta = await self._fetch_youtube_metadata(vid, it.get("is_live", False))
                if meta.get("channel_id") and meta["channel_id"] != t["identifier"]:
                    continue
                if await self._send_content_card(t, meta):
                    self._record_posted_id(vid)
                    found_any += 1
        await ctx.send(f"Pengecekan selesai. Ditemukan dan dikirim: {found_any} konten baru.", ephemeral=True)

    @commands.hybrid_group(name="tt", description="Manajemen pemantauan TikTok")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def tt_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await self.tt_setup(ctx)

    @tt_group.command(name="setup", description="Dashboard All-in-One konfigurasi pemantauan TikTok")
    @app_commands.describe(target="Nama pengguna atau ID TikTok yang ingin diatur (opsional)")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def tt_setup(self, ctx: commands.Context, target: Optional[str] = None):
        found = None
        if target:
            clean = await async_resolve_tiktok_username(target)
            for t in self.config.get("targets", []):
                if t.get("platform") == "tiktok" and (t.get("identifier", "").lower() == clean.lower() or clean.lower() in t.get("display_name", "").lower() or t.get("id") == clean):
                    found = t
                    break
            if not found:
                return await ctx.send(f"Akun TikTok `@{target}` tidak ditemukan.", ephemeral=True)

        view = TikTokStudioView(self, ctx.guild, ctx.author, initial_target=found)
        await ctx.send(embed=view.build_embed(), view=view, ephemeral=True)

    @tt_group.command(name="studio", description="Buka panel All-in-One Studio TikTok")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def tt_studio(self, ctx: commands.Context, target: Optional[str] = None):
        await self.tt_setup(ctx, target)

    @tt_group.command(name="add", description="Tambah akun TikTok untuk dipantau")
    @commands.is_owner()
    async def tt_add(self, ctx: commands.Context, username: str, target_channel: discord.TextChannel = None):
        channel_to_use = target_channel or ctx.channel
        clean_user = await async_resolve_tiktok_username(username)
        if not clean_user:
            return await ctx.send("Nama pengguna atau tautan akun TikTok tidak valid.", ephemeral=True)

        for t in self.config["targets"]:
            if t.get("platform") == "tiktok" and t.get("identifier").lower() == clean_user.lower():
                t["target_channel_id"] = channel_to_use.id
                t["target_guild_id"] = ctx.guild.id if ctx.guild else None
                self._save_config()
                return await ctx.send(f"Akun TikTok **@{clean_user}** sudah terdaftar, target diperbarui ke {channel_to_use.mention}.", ephemeral=True)

        new_target = {
            "id": str(uuid.uuid4())[:8],
            "platform": "tiktok",
            "identifier": clean_user,
            "display_name": clean_user,
            "sec_uid": None,
            "target_guild_id": ctx.guild.id if ctx.guild else None,
            "target_channel_id": channel_to_use.id,
            "content": "@everyone {ai_hype}",
            "custom_template": "@everyone {ai_hype}",
            "card_title": "[{judul}]({url})",
            "card_desc": "{deskripsi}",
            "button_label": None,
            "use_card": True,
            "enabled": True,
            "video_enabled": True,
            "live_enabled": True,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        self.config["targets"].append(new_target)
        self._save_config()

        current_items = await self._fetch_tiktok_content(clean_user)
        for it in current_items:
            if it.get("sec_uid") and not new_target.get("sec_uid"):
                new_target["sec_uid"] = it["sec_uid"]
            if it.get("creator") and new_target.get("display_name") == clean_user:
                new_target["display_name"] = it["creator"]
            if not it.get("is_live") and it["video_id"] not in self.cache["posted_ids"]:
                self.cache["posted_ids"].append(it["video_id"])
        self._save_config()
        self._save_cache()

        await ctx.send(f"Berhasil menambahkan TikTok **@{clean_user}** ke pemantauan di {channel_to_use.mention}.", ephemeral=True)

    @tt_group.command(name="remove", description="Hapus akun TikTok dari pemantauan")
    @commands.is_owner()
    async def tt_remove(self, ctx: commands.Context, username: str):
        clean_user = await async_resolve_tiktok_username(username)
        before_count = len(self.config["targets"])
        self.config["targets"] = [
            t for t in self.config["targets"]
            if not (t.get("platform") == "tiktok" and t.get("identifier").lower() == clean_user.lower())
        ]
        if len(self.config["targets"]) < before_count:
            self._save_config()
            return await ctx.send(f"Akun TikTok `@{clean_user}` berhasil dihapus dari pemantauan.", ephemeral=True)
        await ctx.send(f"Akun TikTok `@{clean_user}` tidak ditemukan.", ephemeral=True)

    @tt_group.command(name="config", description="Buka panel pengaturan untuk akun TikTok")
    @app_commands.describe(target="Nama pengguna atau ID TikTok yang ingin diatur (opsional)")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def tt_config(self, ctx: commands.Context, target: Optional[str] = None):
        await self.tt_setup(ctx, target)

    @tt_group.command(name="clearcache", description="Bersihkan cache riwayat video/live TikTok agar bot mendeteksi ulang")
    @app_commands.describe(target="Username TikTok yang ingin dibersihkan cachenya (opsional)")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def tt_clearcache(self, ctx: commands.Context, target: Optional[str] = None):
        await ctx.defer(ephemeral=True)
        count = await self._clear_target_cache("tiktok", target)
        if target:
            await ctx.send(f"🧹 Berhasil membersihkan **{count}** cache riwayat untuk TikTok `@{target}`! Video/Live berikutnya akan dianggap baru.", ephemeral=True)
        else:
            await ctx.send(f"🧹 Berhasil membersihkan seluruh cache TikTok (**{count}** konten)! Seluruh akun TikTok akan diperiksa ulang.", ephemeral=True)


    @tt_group.command(name="list", description="Daftar akun TikTok yang dipantau")
    @commands.is_owner()
    async def tt_list(self, ctx: commands.Context):
        tt_targets = [t for t in self.config["targets"] if t.get("platform") == "tiktok"]
        if not tt_targets:
            return await ctx.send("Belum ada akun TikTok yang dipantau.", ephemeral=True)

        lines = ["**Daftar Pemantauan TikTok:**"]
        for idx, t in enumerate(tt_targets, 1):
            status = "AKTIF" if t.get("enabled", True) else "NONAKTIF"
            ch_mention = f"<#{t['target_channel_id']}>"
            lines.append(f"{idx}. **@{t['display_name']}** - {ch_mention} [{status}] Mode: `{t.get('message_mode', 'ai')}` Mention: `{t.get('mention_role')}`")
        await ctx.send("\n".join(lines), ephemeral=True)

    @tt_group.command(name="test", description="Kirim uji coba notifikasi untuk URL TikTok")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def tt_test(self, ctx: commands.Context, url: str, channel: discord.TextChannel = None):
        target_channel = channel or ctx.channel
        await ctx.defer(ephemeral=True)
        try:
            meta = await self._fetch_single_tiktok_metadata(url)
            if not meta or not meta.get("video_id"):
                return await ctx.send("❌ Gagal mengekstrak metadata TikTok. Pastikan URL valid dan video bersifat publik.", ephemeral=True)

            existing_target = None
            clean_creator = normalize_tiktok_username(meta["creator"]) or meta["creator"].lower().lstrip("@")
            for t in self.config.get("targets", []):
                if t.get("platform") == "tiktok" and t.get("identifier", "").lower() == clean_creator:
                    existing_target = t
                    break

            dummy_target = {
                "platform": "tiktok",
                "identifier": clean_creator,
                "display_name": meta["creator"],
                "target_channel_id": target_channel.id,
                "mention_role": existing_target.get("mention_role", "none") if existing_target else "none",
                "message_mode": existing_target.get("message_mode", "ai") if existing_target else "ai",
                "custom_template": existing_target.get("custom_template") if existing_target else None,
                "card_title": existing_target.get("card_title") if existing_target else None,
                "card_desc": existing_target.get("card_desc") if existing_target else None,
                "button_label": existing_target.get("button_label") if existing_target else None,
                "use_card": existing_target.get("use_card", True) if existing_target else True,
            }
            card_sent = await self._send_content_card(dummy_target, meta)

            embed = discord.Embed(
                title="🎬 Preview Pengujian Notifikasi TikTok",
                description="Pengujian notifikasi berhasil diproses dengan detail konten di bawah ini:",
                color=0x00F2FE
            )
            embed.add_field(name="👤 Kreator / Akun", value=f"**@{meta['creator']}**", inline=True)
            embed.add_field(name="🆔 ID Video", value=f"`{meta['video_id']}`", inline=True)
            embed.add_field(name="📢 Saluran Target", value=target_channel.mention, inline=True)
            caption_preview = meta['title'][:250] + ("..." if len(meta['title']) > 250 else "")
            embed.add_field(name="📝 Caption / Judul", value=caption_preview, inline=False)
            embed.add_field(name="🔗 Tautan Video", value=f"[Buka Video TikTok]({meta['url']})", inline=False)
            status_text = f"✅ Notifikasi berhasil dikirim ke {target_channel.mention}." if card_sent else f"⚠️ Gagal mengirim notifikasi ke {target_channel.mention}."
            embed.add_field(name="⚡ Status Pengiriman", value=status_text, inline=False)
            if meta.get("thumbnail"):
                embed.set_thumbnail(url=meta["thumbnail"])
            embed.set_footer(text="Gunakan link video TikTok siapapun untuk preview format notifikasi.")
            await ctx.send(embed=embed, ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Terjadi kesalahan saat menguji URL TikTok: {e}", ephemeral=True)

    @tt_group.command(name="check", description="Paksa cek pembaruan TikTok sekarang")
    @commands.is_owner()
    async def tt_check(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        targets = [t for t in self.config["targets"] if t.get("platform") == "tiktok" and t.get("enabled", True)]
        found_any = 0
        for t in targets:
            items = await self._fetch_tiktok_content(t["identifier"], t.get("sec_uid"))
            for it in items:
                if it.get("sec_uid") and not t.get("sec_uid"):
                    t["sec_uid"] = it["sec_uid"]
                    self._save_config()
                vid = it["video_id"]
                if self._is_id_posted(vid):
                    continue
                if await self._send_content_card(t, it):
                    if not it.get("is_live"):
                        self._record_posted_id(vid)
                    found_any += 1
        await ctx.send(f"Pengecekan selesai. Ditemukan dan dikirim: {found_any} video TikTok baru.", ephemeral=True)

    @commands.hybrid_group(name="ig", description="Manajemen pemantauan Instagram")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def ig_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await self.ig_setup(ctx)

    @ig_group.command(name="setup", description="Dashboard All-in-One konfigurasi pemantauan Instagram")
    @app_commands.describe(target="Nama pengguna atau ID Instagram yang ingin diatur (opsional)")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def ig_setup(self, ctx: commands.Context, target: Optional[str] = None):
        found = None
        if target:
            clean = await async_resolve_instagram_username(target)
            for t in self.config.get("targets", []):
                if t.get("platform") == "instagram" and (t.get("identifier", "").lower() == clean.lower() or clean.lower() in t.get("display_name", "").lower() or t.get("id") == clean):
                    found = t
                    break
            if not found:
                return await ctx.send(f"Akun Instagram `@{target}` tidak ditemukan.", ephemeral=True)

        view = InstagramStudioView(self, ctx.guild, ctx.author, initial_target=found)
        await ctx.send(embed=view.build_embed(), view=view, ephemeral=True)

    @ig_group.command(name="studio", description="Buka panel All-in-One Studio Instagram")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def ig_studio(self, ctx: commands.Context, target: Optional[str] = None):
        await self.ig_setup(ctx, target)

    @ig_group.command(name="add", description="Tambah akun Instagram untuk dipantau")
    @commands.is_owner()
    async def ig_add(self, ctx: commands.Context, username: str, target_channel: Optional[discord.TextChannel] = None):
        channel_to_use = target_channel or ctx.channel
        clean_user = await async_resolve_instagram_username(username)
        if not clean_user:
            return await ctx.send("Nama pengguna atau tautan akun Instagram tidak valid.", ephemeral=True)

        for t in self.config["targets"]:
            if t.get("platform") == "instagram" and t.get("identifier").lower() == clean_user.lower():
                t["target_channel_id"] = channel_to_use.id
                t["target_guild_id"] = ctx.guild.id if ctx.guild else None
                self._save_config()
                return await ctx.send(f"Akun Instagram **@{clean_user}** sudah terdaftar, target diperbarui ke {channel_to_use.mention}.", ephemeral=True)

        new_target = {
            "id": str(uuid.uuid4())[:8],
            "platform": "instagram",
            "identifier": clean_user,
            "display_name": clean_user,
            "target_guild_id": ctx.guild.id if ctx.guild else None,
            "target_channel_id": channel_to_use.id,
            "content": "@everyone {ai_hype}",
            "custom_template": "@everyone {ai_hype}",
            "card_title": "[{judul}]({url})",
            "card_desc": "{deskripsi}",
            "button_label": None,
            "use_card": True,
            "enabled": True,
            "feed_enabled": True,
            "reels_enabled": True,
            "stories_enabled": True,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        self.config["targets"].append(new_target)
        self._save_config()

        current_items = await self._fetch_instagram_content(clean_user)
        for it in current_items:
            if it.get("creator") and new_target.get("display_name") == clean_user:
                new_target["display_name"] = it["creator"]
            if not it.get("is_story") and it["video_id"] not in self.cache["posted_ids"]:
                self.cache["posted_ids"].append(it["video_id"])
        self._save_config()
        self._save_cache()

        await ctx.send(f"Berhasil menambahkan Instagram **@{clean_user}** ke pemantauan di {channel_to_use.mention}.", ephemeral=True)

    @ig_group.command(name="remove", description="Hapus akun Instagram dari pemantauan")
    @commands.is_owner()
    async def ig_remove(self, ctx: commands.Context, username: str):
        clean_user = await async_resolve_instagram_username(username)
        before_count = len(self.config["targets"])
        self.config["targets"] = [
            t for t in self.config["targets"]
            if not (t.get("platform") == "instagram" and t.get("identifier").lower() == clean_user.lower())
        ]
        if len(self.config["targets"]) < before_count:
            self._save_config()
            return await ctx.send(f"Akun Instagram `@{clean_user}` berhasil dihapus dari pemantauan.", ephemeral=True)
        await ctx.send(f"Akun Instagram `@{clean_user}` tidak ditemukan.", ephemeral=True)

    @ig_group.command(name="config", description="Buka panel pengaturan All-in-One untuk akun Instagram")
    @app_commands.describe(target="Nama pengguna atau ID Instagram yang ingin diatur (opsional)")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def ig_config(self, ctx: commands.Context, target: Optional[str] = None):
        await self.ig_setup(ctx, target)

    @ig_group.command(name="clearcache", description="Bersihkan cache riwayat postingan/reels/story Instagram agar bot mendeteksi ulang")
    @app_commands.describe(target="Username Instagram yang ingin dibersihkan cachenya (opsional)")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def ig_clearcache(self, ctx: commands.Context, target: Optional[str] = None):
        await ctx.defer(ephemeral=True)
        count = await self._clear_target_cache("instagram", target)
        if target:
            await ctx.send(f"🧹 Berhasil membersihkan **{count}** cache riwayat untuk Instagram `@{target}`! Postingan/Story berikutnya akan dianggap baru.", ephemeral=True)
        else:
            await ctx.send(f"🧹 Berhasil membersihkan seluruh cache Instagram (**{count}** konten)! Seluruh akun Instagram akan diperiksa ulang.", ephemeral=True)

    @ig_group.command(name="list", description="Daftar akun Instagram yang dipantau")
    @commands.is_owner()
    async def ig_list(self, ctx: commands.Context):
        ig_targets = [t for t in self.config["targets"] if t.get("platform") == "instagram"]
        if not ig_targets:
            return await ctx.send("Belum ada akun Instagram yang dipantau.", ephemeral=True)

        lines = ["**Daftar Pemantauan Instagram:**"]
        for idx, t in enumerate(ig_targets, 1):
            status = "AKTIF" if t.get("enabled", True) else "NONAKTIF"
            ch_mention = f"<#{t['target_channel_id']}>"
            lines.append(f"{idx}. **@{t['display_name']}** - {ch_mention} [{status}] Mode: `{t.get('message_mode', 'ai')}` Mention: `{t.get('mention_role')}`")
        await ctx.send("\n".join(lines), ephemeral=True)

    @ig_group.command(name="test", description="Kirim uji coba notifikasi untuk URL Instagram")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def ig_test(self, ctx: commands.Context, url: str, channel: Optional[discord.TextChannel] = None):
        target_channel = channel or ctx.channel
        await ctx.defer(ephemeral=True)
        try:
            meta = await self._fetch_single_instagram_metadata(url)
            if not meta or not meta.get("video_id"):
                return await ctx.send("❌ Gagal mengekstrak metadata Instagram. Pastikan URL valid dan postingan bersifat publik.", ephemeral=True)

            existing_target = None
            clean_creator = normalize_instagram_username(meta["creator"]) or meta["creator"].lower().lstrip("@")
            for t in self.config.get("targets", []):
                if t.get("platform") == "instagram" and t.get("identifier", "").lower() == clean_creator:
                    existing_target = t
                    break

            dummy_target = {
                "platform": "instagram",
                "identifier": clean_creator,
                "display_name": meta["creator"],
                "target_channel_id": target_channel.id,
                "mention_role": existing_target.get("mention_role", "none") if existing_target else "none",
                "message_mode": existing_target.get("message_mode", "ai") if existing_target else "ai",
                "custom_template": existing_target.get("custom_template") if existing_target else None,
                "card_title": existing_target.get("card_title") if existing_target else None,
                "card_desc": existing_target.get("card_desc") if existing_target else None,
                "button_label": existing_target.get("button_label") if existing_target else None,
                "use_card": existing_target.get("use_card", True) if existing_target else True,
            }
            card_sent = await self._send_content_card(dummy_target, meta)

            embed = discord.Embed(
                title="📸 Preview Pengujian Notifikasi Instagram",
                description="Pengujian notifikasi berhasil diproses dengan detail konten di bawah ini:",
                color=0xE1306C
            )
            embed.add_field(name="👤 Kreator / Akun", value=f"**@{meta['creator']}**", inline=True)
            embed.add_field(name="🆔 ID Konten", value=f"`{meta['video_id']}`", inline=True)
            embed.add_field(name="📢 Saluran Target", value=target_channel.mention, inline=True)
            caption_preview = meta['title'][:250] + ("..." if len(meta['title']) > 250 else "")
            embed.add_field(name="📝 Caption / Judul", value=caption_preview, inline=False)
            embed.add_field(name="🔗 Tautan Konten", value=f"[Buka di Instagram]({meta['url']})", inline=False)
            status_text = f"✅ Notifikasi berhasil dikirim ke {target_channel.mention}." if card_sent else f"⚠️ Gagal mengirim notifikasi ke {target_channel.mention}."
            embed.add_field(name="⚡ Status Pengiriman", value=status_text, inline=False)
            if meta.get("thumbnail"):
                embed.set_thumbnail(url=meta["thumbnail"])
            embed.set_footer(text="Gunakan link postingan atau reels Instagram publik untuk preview format notifikasi.")
            await ctx.send(embed=embed, ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Terjadi kesalahan saat menguji URL Instagram: {e}", ephemeral=True)

    @ig_group.command(name="check", description="Paksa cek pembaruan Instagram sekarang")
    @commands.is_owner()
    async def ig_check(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        targets = [t for t in self.config["targets"] if t.get("platform") == "instagram" and t.get("enabled", True)]
        found_any = 0
        for t in targets:
            items = await self._fetch_instagram_content(t["identifier"])
            for it in items:
                vid = it["video_id"]
                if self._is_id_posted(vid):
                    continue
                is_story = it.get("is_story", False)
                is_reel = it.get("is_reel", False)
                if is_story and not t.get("stories_enabled", True):
                    self._record_posted_id(vid)
                    continue
                if is_reel and not t.get("reels_enabled", True):
                    self._record_posted_id(vid)
                    continue
                if not is_story and not is_reel and not t.get("feed_enabled", True):
                    self._record_posted_id(vid)
                    continue
                if await self._send_content_card(t, it):
                    self._record_posted_id(vid)
                    found_any += 1
        await ctx.send(f"Pengecekan selesai. Ditemukan dan dikirim: {found_any} konten Instagram baru.", ephemeral=True)

    @commands.hybrid_command(name="social", aliases=["sosmed", "socialhub", "socialstudio"], description="Buka studio pengaturan notifikasi media sosial")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def social_studio(self, ctx: commands.Context, target: Optional[str] = None):
        found = None
        if target:
            clean = target.lstrip("@").strip().lower()
            for t in self.config.get("targets", []):
                if clean in (t.get("identifier", "").lower(), t.get("display_name", "").lower(), t.get("id")):
                    found = t
                    break
            if not found:
                return await ctx.send(f"Target `{target}` tidak ditemukan.", ephemeral=True)

        if found:
            plat = found.get("platform")
            if plat == "instagram":
                view = InstagramStudioView(self, ctx.guild, ctx.author, initial_target=found)
            elif plat == "tiktok":
                view = TikTokStudioView(self, ctx.guild, ctx.author, initial_target=found)
            else:
                view = YouTubeStudioView(self, ctx.guild, ctx.author, initial_target=found)
            return await ctx.send(embed=view.build_embed(), view=view, ephemeral=True)

        yt_view = YouTubeStudioView(self, ctx.guild, ctx.author)
        if yt_view.get_targets():
            return await ctx.send(embed=yt_view.build_embed(), view=yt_view, ephemeral=True)
        tt_view = TikTokStudioView(self, ctx.guild, ctx.author)
        if tt_view.get_targets():
            return await ctx.send(embed=tt_view.build_embed(), view=tt_view, ephemeral=True)
        ig_view = InstagramStudioView(self, ctx.guild, ctx.author)
        if ig_view.get_targets():
            return await ctx.send(embed=ig_view.build_embed(), view=ig_view, ephemeral=True)
        await ctx.send(embed=yt_view.build_embed(), view=yt_view, ephemeral=True)

    @commands.command(name="socialadd", aliases=["addsocial", "tambahsocial"])
    @commands.is_owner()
    async def social_add(self, ctx: commands.Context, platform: Literal["youtube", "tiktok", "instagram"], target: str, kanal: Optional[discord.TextChannel] = None):
        channel_to_use = kanal or ctx.channel
        plat = platform.lower()
        if plat == "youtube":
            return await self.yt_add(ctx, target, channel_to_use)
        elif plat == "tiktok":
            return await self.tt_add(ctx, target, channel_to_use)
        elif plat == "instagram":
            return await self.ig_add(ctx, target, channel_to_use)

    @commands.command(name="socialremove", aliases=["rmsocial", "hapussocial"])
    @commands.is_owner()
    async def social_remove(self, ctx: commands.Context, target: str):
        clean_user = await async_resolve_tiktok_username(target)
        clean_ig = await async_resolve_instagram_username(target)
        raw_clean = target.lstrip("@").strip().lower()
        before_count = len(self.config["targets"])
        self.config["targets"] = [
            t for t in self.config["targets"]
            if not (clean_user.lower() in (t.get("identifier", "").lower(), t.get("display_name", "").lower(), t.get("id")) or clean_ig.lower() in (t.get("identifier", "").lower(), t.get("display_name", "").lower(), t.get("id")) or raw_clean in (t.get("identifier", "").lower(), t.get("display_name", "").lower(), t.get("id")))
        ]
        if len(self.config["targets"]) < before_count:
            self._save_config()
            return await ctx.send(f"Target `{target}` berhasil dihapus dari pemantauan.", ephemeral=True)
        await ctx.send(f"Target `{target}` tidak ditemukan.", ephemeral=True)

    @commands.command(name="ttadd", aliases=["addtt", "tiktokadd", "tambahtt"])
    @commands.is_owner()
    async def ttadd_cmd(self, ctx: commands.Context, username: str, target_channel: Optional[discord.TextChannel] = None):
        return await self.tt_add(ctx, username, target_channel)

    @commands.command(name="ttremove", aliases=["removett", "tiktokremove", "deltt", "ttdel", "hapustt"])
    @commands.is_owner()
    async def ttremove_cmd(self, ctx: commands.Context, username: str):
        return await self.tt_remove(ctx, username)

    @commands.command(name="ttconfig", aliases=["configtt", "tiktokconfig", "settingtt"])
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def ttconfig_cmd(self, ctx: commands.Context, target: Optional[str] = None):
        return await self.tt_config(ctx, target)

    @commands.command(name="igadd", aliases=["addig", "instagramadd", "tambahig"])
    @commands.is_owner()
    async def igadd_cmd(self, ctx: commands.Context, username: str, target_channel: Optional[discord.TextChannel] = None):
        return await self.ig_add(ctx, username, target_channel)

    @commands.command(name="igremove", aliases=["removeig", "instagramremove", "delig", "igdel", "hapusig"])
    @commands.is_owner()
    async def igremove_cmd(self, ctx: commands.Context, username: str):
        return await self.ig_remove(ctx, username)

    @commands.command(name="igconfig", aliases=["configig", "instagramconfig", "settingig"])
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def igconfig_cmd(self, ctx: commands.Context, target: Optional[str] = None):
        return await self.ig_config(ctx, target)

    @commands.command(name="sociallist", aliases=["listsocial"])
    @commands.is_owner()
    async def social_list(self, ctx: commands.Context):
        targets = self.config.get("targets", [])
        if not targets:
            return await ctx.send("Belum ada target yang dipantau.", ephemeral=True)

        lines = ["**Daftar Pemantauan Media Sosial:**"]
        for idx, t in enumerate(targets, 1):
            plat = t.get("platform", "").capitalize()
            status = "AKTIF" if t.get("enabled", True) else "NONAKTIF"
            ch = f"<#{t['target_channel_id']}>"
            lines.append(f"{idx}. `[{plat}]` **{t['display_name']}** - {ch} [{status}]")
        await ctx.send("\n".join(lines), ephemeral=True)

    @commands.command(name="socialtest", aliases=["testsocial"])
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def social_test(self, ctx: commands.Context, url: str, kanal: Optional[discord.TextChannel] = None):
        target_ch = kanal or ctx.channel
        clean_url = url.strip()
        if "tiktok.com" in clean_url:
            return await self.tt_test(ctx, clean_url, target_ch)
        elif "instagram.com" in clean_url:
            return await self.ig_test(ctx, clean_url, target_ch)
        else:
            return await self.yt_test(ctx, clean_url, target_ch)

    @commands.command(name="socialcheck", aliases=["checksocial"])
    @commands.is_owner()
    async def social_check(self, ctx: commands.Context):
        return await self.checker_check(ctx)

    @commands.group(name="checker")
    @commands.is_owner()
    async def checker_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Gunakan `!checker list`, `!checker check`, `!checker interval`, `!checker cache`, `!checker resetcache`.", ephemeral=True)

    @checker_group.command(name="list")
    @commands.is_owner()
    async def checker_list(self, ctx: commands.Context):
        targets = self.config.get("targets", [])
        if not targets:
            return await ctx.send("Belum ada target yang dipantau di SocialChecker.", ephemeral=True)

        lines = ["**Daftar Seluruh Target SocialChecker:**"]
        for idx, t in enumerate(targets, 1):
            plat = t.get("platform", "").upper()
            status = "AKTIF" if t.get("enabled", True) else "NONAKTIF"
            ch = f"<#{t['target_channel_id']}>"
            lines.append(f"{idx}. `[{plat}]` **{t['display_name']}** - {ch} [{status}] Mode: `{t.get('message_mode', 'ai')}`")
        await ctx.send("\n".join(lines), ephemeral=True)

    @checker_group.command(name="check", description="Cek pembaruan semua target secara serentak")
    @commands.is_owner()
    async def checker_check(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        targets = [t for t in self.config["targets"] if t.get("enabled", True)]
        found_any = 0
        for t in targets:
            platform = t.get("platform")
            if platform == "youtube":
                items = await self._fetch_youtube_content(t["identifier"])
                for it in items:
                    vid = it["video_id"]
                    if vid in self.cache["posted_ids"]:
                        continue
                    meta = await self._fetch_youtube_metadata(vid, it.get("is_live", False))
                    if meta.get("channel_id") and meta["channel_id"] != t["identifier"]:
                        continue
                    if await self._send_content_card(t, meta):
                        self.cache["posted_ids"].append(vid)
                        found_any += 1
            elif platform == "tiktok":
                items = await self._fetch_tiktok_content(t["identifier"], t.get("sec_uid"))
                for it in items:
                    if it.get("sec_uid") and not t.get("sec_uid"):
                        t["sec_uid"] = it["sec_uid"]
                        self._save_config()
                    vid = it["video_id"]
                    if vid in self.cache["posted_ids"]:
                        continue
                    if await self._send_content_card(t, it):
                        if not it.get("is_live"):
                            self.cache["posted_ids"].append(vid)
                        found_any += 1
            elif platform == "instagram":
                items = await self._fetch_instagram_content(t["identifier"])
                for it in items:
                    vid = it["video_id"]
                    if vid in self.cache["posted_ids"]:
                        continue
                    if await self._send_content_card(t, it):
                        if not it.get("is_story"):
                            self.cache["posted_ids"].append(vid)
                        found_any += 1
        self._save_cache()
        await ctx.send(f"Pengecekan serentak selesai. Ditemukan dan dikirim: {found_any} konten baru.", ephemeral=True)


    @checker_group.command(name="interval", description="Ubah interval polling checker dalam detik")
    @commands.is_owner()
    async def checker_interval(self, ctx: commands.Context, seconds: int):
        if seconds < 10:
            return await ctx.send("Interval minimum adalah 10 detik.", ephemeral=True)
        self.config["check_interval"] = seconds
        self._save_config()
        self.checker_loop.change_interval(seconds=seconds)
        await ctx.send(f"Interval polling berhasil diubah ke {seconds} detik.", ephemeral=True)

    @checker_group.command(name="cache", description="Lihat jumlah ID tersimpan di cache")
    @commands.is_owner()
    async def checker_cache(self, ctx: commands.Context):
        count = len(self.cache.get("posted_ids", []))
        await ctx.send(f"Jumlah riwayat ID konten di cache: **{count}** item.", ephemeral=True)

    @checker_group.command(name="resetcache", description="Reset cache ID yang sudah diposting")
    @commands.is_owner()
    async def checker_resetcache(self, ctx: commands.Context):
        self.cache["posted_ids"] = []
        self._save_cache()
        await ctx.send("Cache riwayat ID berhasil dikosongkan.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(SocialChecker(bot))

