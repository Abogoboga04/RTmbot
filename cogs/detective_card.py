import io
import os
import math
import time
import re
import unicodedata
import asyncio
from datetime import datetime
from io import BytesIO

import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont

from cogs.leveling import load_json, LEVEL_FILE, BANK_FILE, CONFIG_FILE

_cached_font_bytes = {}

async def _fetch_font_bytes(url: str) -> bytes:
    if url in _cached_font_bytes:
        return _cached_font_bytes[url]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    _cached_font_bytes[url] = data
                    return data
    except Exception:
        pass
    return None

def is_safe_printable_char(ch: str) -> bool:
    code = ord(ch)
    # ASCII printable (32 to 126)
    if 32 <= code <= 126:
        return True
    # Latin-1 Supplement & Extended (160 to 591)
    if 160 <= code <= 591:
        return True
    # Tanda baca umum yang aman
    if code in (0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2013, 0x2014):
        return True
    return False

def clean_display_text(text: str) -> str:
    """
    Membersihkan teks secara ketat dari karakter invisible, variation selectors,
    tag glyphs, dan unicode liar yang gagal dirender dan memicu kotak kosong (□).
    """
    if not text:
        return "MEMBER"
    text = unicodedata.normalize('NFKC', str(text))
    cleaned = ''.join(ch for ch in text if is_safe_printable_char(ch)).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned if cleaned else "MEMBER"

