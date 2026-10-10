import io
import os
import math
import time
import random
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

        # Fallback Google Fonts jika berjalan di Linux / Railway container
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
            "title": load_font(f_serif_bold_path, remote_serif_bold_bytes, 30),
            "subtitle": load_font(f_serif_bold_path, remote_serif_bold_bytes, 15),
            "name_header": load_font(f_serif_bold_path, remote_serif_bold_bytes, 28),
            "badge": load_font(f_sans_bold_path, remote_sans_bold_bytes, 17),
            "label": load_font(f_serif_bold_path, remote_serif_bold_bytes, 16),
            "value": load_font(f_serif_bold_path, remote_serif_bold_bytes, 17),
            "photo_label": load_font(f_sans_bold_path, remote_sans_bold_bytes, 14),
            "quote": load_font(f_serif_reg_path, remote_serif_reg_bytes, 16),
            "sign_name": load_font(f_serif_bold_path, remote_serif_bold_bytes, 17),
            "sign_role": load_font(f_serif_reg_path, remote_serif_reg_bytes, 13),
            "stamp_title": load_font(f_sans_bold_path, remote_sans_bold_bytes, 15),
            "stamp_date": load_font(f_sans_bold_path, remote_sans_bold_bytes, 15),
            "stamp_sub": load_font(f_sans_bold_path, remote_sans_bold_bytes, 11),
            "auth_id": load_font(f_sans_reg_path, remote_sans_reg_bytes, 12),
        }

    def _draw_star(self, draw, cx, cy, r_outer=12, r_inner=6, fill=(245, 195, 60, 255), outline=(180, 135, 30, 255)):
        points = []
        for i in range(10):
            r = r_outer if i % 2 == 0 else r_inner
            angle = i * math.pi / 5 - math.pi / 2
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            points.append((x, y))
        draw.polygon(points, fill=fill, outline=outline)

    def _draw_sakura(self, draw, cx, cy, r_petal=7, fill=(255, 170, 195, 255), outline=(215, 95, 130, 255)):
        for i in range(5):
            angle = i * 2 * math.pi / 5 - math.pi / 2
            px = cx + 7 * math.cos(angle)
            py = cy + 7 * math.sin(angle)
            draw.ellipse([(px - r_petal, py - r_petal), (px + r_petal, py + r_petal)], fill=fill, outline=outline)
        draw.ellipse([(cx - 4, cy - 4), (cx + 4, cy + 4)], fill=(255, 235, 120, 255))

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

        safe_user_name = unicodedata.normalize('NFKC', target.display_name).strip()
        safe_guild_name = unicodedata.normalize('NFKC', guild.name).strip()

        # Ambil role tertinggi pengguna (kecuali @everyone)
        user_roles = [r for r in target.roles if r.name != "@everyone"]
        highest_role_name = user_roles[-1].name.upper() if user_roles else "MEMBER RESMI"

        def _render():
            W, H = 1100, 680
            bg_color = (252, 249, 241, 255) # Warm parchment
            card = Image.new("RGBA", (W, H), bg_color)
            draw = ImageDraw.Draw(card)

            gold_dark = (175, 142, 75, 255)
            gold_light = (212, 188, 130, 255)
            text_dark = (44, 34, 30, 255)
            text_gold = (140, 115, 85, 255)
            red_seal = (178, 44, 44, 255)

            # 1. Double Gold Border
            draw.rectangle([(25, 25), (W - 25, H - 25)], outline=gold_dark, width=3)
            draw.rectangle([(35, 35), (W - 35, H - 35)], outline=gold_light, width=1)

            # Corner dots
            for cx, cy in [(25, 25), (W - 25, 25), (25, H - 25), (W - 25, H - 25)]:
                draw.ellipse([(cx - 4, cy - 4), (cx + 4, cy + 4)], fill=gold_dark)

            for cx, cy in [(42, 42), (W - 42, 42), (42, H - 42), (W - 42, H - 42)]:
                draw.ellipse([(cx - 2, cy - 2), (cx + 2, cy + 2)], fill=gold_dark)

            # 2. Top Header Left
            title_text = f"BIRO DETEKTIF RESMI {safe_guild_name.upper()}"
            if len(title_text) > 38:
                title_text = title_text[:35] + "..."
            draw.text((65, 55), title_text, font=fonts["title"], fill=text_dark)
            draw.text((65, 96), "KASUS SPESIAL • 28 OKTOBER 2026", font=fonts["subtitle"], fill=text_gold)

            # 3. Top Header Right Badge
            badge_tier = "RANK: S-CLASS MASTER" if rank_pos <= 3 else f"RANK: #{rank_pos} • CLASS-A"
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

            # Nomor lisensi acak deterministik berbasis target ID
            rnd_num = (abs(hash(str(target.id))) % 9000) + 1000
            license_num = f"HR-2810-{rnd_num}"
            fields = [
                ("NOMOR LISENSI :", license_num),
                ("TANGGAL RESMI :", "28 OKTOBER 2026"),
                ("STATUS :", "AKTIF & TERVERIFIKASI RESMI"),
                ("TOTAL EXP :", f"{exp:,} EXP (Level {level})"),
                ("SALDO KAS :", f"{balance:,} RSWN"),
            ]

            field_y = 215
            for label, val in fields:
                draw.text((285, field_y), label, font=fonts["label"], fill=text_gold)
                draw.text((475, field_y), val, font=fonts["value"], fill=text_dark)
                field_y += 37

            # 6. Right Wax Seal / Stamp
            seal_cx, seal_cy = 930, 275
            seal_r = 72
            draw.ellipse([(seal_cx - seal_r - 6, seal_cy - seal_r - 6), (seal_cx + seal_r + 6, seal_cy + seal_r + 6)], outline=(220, 100, 100, 80), width=4)
            draw.ellipse([(seal_cx - seal_r, seal_cy - seal_r), (seal_cx + seal_r, seal_cy + seal_r)], fill=red_seal, outline=(140, 30, 30, 255), width=3)
            draw.ellipse([(seal_cx - seal_r + 8, seal_cy - seal_r + 8), (seal_cx + seal_r - 8, seal_cy + seal_r - 8)], outline=(240, 160, 160, 180), width=1)

            # Stamp details dengan vector sakura
            self._draw_sakura(draw, seal_cx - 36, seal_cy - 30, r_petal=5)
            st1 = "RESMI"
            b1 = fonts["stamp_title"].getbbox(st1)
            draw.text((seal_cx - (b1[2]-b1[0])//2 + 8, seal_cy - 39), st1, font=fonts["stamp_title"], fill=(255, 240, 240, 255))

            st2 = "28 OKT"
            b2 = fonts["stamp_date"].getbbox(st2)
            draw.text((seal_cx - (b2[2]-b2[0])//2, seal_cy - 12), st2, font=fonts["stamp_date"], fill=(255, 255, 255, 255))

            st3 = "VERIFIED"
            b3 = fonts["stamp_sub"].getbbox(st3)
            draw.text((seal_cx - (b3[2]-b3[0])//2, seal_cy + 14), st3, font=fonts["stamp_sub"], fill=(255, 220, 220, 255))

            # 7. Horizontal Divider
            draw.line([(65, 435), (W - 65, 435)], fill=gold_light, width=1)

            # 8. Quote / Official Decree
            quote_text = "Lisensi resmi ini diterbitkan secara sah atas keberhasilan memecahkan Kasus Spesial 28 Oktober."
            q_bbox = fonts["quote"].getbbox(quote_text)
            qw = q_bbox[2] - q_bbox[0]
            draw.text(((W - qw) // 2, 465), quote_text, font=fonts["quote"], fill=(122, 103, 80, 255))

            # 9. Authority / Signatures Section
            draw.text((150, 520), "Mas Ilham Endriadi", font=fonts["sign_name"], fill=text_dark)
            draw.text((140, 545), "Kawan Seberang Pulau (Padang)", font=fonts["sign_role"], fill=text_gold)

            # Center stars and flower
            self._draw_star(draw, W // 2 - 35, 535, r_outer=13, r_inner=6)
            self._draw_sakura(draw, W // 2, 535, r_petal=7)
            self._draw_star(draw, W // 2 + 35, 535, r_outer=13, r_inner=6)

            draw.text((740, 520), "Segenap Sahabat Discord RTM", font=fonts["sign_name"], fill=text_dark)
            draw.text((765, 545), "Keluarga Server & Squad Mabar", font=fonts["sign_role"], fill=text_gold)

            # 10. Bottom Authentication Token
            short_uid = str(target.id)[:6]
            auth_str = f"ID OTENTIKASI RESMI: HR-{short_uid}-BDG-SQUAD-RTM-VERIFIED"
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
        aliases=["rankdetektif", "testrank"],
        description="Lihat kartu rank bertema Sertifikat Lisensi Biro Detektif Resmi"
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

        file = discord.File(card_buffer, filename=f"detective_license_{target.name}.png")
        await ctx.send(file=file)

async def setup(bot):
    await bot.add_cog(DetectiveCard(bot))
