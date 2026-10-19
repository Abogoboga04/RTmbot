import discord
from discord.ext import commands, tasks
import json
import os
import re
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

from cogs.v2_layout import build_v2_card, send_v2_message

from dotenv import load_dotenv

load_dotenv()

# Setup API Keys Gemini
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


class YouTubeNativeCheckerTest(commands.Cog, name="YouTube Native Checker Test"):
    """
    Modul pengujian mandiri pengecekan YouTube langsung (Native Checker)
    tanpa ketergantungan pada bot luar.
    Mendukung deteksi upload, live streaming, dan premiere.
    """

    def __init__(self, bot):
        self.bot = bot
        self.config_file = "data/yt_test_config.json"
        self.cache_file = "data/yt_test_cache.json"
        
        self.mongo_client = getattr(bot, 'mongo_client', None)
        self.db = None
        self.config_col = None
        self.cache_col = None
        self._ensure_mongo()

        self.config = self._load_config()
        self.cache = self._load_cache()
        
        # Terapkan interval dari konfigurasi (default: 60 detik / 1 menit)
        interval_sec = self.config.get("check_interval_seconds", 60)
        try:
            self.yt_check_loop.change_interval(seconds=interval_sec)
        except Exception:
            pass

        # Mulai background task pengecekan berkala jika event loop sudah siap
        try:
            self.yt_check_loop.start()
        except RuntimeError:
            pass

    def _ensure_mongo(self):
        if not self.mongo_client:
            self.mongo_client = getattr(self.bot, 'mongo_client', None)
        if self.mongo_client and (not self.config_col or not self.cache_col):
            try:
                self.db = self.mongo_client["reSwan"]
                self.config_col = self.db["yt_test_config"]
                self.cache_col = self.db["yt_test_cache"]
            except Exception as e:
                print(f"[YT MONGO INIT ERROR] {e}")

    def cog_unload(self):
        self.yt_check_loop.cancel()

    def _get_interval_text(self):
        sec = self.config.get("check_interval_seconds", 60)
        if sec >= 60:
            mnt = sec // 60
            sisa_sec = sec % 60
            if sisa_sec == 0:
                return f"{sec} detik ({mnt} menit)"
            return f"{sec} detik ({mnt} menit {sisa_sec} detik)"
        return f"{sec} detik"

    # ==========================================
    # PENGELOLAAN KONFIGURASI & CACHE TERISOLASI (MONGO + LOKAL)
    # ==========================================
    def _load_config(self):
        default_config = {
            "check_interval_seconds": 60,
            "channels": []
        }
        self._ensure_mongo()

        # 1. Prioritaskan load dari MongoDB (Aman dari restart / deploy)
        if self.config_col is not None:
            try:
                doc = self.config_col.find_one({"_id": "yt_test_config"})
                if doc and "data" in doc:
                    mongo_data = doc["data"]
                    if "check_interval_minutes" in mongo_data and "check_interval_seconds" not in mongo_data:
                        mongo_data["check_interval_seconds"] = mongo_data["check_interval_minutes"] * 60
                    merged = {**default_config, **mongo_data}
                    # Sinkronkan ke file lokal
                    try:
                        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
                        with open(self.config_file, "w", encoding="utf-8") as f:
                            json.dump(merged, f, indent=4)
                    except:
                        pass
                    return merged
            except Exception as e:
                print(f"[YT MONGO LOAD CONFIG ERROR] {e}")

        # 2. Fallback ke file lokal jika mongo belum siap
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "check_interval_minutes" in data and "check_interval_seconds" not in data:
                        data["check_interval_seconds"] = data["check_interval_minutes"] * 60
                    return {**default_config, **data}
            except Exception as e:
                print(f"[YT TEST] Gagal membaca config: {e}")
        
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4)
        return default_config

    def _save_config(self):
        # 1. Simpan ke file lokal
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"[YT TEST ERROR] Gagal menyimpan config lokal: {e}")

        # 2. Simpan permanen ke MongoDB
        self._ensure_mongo()
        if self.config_col is not None:
            try:
                self.config_col.replace_one(
                    {"_id": "yt_test_config"},
                    {"_id": "yt_test_config", "data": self.config},
                    upsert=True
                )
            except Exception as e:
                print(f"[YT MONGO SAVE CONFIG ERROR] {e}")

    def _load_cache(self):
        default_cache = {
            "posted_video_ids": []
        }
        self._ensure_mongo()

        # 1. Prioritaskan load dari MongoDB
        if self.cache_col is not None:
            try:
                doc = self.cache_col.find_one({"_id": "yt_test_cache"})
                if doc and "data" in doc:
                    merged_cache = {**default_cache, **doc["data"]}
                    try:
                        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
                        with open(self.cache_file, "w", encoding="utf-8") as f:
                            json.dump(merged_cache, f, indent=4)
                    except:
                        pass
                    return merged_cache
            except Exception as e:
                print(f"[YT MONGO LOAD CACHE ERROR] {e}")

        # 2. Fallback ke file lokal
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {**default_cache, **data}
            except Exception as e:
                print(f"[YT TEST] Gagal membaca cache: {e}")
                
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(default_cache, f, indent=4)
        return default_cache

    def _save_cache(self):
        # 1. Simpan ke file lokal
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=4)
        except Exception as e:
            print(f"[YT TEST ERROR] Gagal menyimpan cache lokal: {e}")

        # 2. Simpan permanen ke MongoDB
        self._ensure_mongo()
        if self.cache_col is not None:
            try:
                self.cache_col.replace_one(
                    {"_id": "yt_test_cache"},
                    {"_id": "yt_test_cache", "data": self.cache},
                    upsert=True
                )
            except Exception as e:
                print(f"[YT MONGO SAVE CACHE ERROR] {e}")

    # ==========================================
    # HELPER PARSER & YOUTUBE RESOLVER
    # ==========================================
    def _extract_video_id(self, url: str):
        if not url:
            return None
        url = url.replace('\\', '')
        pattern = r'(?:https?:\/\/)?(?:[a-zA-Z0-9-]+\.)?(?:youtube(?:-nocookie)?\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=|watch\?.*&v=|live\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
        match = re.search(pattern, url)
        return match.group(1) if match else None

    async def resolve_channel_id(self, identifier: str):
        """
        Mengubah handle (@username), link channel, atau ID channel menjadi (channel_id, channel_name).
        """
        clean_id = identifier.strip().rstrip('/')
        
        # 1. Jika sudah berupa UC channel ID (24 karakter berawalan UC)
        if re.match(r'^UC[a-zA-Z0-9_-]{22}$', clean_id):
            channel_name = await self.fetch_channel_name_from_rss(clean_id)
            return clean_id, channel_name or "YouTube Channel"

        # 2. Jika berupa URL langsung ke channel/UC...
        uc_match = re.search(r'youtube\.com\/channel\/(UC[a-zA-Z0-9_-]{22})', clean_id)
        if uc_match:
            cid = uc_match.group(1)
            channel_name = await self.fetch_channel_name_from_rss(cid)
            return cid, channel_name or "YouTube Channel"

        # 3. Jika berupa handle (@name atau youtube.com/@name)
        handle_match = re.search(r'@([a-zA-Z0-9_.-]+)', clean_id)
        target_url = clean_id
        if handle_match:
            target_url = f"https://www.youtube.com/@{handle_match.group(1)}"
        elif not clean_id.startswith("http"):
            target_url = f"https://www.youtube.com/@{clean_id}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7"
        }

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(target_url, headers=headers) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        
                        # Cari channelId di HTML
                        cid_match = re.search(r'\"browseId\":\"(UC[a-zA-Z0-9_-]{22})\"', html)
                        if not cid_match:
                            cid_match = re.search(r'<meta itemprop=\"identifier\" content=\"(UC[a-zA-Z0-9_-]{22})\"', html)
                        if not cid_match:
                            cid_match = re.search(r'channel_id=(UC[a-zA-Z0-9_-]{22})', html)
                            
                        # Cari nama channel di HTML
                        name_match = re.search(r'<meta property=\"og:title\" content=\"(.*?)\"', html)
                        cname = name_match.group(1) if name_match else "YouTube Creator"
                        
                        if cid_match:
                            return cid_match.group(1), cname
        except Exception as e:
            print(f"[YT RESOLVE ERROR] {e}")

        return None, None

    async def fetch_channel_name_from_rss(self, channel_id: str):
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(rss_url) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        root = ET.fromstring(text)
                        author_elem = root.find("{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name")
                        if author_elem is not None and author_elem.text:
                            return author_elem.text.strip()
                        title_elem = root.find("{http://www.w3.org/2005/Atom}title")
                        if title_elem is not None and title_elem.text:
                            return title_elem.text.strip()
        except Exception:
            pass
        return None

    # ==========================================
    # RSS PARSER & STREAM STATUS CLASSIFIER
    # ==========================================
    async def fetch_latest_videos_from_rss(self, channel_id: str):
        """
        Mengambil entri video terbaru dari public Atom/RSS feed YouTube.
        Zero API Quota!
        """
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        videos = []
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(rss_url) as resp:
                    if resp.status != 200:
                        return videos
                    text = await resp.text()
                    root = ET.fromstring(text)
                    ns = {
                        "atom": "http://www.w3.org/2005/Atom",
                        "yt": "http://www.youtube.com/xml/schemas/2015",
                        "media": "http://search.yahoo.com/mrss/"
                    }
                    
                    channel_title_elem = root.find("atom:title", ns)
                    default_channel_name = channel_title_elem.text if channel_title_elem is not None else "YouTube Channel"

                    for entry in root.findall("atom:entry", ns):
                        # Ambil video ID (yt:videoId atau fallback ke atom:id)
                        video_id_elem = entry.find("yt:videoId", ns)
                        if video_id_elem is not None and video_id_elem.text:
                            vid = video_id_elem.text.strip()
                        else:
                            id_elem = entry.find("atom:id", ns)
                            if id_elem is not None and id_elem.text:
                                id_match = re.search(r'yt:video:([a-zA-Z0-9_-]{11})', id_elem.text)
                                vid = id_match.group(1) if id_match else None
                            else:
                                vid = None

                        title_elem = entry.find("atom:title", ns)
                        link_elem = entry.find("atom:link", ns)
                        published_elem = entry.find("atom:published", ns)
                        updated_elem = entry.find("atom:updated", ns)
                        channel_id_elem = entry.find("yt:channelId", ns)
                        
                        desc_elem = entry.find("media:group/media:description", ns)
                        description = desc_elem.text if desc_elem is not None else ""

                        thumb_elem = entry.find("media:group/media:thumbnail", ns)
                        thumbnail_url = thumb_elem.attrib.get("url") if thumb_elem is not None else f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg"

                        author_elem = entry.find("atom:author/atom:name", ns)
                        channel_name = author_elem.text if author_elem is not None else default_channel_name

                        if vid and title_elem is not None:
                            title = title_elem.text.strip()
                            url = link_elem.attrib.get("href") if link_elem is not None else f"https://www.youtube.com/watch?v={vid}"
                            pub = published_elem.text.strip() if published_elem is not None and published_elem.text else ""
                            upd = updated_elem.text.strip() if updated_elem is not None and updated_elem.text else ""
                            cid = channel_id_elem.text.strip() if channel_id_elem is not None and channel_id_elem.text else ""
                            
                            videos.append({
                                "video_id": vid,
                                "title": title,
                                "url": url,
                                "channel_id": cid,
                                "channel_name": channel_name,
                                "published": pub,
                                "updated": upd,
                                "thumbnail_url": thumbnail_url,
                                "description": description
                            })
        except Exception as e:
            print(f"[YT RSS ERROR] {e}")
        return videos

    async def fetch_latest_videos(self, channel_id: str):
        """
        Dual-Engine Video Detector:
        1. Cek langsung tab /videos channel YouTube (real-time, zero CDN delay).
        2. Cek public Atom RSS feed YouTube.
        Menggabungkan keduanya agar tidak ada video yang tertinggal akibat delay cache Google.
        """
        videos = []
        found_vids = set()

        # Engine 1: Channel Videos Tab (Instant & Real-time, mendeteksi video detik itu juga)
        channel_tab_url = f"https://www.youtube.com/channel/{channel_id}/videos"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(channel_tab_url, headers=headers) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        vids = re.findall(r'\"videoId\":\"([a-zA-Z0-9_-]{11})\"', html)
                        for vid in vids[:6]:
                            if vid not in found_vids:
                                found_vids.add(vid)
                                videos.append({
                                    "video_id": vid,
                                    "title": None,
                                    "url": f"https://www.youtube.com/watch?v={vid}",
                                    "channel_id": channel_id,
                                    "channel_name": None,
                                    "published": None,
                                    "updated": None,
                                    "thumbnail_url": f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg",
                                    "description": ""
                                })
        except Exception as e_tab:
            print(f"[YT TAB SCRAPE ERROR] {e_tab}")

        # Engine 2: Atom RSS Feed (Pelengkap Metadata)
        rss_videos = await self.fetch_latest_videos_from_rss(channel_id)
        for rv in rss_videos:
            rv_id = rv.get("video_id")
            if rv_id in found_vids:
                for v in videos:
                    if v["video_id"] == rv_id:
                        if rv.get("title"): v["title"] = rv["title"]
                        if rv.get("channel_name"): v["channel_name"] = rv["channel_name"]
                        if rv.get("published"): v["published"] = rv["published"]
                        if rv.get("updated"): v["updated"] = rv["updated"]
                        if rv.get("description"): v["description"] = rv["description"]
                        break
            else:
                found_vids.add(rv_id)
                videos.append(rv)

        return videos

    def is_video_fresh(self, published_str: str, updated_str: str = None, max_age_hours: int = 4) -> bool:
        """
        Mengecek apakah video masih baru menggunakan kombinasi tag <published> dan <updated>.
        - published: Kapan video diunggah/dijadwalkan.
        - updated: Kapan status video terakhir diperbarui oleh YouTube (misal premiere mulai live).
        Jika kedua waktu sudah lampau (> max_age_hours), dianggap video lama dari arsip feed.
        """
        now_utc = datetime.now(timezone.utc)
        pub_dt, upd_dt = None, None

        if published_str:
            try:
                pub_dt = datetime.fromisoformat(published_str)
            except Exception:
                pass

        if updated_str:
            try:
                upd_dt = datetime.fromisoformat(updated_str)
            except Exception:
                pass

        if not pub_dt and not upd_dt:
            return True

        pub_fresh = False
        if pub_dt:
            pub_age_sec = (now_utc - pub_dt).total_seconds()
            if pub_age_sec <= (max_age_hours * 3600):
                pub_fresh = True

        upd_fresh = False
        if upd_dt:
            upd_age_sec = (now_utc - upd_dt).total_seconds()
            if upd_age_sec <= (max_age_hours * 3600):
                upd_fresh = True

        return pub_fresh or upd_fresh

    async def classify_stream_status(self, video_id: str):
        """
        Mendeteksi secara akurat metadata video dan status penayangannya:
        - Menggunakan YouTube Official oEmbed API untuk jaminan 100% judul dan nama channel
        - Menggunakan inspeksi HTML watch untuk mendeteksi Live Stream, Premiere, atau Upload
        """
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        
        info = {
            "status": "upload",
            "title": None,
            "channel_name": None,
            "description": None,
            "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        }

        # 1. Tier 1: YouTube Official oEmbed API (100% akurat untuk Video, Shorts, Live, Premiere)
        try:
            timeout_oembed = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout_oembed) as session:
                async with session.get(oembed_url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        raw_title = data.get("title", "")
                        if raw_title:
                            info["title"] = " ".join(raw_title.split())
                        if data.get("author_name"):
                            info["channel_name"] = data.get("author_name")
                        if data.get("thumbnail_url"):
                            info["thumbnail_url"] = data.get("thumbnail_url")
        except Exception as e_oe:
            print(f"[YT OEMBED ERROR] {e_oe}")

        # 2. Tier 2: Inspeksi HTML Watch untuk status siaran (Live / Premiere / Upload) & Description
        try:
            timeout_html = aiohttp.ClientTimeout(total=6)
            async with aiohttp.ClientSession(timeout=timeout_html) as session:
                async with session.get(watch_url, headers=headers) as resp:
                    if resp.status == 200:
                        html = await resp.text()

                        # Fallback title jika oEmbed gagal
                        if not info["title"]:
                            t_match = re.search(r'<title>(.*?) - YouTube<\/title>', html)
                            if t_match:
                                info["title"] = t_match.group(1).strip()

                        # Deteksi LIVE STREAMING
                        is_live = False
                        if '"isLive":true' in html or '"status":"LIVE_STREAMING"' in html or '"isLiveContent":true' in html:
                            is_live = True

                        # Deteksi PREMIERE / UPCOMING
                        is_upcoming = False
                        if '"upcomingEvents"' in html or '"scheduledStartTime"' in html or '"isUpcoming":true' in html:
                            is_upcoming = True

                        if is_live:
                            info["status"] = "live"
                        elif is_upcoming:
                            info["status"] = "premier"
                        else:
                            info["status"] = "upload"

                        # Fallback nama channel jika oEmbed gagal
                        if not info["channel_name"]:
                            a_match = re.search(r'\"ownerChannelName\":\"(.*?)\"', html)
                            if a_match:
                                info["channel_name"] = a_match.group(1).encode().decode('unicode_escape')
                            else:
                                og_author = re.search(r'<span itemprop=\"name\" content=\"(.*?)\"', html)
                                if og_author:
                                    info["channel_name"] = og_author.group(1)

                        # Cari deskripsi pendek
                        d_match = re.search(r'\"shortDescription\":\"(.*?)\"', html)
                        if d_match:
                            try:
                                info["description"] = json.loads(f'{{"d":"{d_match.group(1)}"}}')["d"]
                            except:
                                info["description"] = d_match.group(1)
        except Exception as e_html:
            print(f"[YT HTML CLASSIFIER ERROR] {e_html}")

        # Jika thumbnail oEmbed adalah hqdefault dan maxresdefault belum dicoba, pastikan thumbnail valid
        if not info["thumbnail_url"]:
            info["thumbnail_url"] = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

        return info

    # ==========================================
    # GENERATOR AI COPYWRITING KONTEKSTUAL
    # ==========================================
    async def generate_ai_hype(self, channel_name: str, video_title: str, video_type: str, video_desc: str = None):
        """
        Menghasilkan copywriting pengumuman AI yang kontekstual dan mengalir alami
        tanpa batasan kata kaku.
        """
        tipe_map = {
            "live": "Live Streaming Sedang Berlangsung",
            "premier": "Penayangan Perdana (Premiere)",
            "upload": "Video Baru"
        }
        tipe_str = tipe_map.get(video_type, "Konten Terbaru")

        info_lines = []
        if channel_name:
            info_lines.append(f"- Kreator/Channel: {channel_name}")
        if video_title:
            info_lines.append(f"- Judul Video: {video_title}")
        if video_desc:
            clean_desc = video_desc.strip()[:250].replace("\n", " ")
            info_lines.append(f"- Ringkasan: {clean_desc}")

        context_str = "\n".join(info_lines) if info_lines else "Detail belum tersedia."

        prompt = f"""Kamu adalah bot Discord server RTMxBadut.
Tugas kamu membuat 1 kalimat notifikasi/sapaan yang santai, seru, dan asik buat warga server tentang {tipe_str} yang baru saja rilis.

Informasi konten:
{context_str}

Panduan gaya:
1. Hubungkan kalimat kamu secara alami dengan topik atau judul videonya di atas.
2. Gunakan bahasa obrolan Discord/tongkrongan Indonesia yang santai, asik, dan luwes.
3. Sesuaikan dengan situasinya:
   - Kalau video santai/keseharian/vlog, sapa warga server dengan santai dan ajak nonton.
   - Kalau live streaming, ajak warga server langsung merapat ke live chat.
   - Kalau premiere, ingatkan buat standby sebelum mulai.
4. Singkat, padat (cukup 1-2 kalimat). Jangan pakai hashtag (#) dan jangan sertakan URL link di dalam teks karena link sudah disediakan di tombol.

Berikan 1 respon pengumuman kamu sekarang:"""

        # Fallback teks cerdas
        if video_type == "live":
            fallback = f"🔴 {channel_name} lagi LIVE nih dengan judul '{video_title}'. Yuk merapat ke live chat sekarang!"
        elif video_type == "premier":
            fallback = f"⏳ {channel_name} sudah jadwalkan premiere video baru: '{video_title}'. Pasang reminder biar gak ketinggalan!"
        else:
            fallback = f"🎬 Video baru dari {channel_name} sudah tayang: '{video_title}'. Langsung tonton sekarang ya!"

        models_to_try = ['gemini-2.5-flash', 'gemini-3-flash-preview', 'gemini-2.5-flash-lite']
        for model_name in models_to_try:
            attempts = max(1, len(API_KEYS))
            for _ in range(attempts):
                try:
                    model = genai.GenerativeModel(model_name)
                    response = await asyncio.wait_for(model.generate_content_async(prompt), timeout=30.0)
                    if response.text:
                        return response.text.strip().replace('"', '')
                except asyncio.TimeoutError:
                    return fallback
                except google_exceptions.ResourceExhausted:
                    if rotate_api_key():
                        await asyncio.sleep(1)
                        continue
                    else:
                        break
                except Exception:
                    break

        return fallback

    # ==========================================
    # BUILDER NOTIFIKASI DISCORD (V2 CARD / EMBED)
    # ==========================================
    async def send_notification_card(self, target_channel: discord.TextChannel, video_data: dict, ai_hype: str):
        """
        Mengirimkan notifikasi berformat Discord V2 Card dengan tombol aksi langsung.
        """
        video_id = video_data.get("video_id")
        video_url = video_data.get("url") or f"https://www.youtube.com/watch?v={video_id}"
        title = video_data.get("title") or "Video YouTube"
        channel_name = video_data.get("channel_name") or "YouTube Channel"
        status = video_data.get("status", "upload")
        desc = video_data.get("description", "") or ""

        # Pengaturan label & icon sesuai status
        if status == "live":
            status_badge = "🔴 LIVE STREAMING"
            btn_label = "Tonton Live"
            accent_color = 0xed4245 # Merah
        elif status == "premier":
            status_badge = "⏳ PREMIERE YOUTUBE"
            btn_label = "Tonton Premiere"
            accent_color = 0x57f287 # Hijau
        else:
            status_badge = "🎬 VIDEO BARU"
            btn_label = "Tonton Video"
            accent_color = 0x5865f2 # Biru blurple

        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

        # Pesan mention + AI hype di atas kartu
        mention_content = f"@everyone {ai_hype}"

        # 1. Tombol Aksi Langsung
        buttons = [{
            "style": 5, # URL Button
            "label": btn_label,
            "url": video_url
        }]

        # 2. Format Judul & Deskripsi 100% Identik dengan cogs/notif (Foto 3)
        # Judul berupa Markdown Link H1 biru yang bisa diklik
        safe_title = title.replace("[", "(").replace("]", ")")
        card_title = f"[{safe_title}]({video_url})"
        
        # Subtitle menampilkan URL tepat di bawah judul
        if desc and desc.strip():
            card_desc = f"{desc[:250].strip()}\n\n{video_url}"
        else:
            card_desc = f"{video_url}"

        try:
            card = build_v2_card(
                title=card_title,
                description=card_desc,
                fields=None,
                color=None, # NONE: Menghilangkan garis border samping tebal agar bersih dan elegan identik Foto 3
                buttons=buttons,
                media_url=thumbnail_url
            )
            # Kirim teks mention terlebih dahulu agar notifikasi ping berfungsi
            if mention_content and mention_content.strip():
                await target_channel.send(content=mention_content)
            # Kirim kartu V2
            await send_v2_message(self.bot, target_channel.id, [card])
            return True
        except Exception as err:
            print(f"[YT TEST V2 FALLBACK] Gagal kirim V2 card, menggunakan Embed standar: {err}")
            # Fallback ke Standard Rich Embed
            embed = discord.Embed(
                title=title,
                url=video_url,
                description=desc[:400] if desc else video_url,
                color=discord.Color.blue()
            )
            embed.set_author(name=channel_name)
            embed.set_image(url=thumbnail_url)
            embed.set_footer(text="RTMxBadut • YouTube Native Checker")

            view = discord.ui.View()
            view.add_item(discord.ui.Button(label=btn_label, style=discord.ButtonStyle.link, url=video_url))

            await target_channel.send(content=mention_content, embed=embed, view=view)
            return True

    # ==========================================
    # BACKGROUND POLLING LOOP (AUTO CHECKER)
    # ==========================================
    @tasks.loop(seconds=60)
    async def yt_check_loop(self):
        """
        Loop otomatis mengecek channel YouTube yang terdaftar setiap 60 detik (1 menit).
        Dilengkapi Timestamp Freshness Guard agar video lama tidak pernah terkirim sebagai notifikasi baru.
        """
        channels = self.config.get("channels", [])
        if not channels:
            return

        for ch in channels:
            if not ch.get("enabled", True):
                continue

            channel_id = ch.get("channel_id")
            target_disc_id = ch.get("target_discord_channel_id")
            if not channel_id or not target_disc_id:
                continue

            try:
                target_id_int = int(target_disc_id)
            except (ValueError, TypeError):
                continue

            target_disc_channel = self.bot.get_channel(target_id_int)
            if not target_disc_channel:
                try:
                    target_disc_channel = await self.bot.fetch_channel(target_id_int)
                except Exception as e_fetch:
                    print(f"[YT CHECK] Gagal fetch channel Discord {target_id_int}: {e_fetch}")
                    continue

            latest_items = await self.fetch_latest_videos(channel_id)
            if not latest_items:
                continue

            posted_ids = self.cache.get("posted_video_ids", [])

            # Cek entri video teratas dari RSS
            for item in latest_items[:5]:
                vid = item["video_id"]
                if vid in posted_ids:
                    continue

                # 🛡️ TIMESTAMP FRESHNESS GUARD (published & updated):
                # Memeriksa string <published> dan <updated> dari XML:
                # Jika video dan pembaruannya sudah lampau (> 4 jam), simpan ke cache diam-diam dan lewati!
                if not self.is_video_fresh(item.get("published"), item.get("updated"), max_age_hours=4):
                    posted_ids.append(vid)
                    self.cache["posted_video_ids"] = posted_ids
                    self._save_cache()
                    continue

                # Konten baru ditemukan! Analisis status siaran
                classification = await self.classify_stream_status(vid)
                item["status"] = classification["status"]
                if classification.get("title"):
                    item["title"] = classification["title"]
                if classification.get("channel_name"):
                    item["channel_name"] = classification["channel_name"]
                if classification.get("description"):
                    item["description"] = classification["description"]

                clean_title = item["title"]
                if clean_title:
                    date_patterns = [
                        r'\d{4}-\d{2}-\d{2}',
                        r'\d{2}:\d{2}',
                        r'\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}'
                    ]
                    for pattern in date_patterns:
                        clean_title = re.sub(pattern, '', clean_title).strip()

                # Generate AI Hype
                ai_text = await self.generate_ai_hype(
                    channel_name=item["channel_name"],
                    video_title=clean_title,
                    video_type=item["status"],
                    video_desc=item.get("description")
                )

                # Kirim ke Discord
                await self.send_notification_card(target_disc_channel, item, ai_text)

                # Tandai sudah dipost di cache
                posted_ids.append(vid)
                if len(posted_ids) > 500:
                    posted_ids.pop(0)

                self.cache["posted_video_ids"] = posted_ids
                self._save_cache()

                # Beri jeda 3 detik antar video jika ada lebih dari 1 baru
                await asyncio.sleep(3)

    @yt_check_loop.before_loop
    async def before_yt_check_loop(self):
        await self.bot.wait_until_ready()

    # ==========================================
    # COMMAND SUITE (RINGKAS & ELEGAN)
    # ==========================================
    @commands.group(name="yt", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def yt_group(self, ctx):
        """Menu utama bantuan perintah YouTube Native Checker."""
        embed = discord.Embed(
            title="📺 YouTube Native Checker (Test Suite)",
            description="Perintah mandiri untuk pengujian notifikasi YouTube langsung dari server:",
            color=0xed4245
        )
        embed.add_field(name="⚡ Uji Coba Instan", value="`!yttest <url>` atau `!yt test <url>`\nLangsung test link YouTube apa saja (video biasa / live / premiere) ke channel ini.", inline=False)
        embed.add_field(name="➕ Tambah Channel", value="`!ytadd <url/handle>` atau `!yt add <url>`\nPantau channel YouTube baru langsung ke channel Discord ini.", inline=False)
        embed.add_field(name="📋 Lihat Daftar", value="`!ytlist` atau `!yt list`\nLihat semua channel yang sedang dipantau.", inline=False)
        embed.add_field(name="🔄 Cek Sekarang", value="`!ytcheck` atau `!yt check`\nPaksa bot mengecek feed sekarang juga.", inline=False)
        embed.add_field(name="⏱️ Atur Interval", value="`!ytinterval <detik>` atau `!yt interval <detik>`\nAtur interval loop pengecekan (default: 60 detik / 1 menit).", inline=False)
        embed.add_field(name="🗑️ Hapus Channel", value="`!ytdel <channel_id>` atau `!yt del <id>`\nHapus channel dari pemantauan.", inline=False)
        embed.add_field(name="🧹 Bersihkan Cache", value="`!ytclear` atau `!yt clear`\nKosongkan cache test agar bisa kirim ulang.", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="yttest")
    @commands.has_permissions(administrator=True)
    async def yttest_cmd(self, ctx, url: str = None):
        """
        Uji coba instan: Masukkan URL YouTube apa saja (video biasa, live stream, atau premiere).
        Bot akan langsung mendeteksi statusnya, membuat copywriting AI kontekstual,
        dan menampilkan hasilnya langsung di channel ini!
        """
        if not url:
            return await ctx.send("❌ Masukkan URL YouTube yang ingin di-test! Contoh: `!yttest https://www.youtube.com/watch?v=...`")

        vid = self._extract_video_id(url)
        if not vid:
            return await ctx.send("❌ Format URL YouTube tidak valid! Gunakan link video, live, atau shorts YouTube.")

        status_msg = await ctx.send("🔍 *Mendeteksi status siaran YouTube dan mengambil metadata langsung...*")
        
        async with ctx.typing():
            # 1. Klasifikasi status (Live / Premiere / Upload)
            classification = await self.classify_stream_status(vid)
            
            title = classification.get("title") or "Video YouTube"
            channel_name = classification.get("channel_name") or "YouTube Channel"
            video_type = classification.get("status", "upload")
            desc = classification.get("description", "")

            # 2. Buat Copywriting AI Kontekstual
            clean_title = title
            if clean_title:
                date_patterns = [
                    r'\d{4}-\d{2}-\d{2}',
                    r'\d{2}:\d{2}',
                    r'\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}'
                ]
                for pattern in date_patterns:
                    clean_title = re.sub(pattern, '', clean_title).strip()

            ai_text = await self.generate_ai_hype(
                channel_name=channel_name,
                video_title=clean_title,
                video_type=video_type,
                video_desc=desc
            )

            video_data = {
                "video_id": vid,
                "url": url if url.startswith("http") else f"https://www.youtube.com/watch?v={vid}",
                "title": title,
                "channel_name": channel_name,
                "status": video_type,
                "description": desc,
                "thumbnail_url": classification.get("thumbnail_url")
            }

            try:
                await status_msg.delete()
            except:
                pass

            # 3. Kirim tampilan kartu notifikasi
            await self.send_notification_card(ctx.channel, video_data, ai_text)

    @yt_group.command(name="test")
    @commands.has_permissions(administrator=True)
    async def yt_test_sub(self, ctx, url: str):
        await self.yttest_cmd(ctx, url)

    @commands.command(name="ytadd")
    @commands.has_permissions(administrator=True)
    async def ytadd_cmd(self, ctx, *, identifier: str = None):
        """
        Daftarkan channel YouTube untuk dipantau secara otomatis.
        Target Discord otomatis ditetapkan ke channel tempat kamu mengetikkan perintah ini!
        """
        if not identifier:
            return await ctx.send("❌ Masukkan link channel YouTube, handle (@username), atau ID channel! Contoh: `!ytadd https://www.youtube.com/@RizwanFadilah`")

        status_msg = await ctx.send("⏳ *Menghubungi server YouTube untuk mengenali channel...*")
        
        channel_id, channel_name = await self.resolve_channel_id(identifier)
        if not channel_id:
            await status_msg.edit(content="❌ Gagal mengenali channel YouTube. Pastikan link, handle (@nama), atau ID channel benar!")
            return

        # Cek apakah sudah terdaftar
        channels = self.config.get("channels", [])
        for ch in channels:
            if ch.get("channel_id") == channel_id and ch.get("target_discord_channel_id") == ctx.channel.id:
                await status_msg.edit(content=f"⚠️ Channel **{channel_name}** (`{channel_id}`) sudah terdaftar untuk notifikasi di #{ctx.channel.name}!")
                return

        new_entry = {
            "channel_id": channel_id,
            "channel_name": channel_name,
            "target_discord_channel_id": ctx.channel.id,
            "mention_role": "@everyone",
            "enabled": True,
            "added_at": datetime.now(timezone.utc).isoformat()
        }
        channels.append(new_entry)
        self.config["channels"] = channels
        self._save_config()

        # 🛡️ Seed Baseline Cache: Tandai video yang sudah ada saat ini agar tidak dispam sebagai video baru
        current_videos = await self.fetch_latest_videos(channel_id)
        posted_ids = self.cache.get("posted_video_ids", [])
        seeded_count = 0
        for cv in current_videos:
            if cv["video_id"] not in posted_ids:
                posted_ids.append(cv["video_id"])
                seeded_count += 1
        self.cache["posted_video_ids"] = posted_ids
        self._save_cache()

        embed = discord.Embed(
            title="✅ Channel YouTube Berhasil Ditambahkan",
            description=f"Bot sekarang memantau channel ini secara mandiri langsung dari YouTube!\n*(Tersimpan permanen di MongoDB | {seeded_count} video lama sudah dicatat agar tidak dispam)*",
            color=0x57f287
        )
        embed.add_field(name="Nama Channel", value=f"**{channel_name}**", inline=True)
        embed.add_field(name="Channel ID", value=f"`{channel_id}`", inline=True)
        embed.add_field(name="Target Notifikasi", value=ctx.channel.mention, inline=True)
        embed.add_field(name="Interval Pengecekan", value=f"Setiap {self._get_interval_text()}", inline=False)
        embed.set_footer(text="Gunakan !ytcheck untuk memicu pengecekan sekarang juga.")

        await status_msg.edit(content=None, embed=embed)

    @yt_group.command(name="add")
    @commands.has_permissions(administrator=True)
    async def yt_add_sub(self, ctx, *, identifier: str):
        await self.ytadd_cmd(ctx, identifier=identifier)

    @commands.command(name="ytdel", aliases=["ytremove"])
    @commands.has_permissions(administrator=True)
    async def ytdel_cmd(self, ctx, channel_id: str = None):
        """Hapus channel YouTube dari daftar pemantauan."""
        if not channel_id:
            return await ctx.send("❌ Masukkan Channel ID yang ingin dihapus. Gunakan `!ytlist` untuk melihat daftar ID.")

        channels = self.config.get("channels", [])
        initial_len = len(channels)
        self.config["channels"] = [ch for ch in channels if ch.get("channel_id") != channel_id.strip()]

        if len(self.config["channels"]) < initial_len:
            self._save_config()
            await ctx.send(f"✅ Channel dengan ID `{channel_id}` berhasil dihapus dari pemantauan.")
        else:
            await ctx.send(f"❌ Channel dengan ID `{channel_id}` tidak ditemukan dalam daftar pemantauan.")

    @yt_group.command(name="del")
    @commands.has_permissions(administrator=True)
    async def yt_del_sub(self, ctx, channel_id: str):
        await self.ytdel_cmd(ctx, channel_id)

    @commands.command(name="ytlist")
    @commands.has_permissions(administrator=True)
    async def ytlist_cmd(self, ctx):
        """Tampilkan seluruh channel YouTube yang sedang dipantau."""
        channels = self.config.get("channels", [])
        if not channels:
            embed = discord.Embed(
                title="📺 Daftar Pemantauan YouTube (Test)",
                description="Belum ada channel yang dipantau.\nGunakan `!ytadd <url/handle>` untuk mendaftarkan channel YouTube kamu!",
                color=0x3498db
            )
            return await ctx.send(embed=embed)

        embed = discord.Embed(
            title="📺 Channel YouTube yang Sedang Dipantau (Test)",
            description=f"Total ada **{len(channels)}** channel dalam pemantauan native:",
            color=0xed4245
        )

        for i, ch in enumerate(channels, 1):
            c_name = ch.get("channel_name", "Unknown")
            c_id = ch.get("channel_id", "-")
            target_id = ch.get("target_discord_channel_id")
            try:
                t_int = int(target_id)
                target_ch = self.bot.get_channel(t_int)
                target_str = target_ch.mention if target_ch else f"<#{t_int}>"
            except:
                target_str = f"ID: {target_id}"

            embed.add_field(
                name=f"{i}. {c_name}",
                value=f"• **Channel ID:** `{c_id}`\n• **Target:** {target_str}",
                inline=False
            )

        cached_count = len(self.cache.get("posted_video_ids", []))
        embed.set_footer(text=f"Total video dalam cache: {cached_count} | Interval loop: {self._get_interval_text()}")
        await ctx.send(embed=embed)

    @yt_group.command(name="list")
    @commands.has_permissions(administrator=True)
    async def yt_list_sub(self, ctx):
        await self.ytlist_cmd(ctx)

    @commands.command(name="ytinterval")
    @commands.has_permissions(administrator=True)
    async def ytinterval_cmd(self, ctx, seconds: int = None):
        """Atur seberapa cepat bot mengecek YouTube (dalam detik). Contoh: !ytinterval 60"""
        if not seconds or seconds < 10:
            return await ctx.send(f"❌ Masukkan durasi interval minimal 10 detik! Contoh: `!ytinterval 60` (saat ini: **{self._get_interval_text()}**)")
            
        self.config["check_interval_seconds"] = seconds
        self._save_config()
        try:
            self.yt_check_loop.change_interval(seconds=seconds)
        except Exception as e:
            print(f"[YT INTERVAL CHANGE ERROR] {e}")
        
        await ctx.send(f"✅ Interval pemeriksaan YouTube berhasil diubah menjadi **{self._get_interval_text()}**!")

    @yt_group.command(name="interval")
    @commands.has_permissions(administrator=True)
    async def yt_interval_sub(self, ctx, seconds: int):
        await self.ytinterval_cmd(ctx, seconds)

    @commands.command(name="ytcheck")
    @commands.has_permissions(administrator=True)
    async def ytcheck_cmd(self, ctx):
        """Paksa bot mengecek feed & tab video YouTube detik ini juga dengan laporan detail transparan."""
        channels = self.config.get("channels", [])
        if not channels:
            return await ctx.send("⚠️ Belum ada channel yang didaftarkan. Gunakan `!ytadd <url>` terlebih dahulu.")

        msg = await ctx.send("🔄 *Sedang memeriksa update YouTube untuk semua channel (Dual-Engine: RSS + Web Tab)...*")
        
        report_lines = []
        new_count = 0
        posted_ids = self.cache.get("posted_video_ids", [])

        for ch in channels:
            if not ch.get("enabled", True):
                continue

            channel_id = ch.get("channel_id")
            c_name = ch.get("channel_name", "Unknown")
            target_disc_id = ch.get("target_discord_channel_id")
            if not channel_id or not target_disc_id:
                continue

            try:
                target_id_int = int(target_disc_id)
            except (ValueError, TypeError):
                continue

            target_disc_channel = self.bot.get_channel(target_id_int)
            if not target_disc_channel:
                try:
                    target_disc_channel = await self.bot.fetch_channel(target_id_int)
                except Exception:
                    pass

            latest_items = await self.fetch_latest_videos(channel_id)
            if not latest_items:
                report_lines.append(f"• **{c_name}**: Gagal terhubung ke feed/tab YouTube.")
                continue

            top_item = latest_items[0]
            top_vid = top_item["video_id"]

            # Cek status video teratas
            if top_vid in posted_ids:
                v_title = top_item.get("title") or "Video Teratas"
                report_lines.append(f"• **{c_name}**: Video `{top_vid}` ({v_title}) sudah ada di cache *(tidak dikirim ulang)*.")
            else:
                # Video baru ditemukan!
                if target_disc_channel:
                    classification = await self.classify_stream_status(top_vid)
                    top_item["status"] = classification["status"]
                    top_item["title"] = classification.get("title") or top_item.get("title") or "Video YouTube"
                    top_item["channel_name"] = classification.get("channel_name") or c_name
                    top_item["description"] = classification.get("description") or ""

                    clean_title = top_item["title"]
                    if clean_title:
                        for pattern in [r'\d{4}-\d{2}-\d{2}', r'\d{2}:\d{2}', r'\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}']:
                            clean_title = re.sub(pattern, '', clean_title).strip()

                    ai_text = await self.generate_ai_hype(
                        channel_name=top_item["channel_name"],
                        video_title=clean_title,
                        video_type=top_item["status"],
                        video_desc=top_item.get("description")
                    )

                    await self.send_notification_card(target_disc_channel, top_item, ai_text)

                    posted_ids.append(top_vid)
                    if len(posted_ids) > 500: posted_ids.pop(0)
                    self.cache["posted_video_ids"] = posted_ids
                    self._save_cache()

                    report_lines.append(f"• **{c_name}**: 🎉 Video baru **'{top_item['title']}'** (`{top_vid}`) berhasil dikirim ke {target_disc_channel.mention}!")
                    new_count += 1
                else:
                    report_lines.append(f"• **{c_name}**: Video baru terdeteksi tapi target channel Discord tidak ditemukan.")

        embed = discord.Embed(
            title="🔍 Laporan Pemeriksaan YouTube",
            description="\n".join(report_lines) if report_lines else "Tidak ada channel yang aktif diperiksa.",
            color=0x57f287 if new_count > 0 else 0x3498db
        )
        embed.set_footer(text="Tip: Gunakan !ytclear jika kamu ingin mengirimkan ulang video yang sudah tercatat di cache.")
        await msg.edit(content=None, embed=embed)

    @yt_group.command(name="check")
    @commands.has_permissions(administrator=True)
    async def yt_check_sub(self, ctx):
        await self.ytcheck_cmd(ctx)

    @commands.command(name="ytclear")
    @commands.has_permissions(administrator=True)
    async def ytclear_cmd(self, ctx):
        """Bersihkan cache ID video agar kamu bisa menguji kirim ulang video lama."""
        total = len(self.cache.get("posted_video_ids", []))
        self.cache["posted_video_ids"] = []
        self._save_cache()
        await ctx.send(f"🧹 Cache test berhasil dikosongkan ({total} ID video dibersihkan). Sekarang video sebelumnya bisa ditest kirim ulang!")

    @yt_group.command(name="clear")
    @commands.has_permissions(administrator=True)
    async def yt_clear_sub(self, ctx):
        await self.ytclear_cmd(ctx)


async def setup(bot):
    os.makedirs("data", exist_ok=True)
    await bot.add_cog(YouTubeNativeCheckerTest(bot))
