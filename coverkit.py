# -*- coding: utf-8 -*-
"""coverkit —— 一次调用，生成各平台尺寸的封面图（中文安全）。

为什么需要它
------------
同一篇文章要发到小红书、公众号、视频号、知乎、B站，每个平台的封面比例都不一样。
用设计软件一个个改尺寸很慢；让 AI 生图，中文又会被画糊（尤其是标题里的字）。

coverkit 走第三条路：用代码画。

    from coverkit import render
    render("AI 落地第一步不是买工具", subtitle="先找那件每天都在重复的事")

一次输出十个平台尺寸，中文按语义折行、缺字自动校验、字面自动选对
（不会拿到 PingFang.ttc 里的港繁字面 —— 那是 PIL 最经典的静默事故）。

命令行
------
    python coverkit.py --title "标题" --subtitle "副标题" --platform xiaohongshu -o cover.png
    python coverkit.py --title "标题" --all -o ./covers/     # 生成全部平台尺寸
    python coverkit.py --list                               # 看平台与主题清单
"""

from __future__ import annotations

import argparse
import os
import sys

from PIL import Image, ImageDraw

from cjk_render import audit, load_font, wrap

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# 平台尺寸预设
# ---------------------------------------------------------------------------
# 说明：以下为各平台常见的封面/配图推荐尺寸（像素）。平台会不时调整规则，
# 所以 render() 也接受 size=(w, h) 直接覆盖，不必改这个表。
PLATFORMS: dict[str, tuple[int, int, str]] = {
    "xiaohongshu": (1242, 1656, "小红书 · 竖版封面 3:4"),
    "xiaohongshu-square": (1080, 1080, "小红书 · 方图 1:1"),
    "gongzhonghao": (900, 383, "公众号 · 头图 2.35:1"),
    "shipinhao": (1080, 1260, "视频号 · 竖版封面 6:7"),
    "douyin": (1080, 1920, "抖音 · 竖版视频 9:16"),
    "zhihu": (1200, 628, "知乎 · 文章封面 1.91:1"),
    "bilibili": (1146, 717, "B站 · 视频封面 16:10"),
    "weibo": (1200, 675, "微博 · 配图 16:9"),
    "youtube": (1280, 720, "YouTube · 缩略图 16:9"),
    "x": (1600, 900, "X / Twitter · 卡片 16:9"),
}

# ---------------------------------------------------------------------------
# 配色主题
# ---------------------------------------------------------------------------
# 每个主题给 5 个色：背景上端、背景下端（做纵向渐变）、正文、强调色、次要文字。
THEMES: dict[str, dict[str, str]] = {
    "midnight": {
        "bg_top": "#0C1322",
        "bg_bottom": "#17233C",
        "title": "#F2F5FA",
        "accent": "#FF6B35",
        "muted": "#9FB0C8",
    },
    "paper": {
        "bg_top": "#F7F4EE",
        "bg_bottom": "#EDE7DB",
        "title": "#132436",
        "accent": "#D9552B",
        "muted": "#6B7A8C",
    },
    "forest": {
        "bg_top": "#0E1F1A",
        "bg_bottom": "#153428",
        "title": "#EAF3EE",
        "accent": "#4FD1A5",
        "muted": "#9DBFB0",
    },
    "sunset": {
        "bg_top": "#241028",
        "bg_bottom": "#4A1A3A",
        "title": "#FFF2FA",
        "accent": "#FF8A5B",
        "muted": "#D8B4CC",
    },
    "ink": {
        "bg_top": "#111417",
        "bg_bottom": "#1E242B",
        "title": "#F5F1E9",
        "accent": "#E0B04B",
        "muted": "#A8A296",
    },
}


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _vertical_gradient(size: tuple[int, int], top: str, bottom: str) -> Image.Image:
    """纵向渐变。逐行算色 —— 用 1px 宽的竖条再拉伸，比逐像素画快得多。"""
    w, h = size
    a, b = _hex(top), _hex(bottom)
    strip = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        strip.putpixel((0, y), tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))
    return strip.resize((w, h), Image.BILINEAR)