class DetectiveCard(commands.Cog, name="Detective Rank Card"):
    def __init__(self, bot):
        self.bot = bot

    async def _get_fonts(self):
        win_fonts = r"C:\Windows\Fonts"
        f_serif_bold_path = os.path.join(win_fonts, "georgiab.ttf")
        if not os.path.exists(f_serif_bold_path):
            f_serif_bold_path = os.path.join(win_fonts, "timesbd.ttf")

        f_serif_reg_path = os.path.join(win_fonts, "georgia.ttf")
        if not os.path.exists(f_serif_reg_path):
            f_serif_reg_path = os.path.join(win_fonts, "times.ttf")

        f_sans_bold_path = os.path.join(win_fonts, "arialbd.ttf")
        f_sans_reg_path = os.path.join(win_fonts, "arial.ttf")

        remote_serif_bold_bytes = None
        remote_serif_reg_bytes = None
        remote_sans_bold_bytes = None
        remote_sans_reg_bytes = None

        if not os.path.exists(f_serif_bold_path):
            remote_serif_bold_bytes = await _fetch_font_bytes("https://github.com/google/fonts/raw/main/ofl/playfairdisplay/PlayfairDisplay%5Bwght%5D.ttf")
        if not os.path.exists(f_serif_reg_path):
            remote_serif_reg_bytes = await _fetch_font_bytes("https://github.com/google/fonts/raw/main/ofl/merriweather/Merriweather-Regular.ttf")
        if not os.path.exists(f_sans_bold_path):
            remote_sans_bold_bytes = await _fetch_font_bytes("https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf")
        if not os.path.exists(f_sans_reg_path):
            remote_sans_reg_bytes = await _fetch_font_bytes("https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf")

        def load_font(path, remote_bytes, size):
            try:
                if os.path.exists(path):
                    return ImageFont.truetype(path, size)
                elif remote_bytes:
                    return ImageFont.truetype(BytesIO(remote_bytes), size)
            except Exception:
                pass
            return ImageFont.load_default()

        return {
            "title": load_font(f_serif_bold_path, remote_serif_bold_bytes, 28),
            "subtitle": load_font(f_serif_bold_path, remote_serif_bold_bytes, 15),
            "name_header": load_font(f_serif_bold_path, remote_serif_bold_bytes, 28),
            "badge": load_font(f_sans_bold_path, remote_sans_bold_bytes, 17),
            "label": load_font(f_serif_bold_path, remote_serif_bold_bytes, 16),
            "value": load_font(f_serif_bold_path, remote_serif_bold_bytes, 17),
            "photo_label": load_font(f_sans_bold_path, remote_sans_bold_bytes, 14),
            "quote": load_font(f_serif_reg_path, remote_serif_reg_bytes, 16),
            "sign_name": load_font(f_serif_bold_path, remote_serif_bold_bytes, 24), # Ukuran diperbesar
            "sign_role": load_font(f_serif_reg_path, remote_serif_reg_bytes, 15), # Ukuran diperbesar
            "stamp_title": load_font(f_sans_bold_path, remote_sans_bold_bytes, 13),
            "stamp_date": load_font(f_sans_bold_path, remote_sans_bold_bytes, 16),
            "stamp_sub": load_font(f_sans_bold_path, remote_sans_bold_bytes, 12),
            "auth_id": load_font(f_sans_reg_path, remote_sans_reg_bytes, 12),
        }

    def _draw_star(self, draw, cx, cy, r_outer=14, r_inner=7, fill=(245, 195, 60, 255), outline=(180, 135, 30, 255)):
        points = []
        for i in range(10):
            r = r_outer if i % 2 == 0 else r_inner
            angle = i * math.pi / 5 - math.pi / 2
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            points.append((x, y))
        draw.polygon(points, fill=fill, outline=outline)

    def _draw_sakura(self, draw, cx, cy, r_petal=8, fill=(255, 170, 195, 255), outline=(215, 95, 130, 255)):
        for i in range(5):
            angle = i * 2 * math.pi / 5 - math.pi / 2
            px = cx + 8 * math.cos(angle)
            py = cy + 8 * math.sin(angle)
            draw.ellipse([(px - r_petal, py - r_petal), (px + r_petal, py + r_petal)], fill=fill, outline=outline)
        draw.ellipse([(cx - 5, cy - 5), (cx + 5, cy + 5)], fill=(255, 235, 120, 255))

    def _draw_luxury_wax_seal(self, draw, cx, cy, radius=76, stamp_title="• RESMI •", stamp_date="19 JUL", stamp_year="THN 2024", fonts=None):
        teeth = 36
        outer_r = radius
        inner_r = radius - 5
        scallop_pts = []
        for i in range(teeth * 2):
            angle = i * math.pi / teeth
            r = outer_r if i % 2 == 0 else inner_r
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            scallop_pts.append((x, y))

        # Gerigi terluar scallop merah tua
        draw.polygon(scallop_pts, fill=(140, 25, 25, 255), outline=(90, 15, 15, 255))

        # Piringan utama crimson dengan border emas
        draw.ellipse([(cx - radius + 4, cy - radius + 4), (cx + radius - 4, cy + radius - 4)],
                     fill=(185, 38, 38, 255), outline=(218, 165, 32, 255), width=2)

        # Cincin dalam emas
        draw.ellipse([(cx - radius + 10, cy - radius + 10), (cx + radius - 10, cy + radius - 10)],
                     outline=(218, 165, 32, 200), width=1)

        # Butiran manik-manik emas (beaded circle)
        num_dots = 30
        dot_r = radius - 17
        for i in range(num_dots):
            ang = i * 2 * math.pi / num_dots
            dx = cx + dot_r * math.cos(ang)
            dy = cy + dot_r * math.sin(ang)
            draw.ellipse([(dx - 1.5, dy - 1.5), (dx + 1.5, dy + 1.5)], fill=(245, 215, 120, 230))

        # Piringan inti terdalam
        core_r = radius - 23
        draw.ellipse([(cx - core_r, cy - core_r), (cx + core_r, cy + core_r)],
                     fill=(160, 30, 30, 255), outline=(130, 20, 20, 255), width=1)

        # Sakura vektor di atas
        self._draw_sakura(draw, cx, cy - 28, r_petal=5)

        # Teks status stempel
        b1 = fonts["stamp_title"].getbbox(stamp_title)
        draw.text((cx - (b1[2]-b1[0])//2, cy - 18), stamp_title, font=fonts["stamp_title"], fill=(255, 235, 160, 255))

        # Tanggal awal join (hari & bulan)
        b2 = fonts["stamp_date"].getbbox(stamp_date)
        draw.text((cx - (b2[2]-b2[0])//2, cy + 2), stamp_date, font=fonts["stamp_date"], fill=(255, 255, 255, 255))

        # Tahun bergabung
        b3 = fonts["stamp_sub"].getbbox(stamp_year)
        draw.text((cx - (b3[2]-b3[0])//2, cy + 24), stamp_year, font=fonts["stamp_sub"], fill=(255, 220, 180, 255))

    async def render_detective_card(
        self,
        target: discord.Member,
        guild: discord.Guild,
        level: int,
        exp: int,
        balance: int,
        rank_pos: int
    ) -> BytesIO:
        fonts = await self._get_fonts()
        avatar_bytes = None
        try:
            avatar_bytes = await target.display_avatar.replace(size=256, format="png").read()
        except Exception:
            pass

        # Sanitasi teks agar bersih tanpa box glyphs (□)
        safe_user_name = clean_display_text(target.display_name)
        safe_guild_name = clean_display_text(guild.name)

        # Ambil role tertinggi pengguna (kecuali @everyone)
        user_roles = [r for r in target.roles if r.name != "@everyone"]
        highest_role_name = clean_display_text(user_roles[-1].name.upper() if user_roles else "MEMBER RESMI")

        # Ambil nama Owner Server Discord
        server_owner = guild.owner
        server_owner_name = clean_display_text(server_owner.display_name if server_owner else "Owner Server")
        server_owner_role = f"Owner & Pendiri {safe_guild_name[:18]}"

        # Ambil nama Bot secara dinamis (otomatis sinkron jika nama bot berubah)
        bot_display_name = clean_display_text(self.bot.user.name if self.bot.user else "RTMBOT")
        bot_owner_display = f"Owner {bot_display_name}"
        bot_owner_role = "Pengembang Sistem & Bot Server"

        # Format Tanggal Bergabung User ke Server
        months_id = ["JAN", "FEB", "MAR", "APR", "MEI", "JUN", "JUL", "AGU", "SEP", "OKT", "NOV", "DES"]
        months_full_id = [
            "JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI",
            "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"
        ]
        if target.joined_at:
            j_dt = target.joined_at
            j_day = f"{j_dt.day:02d}"
            j_month_abbr = months_id[j_dt.month - 1]
            j_month_full = months_full_id[j_dt.month - 1]
            j_year = f"{j_dt.year}"
            tanggal_resmi_str = f"{j_day} {j_month_full} {j_year}"
            stamp_date_str = f"{j_day} {j_month_abbr}"
            stamp_year_str = f"THN {j_year}"
            sub_header_str = f"SERTIFIKAT RESMI KEANGGOTAAN • SEJAK {j_year}"
        else:
            now_dt = datetime.utcnow()
            j_day = f"{now_dt.day:02d}"
            j_month_abbr = months_id[now_dt.month - 1]
            j_month_full = months_full_id[now_dt.month - 1]
            j_year = f"{now_dt.year}"
            tanggal_resmi_str = f"{j_day} {j_month_full} {j_year}"
            stamp_date_str = f"{j_day} {j_month_abbr}"
            stamp_year_str = f"THN {j_year}"
            sub_header_str = f"SERTIFIKAT RESMI KEANGGOTAAN • {j_year}"

        # Nomor Lisensi resmi berbasis ID Discord pengguna
        license_num = f"RTM-{target.id}"

        def _render():
            W, H = 1100, 680
            bg_color = (252, 249, 241, 255) # Warm parchment
            card = Image.new("RGBA", (W, H), bg_color)
            draw = ImageDraw.Draw(card)

            gold_dark = (175, 142, 75, 255)
            gold_light = (212, 188, 130, 255)
            text_dark = (44, 34, 30, 255)
            text_gold = (140, 115, 85, 255)

            # 1. Double Gold Border
            draw.rectangle([(25, 25), (W - 25, H - 25)], outline=gold_dark, width=3)
            draw.rectangle([(35, 35), (W - 35, H - 35)], outline=gold_light, width=1)

            # Corner dots
            for cx, cy in [(25, 25), (W - 25, 25), (25, H - 25), (W - 25, H - 25)]:
                draw.ellipse([(cx - 4, cy - 4), (cx + 4, cy + 4)], fill=gold_dark)

            for cx, cy in [(42, 42), (W - 42, 42), (42, H - 42), (W - 42, H - 42)]:
                draw.ellipse([(cx - 2, cy - 2), (cx + 2, cy + 2)], fill=gold_dark)

            # 2. Top Header Left (Kartu Resmi Anggota)
            title_text = f"KARTU RESMI ANGGOTA • {safe_guild_name.upper()}"
            draw.text((65, 55), title_text, font=fonts["title"], fill=text_dark)
            draw.text((65, 96), sub_header_str, font=fonts["subtitle"], fill=text_gold)

            # 3. Top Header Right Badge
            badge_tier = f"RANK: #{rank_pos} • CLASS-A" if rank_pos > 3 else "RANK: S-CLASS MASTER"
            badge_w, badge_h = 240, 42
            badge_x, badge_y = W - 65 - badge_w, 60
            draw.rounded_rectangle([(badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h)], radius=8, fill=(192, 57, 43, 255))

            bbox = fonts["badge"].getbbox(badge_tier)
            bw = bbox[2] - bbox[0]
            bh = bbox[3] - bbox[1]
            draw.text((badge_x + (badge_w - bw) // 2, badge_y + (badge_h - bh) // 2 - 2), badge_tier, font=fonts["badge"], fill=(255, 255, 255, 255))

            # Divider bar below header
            draw.line([(65, 125), (W - 65, 125)], fill=gold_dark, width=2)

            # 4. Left Photo ID Box
            box_x, box_y, box_w, box_h = 65, 145, 185, 255
            draw.rounded_rectangle([(box_x, box_y), (box_x + box_w, box_y + box_h)], radius=12, fill=(244, 238, 223, 255), outline=gold_light, width=2)

            avatar_size = 140
            av_x = box_x + (box_w - avatar_size) // 2
            av_y = box_y + 18

            if avatar_bytes:
                try:
                    av_img = Image.open(BytesIO(avatar_bytes)).convert("RGBA").resize((avatar_size, avatar_size))
                except Exception:
                    av_img = Image.new("RGBA", (avatar_size, avatar_size), (120, 140, 170, 255))
            else:
                av_img = Image.new("RGBA", (avatar_size, avatar_size), (120, 140, 170, 255))

            mask = Image.new("L", (avatar_size, avatar_size), 0)
            ImageDraw.Draw(mask).ellipse([(0, 0), (avatar_size, avatar_size)], fill=255)
            card.paste(av_img, (av_x, av_y), mask)
            draw.ellipse([(av_x, av_y), (av_x + avatar_size, av_y + avatar_size)], outline=gold_dark, width=3)

            # Name pill below avatar
            pill_w, pill_h = 145, 34
            pill_x = box_x + (box_w - pill_w) // 2
            pill_y = box_y + avatar_size + 36
            draw.rounded_rectangle([(pill_x, pill_y), (pill_x + pill_w, pill_y + pill_h)], radius=6, fill=(237, 227, 205, 255), outline=gold_dark, width=1)

            p_text = safe_user_name[:12].upper()
            p_bbox = fonts["photo_label"].getbbox(p_text)
            pw = p_bbox[2] - p_bbox[0]
            ph = p_bbox[3] - p_bbox[1]
            draw.text((pill_x + (pill_w - pw) // 2, pill_y + (pill_h - ph) // 2 - 2), p_text, font=fonts["photo_label"], fill=(92, 78, 61, 255))

            # 5. Center Information Fields
            name_title = f"{safe_user_name.upper()} • {highest_role_name.upper()}"
            if len(name_title) > 36:
                name_title = name_title[:33] + "..."
            draw.text((285, 155), name_title, font=fonts["name_header"], fill=text_dark)

            fields = [
                ("NOMOR LISENSI :", license_num),
                ("TANGGAL RESMI :", tanggal_resmi_str),
                ("STATUS :", "AKTIF & TERVERIFIKASI RESMI"),
                ("TOTAL EXP :", f"{exp:,} EXP (Level {level})"),
                ("SALDO KAS :", f"{balance:,} RSWN"),
            ]

            field_y = 215
            for label, val in fields:
                draw.text((285, field_y), label, font=fonts["label"], fill=text_gold)
                draw.text((475, field_y), val, font=fonts["value"], fill=text_dark)
                field_y += 37

            # 6. Right Wax Seal / Stamp (Versi Mewah Scalloped & Beaded)
            seal_cx, seal_cy = 930, 275
            self._draw_luxury_wax_seal(
                draw=draw,
                cx=seal_cx,
                cy=seal_cy,
                radius=78,
                stamp_title="• RESMI •",
                stamp_date=stamp_date_str,
                stamp_year=stamp_year_str,
                fonts=fonts
            )

            # 7. Horizontal Divider
            draw.line([(65, 435), (W - 65, 435)], fill=gold_light, width=1)

            # 8. Quote / Official Decree
            quote_text = f"Lisensi resmi ini diterbitkan secara sah atas keaktifan dan keanggotaan terverifikasi di server {safe_guild_name}."
            q_bbox = fonts["quote"].getbbox(quote_text)
            qw = q_bbox[2] - q_bbox[0]
            draw.text(((W - qw) // 2, 465), quote_text, font=fonts["quote"], fill=(122, 103, 80, 255))

            # 9. Authority / Signatures Section (Kiri: Owner Server, Kanan: Owner Bot)
            draw.text((120, 515), server_owner_name, font=fonts["sign_name"], fill=text_dark)
            draw.text((110, 550), server_owner_role, font=fonts["sign_role"], fill=text_gold)

            # Center stars and flower
            self._draw_star(draw, W // 2 - 40, 535, r_outer=15, r_inner=7)
            self._draw_sakura(draw, W // 2, 535, r_petal=9)
            self._draw_star(draw, W // 2 + 40, 535, r_outer=15, r_inner=7)

            draw.text((720, 515), bot_owner_display, font=fonts["sign_name"], fill=text_dark)
            draw.text((700, 550), bot_owner_role, font=fonts["sign_role"], fill=text_gold)

            # 10. Bottom Authentication Token
            auth_str = f"ID OTENTIKASI RESMI: RTM-{target.id}-VERIFIED"
            a_bbox = fonts["auth_id"].getbbox(auth_str)
            aw = a_bbox[2] - a_bbox[0]
            draw.text(((W - aw) // 2, 630), auth_str, font=fonts["auth_id"], fill=(160, 145, 125, 255))

            buf = BytesIO()
            card.save(buf, format="PNG")
            buf.seek(0)
            return buf

        return await asyncio.to_thread(_render)

    @commands.hybrid_command(
        name="detectiverank",
        aliases=["rankdetektif", "testrank", "karturank"],
        description="Lihat kartu lisensi resmi keanggotaan server bergaya sertifikat eksklusif"
    )
    @app_commands.describe(member="Pilih member yang ingin dilihat kartu lisensinya (opsional)")
    async def detective_rank(self, ctx: commands.Context, member: discord.Member = None):
        await ctx.defer()
        target = member or ctx.author
        user_id = str(target.id)
        guild_id = str(ctx.guild.id)

        all_level_data = load_json(LEVEL_FILE)
        data = all_level_data.get(guild_id, {})
        bank = load_json(BANK_FILE)

        sorted_users = sorted(data.items(), key=lambda x: x[1].get('exp', 0), reverse=True)
        rank_pos = 1
        for idx, (uid, _) in enumerate(sorted_users):
            if uid == user_id:
                rank_pos = idx + 1
                break

        user_data = data.get(user_id, {"level": 0, "exp": 0, "badges": []})
        user_bank = bank.get(user_id, {"balance": 0})

        level = user_data.get('level', 0)
        exp = user_data.get('exp', 0)
        balance = user_bank.get('balance', 0)

        card_buffer = await self.render_detective_card(
            target=target,
            guild=ctx.guild,
            level=level,
            exp=exp,
            balance=balance,
            rank_pos=rank_pos
        )

        file = discord.File(card_buffer, filename=f"license_{target.name}.png")
        await ctx.send(file=file)

async def setup(bot):
    await bot.add_cog(DetectiveCard(bot))
