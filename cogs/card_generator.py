import os
import io
import json
import math
import re
import struct
import unicodedata
import asyncio
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import aiohttp
import discord

REGISTRY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "member_registry.json")

def get_or_create_member_serial_id(guild: discord.Guild, member: discord.Member) -> int:
    """
    Mengambil atau menerbitkan Nomor Registrasi Anggota Permanen (Permanent Serial ID).
    Nomor ini abadi dan tidak akan berkurang/berubah meskipun ada anggota lain yang keluar dari server.
    """
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

FANCY_MAP = {
    'ᴀ':'A','ʙ':'B','ᴄ':'C','ᴅ':'D','ᴇ':'E','ғ':'F','ɢ':'G','ʜ':'H','ɪ':'I','ᴊ':'J','ᴋ':'K','ʟ':'L','ᴍ':'M',
    'ɴ':'N','ᴏ':'O','ᴘ':'P','ǫ':'Q','ʀ':'R','ꜱ':'S','ᴛ':'T','ᴜ':'U','ᴠ':'V','ᴡ':'W','x':'X','ʏ':'Y','ᴢ':'Z',
    '⁰':'0','¹':'1','²':'2','³':'3','⁴':'4','⁵':'5','⁶':'6','⁷':'7','⁸':'8','⁹':'9',
    '₀':'0','₁':'1','₂':'2','₃':'3','₄':'4','₅':'5','₆':'6','₇':'7','₈':'8','₉':'9',
    'ᵃ':'a','ᵇ':'b','ᶜ':'c','ᵈ':'d','ᵉ':'e','ᶠ':'f','ᵍ':'g','ʰ':'h','ⁱ':'i','ʲ':'j','ᵏ':'k','ˡ':'l','ᵐ':'m',
    'ⁿ':'n','ᵒ':'o','ᵖ':'p','ʳ':'r','ˢ':'s','ᵗ':'t','ᵘ':'u','ᵛ':'v','ʷ':'w','ˣ':'x','ʸ':'y','ᶻ':'z'
}

def normalize_fancy_text(text: str) -> str:
    if not text:
        return ""
    mapped = "".join(FANCY_MAP.get(ch, ch) for ch in str(text))
    return unicodedata.normalize("NFKC", mapped)

def is_safe_printable_char(ch: str) -> bool:
    """Filter karakter untuk mencegah box kosong (□) sembari mendukung huruf internasional."""
    code = ord(ch)
    if code in (0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0xFEFF, 0x00AD):
        return False
    if 0xFE00 <= code <= 0xFE0F or 0xE0000 <= code <= 0xE007F:
        return False
    if 32 <= code <= 591:
        return True
    if 0x0400 <= code <= 0x04FF:
        return True
    if 0x0600 <= code <= 0x06FF:
        return True
    if 0x2000 <= code <= 0x206F:
        return True
    if 0x2600 <= code <= 0x27BF:
        return True
    if 0x2B00 <= code <= 0x2BFF:
        return True
    if 0x3000 <= code <= 0x303F:
        return True
    if 0x3040 <= code <= 0x30FF:
        return True
    if 0x4E00 <= code <= 0x9FFF:
        return True
    if 0xAC00 <= code <= 0xD7AF:
        return True
    if 0xFF01 <= code <= 0xFFEE:
        return True
    return False

def clean_display_text(text: str, fallback: str = "MEMBER") -> str:
    """Bersihkan teks dari unicode tak kasat mata, plane 14 selectors, dan kontrol."""
    if not text:
        return fallback
    normalized = normalize_fancy_text(text)
    cleaned = "".join(ch for ch in normalized if is_safe_printable_char(ch)).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned if cleaned else fallback

_CMAP_CACHE = {}

def get_font_cmap(font_path: str) -> set:
    if not font_path or not os.path.isfile(font_path):
        return set()
    if font_path in _CMAP_CACHE:
        return _CMAP_CACHE[font_path]
    try:
        with open(font_path, "rb") as f:
            data = f.read()
        offset = struct.unpack(">I", data[12:16])[0] if data[:4] == b"ttcf" else 0
        num_tables = struct.unpack(">H", data[offset+4:offset+6])[0]
        cmap_offset = None
        for i in range(num_tables):
            entry = offset + 12 + i * 16
            if data[entry:entry+4] == b"cmap":
                cmap_offset = struct.unpack(">I", data[entry+8:entry+12])[0]
                break
        if not cmap_offset:
            _CMAP_CACHE[font_path] = set()
            return set()
        num_subtables = struct.unpack(">H", data[cmap_offset+2:cmap_offset+4])[0]
        chars = set()
        for i in range(num_subtables):
            sub_off = cmap_offset + struct.unpack(">I", data[cmap_offset+8+i*8:cmap_offset+12+i*8])[0]
            fmt = struct.unpack(">H", data[sub_off:sub_off+2])[0]
            if fmt == 4:
                seg_count = struct.unpack(">H", data[sub_off+6:sub_off+8])[0] // 2
                end_codes = struct.unpack(f">{seg_count}H", data[sub_off+14:sub_off+14+seg_count*2])
                start_codes = struct.unpack(f">{seg_count}H", data[sub_off+16+seg_count*2:sub_off+16+seg_count*4])
                for start, end in zip(start_codes, end_codes):
                    if start == 0xFFFF:
                        break
                    chars.update(range(start, end + 1))
            elif fmt == 12:
                n_groups = struct.unpack(">I", data[sub_off+12:sub_off+16])[0]
                for g in range(n_groups):
                    start_c, end_c, _ = struct.unpack(">III", data[sub_off+16+g*12:sub_off+28+g*12])
                    chars.update(range(start_c, end_c + 1))
        _CMAP_CACHE[font_path] = chars
        return chars
    except Exception:
        _CMAP_CACHE[font_path] = set()
        return set()

def draw_text_with_fallback(draw, xy, text, primary_font, fallback_font, primary_cmap, fallback_cmap, fill, align="left"):
    if not text:
        return 0.0
    valid_chars = []
    total_w = 0.0
    for ch in str(text):
        c = ord(ch)
        if c in primary_cmap:
            f = primary_font
        elif c in fallback_cmap:
            f = fallback_font
        elif ch in (" ", "\t"):
            f = primary_font
        else:
            continue
        ch_w = f.getlength(ch)
        valid_chars.append((ch, f, ch_w))
        total_w += ch_w

    x, y = xy
    if align == "center":
        cur_x = float(x) - total_w / 2.0
    elif align == "right":
        cur_x = float(x) - total_w
    else:
        cur_x = float(x)

    cur_y = float(y)
    for ch, f, ch_w in valid_chars:
        draw.text((cur_x, cur_y), ch, font=f, fill=fill)
        cur_x += ch_w

    return total_w

