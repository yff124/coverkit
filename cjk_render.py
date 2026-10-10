"""cjk-render —— 用 PIL/Pillow 渲染中文时，绕开三个静默事故。

事故一：TTC 字面顺序
    macOS 的 /System/Library/Fonts/PingFang.ttc 是一个字体集合，index 顺序是
    HK / TC / SC，也就是：

        index 0 = 香港繁体 Regular   ← 最容易被当成"常规字重"
        index 1 = 台湾繁体 Regular
        index 2 = 简体 Regular       ← 这才是简体常规
        index 3/4/5 = HK/TC/简 Medium
        index 6/7/8 = HK/TC/简 Semibold

    按直觉写 index 0 当常规，会有两个后果，且都不报错：
      1. 简体字用繁体字形渲染（写法不对，人看得出怪但说不出哪里怪）
      2. 部分简体字直接缺失，画出来是一片空白（例如「稳」「够」）

事故二：缺字静默失败
    PIL 渲染字体里没有的字符时不抛异常，直接画空白。必须自己校验。

事故三：中文硬折行
    中文没有空格，逐字累加到超宽就断行，会出现「知道你在打 / 杂」这种把词
    切开的断句。中文折行要按标点断，不能按像素断。

用法
----
    from PIL import Image, ImageDraw
    from cjk_render import load_font, audit, wrap, draw_block

    font = load_font(38)              # 自动选对字面（不会拿到港繁）
    audit(["要画的所有文字"])          # 交付前必跑：有缺字直接抛错
    lines = wrap(draw, "一段很长的中文正文……", font, max_w=900)

    # 或者直接画：
    draw_block(draw, "一段很长的中文正文……", font, (60, 300), max_w=900)
"""

from __future__ import annotations

import sys
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

__version__ = "0.1.0"
__all__ = [
    "load_font",
    "missing_chars",
    "audit",
    "wrap",
    "draw_block",
    "BREAK_AFTER",
]


# --------------------------------------------------------------------------
# 字体探测：每个平台给一串候选，取第一个能加载的
# --------------------------------------------------------------------------

def _candidates(bold: bool):
    if sys.platform == "darwin":
        return [
            # ⚠ PingFang.ttc 的 index 顺序是 HK / TC / SC。
            #   2 = 简体 Regular，8 = 简体 Semibold —— 千万别用 0 / 1。
            ("/System/Library/Fonts/PingFang.ttc", 8 if bold else 2),
            ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
            ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
            ("/Library/Fonts/Arial Unicode.ttf", 0),
        ]
    if sys.platform.startswith("win"):
        return [
            # 微软雅黑；msyhbd 是粗体
            ("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc", 0),
            ("C:/Windows/Fonts/simhei.ttf", 0),
            ("C:/Windows/Fonts/simsun.ttc", 0),
        ]
    return [
        # Linux / 容器：Noto Sans CJK 是事实标准（Debian: fonts-noto-cjk）
        (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
            if bold
            else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            2,  # index 2 一般是 SC 字面
        ),
        ("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf", 0),
        ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),
        ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),
        ("/usr/share/fonts/truetype/arphic/uming.ttc", 0),
    ]


@lru_cache(maxsize=256)
def _truetype(path: str, index: int, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size, index=index)


@lru_cache(maxsize=16)
def _probe_font() -> ImageFont.FreeTypeFont:
    return load_font(40)


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """加载一个能渲染简体中文的字体。

    自动跳过 TrueType Collection 里的 HK / TC 字面（这是最常见的坑）。
    所有候选都失败时抛 RuntimeError，而不是悄悄退化成默认字体（默认字体
    画中文全是豆腐块）。
    """
    for path, index in _candidates(bold):
        try:
            return _truetype(path, index, size)
        except Exception:
            continue
    raise RuntimeError(
        "找不到可用的中文字体。请安装其中之一："
        "Noto Sans CJK（Linux）、微软雅黑（Windows）、PingFang（macOS 自带）。"
    )


# --------------------------------------------------------------------------
# 缺字校验
# --------------------------------------------------------------------------

