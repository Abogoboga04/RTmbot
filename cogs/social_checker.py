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



class SocialFormatEditorModal(discord.ui.Modal, title="Format Notifikasi"):
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
            label="Isi Pesan Biasa",
            default=current_content,
            placeholder="Contoh: @everyone {ai_hype} (Gunakan: {ai_hype}, {judul}, {channel}, {url})",
            style=discord.TextStyle.paragraph,
            max_length=1500,
            required=True
        )
        self.title_input = discord.ui.TextInput(
            label="Judul Utama",
            default=current_title,
            placeholder="Variabel: {judul}, {channel}, {url}",
            max_length=256,
            required=True
        )
        self.desc_input = discord.ui.TextInput(
            label="Deskripsi Utama",
            default=current_desc,
            placeholder="Variabel: {deskripsi}, {judul}, {url}",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True
        )
        self.btn_input = discord.ui.TextInput(
            label="Label Tombol",
            default=current_btn,
            placeholder="Kosongkan untuk otomatis (cth: Tonton di YouTube)",
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
                p_name = "YouTube" if t.get("platform") == "youtube" else "TikTok"
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
        btn_label = self.target.get("button_label") or ("Buka di TikTok" if self.target.get("platform") == "tiktok" else "Tonton di YouTube")
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

        is_tiktok = self.target.get("platform") == "tiktok"
        d_name = self.target.get("display_name", self.target.get("identifier"))
        target_ident = normalize_tiktok_username(self.target.get("identifier")) if is_tiktok else self.target.get("identifier")
        sample_url = f"https://www.tiktok.com/@{target_ident}" if is_tiktok else "https://www.youtube.com"
        sample_thumb = "https://images.unsplash.com/photo-1611162618071-b39a2ec055fb?w=800" if is_tiktok else "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800"
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

    async def _generate_ai_hype(self, creator: str, title: str, platform: str, is_live: bool = False) -> str:
        if not API_KEYS:
            return self._fallback_hype(creator, platform, is_live)

        tipe_konten = "Live Streaming TikTok" if (platform == "tiktok" and is_live) else ("Video TikTok" if platform == "tiktok" else ("Live Streaming YouTube" if is_live else "Video Baru YouTube"))

        info_lines = []
        if creator:
            info_lines.append(f"- Channel/Kreator: {creator}")
        if title:
            info_lines.append(f"- Judul: {title}")

        context_str = "\n".join(info_lines) if info_lines else "Belum ada detail khusus."

        prompt = f"""Kamu adalah bot Discord server RTMxBadut.
Tugas kamu membuat 1 kalimat notifikasi/sapaan santai dan asik buat warga server tentang {tipe_konten} yang baru rilis/dimulai.

Informasi konten:
{context_str}

Panduan gaya & aturan mutlak:
1. Hubungkan sapaan kamu secara alami dengan judul atau topik kontennya di atas. Jangan buat pujian kosong yang tidak nyambung dengan isi videonya.
2. Gunakan bahasa obrolan Discord/tongkrongan Indonesia yang asik, santai, dan luwes.
3. Sesuaikan dengan situasinya:
   - Kalau video santai/keseharian/vlog, sapa warga server dengan santai dan ajak nonton.
   - Kalau live streaming, ajak warga server langsung merapat ke live chat.
4. Singkat, padat (cukup 1-2 kalimat). Jangan pakai hashtag dan jangan tulis URL link di dalam teks karena link sudah disediakan di tombol.
5. PENTING: DILARANG KERAS menyertakan kalimat pembuka/basa-basi apapun seperti "Siap!", "Berikut adalah...", "Ini dia pengumumannya:", "Tentu!", atau tanda kutip pembuka/penutup.
6. LANGSUNG tulis isi kalimat notifikasinya dari kata pertama tanpa kata pengantar atau judul sama sekali.

Tulis LANGSUNG teks pengumumannya sekarang:"""

        models_to_try = ['gemini-2.5-flash', 'gemini-3-flash-preview', 'gemini-2.5-flash-lite']

        for model_name in models_to_try:
            attempts = max(1, len(API_KEYS))
            for _ in range(attempts):
                try:
                    model = genai.GenerativeModel(model_name)
                    response = await asyncio.wait_for(model.generate_content_async(prompt), timeout=30.0)
                    if response and response.text:
                        cleaned = clean_ai_hype_text(response.text)
                        if cleaned:
                            return cleaned
                except asyncio.TimeoutError:
                    return self._fallback_hype(creator, platform, is_live)
                except google_exceptions.ResourceExhausted:
                    if rotate_api_key():
                        await asyncio.sleep(1)
                        continue
                    else:
                        break
                except Exception:
                    break

        return self._fallback_hype(creator, platform, is_live)

    def _fallback_hype(self, creator: str, platform: str, is_live: bool) -> str:
        if platform == "tiktok":
            if is_live:
                return f"**{creator}** sedang live streaming di TikTok sekarang! Yuk tonton keseruannya!"
            return f"Video TikTok terbaru dari **{creator}** sudah tayang!"
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
        url = f"https://www.tiktok.com/@{clean_user}/"
        try:
            from curl_cffi import requests as cffi_requests
            s = cffi_requests.Session(impersonate="chrome")
            s.headers.update({
                "Referer": "https://www.tiktok.com/",
                "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
            })
            r = s.get(url, timeout=10)
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
            "playlist_items": "1:5",
            "socket_timeout": 12,
            "logger": _SilentYDLLogger(),
        }
        try:
            from yt_dlp.networking.impersonate import ImpersonateTarget
            ydl_opts["impersonate"] = ImpersonateTarget.from_str("chrome")
        except Exception:
            pass
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"tiktokuser:{sec_uid}", download=False)
                if not info or "entries" not in info:
                    return []
                results = []
                for entry in info.get("entries", []):
                    if not entry:
                        continue
                    vid = str(entry.get("id") or "")
                    if not vid:
                        continue
                    url = entry.get("url")
                    if not url or not url.startswith("http"):
                        url = f"https://www.tiktok.com/@{clean_user}/video/{vid}"
                    uploader = entry.get("uploader") or creator_name
                    title_raw = entry.get("title") or f"TikTok Video by @{clean_user}"
                    results.append({
                        "video_id": vid,
                        "title": clean_hyperlink_title(title_raw) or f"TikTok Video by @{clean_user}",
                        "creator": uploader,
                        "url": url,
                        "thumbnail": entry.get("thumbnail"),
                        "description": title_raw,
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
        url = f"https://www.tiktok.com/embed/@{clean_user}/"
        try:
            from curl_cffi import requests as cffi_requests
            s = cffi_requests.Session(impersonate="chrome")
            s.headers.update({
                "Referer": "https://www.tiktok.com/",
                "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
            })
            r = s.get(url, timeout=10)
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
                            "description": desc,
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
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception:
            return None

    async def _fetch_tiktok_content(self, username: str, sec_uid: Optional[str] = None):
        clean_user = normalize_tiktok_username(username)
        if not clean_user:
            return []

        results = []
        known_sec_uid = sec_uid
        display_name = clean_user

        try:
            live_item, fetched_sec_uid, nick, avatar = await asyncio.to_thread(self._sync_tiktok_web_profile, clean_user)
            if live_item:
                results.append(live_item)
            if fetched_sec_uid:
                known_sec_uid = fetched_sec_uid
            if nick:
                display_name = nick
        except Exception:
            pass

        if not any(r.get("is_live") for r in results):
            try:
                live_item = await asyncio.to_thread(self._sync_tiktok_live, clean_user)
                if live_item:
                    results.append(live_item)
            except Exception:
                pass

        if known_sec_uid:
            try:
                sec_videos = await asyncio.to_thread(self._sync_tiktok_secuid_videos, known_sec_uid, clean_user, display_name)
                if sec_videos:
                    results.extend(sec_videos)
                    return results
            except Exception:
                pass

        try:
            embed_results = await asyncio.to_thread(self._sync_tiktok_embed, clean_user)
            if embed_results:
                if known_sec_uid:
                    for er in embed_results:
                        er["sec_uid"] = known_sec_uid
                results.extend(embed_results)
                return results
        except Exception:
            pass

        try:
            data = await asyncio.to_thread(self._sync_tiktok_profile, clean_user)
            if data and "entries" in data:
                for entry in data.get("entries", []):
                    if not entry:
                        continue
                    vid = str(entry.get("id"))
                    if not vid:
                        continue

                    url = entry.get("url")
                    if not url or not url.startswith("http"):
                        url = f"https://www.tiktok.com/@{clean_user}/video/{vid}"

                    results.append({
                        "video_id": vid,
                        "title": clean_hyperlink_title(entry.get("title")) or f"TikTok Video by @{clean_user}",
                        "creator": entry.get("uploader") or display_name,
                        "url": url,
                        "thumbnail": entry.get("thumbnail"),
                        "description": entry.get("title") or "",
                        "is_live": False,
                        "sec_uid": known_sec_uid,
                    })
        except Exception:
            pass

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
        thumbnail = content_data.get("thumbnail")

        desc = content_data.get("description") or title or url
        desc = clean_hyperlink_title(desc) if desc else ""

        clean_card_title = clean_hyperlink_title(title)
        if not clean_card_title:
            clean_card_title = "Video TikTok" if platform == "tiktok" else "Video YouTube"

        raw_content = target.get("content") or target.get("custom_template")
        if not raw_content:
            raw_content = "@everyone {ai_hype}"

        intro_text = raw_content
        if "{ai_hype}" in intro_text or "{aihype}" in intro_text:
            ai_text = await self._generate_ai_hype(creator, clean_card_title, platform, is_live)
            intro_text = intro_text.replace("{ai_hype}", ai_text).replace("{aihype}", ai_text)

        intro_text = intro_text.replace("{judul}", clean_card_title)
        intro_text = intro_text.replace("{creator}", creator)
        intro_text = intro_text.replace("{uploader}", creator)
        intro_text = intro_text.replace("{channel}", creator)
        intro_text = intro_text.replace("{url}", url)
        intro_text = intro_text.strip()

        if platform == "tiktok":
            default_btn = "Tonton Live TikTok" if is_live else "Tonton di TikTok"
        else:
            default_btn = "Tonton Live" if is_live else "Tonton Video"
        btn_label = target.get("button_label") or default_btn
        card_title_template = target.get("card_title") or "[{judul}]({url})"
        card_desc_template = target.get("card_desc") or "{deskripsi}"
        use_card = target.get("use_card", True)

        final_card_title = card_title_template.replace("{judul}", clean_card_title).replace("{url}", url).replace("{creator}", creator)
        final_card_desc = card_desc_template.replace("{deskripsi}", desc if desc else url).replace("{judul}", clean_card_title).replace("{url}", url).replace("{creator}", creator).strip()
        if not final_card_desc:
            final_card_desc = url

        buttons = [{
            "label": btn_label,
            "style": 5,
            "url": url,
        }]

        files = None
        attachment_fn = None
        if thumbnail:
            try:
                import io
                timeout = aiohttp.ClientTimeout(total=5)
                dl_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                if "tiktok" in str(thumbnail):
                    dl_headers["Referer"] = "https://www.tiktok.com/"
                async with aiohttp.ClientSession(timeout=timeout, headers=dl_headers) as session:
                    async with session.get(thumbnail) as img_resp:
                        if img_resp.status == 200:
                            img_bytes = await img_resp.read()
                            if img_bytes:
                                files = [discord.File(io.BytesIO(img_bytes), filename="thumbnail.jpg")]
                                attachment_fn = "thumbnail.jpg"
            except Exception:
                files = None
                attachment_fn = None

        if use_card:
            card = build_v2_card(
                title=final_card_title,
                description=final_card_desc,
                color=None,
                buttons=buttons,
                attachment_filename=attachment_fn,
                media_url=thumbnail if not attachment_fn else None,
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
        await channel.send(content=send_content, view=fallback_view)
        return True

    @tasks.loop(seconds=30)
    async def checker_loop(self):
        targets = self.config.get("targets", [])
        if not targets:
            return

        for target in list(targets):
            if not target.get("enabled", True):
                continue

            platform = target.get("platform")
            identifier = target.get("identifier")

            try:
                if platform == "youtube":
                    items = await self._fetch_youtube_content(identifier)
                    for item in items:
                        vid = item["video_id"]
                        if self._is_id_posted(vid):
                            continue

                        meta = await self._fetch_youtube_metadata(vid, item.get("is_live", False))
                        if meta.get("channel_id") and meta["channel_id"] != identifier:
                            continue

                        success = await self._send_content_card(target, meta)
                        if success:
                            self._record_posted_id(vid)
                            await asyncio.sleep(2)

                elif platform == "tiktok":
                    items = await self._fetch_tiktok_content(identifier, target.get("sec_uid"))
                    for item in items:
                        if item.get("sec_uid") and not target.get("sec_uid"):
                            target["sec_uid"] = item["sec_uid"]
                            self._save_config()
                        vid = item["video_id"]
                        if self._is_id_posted(vid):
                            continue

                        success = await self._send_content_card(target, item)
                        if success:
                            self._record_posted_id(vid)
                            await asyncio.sleep(2)

            except Exception:
                pass

    @checker_loop.before_loop
    async def before_checker_loop(self):
        await self.bot.wait_until_ready()


    @commands.hybrid_group(name="yt", description="Manajemen pemantauan YouTube")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def yt_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Gunakan `/yt add`, `/yt remove`, `/yt list`, `/yt setchannel`, `/yt setmode`, `/yt check`.", ephemeral=True)

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
        found = None
        if target:
            clean = target.strip().lower()
            for t in self.config.get("targets", []):
                if t.get("platform") == "youtube" and (t.get("identifier", "").lower() == clean or clean in t.get("display_name", "").lower() or t.get("id") == clean):
                    found = t
                    break
            if not found:
                return await ctx.send(f"Channel `{target}` tidak ditemukan.", ephemeral=True)

        view = SocialCheckerStudioView(self, ctx.guild, ctx.author, platform_filter="youtube", initial_target=found)
        await ctx.send(embed=view.build_embed(), view=view, ephemeral=True)

    @yt_group.command(name="edit", description="Ubah pengaturan channel YouTube langsung dalam satu perintah")
    @app_commands.describe(
        target="Nama channel atau ID YouTube yang ingin diubah",
        kanal="Kanal Discord tujuan notifikasi",
        pesan_biasa="Isi pesan biasa (Gunakan {ai_hype} untuk AI)",
        judul="Pola judul notifikasi",
        deskripsi="Pola deskripsi konten",
        tombol="Teks tombol link",
        gaya="Gaya tampilan pesan (kartu / teks)"
    )
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def yt_edit(
        self,
        ctx: commands.Context,
        target: str,
        kanal: Optional[discord.TextChannel] = None,
        pesan_biasa: Optional[str] = None,
        judul: Optional[str] = None,
        deskripsi: Optional[str] = None,
        tombol: Optional[str] = None,
        gaya: Optional[Literal["kartu", "teks"]] = None
    ):
        clean = target.strip().lower()
        found = None
        for t in self.config.get("targets", []):
            if t.get("platform") == "youtube" and (t.get("identifier", "").lower() == clean or clean in t.get("display_name", "").lower() or t.get("id") == clean):
                found = t
                break
        if not found:
            return await ctx.send(f"Channel `{target}` tidak ditemukan.", ephemeral=True)

        changes = []
        if kanal:
            found["target_channel_id"] = kanal.id
            found["target_guild_id"] = kanal.guild.id
            changes.append(f"Kanal: {kanal.mention}")
        if pesan_biasa:
            found["content"] = pesan_biasa.strip()
            found["custom_template"] = pesan_biasa.strip()
            changes.append(f"Pesan: `{pesan_biasa.strip()}`")
        if judul:
            found["card_title"] = judul.strip()
            changes.append(f"Judul: `{judul.strip()}`")
        if deskripsi:
            found["card_desc"] = deskripsi.strip()
            changes.append(f"Deskripsi: `{deskripsi.strip()}`")
        if tombol:
            found["button_label"] = tombol.strip()
            changes.append(f"Tombol: `{tombol.strip()}`")
        if gaya:
            found["use_card"] = (gaya == "kartu")
            changes.append(f"Gaya: `{'Kartu' if found['use_card'] else 'Teks'}`")

        if not changes:
            return await ctx.send("Tidak ada opsi yang diubah. Isi salah satu parameter untuk mengubah pengaturan.", ephemeral=True)

        self._save_config()
        await ctx.send(f"Pengaturan untuk **{found['display_name']}** diperbarui:\n" + "\n".join(f"- {c}" for c in changes), ephemeral=True)


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
            await ctx.send("Gunakan `/tt add`, `/tt remove`, `/tt list`, `/tt setchannel`, `/tt setmode`, `/tt check`.", ephemeral=True)

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
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        self.config["targets"].append(new_target)
        self._save_config()

        current_items = await self._fetch_tiktok_content(clean_user)
        for it in current_items:
            if it.get("sec_uid") and not new_target.get("sec_uid"):
                new_target["sec_uid"] = it["sec_uid"]
                self._save_config()
            if it["video_id"] not in self.cache["posted_ids"]:
                self.cache["posted_ids"].append(it["video_id"])
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
        found = None
        if target:
            clean = await async_resolve_tiktok_username(target)
            for t in self.config.get("targets", []):
                if t.get("platform") == "tiktok" and (t.get("identifier", "").lower() == clean.lower() or clean.lower() in t.get("display_name", "").lower() or t.get("id") == clean):
                    found = t
                    break
            if not found:
                return await ctx.send(f"Akun TikTok `@{target}` tidak ditemukan.", ephemeral=True)

        view = SocialCheckerStudioView(self, ctx.guild, ctx.author, platform_filter="tiktok", initial_target=found)
        await ctx.send(embed=view.build_embed(), view=view, ephemeral=True)

    @tt_group.command(name="edit", description="Ubah pengaturan akun TikTok langsung dalam satu perintah")
    @app_commands.describe(
        target="Nama pengguna atau ID TikTok yang ingin diubah",
        kanal="Kanal Discord tujuan notifikasi",
        pesan_biasa="Isi pesan biasa (Gunakan {ai_hype} untuk AI)",
        judul="Pola judul notifikasi",
        deskripsi="Pola deskripsi konten",
        tombol="Teks tombol link",
        gaya="Gaya tampilan pesan (kartu / teks)"
    )
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def tt_edit(
        self,
        ctx: commands.Context,
        target: str,
        kanal: Optional[discord.TextChannel] = None,
        pesan_biasa: Optional[str] = None,
        judul: Optional[str] = None,
        deskripsi: Optional[str] = None,
        tombol: Optional[str] = None,
        gaya: Optional[Literal["kartu", "teks"]] = None
    ):
        clean = await async_resolve_tiktok_username(target)
        found = None
        for t in self.config.get("targets", []):
            if t.get("platform") == "tiktok" and (t.get("identifier", "").lower() == clean.lower() or clean.lower() in t.get("display_name", "").lower() or t.get("id") == clean):
                found = t
                break
        if not found:
            return await ctx.send(f"Akun TikTok `@{target}` tidak ditemukan.", ephemeral=True)

        changes = []
        if kanal:
            found["target_channel_id"] = kanal.id
            found["target_guild_id"] = kanal.guild.id
            changes.append(f"Kanal: {kanal.mention}")
        if pesan_biasa:
            found["content"] = pesan_biasa.strip()
            found["custom_template"] = pesan_biasa.strip()
            changes.append(f"Pesan: `{pesan_biasa.strip()}`")
        if judul:
            found["card_title"] = judul.strip()
            changes.append(f"Judul: `{judul.strip()}`")
        if deskripsi:
            found["card_desc"] = deskripsi.strip()
            changes.append(f"Deskripsi: `{deskripsi.strip()}`")
        if tombol:
            found["button_label"] = tombol.strip()
            changes.append(f"Tombol: `{tombol.strip()}`")
        if gaya:
            found["use_card"] = (gaya == "kartu")
            changes.append(f"Gaya: `{'Kartu' if found['use_card'] else 'Teks'}`")

        if not changes:
            return await ctx.send("Tidak ada opsi yang diubah. Isi salah satu parameter untuk mengubah pengaturan.", ephemeral=True)

        self._save_config()
        await ctx.send(f"Pengaturan untuk **@{found['display_name']}** diperbarui:\n" + "\n".join(f"- {c}" for c in changes), ephemeral=True)


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
                    self._record_posted_id(vid)
                    found_any += 1
        await ctx.send(f"Pengecekan selesai. Ditemukan dan dikirim: {found_any} video TikTok baru.", ephemeral=True)

    @commands.hybrid_command(name="social", aliases=["sosmed", "socialhub", "socialstudio"], description="Buka studio pengaturan notifikasi YouTube dan TikTok")
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
        view = SocialCheckerStudioView(self, ctx.guild, ctx.author, initial_target=found)
        await ctx.send(embed=view.build_embed(), view=view, ephemeral=True)

    @commands.command(name="socialadd", aliases=["addsocial", "tambahsocial"])
    @commands.is_owner()
    async def social_add(self, ctx: commands.Context, platform: Literal["youtube", "tiktok"], target: str, kanal: Optional[discord.TextChannel] = None):
        channel_to_use = kanal or ctx.channel
        plat = platform.lower()
        if plat == "youtube":
            return await self.yt_add(ctx, target, channel_to_use)
        elif plat == "tiktok":
            return await self.tt_add(ctx, target, channel_to_use)

    @commands.command(name="socialremove", aliases=["rmsocial", "hapussocial"])
    @commands.is_owner()
    async def social_remove(self, ctx: commands.Context, target: str):
        clean_user = await async_resolve_tiktok_username(target)
        raw_clean = target.lstrip("@").strip().lower()
        before_count = len(self.config["targets"])
        self.config["targets"] = [
            t for t in self.config["targets"]
            if not (clean_user.lower() in (t.get("identifier", "").lower(), t.get("display_name", "").lower(), t.get("id")) or raw_clean in (t.get("identifier", "").lower(), t.get("display_name", "").lower(), t.get("id")))
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