def get_card_fonts():
    """Load font tipografi elegan lintas platform (Windows & Linux Railway)."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    asset_fonts = os.path.join(base_dir, "assets", "fonts")
    
    search_dirs = [
        asset_fonts,
        os.path.join(base_dir, "data", "fonts"),
        r"C:\Windows\Fonts",
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/truetype/liberation",
        "/usr/share/fonts/opentype/noto",
        "/usr/share/fonts/truetype/noto",
        "/usr/share/fonts",
        "/usr/local/share/fonts"
    ]
    
    def find_font(filenames):
        for fn in filenames:
            for d in search_dirs:
                if not os.path.exists(d):
                    continue
                p = os.path.join(d, fn)
                if os.path.isfile(p):
                    return p
        return None

    f_serif_bold = find_font(["georgiab.ttf", "timesbd.ttf", "DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf"])
    f_serif_reg = find_font(["georgia.ttf", "times.ttf", "DejaVuSerif.ttf", "LiberationSerif-Regular.ttf"])
    f_sans_bold = find_font(["arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"])
    f_sans_reg = find_font(["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"])
    f_cjk_bold = find_font(["msyhbd.ttc", "NotoSansCJK-Bold.ttc", "NotoSansCJKsc-Bold.otf", "segoeuib.ttf", "malgunbd.ttf", "DejaVuSans-Bold.ttf"])
    f_cjk_reg = find_font(["msyh.ttc", "NotoSansCJK-Regular.ttc", "NotoSansCJKsc-Regular.otf", "segoeui.ttf", "malgun.ttf", "DejaVuSans.ttf"])

    cmap_serif_bold = get_font_cmap(f_serif_bold)
    cmap_serif_reg = get_font_cmap(f_serif_reg)
    cmap_sans_bold = get_font_cmap(f_sans_bold)
    cmap_sans_reg = get_font_cmap(f_sans_reg)
    cmap_cjk_bold = get_font_cmap(f_cjk_bold)
    cmap_cjk_reg = get_font_cmap(f_cjk_reg)

    def load_font(path, size):
        try:
            if path and os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:
            pass
        return ImageFont.load_default()

    return {
        "title": load_font(f_serif_bold, 28),
        "title_cjk": load_font(f_cjk_bold, 28),
        "subtitle": load_font(f_serif_bold, 15),
        "name_header": load_font(f_serif_bold, 28),
        "name_header_cjk": load_font(f_cjk_bold, 28),
        "badge": load_font(f_sans_bold, 17),
        "label": load_font(f_serif_bold, 16),
        "value": load_font(f_serif_bold, 17),
        "photo_label": load_font(f_sans_bold, 14),
        "photo_label_cjk": load_font(f_cjk_bold, 14),
        "quote": load_font(f_serif_reg, 16),
        "quote_cjk": load_font(f_cjk_reg, 16),
        "sign_name": load_font(f_serif_bold, 24),
        "sign_name_cjk": load_font(f_cjk_bold, 24),
        "sign_role": load_font(f_serif_reg, 15),
        "sign_role_cjk": load_font(f_cjk_reg, 15),
        "stamp_title": load_font(f_sans_bold, 13),
        "stamp_date": load_font(f_sans_bold, 16),
        "stamp_sub": load_font(f_sans_bold, 12),
        "auth_id": load_font(f_sans_reg, 12),
        "cmap_serif_bold": cmap_serif_bold,
        "cmap_serif_reg": cmap_serif_reg,
        "cmap_sans_bold": cmap_sans_bold,
        "cmap_sans_reg": cmap_sans_reg,
        "cmap_cjk_bold": cmap_cjk_bold,
        "cmap_cjk_reg": cmap_cjk_reg,
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
    """
    Menghasilkan file gambar Kartu Resmi Anggota (Sertifikat Eksklusif 1050x660 PNG)
    yang digunakan untuk command /rank dan banner pesan sambutan (welcome).
    """
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

        title_text = clean_display_text(custom_title) if custom_title else f"KARTU RESMI ANGGOTA • {safe_guild_name.upper()}"
        draw_text_with_fallback(draw, (58, 48), title_text, fonts["title"], fonts["title_cjk"], fonts["cmap_serif_bold"], fonts["cmap_cjk_bold"], fill=text_dark, align="left")
        draw.text((58, 86), sub_header_str, font=fonts["subtitle"], fill=text_gold)

        if rank_pos is not None:
            badge_tier = f"RANK: #{rank_pos} • CLASS-A" if rank_pos > 3 else "RANK: S-CLASS MASTER"
        else:
            badge_tier = "ANGGOTA RESMI VERIFIED"

        badge_w, badge_h = 220, 38
        badge_x, badge_y = W - 58 - badge_w, 54
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
        draw_text_with_fallback(draw, (135, 310), short_u, fonts["photo_label"], fonts["photo_label_cjk"], fonts["cmap_sans_bold"], fonts["cmap_cjk_bold"], fill=text_dark, align="center")

        user_header_text = f"{safe_user_name} • {highest_role_name}"
        if len(user_header_text) > 36:
            user_header_text = user_header_text[:33] + "..."
        draw_text_with_fallback(draw, (246, 154), user_header_text, fonts["name_header"], fonts["name_header_cjk"], fonts["cmap_serif_bold"], fonts["cmap_cjk_bold"], fill=text_dark, align="left")

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

        quote_text = f"Lisensi resmi ini diterbitkan secara sah atas keaktifan dan keanggotaan terverifikasi di server {safe_guild_name}."
        draw_text_with_fallback(draw, (W // 2, 445), quote_text, fonts["quote"], fonts["quote_cjk"], fonts["cmap_serif_reg"], fonts["cmap_cjk_reg"], fill=(122, 103, 80, 255), align="center")

        cx_left = 185
        draw_text_with_fallback(draw, (cx_left, 482), server_owner_name, fonts["sign_name"], fonts["sign_name_cjk"], fonts["cmap_serif_bold"], fonts["cmap_cjk_bold"], fill=text_dark, align="center")
        draw_text_with_fallback(draw, (cx_left, 510), server_owner_role, fonts["sign_role"], fonts["sign_role_cjk"], fonts["cmap_serif_reg"], fonts["cmap_cjk_reg"], fill=text_gold, align="center")

        draw_star(draw, W // 2 - 36, 498, r_outer=13, r_inner=6)
        draw_sakura(draw, W // 2, 498, r_petal=7)
        draw_star(draw, W // 2 + 36, 498, r_outer=13, r_inner=6)

        cx_right = 835
        draw_text_with_fallback(draw, (cx_right, 482), bot_owner_name, fonts["sign_name"], fonts["sign_name_cjk"], fonts["cmap_serif_bold"], fonts["cmap_cjk_bold"], fill=text_dark, align="center")
        draw_text_with_fallback(draw, (cx_right, 510), bot_owner_role, fonts["sign_role"], fonts["sign_role_cjk"], fonts["cmap_serif_reg"], fonts["cmap_cjk_reg"], fill=text_gold, align="center")

        auth_str = f"ID OTENTIKASI RESMI: RTM-{target.id}-VERIFIED"
        a_bbox = fonts["auth_id"].getbbox(auth_str)
        aw = a_bbox[2] - a_bbox[0]
        draw.text(((W - aw) // 2, 572), auth_str, font=fonts["auth_id"], fill=(160, 145, 125, 255))

        buf = io.BytesIO()
        card.save(buf, format="PNG")
        buf.seek(0)
        return buf

    return await asyncio.to_thread(_render)

def get_leaderboard_fonts():
    """Load font tipografi modern untuk banner visual leaderboard."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    search_dirs = [
        os.path.join(base_dir, "assets", "fonts"),
        os.path.join(base_dir, "data", "fonts"),
        r"C:\Windows\Fonts",
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/truetype/liberation",
        "/usr/share/fonts",
        "/usr/local/share/fonts"
    ]

    def find_font(filenames):
        for fn in filenames:
            for d in search_dirs:
                if not os.path.exists(d):
                    continue
                p = os.path.join(d, fn)
                if os.path.isfile(p):
                    return p
        return None

    f_bold = find_font(["msyhbd.ttc", "segoeuib.ttf", "arialbd.ttf", "NotoSansCJK-Bold.ttc", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"])
    f_reg = find_font(["msyh.ttc", "segoeui.ttf", "arial.ttf", "NotoSansCJK-Regular.ttc", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"])

    def load_font(path, size):
        try:
            if path and os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:
            pass
        return ImageFont.load_default()

    return {
        "title": load_font(f_bold, 24),
        "subtitle": load_font(f_reg, 13),
        "badge": load_font(f_bold, 11),
        "podium_num": load_font(f_bold, 44),
        "podium_rank": load_font(f_bold, 10),
        "podium_name": load_font(f_bold, 15),
        "podium_score": load_font(f_bold, 14),
        "podium_sub": load_font(f_reg, 11),
        "table_hdr": load_font(f_bold, 13),
        "row_rank": load_font(f_bold, 12),
        "row_name": load_font(f_bold, 13),
        "row_score": load_font(f_bold, 13),
        "row_sub": load_font(f_reg, 10),
        "name_1": load_font(f_bold, 17),
        "name_23": load_font(f_bold, 15),
        "score_1": load_font(f_bold, 15),
        "score_23": load_font(f_bold, 13),
        "sub": load_font(f_reg, 12),
        "footer": load_font(f_reg, 11),
    }

def draw_crown(draw, cx, cy, w=38, h=22, fill=(245, 158, 11, 255)):
    hw = w // 2
    pts = [
        (cx - hw, cy + h // 2),
        (cx - hw, cy - h // 4),
        (cx - hw // 2, cy + h // 4),
        (cx, cy - h // 2),
        (cx + hw // 2, cy + h // 4),
        (cx + hw, cy - h // 4),
        (cx + hw, cy + h // 2)
    ]
    draw.polygon(pts, fill=fill)
    for p in [(cx - hw, cy - h // 4), (cx, cy - h // 2), (cx + hw, cy - h // 4)]:
        draw.ellipse([(p[0] - 2, p[1] - 2), (p[0] + 2, p[1] + 2)], fill=(255, 240, 150, 255))

def draw_fallback_avatar(card, cx, cy, radius, initial, bg_color, fonts):
    diam = radius * 2
    av = Image.new("RGBA", (diam, diam), (0, 0, 0, 0))
    d = ImageDraw.Draw(av)
    d.ellipse([(0, 0), (diam - 1, diam - 1)], fill=bg_color)
    f = fonts["name_23"]
    bb = f.getbbox(initial)
    tw = bb[2] - bb[0]
    th = bb[3] - bb[1]
    d.text(((diam - tw) // 2, (diam - th) // 2 - 2), initial, font=f, fill=(255, 255, 255, 255))
    mask = Image.new("L", (diam, diam), 0)
    ImageDraw.Draw(mask).ellipse([(0, 0), (diam - 1, diam - 1)], fill=255)
    card.paste(av, (cx - radius, cy - radius), mask)

async def generate_top3_podium_card(
    guild: discord.Guild,
    top_users_data: list,
    title_tag: str = "TOP 3 LEADERBOARD",
    subtitle_text: str = None,
    bot_name: str = None,
    footer_system: str = "Sistem Leveling & Aktivitas Server"
) -> io.BytesIO:
    """
    Menghasilkan gambar visual leaderboard HD 3 Besar (1000x580 PNG)
    dengan 3-tier podium emas, perak, dan perunggu simetris tanpa tabel kosong.
    """
    safe_guild_name = clean_display_text(guild.name if guild else "SERVER DISCORD", fallback="SERVER DISCORD")
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M WIB")

    async def _get_avatar(m, sz):
        if not m or not getattr(m, "display_avatar", None):
            return None
        try:
            return await asyncio.wait_for(m.display_avatar.replace(size=sz, format="png").read(), timeout=4.0)
        except Exception:
            return None

    avatar_tasks = []
    for idx, item in enumerate(top_users_data[:3]):
        m_obj = item.get("member") or item.get("user")
        if not m_obj and guild and item.get("name"):
            target_name = item.get("name", "").strip().lower()
            if target_name:
                for gm in guild.members:
                    if gm.display_name.lower() == target_name or gm.name.lower() == target_name:
                        m_obj = gm
                        break
        avatar_tasks.append(_get_avatar(m_obj, 128))

    avatars = await asyncio.gather(*avatar_tasks, return_exceptions=True)

    enriched_users = []
    for idx, item in enumerate(top_users_data[:3]):
        av_bytes = avatars[idx] if idx < len(avatars) and isinstance(avatars[idx], (bytes, bytearray)) else None
        m_obj = item.get("member") or item.get("user")
        fallback_name = getattr(m_obj, "display_name", f"Member {idx + 1}")
        enriched_users.append({
            "name": item.get("name", fallback_name),
            "score_str": item.get("score_str", "+0 EXP"),
            "sub_str": item.get("sub_str", "Lvl 0"),
            "rank": item.get("rank", idx + 1),
            "avatar_bytes": av_bytes
        })

    def _render() -> io.BytesIO:
        W, H = 1000, 580
        card = Image.new("RGBA", (W, H), (11, 15, 25, 255))
        draw = ImageDraw.Draw(card)
        fonts = get_leaderboard_fonts()

        for y in range(H):
            r = int(11 + (y / H) * (28 - 11))
            g = int(15 + (y / H) * (38 - 15))
            b = int(25 + (y / H) * (56 - 25))
            draw.line([(0, y), (W, y)], fill=(r, g, b, 255))

        draw.rounded_rectangle([(16, 16), (W - 16, H - 16)], radius=16, outline=(51, 65, 85, 200), width=1)
        draw.rounded_rectangle([(20, 20), (W - 20, H - 20)], radius=14, outline=(255, 255, 255, 14), width=1)

        tag_display = clean_display_text(title_tag, fallback="TOP 3").upper()
        tb = fonts["badge"].getbbox(tag_display)
        tb_w = tb[2] - tb[0]
        draw.rounded_rectangle([(42, 32), (42 + tb_w + 18, 32 + 24)], radius=6, fill=(30, 58, 138, 220), outline=(59, 130, 246, 255), width=1)
        draw.text((51, 37), tag_display, font=fonts["badge"], fill=(191, 219, 254, 255))

        draw.text((42, 62), safe_guild_name, font=fonts["title"], fill=(255, 255, 255, 255))
        sub_desc = subtitle_text or "Top 3 Anggota Teratas Berdasarkan Aktivitas dan Perolehan Server"
        draw.text((42, 96), clean_display_text(sub_desc, fallback=sub_desc), font=fonts["subtitle"], fill=(148, 163, 184, 255))
        draw.line([(42, 122), (W - 42, 122)], fill=(51, 65, 85, 160), width=1)

        podium_cfg = [
            {
                "rank": 2, "idx": 1, "cx": 230, "r": 42,
                "ped_box": [(140, 420), (320, 505)], "ped_top": [(140, 420), (320, 425)],
                "hi_color": (203, 213, 225, 255), "num_color": (203, 213, 225, 110),
                "score_color": (226, 232, 240, 255), "pill_text": "2ND PLACE",
                "name_font": fonts["name_23"], "score_font": fonts["score_23"],
                "av_y": 275, "name_y": 332, "score_y": 358, "sub_y": 382
            },
            {
                "rank": 1, "idx": 0, "cx": 500, "r": 50,
                "ped_box": [(395, 370), (605, 505)], "ped_top": [(395, 370), (605, 376)],
                "hi_color": (234, 179, 8, 255), "num_color": (234, 179, 8, 130),
                "score_color": (250, 204, 21, 255), "pill_text": "1ST PLACE",
                "name_font": fonts["name_1"], "score_font": fonts["score_1"],
                "av_y": 218, "name_y": 282, "score_y": 308, "sub_y": 332
            },
            {
                "rank": 3, "idx": 2, "cx": 770, "r": 42,
                "ped_box": [(680, 445), (860, 505)], "ped_top": [(680, 445), (860, 450)],
                "hi_color": (249, 115, 22, 255), "num_color": (249, 115, 22, 110),
                "score_color": (253, 186, 116, 255), "pill_text": "3RD PLACE",
                "name_font": fonts["name_23"], "score_font": fonts["score_23"],
                "av_y": 300, "name_y": 358, "score_y": 384, "sub_y": 408
            }
        ]

        for cfg in podium_cfg:
            draw.rounded_rectangle(cfg["ped_box"], radius=10, fill=(30, 41, 59, 230), outline=(51, 65, 85, 200), width=1)
            draw.rounded_rectangle(cfg["ped_top"], radius=3, fill=cfg["hi_color"])

            num_str = str(cfg["rank"])
            nb = fonts["podium_num"].getbbox(num_str)
            nw = nb[2] - nb[0]
            num_y = (cfg["ped_box"][0][1] + cfg["ped_box"][1][1]) // 2 - 12
            draw.text((cfg["cx"] - nw // 2, num_y), num_str, font=fonts["podium_num"], fill=cfg["num_color"])

            pt = cfg["pill_text"]
            pb = fonts["podium_rank"].getbbox(pt)
            pw = pb[2] - pb[0]
            pill_y = cfg["ped_box"][0][1] + 10
            draw.rounded_rectangle([(cfg["cx"] - pw // 2 - 8, pill_y), (cfg["cx"] + pw // 2 + 8, pill_y + 18)], radius=5, fill=(15, 23, 42, 220), outline=cfg["hi_color"], width=1)
            draw.text((cfg["cx"] - pw // 2, pill_y + 3), pt, font=fonts["podium_rank"], fill=cfg["hi_color"])

            cx = cfg["cx"]
            ay = cfg["av_y"]
            r = cfg["r"]

            if cfg["idx"] < len(enriched_users):
                u = enriched_users[cfg["idx"]]
                av_b = u.get("avatar_bytes")
                if av_b:
                    try:
                        av_img = Image.open(io.BytesIO(av_b)).convert("RGBA").resize((r * 2, r * 2), Image.Resampling.LANCZOS)
                        mask = Image.new("L", (r * 2, r * 2), 0)
                        ImageDraw.Draw(mask).ellipse([(0, 0), (r * 2 - 1, r * 2 - 1)], fill=255)
                        card.paste(av_img, (cx - r, ay - r), mask)
                    except Exception:
                        init_char = u["name"][0].upper() if u["name"] else "?"
                        draw_fallback_avatar(card, cx, ay, r, init_char, (51, 65, 85, 255), fonts)
                else:
                    init_char = u["name"][0].upper() if u["name"] else "?"
                    draw_fallback_avatar(card, cx, ay, r, init_char, (51, 65, 85, 255), fonts)

                draw.ellipse([(cx - r - 2, ay - r - 2), (cx + r + 2, ay + r + 2)], outline=cfg["hi_color"], width=3)

                if cfg["rank"] == 1:
                    draw_crown(draw, cx, ay - r - 16, w=38, h=22)

                uname = clean_display_text(u["name"], fallback=f"Juara {cfg['rank']}")
                if len(uname) > 15:
                    uname = uname[:13] + ".."
                ub = cfg["name_font"].getbbox(uname)
                uw = ub[2] - ub[0]
                draw.text((cx - uw // 2, cfg["name_y"]), uname, font=cfg["name_font"], fill=(255, 255, 255, 255))

                sc = clean_display_text(u["score_str"], fallback="+0")
                sb = cfg["score_font"].getbbox(sc)
                sw = sb[2] - sb[0]
                draw.text((cx - sw // 2, cfg["score_y"]), sc, font=cfg["score_font"], fill=cfg["score_color"])

                sub = clean_display_text(u["sub_str"], fallback="-")
                sub_b = fonts["sub"].getbbox(sub)
                sub_w = sub_b[2] - sub_b[0]
                draw.text((cx - sub_w // 2, cfg["sub_y"]), sub, font=fonts["sub"], fill=(148, 163, 184, 255))
            else:
                draw_fallback_avatar(card, cx, ay, r, "-", (30, 41, 59, 255), fonts)
                draw.ellipse([(cx - r - 2, ay - r - 2), (cx + r + 2, ay + r + 2)], outline=(51, 65, 85, 200), width=1)
                dash = "-"
                db = fonts["sub"].getbbox(dash)
                draw.text((cx - (db[2] - db[0]) // 2, ay - 8), dash, font=fonts["sub"], fill=(100, 116, 139, 255))
                empty_lbl = "Belum Terisi"
                eb = fonts["sub"].getbbox(empty_lbl)
                ew = eb[2] - eb[0]
                draw.text((cx - ew // 2, cfg["name_y"]), empty_lbl, font=fonts["sub"], fill=(100, 116, 139, 255))

        draw.line([(42, 532), (W - 42, 532)], fill=(51, 65, 85, 160), width=1)
        resolved_bot_name = bot_name or (guild.me.display_name if guild and getattr(guild, "me", None) else "ハキムラーマン")
        footer_bot_str = f"{clean_display_text(resolved_bot_name, fallback='ハキムラーマン')} • {footer_system}"
        draw.text((42, 545), footer_bot_str, font=fonts["footer"], fill=(100, 116, 139, 255))
        ts_text = f"Diperbarui: {now_str}"
        tb = fonts["footer"].getbbox(ts_text)
        tw = tb[2] - tb[0]
        draw.text((W - 42 - tw, 545), ts_text, font=fonts["footer"], fill=(100, 116, 139, 255))

        buf = io.BytesIO()
        card.save(buf, format="PNG")
        buf.seek(0)
        return buf

    return await asyncio.to_thread(_render)

async def generate_weekly_leaderboard_card(
    guild: discord.Guild,
    top_users_data: list,
    title_tag: str = "WEEKLY LEADERBOARD",
    subtitle_text: str = None,
    bot_name: str = None,
    footer_system: str = "Sistem Leveling & Aktivitas Server"
) -> io.BytesIO:
    safe_guild_name = clean_display_text(guild.name if guild else "SERVER DISCORD", fallback="SERVER DISCORD")
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M WIB")

    async def _get_avatar(m, sz):
        if not m or not getattr(m, "display_avatar", None):
            return None
        try:
            return await asyncio.wait_for(m.display_avatar.replace(size=sz, format="png").read(), timeout=4.0)
        except Exception:
            return None

    avatar_tasks = []
    for idx, item in enumerate(top_users_data[:10]):
        sz = 128 if idx < 3 else 64
        m_obj = item.get("member") or item.get("user")
        if not m_obj and guild and item.get("name"):
            target_name = item.get("name", "").strip().lower()
            if target_name:
                for gm in guild.members:
                    if gm.display_name.lower() == target_name or gm.name.lower() == target_name:
                        m_obj = gm
                        break
        avatar_tasks.append(_get_avatar(m_obj, sz))

    avatars = await asyncio.gather(*avatar_tasks, return_exceptions=True)

    enriched_users = []
    for idx, item in enumerate(top_users_data[:10]):
        av_bytes = avatars[idx] if idx < len(avatars) and isinstance(avatars[idx], (bytes, bytearray)) else None
        m_obj = item.get("member") or item.get("user")
        fallback_name = getattr(m_obj, "display_name", f"Member {idx + 1}")
        enriched_users.append({
            "name": item.get("name", fallback_name),
            "score_str": item.get("score_str", "+0 EXP"),
            "sub_str": item.get("sub_str", "Voice: 0m"),
            "rank": item.get("rank", idx + 1),
            "avatar_bytes": av_bytes
        })

    def _render() -> io.BytesIO:
        W, H = 1200, 675
        card = Image.new("RGBA", (W, H), (11, 15, 25, 255))
        draw = ImageDraw.Draw(card)
        fonts = get_leaderboard_fonts()

        for y in range(H):
            r = int(11 + (y / H) * (30 - 11))
            g = int(15 + (y / H) * (41 - 15))
            b = int(25 + (y / H) * (59 - 25))
            draw.line([(0, y), (W, y)], fill=(r, g, b, 255))

        draw.rounded_rectangle([(18, 18), (W - 18, H - 18)], radius=16, outline=(51, 65, 85, 200), width=1)
        draw.rounded_rectangle([(22, 22), (W - 22, H - 22)], radius=14, outline=(255, 255, 255, 15), width=1)

        tag_display = clean_display_text(title_tag, fallback="LEADERBOARD").upper()
        tb = fonts["badge"].getbbox(tag_display)
        tb_w = tb[2] - tb[0]
        draw.rounded_rectangle([(45, 36), (45 + tb_w + 18, 36 + 24)], radius=6, fill=(30, 58, 138, 200), outline=(59, 130, 246, 255), width=1)
        draw.text((54, 41), tag_display, font=fonts["badge"], fill=(191, 219, 254, 255))

        draw.text((45, 66), safe_guild_name, font=fonts["title"], fill=(255, 255, 255, 255))
        sub_desc = subtitle_text or "Top 10 Perolehan EXP & Aktivitas Mingguan Server • Reset Otomatis Setiap Senin 00:00 UTC"
        draw.text((45, 100), clean_display_text(sub_desc, fallback=sub_desc), font=fonts["subtitle"], fill=(148, 163, 184, 255))
        draw.line([(45, 126), (W - 45, 126)], fill=(51, 65, 85, 160), width=1)

        podium_cfg = [
            {
                "rank": 2, "idx": 1, "cx": 135, "r": 38,
                "ped_box": [(70, 435), (200, 585)], "ped_top": [(70, 435), (200, 441)],
                "ped_color": (30, 41, 59, 230), "hi_color": (203, 213, 225, 255),
                "ring_color": (203, 213, 225, 255), "num_color": (203, 213, 225, 120),
                "score_color": (226, 232, 240, 255), "pill_text": "2ND PLACE",
                "av_y": 315, "name_y": 365, "score_y": 388, "sub_y": 409
            },
            {
                "rank": 1, "idx": 0, "cx": 315, "r": 46,
                "ped_box": [(235, 385), (395, 585)], "ped_top": [(235, 385), (395, 391)],
                "ped_color": (30, 41, 59, 230), "hi_color": (234, 179, 8, 255),
                "ring_color": (234, 179, 8, 255), "num_color": (234, 179, 8, 140),
                "score_color": (250, 204, 21, 255), "pill_text": "1ST PLACE",
                "av_y": 245, "name_y": 305, "score_y": 330, "sub_y": 353
            },
            {
                "rank": 3, "idx": 2, "cx": 495, "r": 38,
                "ped_box": [(430, 470), (560, 585)], "ped_top": [(430, 470), (560, 476)],
                "ped_color": (30, 41, 59, 230), "hi_color": (249, 115, 22, 255),
                "ring_color": (249, 115, 22, 255), "num_color": (249, 115, 22, 120),
                "score_color": (253, 186, 116, 255), "pill_text": "3RD PLACE",
                "av_y": 355, "name_y": 405, "score_y": 428, "sub_y": 449
            }
        ]

        for cfg in podium_cfg:
            draw.rounded_rectangle(cfg["ped_box"], radius=10, fill=cfg["ped_color"], outline=(51, 65, 85, 200), width=1)
            draw.rounded_rectangle(cfg["ped_top"], radius=3, fill=cfg["hi_color"])

            num_str = str(cfg["rank"])
            nb = fonts["podium_num"].getbbox(num_str)
            nw = nb[2] - nb[0]
            num_y = (cfg["ped_box"][0][1] + cfg["ped_box"][1][1]) // 2 - 10
            draw.text((cfg["cx"] - nw // 2, num_y), num_str, font=fonts["podium_num"], fill=cfg["num_color"])

            pt = cfg["pill_text"]
            pb = fonts["podium_rank"].getbbox(pt)
            pw = pb[2] - pb[0]
            draw.rounded_rectangle([(cfg["cx"] - pw // 2 - 8, cfg["ped_box"][0][1] + 10), (cfg["cx"] + pw // 2 + 8, cfg["ped_box"][0][1] + 28)], radius=5, fill=(15, 23, 42, 200), outline=cfg["hi_color"], width=1)
            draw.text((cfg["cx"] - pw // 2, cfg["ped_box"][0][1] + 13), pt, font=fonts["podium_rank"], fill=cfg["hi_color"])

            cx = cfg["cx"]
            ay = cfg["av_y"]
            r = cfg["r"]

            if cfg["idx"] < len(enriched_users):
                u = enriched_users[cfg["idx"]]
                av_b = u.get("avatar_bytes")
                if av_b:
                    try:
                        av_img = Image.open(io.BytesIO(av_b)).convert("RGBA").resize((r * 2, r * 2), Image.Resampling.LANCZOS)
                        mask = Image.new("L", (r * 2, r * 2), 0)
                        ImageDraw.Draw(mask).ellipse([(0, 0), (r * 2 - 1, r * 2 - 1)], fill=255)
                        card.paste(av_img, (cx - r, ay - r), mask)
                    except Exception:
                        init_char = u["name"][0].upper() if u["name"] else "?"
                        draw_fallback_avatar(card, cx, ay, r, init_char, (51, 65, 85, 255), fonts)
                else:
                    init_char = u["name"][0].upper() if u["name"] else "?"
                    draw_fallback_avatar(card, cx, ay, r, init_char, (51, 65, 85, 255), fonts)

                draw.ellipse([(cx - r - 2, ay - r - 2), (cx + r + 2, ay + r + 2)], outline=cfg["ring_color"], width=3)

                if cfg["rank"] == 1:
                    draw_crown(draw, cx, ay - r - 16, w=34, h=20)

                uname = clean_display_text(u["name"], fallback=f"Rank {cfg['rank']}")
                if len(uname) > 14:
                    uname = uname[:12] + ".."
                ub = fonts["podium_name"].getbbox(uname)
                uw = ub[2] - ub[0]
                draw.text((cx - uw // 2, cfg["name_y"]), uname, font=fonts["podium_name"], fill=(255, 255, 255, 255))

                sc = clean_display_text(u["score_str"], fallback="+0")
                sb = fonts["podium_score"].getbbox(sc)
                sw = sb[2] - sb[0]
                draw.text((cx - sw // 2, cfg["score_y"]), sc, font=fonts["podium_score"], fill=cfg["score_color"])

                sub = clean_display_text(u["sub_str"], fallback="-")
                sub_b = fonts["podium_sub"].getbbox(sub)
                sub_w = sub_b[2] - sub_b[0]
                draw.text((cx - sub_w // 2, cfg["sub_y"]), sub, font=fonts["podium_sub"], fill=(148, 163, 184, 255))
            else:
                draw_fallback_avatar(card, cx, ay, r, "-", (30, 41, 59, 255), fonts)
                draw.ellipse([(cx - r - 2, ay - r - 2), (cx + r + 2, ay + r + 2)], outline=(51, 65, 85, 200), width=1)
                empty_lbl = "Belum Terisi"
                eb = fonts["podium_sub"].getbbox(empty_lbl)
                ew = eb[2] - eb[0]
                draw.text((cx - ew // 2, cfg["name_y"]), empty_lbl, font=fonts["podium_sub"], fill=(100, 116, 139, 255))

        draw.text((615, 142), "PERINGKAT #4 - #10", font=fonts["table_hdr"], fill=(255, 255, 255, 255))
        draw.text((1060, 144), "PEROLEHAN EXP", font=fonts["podium_rank"], fill=(148, 163, 184, 255))

        start_y = 172
        row_h = 49
        gap = 9
        for i in range(3, 10):
            row_idx = i - 3
            ry = start_y + row_idx * (row_h + gap)
            draw.rounded_rectangle([(615, ry), (1155, ry + row_h)], radius=8, fill=(24, 33, 47, 180), outline=(51, 65, 85, 140), width=1)

            rank_str = f"#{i + 1}"
            rb = fonts["row_rank"].getbbox(rank_str)
            rw = rb[2] - rb[0]
            draw.rounded_rectangle([(627, ry + 10), (665, ry + 38)], radius=6, fill=(15, 23, 42, 220), outline=(51, 65, 85, 180), width=1)
            draw.text((646 - rw // 2, ry + 16), rank_str, font=fonts["row_rank"], fill=(203, 213, 225, 255))

            if i < len(enriched_users):
                u = enriched_users[i]
                av_b = u.get("avatar_bytes")
                if av_b:
                    try:
                        av_img = Image.open(io.BytesIO(av_b)).convert("RGBA").resize((32, 32), Image.Resampling.LANCZOS)
                        mask = Image.new("L", (32, 32), 0)
                        ImageDraw.Draw(mask).ellipse([(0, 0), (31, 31)], fill=255)
                        card.paste(av_img, (680, ry + 8), mask)
                    except Exception:
                        init_char = u["name"][0].upper() if u["name"] else "?"
                        draw_fallback_avatar(card, 696, ry + 24, 16, init_char, (71, 85, 105, 255), fonts)
                else:
                    init_char = u["name"][0].upper() if u["name"] else "?"
                    draw_fallback_avatar(card, 696, ry + 24, 16, init_char, (71, 85, 105, 255), fonts)

                draw.ellipse([(680, ry + 8), (712, ry + 40)], outline=(100, 116, 139, 200), width=1)

                uname = clean_display_text(u["name"], fallback=f"Rank {i + 1}")
                if len(uname) > 18:
                    uname = uname[:16] + ".."
                draw.text((724, ry + 16), uname, font=fonts["row_name"], fill=(255, 255, 255, 255))

                sc = clean_display_text(u["score_str"], fallback="+0")
                sb = fonts["row_score"].getbbox(sc)
                sw = sb[2] - sb[0]
                draw.text((1140 - sw, ry + 9), sc, font=fonts["row_score"], fill=(56, 189, 248, 255))

                sub = clean_display_text(u["sub_str"], fallback="-")
                sub_b = fonts["row_sub"].getbbox(sub)
                sub_w = sub_b[2] - sub_b[0]
                draw.text((1140 - sub_w, ry + 28), sub, font=fonts["row_sub"], fill=(148, 163, 184, 255))
            else:
                draw.text((724, ry + 16), "-", font=fonts["row_sub"], fill=(100, 116, 139, 255))

        draw.line([(45, 622), (W - 45, 622)], fill=(51, 65, 85, 160), width=1)
        resolved_bot_name = bot_name or (guild.me.display_name if guild and getattr(guild, "me", None) else "ハキムラーマン")
        footer_bot_str = f"{clean_display_text(resolved_bot_name, fallback='ハキムラーマン')} • {footer_system}"
        draw.text((45, 636), footer_bot_str, font=fonts["footer"], fill=(100, 116, 139, 255))
        ts_text = f"Diperbarui: {now_str}"
        tb = fonts["footer"].getbbox(ts_text)
        tw = tb[2] - tb[0]
        draw.text((W - 45 - tw, 636), ts_text, font=fonts["footer"], fill=(100, 116, 139, 255))

        buf = io.BytesIO()
        card.save(buf, format="PNG")
        buf.seek(0)
        return buf

    return await asyncio.to_thread(_render)


def get_booster_card_fonts():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    asset_fonts = os.path.join(base_dir, "assets", "fonts")
    search_dirs = [
        asset_fonts,
        os.path.join(base_dir, "data", "fonts"),
        r"C:\Windows\Fonts",
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/truetype/liberation",
        "/usr/share/fonts/opentype/noto",
        "/usr/share/fonts/truetype/noto",
        "/usr/share/fonts",
        "/usr/local/share/fonts"
    ]

    def find_font(filenames):
        for fn in filenames:
            for d in search_dirs:
                if not os.path.exists(d):
                    continue
                p = os.path.join(d, fn)
                if os.path.isfile(p):
                    return p
        return None

    f_sans_bold = find_font(["arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"])
    f_sans_reg = find_font(["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"])
    f_cjk_bold = find_font(["msyhbd.ttc", "NotoSansCJK-Bold.ttc", "NotoSansCJKsc-Bold.otf", "segoeuib.ttf", "malgunbd.ttf", "DejaVuSans-Bold.ttf"])
    f_cjk_reg = find_font(["msyh.ttc", "NotoSansCJK-Regular.ttc", "NotoSansCJKsc-Regular.otf", "segoeui.ttf", "malgun.ttf", "DejaVuSans.ttf"])

    cmap_sans_bold = get_font_cmap(f_sans_bold)
    cmap_sans_reg = get_font_cmap(f_sans_reg)
    cmap_cjk_bold = get_font_cmap(f_cjk_bold)
    cmap_cjk_reg = get_font_cmap(f_cjk_reg)

    def load_font(path, size):
        try:
            if path and os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:
            pass
        return ImageFont.load_default()

    return {
        "header_title": load_font(f_sans_bold, 20),
        "header_sub": load_font(f_sans_bold, 13),
        "name": load_font(f_sans_bold, 36),
        "name_cjk": load_font(f_cjk_bold, 36),
        "tag": load_font(f_sans_reg, 19),
        "tag_cjk": load_font(f_cjk_reg, 19),
        "badge": load_font(f_sans_bold, 14),
        "box_label": load_font(f_sans_bold, 13),
        "box_val": load_font(f_sans_bold, 21),
        "box_val_cjk": load_font(f_cjk_bold, 21),
        "bar_text": load_font(f_sans_bold, 13),
        "bar_text_cjk": load_font(f_cjk_bold, 13),
        "footer": load_font(f_sans_reg, 14),
        "footer_cjk": load_font(f_cjk_reg, 14),
        "name_23": load_font(f_sans_bold, 54),
        "cmap_sans_bold": cmap_sans_bold,
        "cmap_sans_reg": cmap_sans_reg,
        "cmap_cjk_bold": cmap_cjk_bold,
        "cmap_cjk_reg": cmap_cjk_reg,
    }


async def generate_booster_card(
    bot: discord.Client,
    guild: discord.Guild,
    member: discord.Member,
    boost_count: int = 1,
    tier: str = "Tier 1",
    custom_bg_url: str = None
) -> io.BytesIO:
    avatar_bytes = None
    if member:
        try:
            avatar_bytes = await member.display_avatar.replace(size=256, format="png").read()
        except Exception:
            pass

    custom_bg_bytes = None
    if custom_bg_url and str(custom_bg_url).startswith("http"):
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as sess:
                async with sess.get(custom_bg_url) as r:
                    if r.status == 200:
                        custom_bg_bytes = await r.read()
        except Exception:
            pass

    safe_name = clean_display_text(member.display_name if member else "Booster")
    safe_tag = clean_display_text(member.name if member else "booster")
    safe_guild = clean_display_text(guild.name if guild else "Server")

    def _render() -> io.BytesIO:
        W, H = 1050, 580
        fonts = get_booster_card_fonts()

        if custom_bg_bytes:
            try:
                raw_bg = Image.open(io.BytesIO(custom_bg_bytes)).convert("RGBA")
                bg_w, bg_h = raw_bg.size
                ratio = max(W / bg_w, H / bg_h)
                new_size = (int(bg_w * ratio), int(bg_h * ratio))
                raw_bg = raw_bg.resize(new_size, Image.Resampling.LANCZOS)
                crop_x = (new_size[0] - W) // 2
                crop_y = (new_size[1] - H) // 2
                card = raw_bg.crop((crop_x, crop_y, crop_x + W, crop_y + H))
                dark_tint = Image.new("RGBA", (W, H), (10, 6, 20, 215))
                card = Image.alpha_composite(card, dark_tint)
            except Exception:
                card = Image.new("RGBA", (W, H), (11, 7, 22, 255))
        else:
            card = Image.new("RGBA", (W, H), (11, 7, 22, 255))
            draw_bg = ImageDraw.Draw(card)
            for y in range(H):
                r = int(10 + (26 - 10) * (y / H))
                g = int(6 + (12 - 6) * (y / H))
                b = int(20 + (46 - 20) * (y / H))
                draw_bg.line([(0, y), (W, y)], fill=(r, g, b, 255))

        draw = ImageDraw.Draw(card)

        for p_idx, (sx, sy) in enumerate([
            (75, 80), (140, 510), (280, 75), (420, 95), (600, 70), (780, 110),
            (950, 85), (980, 480), (480, 530), (720, 520), (880, 390)
        ]):
            r_out = 4 if p_idx % 2 == 0 else 3
            draw_star(draw, sx, sy, r_outer=r_out, r_inner=1, fill=(244, 127, 255, 120), outline=(0, 240, 255, 100))

        draw.rounded_rectangle([(14, 14), (W - 14, H - 14)], radius=26, outline=(244, 127, 255, 230), width=3)
        draw.rounded_rectangle([(20, 20), (W - 20, H - 20)], radius=22, outline=(0, 240, 255, 80), width=1)

        draw.rounded_rectangle([(45, 42), (325, 78)], radius=18, fill=(35, 16, 58, 220), outline=(244, 127, 255, 120), width=1)
        draw_star(draw, 64, 60, r_outer=6, r_inner=3, fill=(244, 127, 255, 255), outline=(255, 255, 255, 200))
        draw.text((78, 51), "DISCORD NITRO BOOSTER", font=fonts["header_sub"], fill=(244, 127, 255, 255))

        draw.text((W - 310, 50), "OFFICIAL SERVER BOOSTER", font=fonts["header_sub"], fill=(180, 170, 215, 255))
        draw.line([(45, 96), (W - 45, 96)], fill=(244, 127, 255, 60), width=1)

        cx, cy, radius = 185, 290, 90
        draw.ellipse([(cx - radius - 12, cy - radius - 12), (cx + radius + 12, cy + radius + 12)], outline=(0, 240, 255, 120), width=2)
        draw.ellipse([(cx - radius - 5, cy - radius - 5), (cx + radius + 5, cy + radius + 5)], outline=(244, 127, 255, 255), width=4)

        if avatar_bytes:
            try:
                av_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((radius * 2, radius * 2), Image.Resampling.LANCZOS)
                mask = Image.new("L", (radius * 2, radius * 2), 0)
                ImageDraw.Draw(mask).ellipse([(0, 0), (radius * 2 - 1, radius * 2 - 1)], fill=255)
                card.paste(av_img, (cx - radius, cy - radius), mask)
            except Exception:
                draw_fallback_avatar(card, cx, cy, radius, safe_name[0].upper() if safe_name else "B", (75, 25, 110, 255), fonts)
        else:
            draw_fallback_avatar(card, cx, cy, radius, safe_name[0].upper() if safe_name else "B", (75, 25, 110, 255), fonts)

        draw.rounded_rectangle([(85, 415), (285, 448)], radius=16, fill=(244, 127, 255, 235), outline=(255, 255, 255, 180), width=1)
        draw_star(draw, 105, 431, r_outer=5, r_inner=2, fill=(22, 10, 38, 255), outline=(22, 10, 38, 255))
        draw_star(draw, 265, 431, r_outer=5, r_inner=2, fill=(22, 10, 38, 255), outline=(22, 10, 38, 255))
        draw.text((118, 423), "SERVER BOOSTER", font=fonts["badge"], fill=(22, 10, 38, 255))

        tx = 335
        display_name_clipped = safe_name[:22] + ".." if len(safe_name) > 24 else safe_name
        draw_text_with_fallback(
            draw, (tx, 135), display_name_clipped,
            fonts["name"], fonts["name_cjk"],
            fonts["cmap_sans_bold"], fonts["cmap_cjk_bold"],
            (255, 255, 255, 255)
        )

        tag_clipped = f"@{safe_tag[:26]}"
        draw_text_with_fallback(
            draw, (tx, 185), tag_clipped,
            fonts["tag"], fonts["tag_cjk"],
            fonts["cmap_sans_reg"], fonts["cmap_cjk_reg"],
            (195, 185, 225, 255)
        )

        draw.line([(tx, 225), (W - 55, 225)], fill=(244, 127, 255, 80), width=1)

        box_top = 245
        box_bot = 380
        draw.rounded_rectangle([(tx, box_top), (W - 55, box_bot)], radius=18, fill=(24, 14, 46, 200), outline=(244, 127, 255, 90), width=1)
        mid_x = tx + (W - 55 - tx) // 2
        draw.line([(mid_x, box_top + 16), (mid_x, box_bot - 16)], fill=(244, 127, 255, 60), width=1)

        draw.text((tx + 24, box_top + 20), "STATUS SERVER", font=fonts["box_label"], fill=(185, 175, 220, 255))
        g_name_clipped = safe_guild[:20] + ".." if len(safe_guild) > 22 else safe_guild
        draw_text_with_fallback(
            draw, (tx + 24, box_top + 48), g_name_clipped,
            fonts["box_val"], fonts["box_val_cjk"],
            fonts["cmap_sans_bold"], fonts["cmap_cjk_bold"],
            (255, 255, 255, 255)
        )
        draw.text((tx + 24, box_top + 84), "Komunitas Resmi", font=fonts["header_sub"], fill=(0, 240, 255, 220))

        draw.text((mid_x + 24, box_top + 20), "LEVEL TIER SERVER", font=fonts["box_label"], fill=(185, 175, 220, 255))
        tier_val_str = f"{tier} • {boost_count} Boosts"
        draw_text_with_fallback(
            draw, (mid_x + 24, box_top + 48), tier_val_str,
            fonts["box_val"], fonts["box_val_cjk"],
            fonts["cmap_sans_bold"], fonts["cmap_cjk_bold"],
            (255, 215, 0, 255)
        )
        draw.text((mid_x + 24, box_top + 84), "Status Keaktifan: Maksimal", font=fonts["header_sub"], fill=(244, 127, 255, 220))

        if boost_count < 2:
            target_needed = 2
            target_tier_str = "Tier 1"
            pct = max(0.08, min(1.0, boost_count / 2))
            rem_str = f"{2 - boost_count} Boosts lagi menuju {target_tier_str}"
        elif boost_count < 7:
            target_needed = 7
            target_tier_str = "Tier 2"
            pct = max(0.08, min(1.0, (boost_count - 2) / (7 - 2)))
            rem_str = f"{7 - boost_count} Boosts lagi menuju {target_tier_str}"
        elif boost_count < 14:
            target_needed = 14
            target_tier_str = "Tier 3"
            pct = max(0.08, min(1.0, (boost_count - 7) / (14 - 7)))
            rem_str = f"{14 - boost_count} Boosts lagi menuju {target_tier_str}"
        else:
            target_needed = boost_count
            target_tier_str = "Tier 3 (Maksimal)"
            pct = 1.0
            rem_str = "Tingkat Tertinggi Server Telah Tercapai!"

        pct_display = int(pct * 100)
        progress_label = f"Progress: {boost_count} Boosts ({pct_display}%) • {rem_str}"
        draw_text_with_fallback(
            draw, (tx + 2, 400), progress_label,
            fonts["bar_text"], fonts["bar_text_cjk"],
            fonts["cmap_sans_bold"], fonts["cmap_cjk_bold"],
            (225, 215, 250, 255)
        )

        bar_x1 = tx
        bar_x2 = W - 55
        bar_y1 = 426
        bar_y2 = 448
        draw.rounded_rectangle([(bar_x1, bar_y1), (bar_x2, bar_y2)], radius=11, fill=(36, 20, 58, 255), outline=(75, 45, 110, 255), width=1)
        fill_w = int((bar_x2 - bar_x1) * pct)
        if fill_w > 12:
            draw.rounded_rectangle([(bar_x1 + 2, bar_y1 + 2), (bar_x1 + fill_w - 2, bar_y2 - 2)], radius=9, fill=(244, 127, 255, 255))

        footer_text = "Terima kasih banyak telah menjadi Server Booster dan memajukan server ini! 💜"
        draw_text_with_fallback(
            draw, (tx + 2, 482), footer_text,
            fonts["footer"], fonts["footer_cjk"],
            fonts["cmap_sans_reg"], fonts["cmap_cjk_reg"],
            (175, 165, 210, 255)
        )

        buf = io.BytesIO()
        card.save(buf, format="PNG")
        buf.seek(0)
        return buf

    return await asyncio.to_thread(_render)

