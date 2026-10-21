import os
import io
import json
import math
import re
import unicodedata
import asyncio
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import aiohttp
import discord

REGISTRY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "member_registry.json")


def get_or_create_member_serial_id(guild: discord.Guild, member: discord.Member) -> int:
    if not guild or not member:
        return 1

    guild_id = str(guild.id)
    user_id = str(member.id)

    registry = {}
    try:
        if os.path.exists(REGISTRY_FILE):
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                registry = json.load(f)
    except Exception:
        registry = {}

    if guild_id not in registry or not isinstance(registry[guild_id], dict):
        base_count = getattr(guild, "member_count", 1) or 1
        registry[guild_id] = {
            "counter": max(base_count, 1),
            "members": {}
        }

    guild_data = registry[guild_id]
    if "members" not in guild_data or not isinstance(guild_data["members"], dict):
        guild_data["members"] = {}
    if "counter" not in guild_data:
        guild_data["counter"] = max(getattr(guild, "member_count", 1) or 1, 1)

    if user_id in guild_data["members"]:
        return guild_data["members"][user_id]

    current_count = getattr(guild, "member_count", 1) or 1
    new_serial = max(guild_data["counter"] + 1, current_count)
    guild_data["counter"] = new_serial
    guild_data["members"][user_id] = new_serial

    try:
        os.makedirs(os.path.dirname(REGISTRY_FILE), exist_ok=True)
        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return new_serial


SMALL_CAPS_MAP = {
    '\u1d00': 'A', '\u0299': 'B', '\u1d04': 'C', '\u1d05': 'D', '\u1d07': 'E',
    '\ua730': 'F', '\u0262': 'G', '\u029c': 'H', '\u026a': 'I', '\u1d0a': 'J',
    '\u1d0b': 'K', '\u029f': 'L', '\u1d0d': 'M', '\u0274': 'N', '\u1d0f': 'O',
    '\u1d18': 'P', '\u0291': 'Q', '\u0280': 'R', '\ua731': 'S', '\u1d1b': 'T',
    '\u1d1c': 'U', '\u1d20': 'V', '\u1d21': 'W', '\u1d22': 'Z', '\u028f': 'Y'
}


def is_safe_printable_char(ch: str) -> bool:
    code = ord(ch)
    if 32 <= code <= 126:
        return True
    if 160 <= code <= 591:
        return True
    if code in (0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2013, 0x2014):
        return True
    return False


def clean_display_text(text: str) -> str:
    if not text:
        return "MEMBER"
    chars = []
    for ch in str(text):
        if ch in SMALL_CAPS_MAP:
            chars.append(SMALL_CAPS_MAP[ch])
        else:
            code = ord(ch)
            if 0x24b6 <= code <= 0x24cf:
                chars.append(chr(code - 0x24b6 + ord('A')))
            elif 0x24d0 <= code <= 0x24e9:
                chars.append(chr(code - 0x24d0 + ord('a')))
            elif 0x249c <= code <= 0x24b5:
                chars.append(chr(code - 0x249c + ord('a')))
            else:
                chars.append(ch)
    raw = ''.join(chars)
    nfd = ''.join(c for c in unicodedata.normalize('NFD', raw) if unicodedata.category(c) != 'Mn')
    nfkc = unicodedata.normalize('NFKC', nfd)
    cleaned = ''.join(ch for ch in nfkc if is_safe_printable_char(ch)).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned if cleaned else "MEMBER"


def find_font(filenames):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    asset_fonts = os.path.join(base_dir, "assets", "fonts")
    search_dirs = [
        asset_fonts,
        os.path.join(base_dir, "data", "fonts"),
        r"C:\Windows\Fonts",
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/truetype/liberation",
        "/usr/share/fonts",
        "/usr/local/share/fonts"
    ]
    for d in search_dirs:
        if not os.path.exists(d):
            continue
        for fn in filenames:
            p = os.path.join(d, fn)
            if os.path.isfile(p):
                return p
    return None


