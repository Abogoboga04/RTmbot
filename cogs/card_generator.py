import os
import io
import math
import re
import unicodedata
import asyncio
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import aiohttp
import discord

def is_safe_printable_char(ch: str) -> bool:
    """Filter ketat untuk mencegah karakter box kosong (□)."""
    code = ord(ch)
    # ASCII standar yang dapat dicetak (huruf, angka, tanda baca dasar)
    if 32 <= code <= 126:
        return True
    # Latin-1 Suplemen & Latin Extended A/B (aksen & huruf Eropa umum)
    if 160 <= code <= 591:
        return True
    # Simbol tipografi aman (kutip melengkung, bullet, dash)
    if code in (0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2013, 0x2014):
        return True
    return False

def clean_display_text(text: str) -> str:
    """Bersihkan teks dari unicode tak kasat mata, plane 14 selectors, dan kontrol."""
    if not text:
        return "MEMBER"
    text = unicodedata.normalize('NFKC', str(text))
    cleaned = ''.join(ch for ch in text if is_safe_printable_char(ch)).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned if cleaned else "MEMBER"

def get_card_fonts():
    """Load font tipografi elegan Windows dengan fallback terjamin."""
    win_fonts = r"C:\Windows\Fonts"
    f_serif_bold = os.path.join(win_fonts, "georgiab.ttf")
    if not os.path.exists(f_serif_bold):
        f_serif_bold = os.path.join(win_fonts, "timesbd.ttf")
    
    f_serif_reg = os.path.join(win_fonts, "georgia.ttf")
    if not os.path.exists(f_serif_reg):
        f_serif_reg = os.path.join(win_fonts, "times.ttf")

    f_sans_bold = os.path.join(win_fonts, "arialbd.ttf")
    f_sans_reg = os.path.join(win_fonts, "arial.ttf")

    def load_font(path, size):
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:
            pass
        return ImageFont.load_default()

    return {
        "title": load_font(f_serif_bold, 28),
        "subtitle": load_font(f_serif_bold, 15),
        "name_header": load_font(f_serif_bold, 28),
        "badge": load_font(f_sans_bold, 17),
        "label": load_font(f_serif_bold, 16),
        "value": load_font(f_serif_bold, 17),
        "photo_label": load_font(f_sans_bold, 14),
        "quote": load_font(f_serif_reg, 16),
        "sign_name": load_font(f_serif_bold, 24),
        "sign_role": load_font(f_serif_reg, 15),
        "stamp_title": load_font(f_sans_bold, 13),
        "stamp_date": load_font(f_sans_bold, 16),
        "stamp_sub": load_font(f_sans_bold, 12),
        "auth_id": load_font(f_sans_reg, 12),
    }

def draw_star(draw, cx, cy, r_outer=15, r_inner=7, fill=(245, 195, 60, 255), outline=(180, 135, 30, 255)):
    points = []
    for i in range(10):
        r = r_outer if i % 2 == 0 else r_inner
        angle = i * math.pi / 5 - math.pi / 2
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        points.append((x, y))
    draw.polygon(points, fill=fill, outline=outline)

def draw_sakura(draw, cx, cy, r_petal=9, fill=(255, 170, 195, 255), outline=(215, 95, 130, 255)):
    for i in range(5):
        angle = i * 2 * math.pi / 5 - math.pi / 2
        px = cx + 8 * math.cos(angle)
        py = cy + 8 * math.sin(angle)
        draw.ellipse([(px - r_petal, py - r_petal), (px + r_petal, py + r_petal)], fill=fill, outline=outline)
    draw.ellipse([(cx - 5, cy - 5), (cx + 5, cy + 5)], fill=(255, 235, 120, 255))

