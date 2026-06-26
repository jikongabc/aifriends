#!/usr/bin/env python
# 种子脚本：批量生成背景图/头像并创建西游记主题角色（含 v3 音色）。
# 用法（在 backend/ 下，已 source .env）：python scripts/seed_characters.py
import os
import sys
import math
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont
from web.models.user import UserProfile
from web.models.character import Character, Voice

MEDIA = settings.MEDIA_ROOT
BG_DIR = MEDIA / "character" / "background_images"
AV_DIR = MEDIA / "character" / "photos"
BG_DIR.mkdir(parents=True, exist_ok=True)
AV_DIR.mkdir(parents=True, exist_ok=True)

W, H = 600, 1000  # 竖版卡片比例


# 生成上下两色竖向渐变作为背景。
def gradient(path, top, bottom, sun=None):
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = y / H
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(W):
            px[x, y] = (r, g, b)
    if sun:
        d = ImageDraw.Draw(img, "RGBA")
        cx, cy, rad = sun
        for rr in range(rad, 0, -1):
            a = int(120 * (1 - rr / rad))
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(255, 245, 200, a))
        d.ellipse([cx - 38, cy - 38, cx + 38, cy + 38], fill=(255, 240, 190, 255))
    img.save(path, "PNG")


# 生成圆形纯色头像，中间写角色名首字。
def avatar(path, text, color):
    size = 200
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, size, size], fill=color)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 90
        )
    except Exception:
        font = ImageFont.load_default()
    # 取首字（中文）
    ch = text[0]
    bbox = d.textbbox((0, 0), ch, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(
        ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
        ch,
        fill="white",
        font=font,
    )
    img.save(path, "PNG")


# 两套背景：晴空海面 / 落日海面
gradient(BG_DIR / "sky.png", (96, 175, 255), (190, 232, 255))
gradient(BG_DIR / "sunset.png", (255, 138, 40), (120, 50, 70), sun=(300, 560, 70))

# 角色定义：名字、音色名、voice_id、人设、背景、头像底色
CHARACTERS = [
    (
        "孙悟空",
        "龙猴哥",
        "longhouge_v3",
        "sky",
        "机灵、调皮、耿直，话多又带点痞气。用调皮中带点不耐烦的语气，语速快，有点痞痞的街头感，说话耿直。",
        (245, 158, 11),
    ),
    (
        "猪八戒",
        "龙老铁",
        "longlaotie_v3",
        "sunset",
        "原是天蓬元帅，因调戏嫦娥被贬下凡错投猪胎。贪吃好色但心地不坏，总想偷懒却关键时刻靠得住。",
        (217, 119, 87),
    ),
    (
        "沙僧",
        "龙三叔",
        "longsanshu_v3",
        "sky",
        "原是凌霄殿卷帘大将，因失手打碎琉璃盏被贬流沙河。任劳任怨的劳模，口头禅“大师兄说得对”。",
        (75, 119, 130),
    ),
    (
        "唐僧",
        "龙书",
        "longshu_v3",
        "sunset",
        "如来座下金蝉子转世。慈悲为怀但略迂腐，念经超度专业户。三句不离“出家人”，五步必说“阿弥陀佛”。",
        (180, 120, 60),
    ),
    (
        "红孩儿",
        "龙杰力豆",
        "longjielidou_v3",
        "sky",
        "聪明顽皮，有点中二又爱炫技。语气活泼，稍微有点小狂，有“我天下第一”的中二热血感。嘴硬心软。",
        (220, 70, 60),
    ),
    (
        "东海龙王",
        "龙老伯",
        "longlaobo_v3",
        "sunset",
        "自带威严、老派、好面子，但不失人情味。语气威严，像个爱面子的老领导，语调庄重带点官腔。",
        (40, 110, 140),
    ),
    (
        "观音菩萨",
        "龙婉",
        "longwan_v3",
        "sky",
        "温柔稳重，智慧慈悲，像温柔家长。声音柔和、从容，有温柔却坚定的感觉。语调舒缓，像一位慈爱长者。",
        (110, 150, 200),
    ),
    (
        "如来佛祖",
        "龙逸尘",
        "longyichen_v3",
        "sky",
        "超然淡定，睿智庄重，但口吻亲切。语气沉稳，带有禅意，不装神秘而是贴近人心，用平静的话道出深刻道理。",
        (150, 120, 90),
    ),
]


def main():
    author = UserProfile.objects.order_by("id").first()
    if not author:
        print("没有任何 UserProfile，请先注册一个用户再运行。")
        return
    print(f"作者 = {author.user.username} (id={author.id})")

    created = 0
    for name, vname, vid, bg, profile, color in CHARACTERS:
        if Character.objects.filter(name=name, author=author).exists():
            print(f"  跳过已存在: {name}")
            continue
        # 头像
        av_rel = f"character/photos/{vid}.png"
        avatar(MEDIA / av_rel, name, color)
        # 音色（去重）
        voice, _ = Voice.objects.get_or_create(voice_id=vid, defaults={"name": vname})
        Character.objects.create(
            author=author,
            name=name,
            photo=av_rel,
            voice=voice,
            profile=profile,
            background_image=f"character/background_images/{bg}.png",
        )
        created += 1
        print(f"  创建: {name} <- {vname}({vid})")

    print(f"完成，新建 {created} 个角色。当前角色总数：{Character.objects.count()}")


if __name__ == "__main__":
    main()