def missing_chars(
    text: str, font: ImageFont.FreeTypeFont | None = None
) -> list[str]:
    """返回该字体渲染不出来的字符（画出来会是一片空白）。"""
    font = font or _probe_font()
    pad = 8
    side = font.size * 2 + pad * 2
    canvas = Image.new("L", (side, side), 0)
    draw = ImageDraw.Draw(canvas)

    missing: list[str] = []
    for ch in dict.fromkeys(text):  # 去重且保序
        if ch.isspace():
            continue
        canvas.paste(0, (0, 0, canvas.width, canvas.height))
        draw.text((pad, pad), ch, font=font, fill=255)
        if canvas.getbbox() is None:  # 整张画布仍是全黑 → 这个字没画出来
            missing.append(ch)
    return missing


def audit(strings, font: ImageFont.FreeTypeFont | None = None) -> bool:
    """交付前自检：把这次要画的所有文字传进来，有缺字直接抛错。

    宁可让脚本炸掉，也不要交付一张少了字的图 —— 那是静默事故，没人会发现。
    """
    if isinstance(strings, str):
        strings = [strings]
    text = "".join(strings)
    missing = missing_chars(text, font)
    if missing:
        raise RuntimeError(
            f"字体缺字，无法渲染：{''.join(missing)}\n"
            "（macOS 上多半是把 PingFang.ttc 的 index 0/1 当常规用了 —— "
            "那是港繁 / 台繁；简体应该用 index 2）"
        )
    return True


# --------------------------------------------------------------------------
# 中文语义折行
# --------------------------------------------------------------------------

# 中文没有空格，硬折行会把词切断。优先在这些标点后断 —— 它们天然是语义边界。
BREAK_AFTER = "，。、：；！？）」』】〉》〕｝…—,.:;!?)]}"

# 不该出现在行首的标点（避免"甩标点"）
NO_LINE_START = "，。、：；！？）」』】〉》〕｝%‰℃"

# 数字不要和后缀拆开：「20」和「+」分到两行，读起来像两个数
_NUM_SUFFIX = "+%万亿人天条个年月日时分秒"


def wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    """按像素宽度折行，但语义边界优先于像素边界。

    规则：
      1. 在溢出点往前 12 字内找最近的语义断点，找到就在那儿断；
      2. 找不到才硬断，但硬断前若行尾是数字、下一个字是量词/百分号，往回退一格；
      3. 标点永远留在上一行末尾，不甩到下一行行首。
    """
    lines: list[str] = []
    cur = ""

    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue

        if draw.textlength(cur + ch, font=font) <= max_w:
            cur += ch
            continue

        # 1) 语义断点优先
        cut = -1
        for i in range(len(cur) - 1, max(len(cur) - 12, -1), -1):
            if cur[i] in BREAK_AFTER:
                cut = i + 1
                break
        if cut > 0:
            lines.append(cur[:cut])
            cur = cur[cut:] + ch
            continue

        # 2) 数字不与量词/百分号拆开
        if cur and cur[-1].isdigit() and ch in _NUM_SUFFIX:
            cur, ch = cur[:-1], cur[-1] + ch

        # 3) 标点不甩到行首
        if cur and ch in NO_LINE_START:
            lines.append(cur + ch)
            cur = ""
            continue

        lines.append(cur)
        cur = ch

    if cur:
        lines.append(cur)
    return lines


def draw_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    xy: tuple[int, int],
    max_w: int,
    fill=(0, 0, 0),
    line_spacing: float = 1.4,
) -> int:
    """在指定位置画一段自动折行的中文，返回画完后的 y 坐标（方便继续往下排）。"""
    x, y = xy
    step = int(font.size * line_spacing)
    for line in wrap(draw, text, font, max_w):
        draw.text((x, y), line, font=font, fill=fill)
        y += step
    return y


if __name__ == "__main__":
    # 自检：加载字体 + 渲染一段容易缺字的中文
    f = load_font(40)
    audit(["中文渲染自检：稳、够、藏、翻、爨"])  # 「爨」大概率缺字，用它看校验是否生效
    print(f"OK — 字体已加载（{f.path} index={getattr(f, 'index', '?')}）")