def draw_luxury_wax_seal(draw, cx, cy, radius=78, stamp_title="• RESMI •", stamp_date="19 JUL", stamp_year="THN 2024", fonts=None):
    """Render stempel lilin mewah bergaya kekaisaran dengan 36 gerigi bintang & cincin manik emas."""
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
    
    draw.polygon(scallop_pts, fill=(140, 25, 25, 255), outline=(90, 15, 15, 255))
    draw.ellipse([(cx - radius + 4, cy - radius + 4), (cx + radius - 4, cy + radius - 4)], 
                 fill=(185, 38, 38, 255), outline=(218, 165, 32, 255), width=2)
    
    # Cincin manik-manik emas (30 dots)
    dot_r = radius - 11
    for i in range(30):
        angle = i * 2 * math.pi / 30
        dx = cx + dot_r * math.cos(angle)
        dy = cy + dot_r * math.sin(angle)
        draw.ellipse([(dx - 1.5, dy - 1.5), (dx + 1.5, dy + 1.5)], fill=(255, 223, 128, 255))
        
    draw.ellipse([(cx - radius + 16, cy - radius + 16), (cx + radius - 16, cy + radius - 16)], 
                 outline=(218, 165, 32, 200), width=1)
    
    # Lambang sakura di bagian atas seal
    draw_sakura(draw, cx, cy - 35, r_petal=5, fill=(255, 190, 210, 255), outline=(200, 70, 90, 255))
    
    # Teks label RESMI
    b1 = fonts["stamp_title"].getbbox(stamp_title)
    w1 = b1[2] - b1[0]
    draw.text((cx - w1 // 2, cy - 18), stamp_title, font=fonts["stamp_title"], fill=(255, 245, 220, 255))
    
    # Teks tanggal
    b2 = fonts["stamp_date"].getbbox(stamp_date)
    w2 = b2[2] - b2[0]
    draw.text((cx - w2 // 2, cy + 2), stamp_date, font=fonts["stamp_date"], fill=(255, 255, 255, 255))
    
    # Teks tahun
    b3 = fonts["stamp_sub"].getbbox(stamp_year)
    w3 = b3[2] - b3[0]
    draw.text((cx - w3 // 2, cy + 25), stamp_year, font=fonts["stamp_sub"], fill=(255, 230, 230, 255))

async def generate_official_member_card(
    bot: discord.Client,
    target: discord.Member,
    guild: discord.Guild,
    exp: int = 0,
    level: int = 0,
    balance: int = 0,
    rank_pos: int = None,
    custom_title: str = None
) -> io.BytesIO:
    """
    Menghasilkan file gambar Kartu Resmi Anggota (Sertifikat Eksklusif 1050x660 PNG)
    yang digunakan untuk command /rank dan banner pesan sambutan (welcome).
    """
    # Unduh Avatar Target
    avatar_bytes = None
    try:
        avatar_bytes = await target.display_avatar.replace(size=256, format="png").read()
    except Exception:
        pass

    # Sanitasi Teks
    safe_user_name = clean_display_text(target.display_name)
    safe_guild_name = clean_display_text(guild.name)

    # Role Tertinggi
    user_roles = [r for r in target.roles if r.name != "@everyone"]
    highest_role_name = clean_display_text(user_roles[-1].name.upper() if user_roles else "ANGGOTA RESMI")

    # Nama Owner Server
    server_owner = guild.owner
    server_owner_name = clean_display_text(server_owner.display_name if server_owner else "Owner Server")
    server_owner_role = f"Owner & Pendiri {safe_guild_name[:18]}"

    # Nama Owner Bot & Nama Bot Dinamis
    try:
        app_info = await bot.application_info()
        bot_owner = app_info.owner
        bot_owner_name = clean_display_text(bot_owner.display_name if bot_owner else "DRH71")
    except Exception:
        bot_owner_name = "DRH71"

    bot_display_name = clean_display_text(bot.user.name if bot.user else "RTMBOT")
    bot_owner_role = f"Pengembang & Owner Bot {bot_display_name}"

    # Format Tanggal Bergabung
    months_id = ["JAN", "FEB", "MAR", "APR", "MEI", "JUN", "JUL", "AGU", "SEP", "OKT", "NOV", "DES"]
    months_full_id = [
        "JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI",
        "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"
    ]
    if target.joined_at:
        j_dt = target.joined_at
        j_day = f"{j_dt.day:02d}"
        j_month_num = j_dt.month
        j_month_short = months_id[j_month_num - 1]
        j_month_full = months_full_id[j_month_num - 1]
        j_year = str(j_dt.year)
    else:
        now_dt = datetime.utcnow()
        j_day = f"{now_dt.day:02d}"
        j_month_short = months_id[now_dt.month - 1]
        j_month_full = months_full_id[now_dt.month - 1]
        j_year = str(now_dt.year)

    official_date_str = f"{int(j_day)} {j_month_full} {j_year}"
    stamp_date_str = f"{int(j_day)} {j_month_short}"
    stamp_year_str = f"THN {j_year}"
    sub_header_str = f"SERTIFIKAT RESMI KEANGGOTAAN • SEJAK {j_year}"

    def _render() -> io.BytesIO:
        W, H = 1050, 660
        card = Image.new("RGBA", (W, H), (252, 250, 242, 255))
        draw = ImageDraw.Draw(card)
        fonts = get_card_fonts()

        gold_dark = (175, 143, 84, 255)
        gold_light = (212, 188, 130, 255)
        text_dark = (44, 34, 30, 255)
        text_gold = (140, 115, 85, 255)

        # 1. Double Gold Border & Corner Dots
        draw.rectangle([(25, 25), (W - 25, H - 25)], outline=gold_dark, width=3)
        draw.rectangle([(33, 33), (W - 33, H - 33)], outline=gold_light, width=1)
        for cx, cy in [(42, 42), (W - 42, 42), (42, H - 42), (W - 42, H - 42)]:
            draw.ellipse([(cx - 2, cy - 2), (cx + 2, cy + 2)], fill=gold_dark)

        # 2. Header Judul
        title_text = custom_title or f"KARTU RESMI ANGGOTA • {safe_guild_name.upper()}"
        draw.text((65, 55), title_text, font=fonts["title"], fill=text_dark)
        draw.text((65, 96), sub_header_str, font=fonts["subtitle"], fill=text_gold)

        # 3. Badge Peringkat Kanan Atas
        if rank_pos is not None:
            badge_tier = f"RANK: #{rank_pos} • CLASS-A" if rank_pos > 3 else "RANK: S-CLASS MASTER"
        else:
            badge_tier = "ANGGOTA RESMI VERIFIED"
            
        badge_w, badge_h = 240, 42
        badge_x, badge_y = W - 65 - badge_w, 60
        draw.rounded_rectangle([(badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h)], radius=8, fill=(192, 57, 43, 255))
        bw = fonts["badge"].getbbox(badge_tier)
        bw_w = bw[2] - bw[0]
        bw_h = bw[3] - bw[1]
        draw.text((badge_x + (badge_w - bw_w) // 2, badge_y + (badge_h - bw_h) // 2 - 2), badge_tier, font=fonts["badge"], fill=(255, 255, 255, 255))

        # 4. Kotak Foto Avatar
        frame_box = [(65, 140), (245, 390)]
        draw.rounded_rectangle(frame_box, radius=12, fill=(245, 240, 225, 255), outline=gold_light, width=2)

        pic_cx, pic_cy, pic_r = 155, 225, 65
        if avatar_bytes:
            try:
                av_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((pic_r * 2, pic_r * 2), Image.Resampling.LANCZOS)
                av_mask = Image.new("L", (pic_r * 2, pic_r * 2), 0)
                ImageDraw.Draw(av_mask).ellipse((0, 0, pic_r * 2, pic_r * 2), fill=255)
                card.paste(av_img, (pic_cx - pic_r, pic_cy - pic_r), av_mask)
            except Exception:
                draw.ellipse([(pic_cx - pic_r, pic_cy - pic_r), (pic_cx + pic_r, pic_cy + pic_r)], fill=(120, 140, 170, 255))
        else:
            draw.ellipse([(pic_cx - pic_r, pic_cy - pic_r), (pic_cx + pic_r, pic_cy + pic_r)], fill=(120, 140, 170, 255))

        draw.ellipse([(pic_cx - pic_r - 2, pic_cy - pic_r - 2), (pic_cx + pic_r + 2, pic_cy + pic_r + 2)], outline=gold_dark, width=2)

        # Label Nama di Bawah Foto Avatar
        tag_box = [(83, 315), (227, 347)]
        draw.rounded_rectangle(tag_box, radius=6, fill=(238, 230, 210, 255), outline=gold_light, width=1)
        short_u = safe_user_name[:12]
        tb = fonts["photo_label"].getbbox(short_u)
        tb_w = tb[2] - tb[0]
        draw.text((83 + (144 - tb_w) // 2, 323), short_u, font=fonts["photo_label"], fill=text_dark)

        # 5. Detail Profil & Lisensi
        user_header_text = f"{safe_user_name} • {highest_role_name}"
        if len(user_header_text) > 36:
            user_header_text = user_header_text[:33] + "..."
        draw.text((280, 155), user_header_text, font=fonts["name_header"], fill=text_dark)

        field_y = 215
        license_number = f"RTM-{target.id}"
        fields = [
            ("NOMOR LISENSI :", license_number),
            ("TANGGAL RESMI :", official_date_str),
            ("STATUS :", "AKTIF & TERVERIFIKASI RESMI"),
            ("TOTAL EXP :", f"{exp:,} EXP (Level {level})"),
            ("SALDO KAS :", f"{balance:,} RSWN"),
        ]
        for label, val in fields:
            draw.text((280, field_y), label, font=fonts["label"], fill=text_gold)
            draw.text((475, field_y), val, font=fonts["value"], fill=text_dark)
            field_y += 37

        # 6. Luxury Scalloped Wax Seal
        seal_cx, seal_cy = 930, 275
        draw_luxury_wax_seal(
            draw=draw,
            cx=seal_cx,
            cy=seal_cy,
            radius=78,
            stamp_title="• RESMI •",
            stamp_date=stamp_date_str,
            stamp_year=stamp_year_str,
            fonts=fonts
        )

        # 7. Divider Horizontal
        draw.line([(65, 435), (W - 65, 435)], fill=gold_light, width=1)

        # 8. Teks Dekrit / Pengesahan
        quote_text = f"Lisensi resmi ini diterbitkan secara sah atas keaktifan dan keanggotaan terverifikasi di server {safe_guild_name}."
        q_bbox = fonts["quote"].getbbox(quote_text)
        qw = q_bbox[2] - q_bbox[0]
        draw.text(((W - qw) // 2, 465), quote_text, font=fonts["quote"], fill=(122, 103, 80, 255))

        # 9. Tanda Tangan Resmi (Owner Server & Owner Bot Rata Tengah)
        cx_left = 200
        sw = fonts["sign_name"].getbbox(server_owner_name)[2] - fonts["sign_name"].getbbox(server_owner_name)[0]
        draw.text((cx_left - sw // 2, 515), server_owner_name, font=fonts["sign_name"], fill=text_dark)
        srw = fonts["sign_role"].getbbox(server_owner_role)[2] - fonts["sign_role"].getbbox(server_owner_role)[0]
        draw.text((cx_left - srw // 2, 550), server_owner_role, font=fonts["sign_role"], fill=text_gold)

        # Bintang & Sakura di Tengah
        draw_star(draw, W // 2 - 40, 535, r_outer=15, r_inner=7)
        draw_sakura(draw, W // 2, 535, r_petal=9)
        draw_star(draw, W // 2 + 40, 535, r_outer=15, r_inner=7)

        # Owner Bot
        cx_right = 800
        bw = fonts["sign_name"].getbbox(bot_owner_name)[2] - fonts["sign_name"].getbbox(bot_owner_name)[0]
        draw.text((cx_right - bw // 2, 515), bot_owner_name, font=fonts["sign_name"], fill=text_dark)
        brw = fonts["sign_role"].getbbox(bot_owner_role)[2] - fonts["sign_role"].getbbox(bot_owner_role)[0]
        draw.text((cx_right - brw // 2, 550), bot_owner_role, font=fonts["sign_role"], fill=text_gold)

        # 10. ID Otentikasi Footer
        auth_str = f"ID OTENTIKASI RESMI: RTM-{target.id}-VERIFIED"
        a_bbox = fonts["auth_id"].getbbox(auth_str)
        aw = a_bbox[2] - a_bbox[0]
        draw.text(((W - aw) // 2, 630), auth_str, font=fonts["auth_id"], fill=(160, 145, 125, 255))

        buf = io.BytesIO()
        card.save(buf, format="PNG")
        buf.seek(0)
        return buf

    return await asyncio.to_thread(_render)
