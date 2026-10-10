# coverkit

**一句话，生成十个平台尺寸的封面图。中文不会画糊，字不会少。**

![demo](examples/01_小红书_竖版_midnight.png)

同一篇文章要发到小红书、公众号、视频号、知乎、B站 —— 每个平台的封面比例都不一样。
用设计软件一个个改尺寸很慢；让 AI 生图，标题里的中文又会被画糊。

coverkit 走第三条路：**用代码画**。给一句标题，输出所有平台尺寸。

```bash
python coverkit.py --title "AI 落地第一步，不是买工具" --all -o covers/
```

```
covers/xiaohongshu.png          1242×1656
covers/gongzhonghao.png          900×383
covers/bilibili.png             1146×717
...共 10 张
```

## 为什么不用 AI 生图 / 设计软件

| 方案 | 问题 |
|---|---|
| AI 生图 | 图好看，**中文标题必糊** —— 笔画密集的汉字是扩散模型的弱项 |
| 设计软件 | 一张图改 10 个尺寸，纯手工；换标题要重排 |
| **coverkit** | 标题是变量，尺寸是参数，**一条命令出全套**，且每次结果一致 |

## 安装

只有一个依赖：

```bash
pip install pillow
```

把 `coverkit.py` 和 `cjk_render.py` 放进你的项目即可（两个单文件，无包结构）。

> `cjk_render.py` 来自同作者的 [cjk-text-render](https://github.com/yff124/cjk-text-render)（MIT），
> 负责字体选择和中文折行。这里内联一份是为了让 coverkit 能独立下载即用。

## 用法

### 命令行

```bash
# 单个平台
python coverkit.py --title "标题" --subtitle "副标题" --platform xiaohongshu -o cover.png

# 全部平台（文件名 = 平台名）
python coverkit.py --title "标题" --all -o covers/

# 带栏目标签和作者署名
python coverkit.py --title "标题" --kicker "AI 落地笔记" --footer "杨大飞 · 2026" -o cover.png

# 自定义尺寸 / 主题 / 样式
python coverkit.py --title "标题" --size 1400x1400 --theme paper --style gradient -o cover.png

# 看全部预设
python coverkit.py --list
```

### 代码

```python
from coverkit import render

render(
    "AI 落地第一步，不是买工具",
    subtitle="先找那件每天都在重复的事，再说别的。",
    kicker="AI 落地笔记",
    footer="杨大飞 · 4A 广告 10 年",
    platform="xiaohongshu",
    theme="midnight",
    style="split",
    out="cover.png",
)
```

## 平台尺寸

| 平台名 | 尺寸 | 用途 |
|---|---|---|
| `xiaohongshu` | 1242 × 1656 | 小红书 · 竖版封面 3:4 |
| `xiaohongshu-square` | 1080 × 1080 | 小红书 · 方图 1:1 |
| `gongzhonghao` | 900 × 383 | 公众号 · 头图 2.35:1 |
| `shipinhao` | 1080 × 1260 | 视频号 · 竖版封面 6:7 |
| `douyin` | 1080 × 1920 | 抖音 · 竖版视频 9:16 |
| `zhihu` | 1200 × 628 | 知乎 · 文章封面 1.91:1 |
| `bilibili` | 1146 × 717 | B站 · 视频封面 16:10 |
| `weibo` | 1200 × 675 | 微博 · 配图 16:9 |
| `youtube` | 1280 × 720 | YouTube · 缩略图 16:9 |
| `x` | 1600 × 900 | X / Twitter · 卡片 16:9 |

平台会不时调整推荐尺寸，所以 `render(size=(w, h))` / `--size WxH` 可以直接覆盖，
不必等这个表更新。

## 主题与样式

**主题**（`--theme`）：`midnight`（深蓝+橙）、`paper`（米白+朱橙）、
`forest`（墨绿+薄荷）、`sunset`（紫+珊瑚）、`ink`（近黑+金）

**样式**（`--style`）：

- `split` —— 左侧竖色带（默认，视觉重心最稳）
- `gradient` —— 纯纵向渐变
- `solid` —— 纯色

## 设计上的两个刻意选择

**1. 输出 PNG，不用 JPG。**
中文小字的笔画密集处，JPEG 压缩会产生彩色噪点。非要用 JPG 的话 `quality` 别低于 95。

**2. 交付前强制校验缺字。**
PIL 渲染字体里没有的字符时不抛异常，直接画空白 —— 也就是说你会拿到一张
"少了字"的图，而且**看不出来**。coverkit 在画之前先跑一遍 `audit()`，
有缺字直接炸掉：

```
RuntimeError: 字体缺字，无法渲染：稳
（macOS 上多半是把 PingFang.ttc 的 index 0/1 当常规用了 —— 那是港繁 / 台繁；简体应该用 index 2）
```

宁可脚本失败，也不要交付一张静默事故的图。

## 跑一遍示例

```bash
python3 examples/demo.py      # 在 examples/ 生成 3 张不同平台/主题的样例
```

## License

MIT
