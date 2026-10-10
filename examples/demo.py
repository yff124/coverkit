# -*- coding: utf-8 -*-
"""跑一遍就知道效果：python3 examples/demo.py

会在 examples/ 下生成 3 张不同平台 / 主题的样例。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coverkit import render  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

TITLE = "AI 落地第一步，不是买工具"
SUB = "先找那件每天都在重复的事，再说别的。"

render(
    TITLE,
    subtitle=SUB,
    kicker="AI 落地笔记",
    footer="杨大飞 · 4A 广告 10 年",
    platform="xiaohongshu",
    theme="midnight",
    style="split",
    out=os.path.join(HERE, "01_小红书_竖版_midnight.png"),
)

render(
    TITLE,
    subtitle=SUB,
    kicker="AI 落地笔记",
    platform="gongzhonghao",
    theme="paper",
    style="gradient",
    out=os.path.join(HERE, "02_公众号头图_paper.png"),
)

render(
    "一个人，一支团队的活",
    subtitle="把 AI 当同事之后发生的真实变化",
    platform="bilibili",
    theme="forest",
    style="split",
    out=os.path.join(HERE, "03_B站封面_forest.png"),
)

print("done →", HERE)