# ---------------------------------------------------------------------------
# 标题自适应：在给定宽高里找最大可用字号
# ---------------------------------------------------------------------------

def fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_w: int,
    max_h: int,
    start: int,
    min_size: int = 20,
    bold: bool = True,
    line_spacing: float = 1.22,
):
    """从 start 逐档减字号，返回第一个能放进 max_w × max_h 的 (font, lines)。

    注意 min_size 必须小于 start，否则 `while size > min_size` 首次即为假、
    循环被跳过，反而把字号反向撑到 min_size 溢出画布 —— 这是这类函数
    最常见的 off-by-one 事故。
    """
    if min_size >= start:
        min_size = max(12, start // 2)

    size = start
    while size > min_size:
        font = load_font(size, bold=bold)
        lines = wrap(draw, text, font, max_w)
        step = int(size * line_spacing)
        if len(lines) * step <= max_h:
            return font, lines
        size -= 2

    font = load_font(min_size, bold=bold)
    return font, wrap(draw, text, font, max_w)


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

def render(
    title: str,
    subtitle: str | None = None,
    kicker: str | None = None,
    footer: str | None = None,
    platform: str = "xiaohongshu",
    theme: str = "midnight",
    style: str = "split",
    size: tuple[int, int] | None = None,
    out: str = "cover.png",
) -> str:
    """画一张封面。返回输出文件路径。

    platform  见 PLATFORMS（也可用 size=(w,h) 直接指定尺寸）
    theme     见 THEMES
    style     "split"（左侧色带）| "gradient"（纯渐变）| "solid"（纯色）
    """
    if size is None:
        if platform not in PLATFORMS:
            raise KeyError(f"未知平台 {platform!r}，可选：{', '.join(PLATFORMS)}")
        w, h, _ = PLATFORMS[platform]
    else:
        w, h = size

    if theme not in THEMES:
        raise KeyError(f"未知主题 {theme!r}，可选：{', '.join(THEMES)}")
    pal = THEMES[theme]

    # --- 背景 ---
    if style == "solid":
        img = Image.new("RGB", (w, h), _hex(pal["bg_bottom"]))
    else:
        img = _vertical_gradient((w, h), pal["bg_top"], pal["bg_bottom"])

    draw = ImageDraw.Draw(img)
    base = min(w, h)
    margin = int(base * 0.075)

    # --- split 样式：左侧竖色带（视觉重心的锚点） ---
    band_w = 0
    if style == "split":
        band_w = int(w * 0.055)
        draw.rectangle([0, 0, band_w, h], fill=_hex(pal["accent"]))

    content_x = margin + band_w
    text_w = w - content_x - margin

    # --- 交付前必跑：缺字直接抛错，而不是交一张少了字的图 ---
    guard = [t for t in (kicker, title, subtitle, footer) if t]
    if guard:
        audit(guard)

    # --- 排版：把 kicker / 标题 / 副标题 垂直居中堆叠 ---
    k_size = max(14, int(base * 0.030))
    s_size = max(16, int(base * 0.040))

    k_font = load_font(k_size, bold=True) if kicker else None
    k_step = int(k_size * 1.8) if kicker else 0

    title_start = int(base * 0.115)
    title_font, title_lines = fit_font(
        draw, title, text_w, int(h * 0.46), title_start, bold=True
    )
    t_step = int(title_font.size * 1.22)

    sub_lines: list[str] = []
    if subtitle:
        sub_font = load_font(s_size, bold=False)
        sub_lines = wrap(draw, subtitle, sub_font, text_w)
        sub_step = int(s_size * 1.5)
    else:
        sub_font = None
        sub_step = 0

    gap_k = int(base * 0.045) if kicker else 0
    gap_s = int(base * 0.055) if subtitle else 0

    total = (
        k_step + gap_k + len(title_lines) * t_step + gap_s + len(sub_lines) * sub_step
    )
    y = max(margin, (h - total) // 2)

    # --- 画 ---
    if kicker and k_font:
        draw.text((content_x, y), kicker, font=k_font, fill=_hex(pal["accent"]))
        y += k_step + gap_k

    for line in title_lines:
        draw.text((content_x, y), line, font=title_font, fill=_hex(pal["title"]))
        y += t_step

    if subtitle and sub_font:
        y += gap_s
        for line in sub_lines:
            draw.text((content_x, y), line, font=sub_font, fill=_hex(pal["muted"]))
            y += sub_step

    # --- 底部强调线 ---
    rule_y = h - margin
    draw.rectangle(
        [content_x, rule_y, content_x + int(text_w * 0.34), rule_y + max(3, base // 260)],
        fill=_hex(pal["accent"]),
    )

    if footer:
        f_size = max(12, int(base * 0.024))
        f_font = load_font(f_size, bold=False)
        draw.text(
            (content_x, rule_y + int(base * 0.030)),
            footer,
            font=f_font,
            fill=_hex(pal["muted"]),
        )

    # --- 输出（PNG：中文小字笔画密集，JPG 会出彩色噪点） ---
    d = os.path.dirname(os.path.abspath(out))
    if d:
        os.makedirs(d, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    return out


def render_all(
    title: str,
    subtitle: str | None = None,
    kicker: str | None = None,
    footer: str | None = None,
    theme: str = "midnight",
    style: str = "split",
    outdir: str = "covers",
) -> list[str]:
    """一次生成全部平台尺寸，文件名即平台名。"""
    paths = []
    for name in PLATFORMS:
        p = render(
            title,
            subtitle=subtitle,
            kicker=kicker,
            footer=footer,
            platform=name,
            theme=theme,
            style=style,
            out=os.path.join(outdir, f"{name}.png"),
        )
        paths.append(p)
    return paths


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> int:
    ap = argparse.ArgumentParser(
        prog="coverkit", description="一次生成各平台尺寸的封面图（中文安全）"
    )
    ap.add_argument("--title", help="主标题（必填，除非用 --list）")
    ap.add_argument("--subtitle", help="副标题")
    ap.add_argument("--kicker", help="左上角小标签，如栏目名")
    ap.add_argument("--footer", help="底部小字，如作者 / 日期")
    ap.add_argument("--platform", default="xiaohongshu", help="平台名，见 --list")
    ap.add_argument("--theme", default="midnight", help="主题名，见 --list")
    ap.add_argument("--style", default="split", choices=["split", "gradient", "solid"])
    ap.add_argument("--size", help="自定义尺寸，格式 WxH，覆盖平台预设")
    ap.add_argument("--all", action="store_true", help="生成全部平台尺寸")
    ap.add_argument("-o", "--out", default="cover.png", help="输出文件或目录")
    ap.add_argument("--list", action="store_true", help="列出平台与主题")
    args = ap.parse_args()

    if args.list:
        print("平台：")
        for k, (w, h, desc) in PLATFORMS.items():
            print(f"  {k:<20} {w}x{h}   {desc}")
        print("\n主题：" + "、".join(THEMES))
        print("样式：split / gradient / solid")
        return 0

    if not args.title:
        ap.error("--title 必填（或用 --list 查看预设）")

    size = None
    if args.size:
        try:
            w, h = args.size.lower().split("x")
            size = (int(w), int(h))
        except Exception:
            ap.error("--size 格式应为 WxH，例如 1242x1656")

    if args.all:
        outdir = args.out if not args.out.endswith(".png") else "covers"
        paths = render_all(
            args.title,
            subtitle=args.subtitle,
            kicker=args.kicker,
            footer=args.footer,
            theme=args.theme,
            style=args.style,
            outdir=outdir,
        )
        print(f"生成 {len(paths)} 张 → {outdir}/")
    else:
        p = render(
            args.title,
            subtitle=args.subtitle,
            kicker=args.kicker,
            footer=args.footer,
            platform=args.platform,
            theme=args.theme,
            style=args.style,
            size=size,
            out=args.out,
        )
        print("已生成:", p)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
