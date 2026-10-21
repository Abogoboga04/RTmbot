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
from discord.ext import commands, tasks
import google.generativeai as genai
import yt_dlp
from dotenv import load_dotenv
from cogs.v2_layout import build_v2_card, send_v2_message

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
                    return {**default_cache, **doc["data"]}
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

    def _save_cache(self):
        if len(self.cache["posted_ids"]) > 500:
            self.cache["posted_ids"] = self.cache["posted_ids"][-500:]

        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=4)
        except Exception:
            pass

        self._ensure_mongo()
        if self.cache_col is not None:
            try:
                self.cache_col.replace_one(
                    {"_id": "social_checker_cache"},
                    {"_id": "social_checker_cache", "data": self.cache},
                    upsert=True,
                )
            except Exception:
                pass

    async def _generate_ai_hype(self, creator: str, title: str, platform: str, is_live: bool = False) -> str:
        if not API_KEYS:
            return self._fallback_hype(creator, platform, is_live)

        type_text = "TikTok video" if platform == "tiktok" else ("siaran langsung (Live)" if is_live else "video YouTube")
        prompt = (
            f"Kamu adalah bot notifikasi ramah dan santai di server Discord. "
            f"Kreator '{creator}' baru saja mempublikasikan {type_text} dengan judul/caption: \"{title}\". "
            f"Tulis 1 kalimat pengantar yang seru, hangat, dan mengajak member menonton sekarang tanpa basa-basi."
        )

        for _ in range(len(API_KEYS)):
            try:
                model = genai.GenerativeModel("gemini-1.5-flash")
                response = await asyncio.to_thread(model.generate_content, prompt)
                if response and response.text:
                    clean_text = " ".join(response.text.strip().splitlines())
                    return clean_text.strip('\'"')
            except Exception:
                rotate_api_key()

        return self._fallback_hype(creator, platform, is_live)

    def _fallback_hype(self, creator: str, platform: str, is_live: bool) -> str:
        if platform == "tiktok":
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
        url = f"https://www.youtube.com/channel/{channel_id}/live"
        try:
            timeout = aiohttp.ClientTimeout(total=6)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=self.http_headers, allow_redirects=True) as resp:
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
                            meta["title"] = raw_title
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

    def _sync_tiktok_profile(self, username: str):
        clean_user = username.lstrip("@").strip()
        url = f"https://www.tiktok.com/@{clean_user}"
        ydl_opts = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "playlist_items": "1:3",
            "socket_timeout": 10,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    async def _fetch_tiktok_content(self, username: str):
        clean_user = username.lstrip("@").strip()
        try:
            data = await asyncio.to_thread(self._sync_tiktok_profile, clean_user)
            if not data or "entries" not in data:
                return []

            results = []
            now_ts = datetime.now(timezone.utc).timestamp()
            for entry in data.get("entries", []):
                if not entry:
                    continue
                vid = str(entry.get("id"))
                if not vid:
                    continue

                ts = entry.get("timestamp")
                if ts and (now_ts - float(ts)) > (6 * 3600):
                    continue

                url = entry.get("url")
                if not url or not url.startswith("http"):
                    url = f"https://www.tiktok.com/@{clean_user}/video/{vid}"

                results.append({
                    "video_id": vid,
                    "title": entry.get("title") or f"TikTok Video by @{clean_user}",
                    "creator": entry.get("uploader") or clean_user,
                    "url": url,
                    "thumbnail": entry.get("thumbnail"),
                    "description": entry.get("title") or "",
                    "is_live": False,
                })
            return results
        except Exception:
            return []

    async def _fetch_single_tiktok_metadata(self, url: str) -> dict:
        meta = None
        ydl_opts = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 10,
        }
        try:
            data = await asyncio.to_thread(lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False))
            if data and data.get("id"):
                meta = {
                    "video_id": str(data.get("id")),
                    "title": data.get("title") or "TikTok Video",
                    "creator": data.get("uploader") or data.get("creator") or "TikTok Creator",
                    "url": data.get("webpage_url") or url,
                    "thumbnail": data.get("thumbnail"),
                    "description": data.get("title") or "",
                    "is_live": False,
                }
        except Exception:
            pass

        if not meta or not meta.get("thumbnail"):
            try:
                clean_url = urllib.parse.quote(url, safe="")
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"https://www.tikwm.com/api/?url={clean_url}", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            res_json = await resp.json()
                            if res_json.get("code") == 0 and res_json.get("data"):
                                d = res_json["data"]
                                meta = {
                                    "video_id": str(d.get("id") or (meta.get("video_id") if meta else "")),
                                    "title": d.get("title") or (meta.get("title") if meta else "TikTok Video"),
                                    "creator": d.get("author", {}).get("unique_id") or d.get("author", {}).get("nickname") or (meta.get("creator") if meta else "TikTok Creator"),
                                    "url": url,
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

        mention = target.get("mention_role", "@everyone")
        if mention.lower() in ("none", "null", "off", "disable", ""):
            mention_str = ""
        elif mention.startswith("<@") or mention.startswith("@"):
            mention_str = mention
        elif mention.isdigit():
            mention_str = f"<@&{mention}>"
        else:
            mention_str = mention

        mode = target.get("message_mode", "ai")
        creator = content_data.get("creator") or target.get("display_name", "Creator")
        title = content_data.get("title", "")
        url = content_data.get("url", "")
        platform = target.get("platform", "youtube")
        is_live = content_data.get("is_live", False)
        thumbnail = content_data.get("thumbnail")

        if mode == "custom" and target.get("custom_template"):
            intro_text = target["custom_template"].format(
                creator=creator,
                judul=title,
                url=url,
                mention=mention_str,
            )
        elif mode == "ai":
            hype = await self._generate_ai_hype(creator, title, platform, is_live)
            intro_text = f"{mention_str} {hype}".strip()
        else:
            if platform == "tiktok":
                intro_text = f"{mention_str} Video TikTok baru dari **{creator}** nih!".strip()
            elif is_live:
                intro_text = f"{mention_str} **{creator}** lagi live streaming nih!".strip()
            else:
                intro_text = f"{mention_str} Video baru dari **{creator}** nih!".strip()

        btn_label = "Tonton di TikTok" if platform == "tiktok" else ("Tonton Live" if is_live else "Tonton Video")
        btn_color = 0x000000 if platform == "tiktok" else (0xED4245 if is_live else 0xFF0000)

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
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(thumbnail) as img_resp:
                        if img_resp.status == 200:
                            img_bytes = await img_resp.read()
                            files = [discord.File(io.BytesIO(img_bytes), filename="thumbnail.jpg")]
                            attachment_fn = "thumbnail.jpg"
            except Exception:
                files = None
                attachment_fn = None

        card = build_v2_card(
            title=f"[{title}]({url})",
            description=desc,
            color=btn_color,
            buttons=buttons,
            attachment_filename=attachment_fn,
            media_url=thumbnail if not attachment_fn else None,
        )

        res = await send_v2_message(self.bot, channel.id, [card], files=files, content=intro_text)
        if isinstance(res, dict) and "error_msg" in res:
            return False
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
                        if vid in self.cache["posted_ids"]:
                            continue

                        meta = await self._fetch_youtube_metadata(vid, item.get("is_live", False))
                        if meta.get("channel_id") and meta["channel_id"] != identifier:
                            continue

                        success = await self._send_content_card(target, meta)
                        if success:
                            self.cache["posted_ids"].append(vid)
                            self._save_cache()
                            await asyncio.sleep(2)

                elif platform == "tiktok":
                    items = await self._fetch_tiktok_content(identifier)
                    for item in items:
                        vid = item["video_id"]
                        if vid in self.cache["posted_ids"]:
                            continue

                        success = await self._send_content_card(target, item)
                        if success:
                            self.cache["posted_ids"].append(vid)
                            self._save_cache()
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
            "mention_role": "@everyone",
            "message_mode": "ai",
            "custom_template": None,
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

    @yt_group.command(name="setchannel", description="Ubah channel Discord tujuan notifikasi")
    @commands.is_owner()
    async def yt_setchannel(self, ctx: commands.Context, identifier: str, target_channel: discord.TextChannel):
        for t in self.config["targets"]:
            if t.get("platform") == "youtube" and (t.get("identifier") == identifier or identifier in t.get("display_name", "")):
                t["target_channel_id"] = target_channel.id
                t["target_guild_id"] = target_channel.guild.id
                self._save_config()
                return await ctx.send(f"Target notifikasi untuk **{t['display_name']}** diubah ke {target_channel.mention}.", ephemeral=True)
        await ctx.send(f"Channel `{identifier}` tidak ditemukan.", ephemeral=True)

    @yt_group.command(name="setmention", description="Ubah mention role (@everyone, @role, atau none)")
    @commands.is_owner()
    async def yt_setmention(self, ctx: commands.Context, identifier: str, role: str):
        for t in self.config["targets"]:
            if t.get("platform") == "youtube" and (t.get("identifier") == identifier or identifier in t.get("display_name", "")):
                t["mention_role"] = role
                self._save_config()
                return await ctx.send(f"Mention role untuk **{t['display_name']}** diubah menjadi `{role}`.", ephemeral=True)
        await ctx.send(f"Channel `{identifier}` tidak ditemukan.", ephemeral=True)

    @yt_group.command(name="setmode", description="Ubah mode pesan (ai, default, custom)")
    @commands.is_owner()
    async def yt_setmode(self, ctx: commands.Context, identifier: str, mode: str, *, custom_text: str = None):
        valid_modes = ("ai", "default", "custom")
        clean_mode = mode.lower()
        if clean_mode not in valid_modes:
            return await ctx.send(f"Mode tidak valid. Pilihan: `ai`, `default`, `custom`.", ephemeral=True)

        for t in self.config["targets"]:
            if t.get("platform") == "youtube" and (t.get("identifier") == identifier or identifier in t.get("display_name", "")):
                t["message_mode"] = clean_mode
                if custom_text:
                    t["custom_template"] = custom_text
                self._save_config()
                return await ctx.send(f"Mode pesan untuk **{t['display_name']}** diubah ke `{clean_mode}`.", ephemeral=True)
        await ctx.send(f"Channel `{identifier}` tidak ditemukan.", ephemeral=True)

    @yt_group.command(name="toggle", description="Aktifkan atau nonaktifkan pemantauan channel")
    @commands.is_owner()
    async def yt_toggle(self, ctx: commands.Context, identifier: str):
        for t in self.config["targets"]:
            if t.get("platform") == "youtube" and (t.get("identifier") == identifier or identifier in t.get("display_name", "")):
                t["enabled"] = not t.get("enabled", True)
                status_str = "diaktifkan" if t["enabled"] else "dinonaktifkan"
                self._save_config()
                return await ctx.send(f"Pemantauan untuk **{t['display_name']}** telah {status_str}.", ephemeral=True)
        await ctx.send(f"Channel `{identifier}` tidak ditemukan.", ephemeral=True)

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

    @yt_group.command(name="test", description="Kirim kartu V2 uji coba untuk URL YouTube dan tampilkan detail preview")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def yt_test(self, ctx: commands.Context, url: str, channel: discord.TextChannel = None):
        target_channel = channel or ctx.channel
        await ctx.defer(ephemeral=True)
        vid = self._extract_youtube_id(url)
        if not vid:
            return await ctx.send("URL YouTube tidak valid.", ephemeral=True)

        meta = await self._fetch_youtube_metadata(vid)
        dummy_target = {
            "platform": "youtube",
            "identifier": meta.get("channel_id") or "test",
            "display_name": meta.get("creator", "Creator"),
            "target_channel_id": target_channel.id,
            "mention_role": "none",
            "message_mode": "ai",
            "custom_template": None,
        }
        card_sent = await self._send_content_card(dummy_target, meta)
        embed = discord.Embed(
            title="🎬 Preview Pengujian Notifikasi YouTube",
            description="Pengujian kartu notifikasi V2 berhasil diproses dengan detail konten di bawah ini:",
            color=0xFF0000
        )
        embed.add_field(name="👤 Channel / Kreator", value=f"**{meta.get('creator', 'Creator')}**", inline=True)
        embed.add_field(name="🆔 ID Video", value=f"`{meta.get('video_id', vid)}`", inline=True)
        embed.add_field(name="📢 Saluran Target", value=target_channel.mention, inline=True)
        embed.add_field(name="📝 Judul Video", value=meta.get('title', 'Video')[:250], inline=False)
        embed.add_field(name="🔗 Tautan Video", value=f"[Buka Video YouTube]({meta.get('url', url)})", inline=False)
        status_text = f"✅ Kartu V2 berhasil dikirim ke {target_channel.mention}." if card_sent else f"⚠️ Gagal mengirim kartu V2 ke {target_channel.mention}."
        embed.add_field(name="⚡ Status Kartu V2", value=status_text, inline=False)
        if meta.get("thumbnail"):
            embed.set_thumbnail(url=meta["thumbnail"])
        embed.set_footer(text="Gunakan link video YouTube siapapun untuk preview format kartu notifikasi.")
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
                if vid in self.cache["posted_ids"]:
                    continue
                meta = await self._fetch_youtube_metadata(vid, it.get("is_live", False))
                if meta.get("channel_id") and meta["channel_id"] != t["identifier"]:
                    continue
                if await self._send_content_card(t, meta):
                    self.cache["posted_ids"].append(vid)
                    found_any += 1
        self._save_cache()
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
        clean_user = username.lstrip("@").strip()

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
            "target_guild_id": ctx.guild.id if ctx.guild else None,
            "target_channel_id": channel_to_use.id,
            "mention_role": "@everyone",
            "message_mode": "ai",
            "custom_template": None,
            "enabled": True,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        self.config["targets"].append(new_target)
        self._save_config()

        current_items = await self._fetch_tiktok_content(clean_user)
        for it in current_items:
            if it["video_id"] not in self.cache["posted_ids"]:
                self.cache["posted_ids"].append(it["video_id"])
        self._save_cache()

        await ctx.send(f"Berhasil menambahkan TikTok **@{clean_user}** ke pemantauan di {channel_to_use.mention}.", ephemeral=True)

    @tt_group.command(name="remove", description="Hapus akun TikTok dari pemantauan")
    @commands.is_owner()
    async def tt_remove(self, ctx: commands.Context, username: str):
        clean_user = username.lstrip("@").strip().lower()
        before_count = len(self.config["targets"])
        self.config["targets"] = [
            t for t in self.config["targets"]
            if not (t.get("platform") == "tiktok" and t.get("identifier").lower() == clean_user)
        ]
        if len(self.config["targets"]) < before_count:
            self._save_config()
            return await ctx.send(f"Akun TikTok `@{clean_user}` berhasil dihapus dari pemantauan.", ephemeral=True)
        await ctx.send(f"Akun TikTok `@{clean_user}` tidak ditemukan.", ephemeral=True)

    @tt_group.command(name="setchannel", description="Ubah channel Discord tujuan notifikasi")
    @commands.is_owner()
    async def tt_setchannel(self, ctx: commands.Context, username: str, target_channel: discord.TextChannel):
        clean_user = username.lstrip("@").strip().lower()
        for t in self.config["targets"]:
            if t.get("platform") == "tiktok" and t.get("identifier").lower() == clean_user:
                t["target_channel_id"] = target_channel.id
                t["target_guild_id"] = target_channel.guild.id
                self._save_config()
                return await ctx.send(f"Target notifikasi TikTok **@{t['display_name']}** diubah ke {target_channel.mention}.", ephemeral=True)
        await ctx.send(f"Akun TikTok `@{clean_user}` tidak ditemukan.", ephemeral=True)

    @tt_group.command(name="setmention", description="Ubah mention role (@everyone, @role, atau none)")
    @commands.is_owner()
    async def tt_setmention(self, ctx: commands.Context, username: str, role: str):
        clean_user = username.lstrip("@").strip().lower()
        for t in self.config["targets"]:
            if t.get("platform") == "tiktok" and t.get("identifier").lower() == clean_user:
                t["mention_role"] = role
                self._save_config()
                return await ctx.send(f"Mention role untuk TikTok **@{t['display_name']}** diubah menjadi `{role}`.", ephemeral=True)
        await ctx.send(f"Akun TikTok `@{clean_user}` tidak ditemukan.", ephemeral=True)

    @tt_group.command(name="setmode", description="Ubah mode pesan (ai, default, custom)")
    @commands.is_owner()
    async def tt_setmode(self, ctx: commands.Context, username: str, mode: str, *, custom_text: str = None):
        valid_modes = ("ai", "default", "custom")
        clean_mode = mode.lower()
        if clean_mode not in valid_modes:
            return await ctx.send("Mode tidak valid. Pilihan: `ai`, `default`, `custom`.", ephemeral=True)

        clean_user = username.lstrip("@").strip().lower()
        for t in self.config["targets"]:
            if t.get("platform") == "tiktok" and t.get("identifier").lower() == clean_user:
                t["message_mode"] = clean_mode
                if custom_text:
                    t["custom_template"] = custom_text
                self._save_config()
                return await ctx.send(f"Mode pesan untuk TikTok **@{t['display_name']}** diubah ke `{clean_mode}`.", ephemeral=True)
        await ctx.send(f"Akun TikTok `@{clean_user}` tidak ditemukan.", ephemeral=True)

    @tt_group.command(name="toggle", description="Aktifkan atau nonaktifkan pemantauan akun TikTok")
    @commands.is_owner()
    async def tt_toggle(self, ctx: commands.Context, username: str):
        clean_user = username.lstrip("@").strip().lower()
        for t in self.config["targets"]:
            if t.get("platform") == "tiktok" and t.get("identifier").lower() == clean_user:
                t["enabled"] = not t.get("enabled", True)
                status_str = "diaktifkan" if t["enabled"] else "dinonaktifkan"
                self._save_config()
                return await ctx.send(f"Pemantauan TikTok **@{t['display_name']}** telah {status_str}.", ephemeral=True)
        await ctx.send(f"Akun TikTok `@{clean_user}` tidak ditemukan.", ephemeral=True)

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

    @tt_group.command(name="test", description="Kirim kartu V2 uji coba untuk URL TikTok dan tampilkan detail preview")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    async def tt_test(self, ctx: commands.Context, url: str, channel: discord.TextChannel = None):
        target_channel = channel or ctx.channel
        await ctx.defer(ephemeral=True)
        try:
            meta = await self._fetch_single_tiktok_metadata(url)
            if not meta or not meta.get("video_id"):
                return await ctx.send("❌ Gagal mengekstrak metadata TikTok. Pastikan URL valid dan video bersifat publik.", ephemeral=True)

            dummy_target = {
                "platform": "tiktok",
                "identifier": meta["creator"],
                "display_name": meta["creator"],
                "target_channel_id": target_channel.id,
                "mention_role": "none",
                "message_mode": "ai",
                "custom_template": None,
            }
            card_sent = await self._send_content_card(dummy_target, meta)

            embed = discord.Embed(
                title="🎬 Preview Pengujian Notifikasi TikTok",
                description="Pengujian kartu notifikasi V2 berhasil diproses dengan detail konten di bawah ini:",
                color=0x00F2FE
            )
            embed.add_field(name="👤 Kreator / Akun", value=f"**@{meta['creator']}**", inline=True)
            embed.add_field(name="🆔 ID Video", value=f"`{meta['video_id']}`", inline=True)
            embed.add_field(name="📢 Saluran Target", value=target_channel.mention, inline=True)
            caption_preview = meta['title'][:250] + ("..." if len(meta['title']) > 250 else "")
            embed.add_field(name="📝 Caption / Judul", value=caption_preview, inline=False)
            embed.add_field(name="🔗 Tautan Video", value=f"[Buka Video TikTok]({meta['url']})", inline=False)
            status_text = f"✅ Kartu V2 berhasil dikirim ke {target_channel.mention}." if card_sent else f"⚠️ Gagal mengirim kartu V2 ke {target_channel.mention}."
            embed.add_field(name="⚡ Status Kartu V2", value=status_text, inline=False)
            if meta.get("thumbnail"):
                embed.set_thumbnail(url=meta["thumbnail"])
            embed.set_footer(text="Gunakan link video TikTok siapapun untuk preview format kartu notifikasi.")
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
            items = await self._fetch_tiktok_content(t["identifier"])
            for it in items:
                vid = it["video_id"]
                if vid in self.cache["posted_ids"]:
                    continue
                if await self._send_content_card(t, it):
                    self.cache["posted_ids"].append(vid)
                    found_any += 1
        self._save_cache()
        await ctx.send(f"Pengecekan selesai. Ditemukan dan dikirim: {found_any} video TikTok baru.", ephemeral=True)

    @commands.hybrid_group(name="checker", description="Manajemen global checker")
    @commands.is_owner()
    async def checker_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Gunakan `/checker list`, `/checker check`, `/checker interval`, `/checker cache`, `/checker resetcache`.", ephemeral=True)

    @checker_group.command(name="list", description="Daftar semua target YouTube & TikTok")
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
                items = await self._fetch_tiktok_content(t["identifier"])
                for it in items:
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