f_serif_bold = find_font(["georgiab.ttf", "timesbd.ttf", "DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf"])
f_serif_reg = find_font(["georgia.ttf", "times.ttf", "DejaVuSerif.ttf", "LiberationSerif-Regular.ttf"])
f_sans_bold = find_font(["arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"])
f_sans_reg = find_font(["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"])


def load_font(path, size):
    try:
        if path and os.path.exists(path):
            return ImageFont.truetype(path, size)
    except Exception:
        pass
    return ImageFont.load_default()


def get_card_fonts():
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

    dot_r = radius - 11
    for i in range(30):
        angle = i * 2 * math.pi / 30
        dx = cx + dot_r * math.cos(angle)
        dy = cy + dot_r * math.sin(angle)
        draw.ellipse([(dx - 1.5, dy - 1.5), (dx + 1.5, dy + 1.5)], fill=(255, 223, 128, 255))

    draw.ellipse([(cx - radius + 16, cy - radius + 16), (cx + radius - 16, cy + radius - 16)],
                 outline=(218, 165, 32, 200), width=1)

    draw_sakura(draw, cx, cy - 35, r_petal=5, fill=(255, 190, 210, 255), outline=(200, 70, 90, 255))

    b1 = fonts["stamp_title"].getbbox(stamp_title)
    w1 = b1[2] - b1[0]
    draw.text((cx - w1 // 2, cy - 18), stamp_title, font=fonts["stamp_title"], fill=(255, 245, 220, 255))

    b2 = fonts["stamp_date"].getbbox(stamp_date)
    w2 = b2[2] - b2[0]
    draw.text((cx - w2 // 2, cy + 2), stamp_date, font=fonts["stamp_date"], fill=(255, 255, 255, 255))

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
    if rank_pos is None and guild and target:
        try:
            rank_pos = get_or_create_member_serial_id(guild, target)
        except Exception:
            pass

    avatar_bytes = None
    try:
        avatar_bytes = await target.display_avatar.replace(size=256, format="png").read()
    except Exception:
        pass

    safe_user_name = clean_display_text(target.display_name)
    safe_guild_name = clean_display_text(guild.name)

    user_roles = [r for r in target.roles if r.name != "@everyone"]
    highest_role_name = clean_display_text(user_roles[-1].name.upper() if user_roles else "ANGGOTA RESMI")

    server_owner = guild.owner
    server_owner_name = clean_display_text(server_owner.display_name if server_owner else "Owner Server")
    server_owner_role = f"Owner & Pendiri {safe_guild_name[:18]}"

    try:
        app_info = await bot.application_info()
        bot_owner = app_info.owner
        bot_owner_name = clean_display_text(bot_owner.display_name if bot_owner else "DRH71")
    except Exception:
        bot_owner_name = "DRH71"

    bot_display_name = clean_display_text(bot.user.name if bot.user else "RTMBOT")
    bot_owner_role = f"Pengembang & Owner Bot {bot_display_name}"

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
        W, H = 1024, 631
        card = Image.new("RGBA", (W, H), (255, 251, 242, 255))
        draw = ImageDraw.Draw(card)
        fonts = get_card_fonts()

        gold_dark = (212, 175, 55, 255)
        gold_light = (217, 189, 138, 255)
        text_dark = (44, 34, 30, 255)
        text_gold = (140, 115, 85, 255)

        draw.rectangle([(20, 20), (W - 20, H - 22)], outline=gold_dark, width=4)
        draw.rectangle([(32, 32), (W - 32, H - 33)], outline=gold_light, width=1)

        bracket_len = 22
        dot_dist = 7
        draw.line([(42, 42), (42 + bracket_len, 42)], fill=gold_dark, width=2)
        draw.line([(42, 42), (42, 42 + bracket_len)], fill=gold_dark, width=2)
        draw.ellipse([(42 + dot_dist - 2, 42 + dot_dist - 2), (42 + dot_dist + 2, 42 + dot_dist + 2)], fill=gold_dark)

        draw.line([(W - 42, 42), (W - 42 - bracket_len, 42)], fill=gold_dark, width=2)
        draw.line([(W - 42, 42), (W - 42, 42 + bracket_len)], fill=gold_dark, width=2)
        draw.ellipse([(W - 42 - dot_dist - 2, 42 + dot_dist - 2), (W - 42 - dot_dist + 2, 42 + dot_dist + 2)], fill=gold_dark)

        draw.line([(42, H - 43), (42 + bracket_len, H - 43)], fill=gold_dark, width=2)
        draw.line([(42, H - 43), (42, H - 43 - bracket_len)], fill=gold_dark, width=2)
        draw.ellipse([(42 + dot_dist - 2, H - 43 - dot_dist - 2), (42 + dot_dist + 2, H - 43 - dot_dist + 2)], fill=gold_dark)

        draw.line([(W - 42, H - 43), (W - 42 - bracket_len, H - 43)], fill=gold_dark, width=2)
        draw.line([(W - 42, H - 43), (W - 42, H - 43 - bracket_len)], fill=gold_dark, width=2)
        draw.ellipse([(W - 42 - dot_dist - 2, H - 43 - dot_dist - 2), (W - 42 - dot_dist + 2, H - 43 - dot_dist + 2)], fill=gold_dark)

        badge_w, badge_h = 220, 38
        badge_x, badge_y = W - 58 - badge_w, 54

        title_text = custom_title or f"KARTU RESMI ANGGOTA • {safe_guild_name.upper()}"
        max_title_w = badge_x - 58 - 18
        title_font = fonts["title"]
        tb = title_font.getbbox(title_text)
        tw = tb[2] - tb[0]
        if tw > max_title_w:
            for s in [24, 21, 18, 16]:
                cand_font = load_font(f_serif_bold, s)
                cb = cand_font.getbbox(title_text)
                if (cb[2] - cb[0]) <= max_title_w:
                    title_font = cand_font
                    break
            else:
                while len(title_text) > 15:
                    title_text = title_text[:-4].strip() + "..."
                    cb = title_font.getbbox(title_text)
                    if (cb[2] - cb[0]) <= max_title_w:
                        break

        draw.text((58, 48), title_text, font=title_font, fill=text_dark)
        draw.text((58, 86), sub_header_str, font=fonts["subtitle"], fill=text_gold)

        if rank_pos is not None:
            badge_tier = f"RANK: #{rank_pos} • CLASS-A" if rank_pos > 3 else "RANK: S-CLASS MASTER"
        else:
            badge_tier = "ANGGOTA RESMI VERIFIED"
        draw.rounded_rectangle([(badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h)], radius=8, fill=(192, 57, 43, 255))
        bw = fonts["badge"].getbbox(badge_tier)
        b_w = bw[2] - bw[0]
        b_h = bw[3] - bw[1]
        draw.text((badge_x + (badge_w - b_w) // 2, badge_y + (badge_h - b_h) // 2 - 2), badge_tier, font=fonts["badge"], fill=(255, 255, 255, 255))

        draw.line([(58, 109), (W - 58, 109)], fill=gold_dark, width=1)

        frame_box = [(58, 138), (212, 345)]
        draw.rounded_rectangle(frame_box, radius=8, fill=(255, 246, 233, 255), outline=gold_light, width=1)

        pic_cx, pic_cy, pic_r = 135, 222, 54
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

        tag_box = [(75, 302), (195, 332)]
        draw.rounded_rectangle(tag_box, radius=6, fill=(248, 237, 218, 255), outline=gold_light, width=1)
        short_u = safe_user_name[:12]
        tb = fonts["photo_label"].getbbox(short_u)
        tb_w = tb[2] - tb[0]
        draw.text((75 + (120 - tb_w) // 2, 310), short_u, font=fonts["photo_label"], fill=text_dark)

        user_header_text = f"{safe_user_name} • {highest_role_name}"
        if len(user_header_text) > 36:
            user_header_text = user_header_text[:33] + "..."
        draw.text((246, 154), user_header_text, font=fonts["name_header"], fill=text_dark)

        user_suffix = str(target.id)[-5:]
        guild_suffix = str(guild.id)[-4:] if guild else "0000"
        license_number = f"{user_suffix}-{guild_suffix}"
        field_y = 205
        fields = [
            ("NOMOR LISENSI :", license_number),
            ("TANGGAL RESMI :", official_date_str),
            ("STATUS        :", "AKTIF & TERVERIFIKASI RESMI"),
            ("TOTAL EXP     :", f"{exp:,} EXP (Level {level})"),
            ("SALDO KAS     :", f"{balance:,} RSWN"),
        ]
        for label, val in fields:
            draw.text((246, field_y), label, font=fonts["label"], fill=text_gold)
            draw.text((415, field_y), val, font=fonts["value"], fill=text_dark)
            field_y += 33

        seal_cx, seal_cy = 887, 240
        draw_luxury_wax_seal(
            draw=draw,
            cx=seal_cx,
            cy=seal_cy,
            radius=64,
            stamp_title="• RESMI •",
            stamp_date=stamp_date_str,
            stamp_year=stamp_year_str,
            fonts=fonts
        )

        draw.line([(58, 415), (W - 58, 415)], fill=gold_light, width=1)

        display_guild_in_quote = safe_guild_name if len(safe_guild_name) <= 30 else (safe_guild_name[:27] + "...")
        quote_text = f"Lisensi resmi ini diterbitkan secara sah atas keaktifan dan keanggotaan terverifikasi di server {display_guild_in_quote}."
        q_bbox = fonts["quote"].getbbox(quote_text)
        qw = q_bbox[2] - q_bbox[0]
        if qw > (W - 116):
            quote_text = f"Lisensi resmi ini diterbitkan atas keaktifan dan keanggotaan di server {display_guild_in_quote}."
            q_bbox = fonts["quote"].getbbox(quote_text)
            qw = q_bbox[2] - q_bbox[0]
        draw.text(((W - qw) // 2, 445), quote_text, font=fonts["quote"], fill=(122, 103, 80, 255))

        cx_left = 185
        sw = fonts["sign_name"].getbbox(server_owner_name)[2] - fonts["sign_name"].getbbox(server_owner_name)[0]
        draw.text((cx_left - sw // 2, 482), server_owner_name, font=fonts["sign_name"], fill=text_dark)
        srw = fonts["sign_role"].getbbox(server_owner_role)[2] - fonts["sign_role"].getbbox(server_owner_role)[0]
        if srw > 260:
            server_owner_role = f"Owner & Pendiri {safe_guild_name[:12]}..."
            srw = fonts["sign_role"].getbbox(server_owner_role)[2] - fonts["sign_role"].getbbox(server_owner_role)[0]
        draw.text((cx_left - srw // 2, 510), server_owner_role, font=fonts["sign_role"], fill=text_gold)

        draw_star(draw, W // 2 - 36, 498, r_outer=13, r_inner=6)
        draw_sakura(draw, W // 2, 498, r_petal=7)
        draw_star(draw, W // 2 + 36, 498, r_outer=13, r_inner=6)

        cx_right = 835
        bw = fonts["sign_name"].getbbox(bot_owner_name)[2] - fonts["sign_name"].getbbox(bot_owner_name)[0]
        draw.text((cx_right - bw // 2, 482), bot_owner_name, font=fonts["sign_name"], fill=text_dark)
        brw = fonts["sign_role"].getbbox(bot_owner_role)[2] - fonts["sign_role"].getbbox(bot_owner_role)[0]
        draw.text((cx_right - brw // 2, 510), bot_owner_role, font=fonts["sign_role"], fill=text_gold)

        auth_str = f"ID OTENTIKASI RESMI: RTM-{target.id}-VERIFIED"
        a_bbox = fonts["auth_id"].getbbox(auth_str)
        aw = a_bbox[2] - a_bbox[0]
        draw.text(((W - aw) // 2, 572), auth_str, font=fonts["auth_id"], fill=(160, 145, 125, 255))

        buf = io.BytesIO()
        card.save(buf, format="PNG")
        buf.seek(0)
        return buf

    return await asyncio.to_thread(_render)
