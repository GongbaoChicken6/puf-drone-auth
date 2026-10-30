# -*- coding: utf-8 -*-
"""图 2-6 HF-IDA 六帧双向认证流程（v5，学长样本流程图风格）。

布局 DNA 学自学长样本图 4（认证业务流程图，docx 解包实测）：
  纵向主干 + 浅色填充矩形（蓝 #c8e2fa）+ 黄色菱形判断（#f0da9c）
  + 红/粉端点（#edd1d5）+ 直角折线连接。
v5（10-26 用户定）：框内宋体副行注释全部删除，只留黑体主行；
字段/字节布局等细节一律由正文 2.2.3 承载。
v6（10-27 用户定）：字体与图 2-1/学长统一——西文与数字 Times New Roman、
中文黑体（matplotlib≥3.6 字形级回退：family 列表按序取字形）。
v7（10-27 用户定，基准=图表制作方案头部 10-27 变更「dataviz 直做」）：
  字体换 system sans（Segoe UI + 雅黑，与图 1-1 HTML 同栈）；
  填充色弃学长样本实测色，改方案 §3 调色板族浅色调并赋语义——
  过程=slot1 蓝族 TINT1、判定=slot2 橙族浅调、失败终态=发散红族浅调、
  成功终态=slot3 青绿族浅调（状态色只用于好坏语义）、起点=中性灰；
  全部墨字墨边，线宽 1.1→1.2。版式（学长布局 DNA）与文本不动。
数据源：docs/protocol_contract.md §5；阈值 src/python/server/threshold.py。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.font_manager import FontProperties

from _style import INK, INK2, INK3, TINT1

# 调色板族浅色调（方案 §3；填充只作身份/语义，文字一律墨色，打印安全）
BLUE = TINT1                                   # 过程框：slot1 蓝族
YELLOW = "#fbe0d2"                             # 判定菱形：slot2 橙 #eb6834 族浅调
RED = "#f9d7d6"                                # 失败终态：发散红 #e34948 族浅调
GREEN = "#d3f0e4"                              # 成功终态：slot3 青绿 #1baf7a 族浅调
GRAY = "#f0efec"                               # 起点：中性灰

FONT = FontProperties(family=["Segoe UI", "Microsoft YaHei"])  # system sans，同图 1-1
# 不用 mathtext：$...$ 会让整串走 stix、中文变空框（v5 潜伏 bug，v6 修）

fig, ax = plt.subplots(figsize=(4.5, 7.05))
ax.set_xlim(0, 100)
ax.set_ylim(-5.5, 153)
ax.axis("off")
LW = 1.2


def box(cx, cy, w, h, main, fill=BLUE, fs=8.2):
    ax.add_patch(mpatches.FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle="round,pad=0,rounding_size=0.6",
        facecolor=fill, edgecolor=INK, linewidth=LW))
    ax.text(cx, cy, main, ha="center", va="center",
            fontproperties=FONT, fontsize=fs, color=INK)


def diamond(cx, cy, hw, hh, main):
    ax.add_patch(mpatches.Polygon(
        [(cx, cy + hh), (cx + hw, cy), (cx, cy - hh), (cx - hw, cy)],
        closed=True, facecolor=YELLOW, edgecolor=INK, linewidth=LW))
    ax.text(cx, cy, main, ha="center", va="center",
            fontproperties=FONT, fontsize=8.0, color=INK)


def stadium(cx, cy, w, h, text, fill=GRAY, fs=8.0):
    ax.add_patch(mpatches.FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle=f"round,pad=0,rounding_size={h / 2}",
        facecolor=fill, edgecolor=INK, linewidth=LW))
    ax.text(cx, cy, text, ha="center", va="center",
            fontproperties=FONT, fontsize=fs, color=INK)


def poly(pts):
    """直角折线；最后一段带箭头。"""
    xs, ys = zip(*pts)
    ax.plot(xs[:-1], ys[:-1], color=INK, lw=LW, solid_capstyle="butt", zorder=1)
    ax.annotate("", xy=pts[-1], xytext=pts[-2],
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=LW,
                                mutation_scale=11, shrinkA=0, shrinkB=0))


def label(x, y, text):
    """分支条件标签（判断语义，黑体加粗，保留）。"""
    ax.text(x, y, text, ha="center", va="center",
            fontproperties=FONT, fontsize=7.0, fontweight="bold", color=INK)


# ================= 主干 =================
stadium(50, 147, 36, 7, "开始：终端上电接入")
box(50, 135, 46, 9, "① 接入请求")
box(50, 123, 46, 9, "② 挑战（基站下发）")
box(50, 111, 46, 9, "③ 指纹响应（终端测量）")
box(50, 99, 46, 9, "基站比对注册模板")
diamond(50, 85, 21, 9, "HD 判决")

poly([(50, 143.5), (50, 139.5)])
poly([(50, 130.5), (50, 127.5)])
poly([(50, 118.5), (50, 115.5)])
poly([(50, 106.5), (50, 103.5)])
poly([(50, 94.5), (50, 94.0)])

# ================= 三分支 =================
# ④a 左：直接通过
box(23, 75, 26, 8, "④a 判决 PASS")
poly([(29, 85), (23, 85), (23, 79)])
label(26, 87.6, "HD ≤ 6")

# ④b 右：直接拒绝
box(79, 75, 26, 8, "④b 判决 REJECT")
poly([(71, 85), (79, 85), (79, 79)])
label(75, 87.6, "HD ≥ 16")
stadium(79, 64, 22, 6.5, "认证失败", fill=RED)
poly([(79, 71), (79, 67.25)])

# ④c 下：灰区加测
box(50, 69, 27, 8, "④c 灰区加测")
poly([(50, 76), (50, 73)])
label(58.0, 75.2, "6 < HD < 16")
box(50, 57, 27, 8, "⑤ 复测响应")
poly([(50, 65), (50, 61)])

# 回环：⑤ 复测响应 → 右侧绕行 → 回 HD 判决
poly([(50, 53), (50, 49), (95, 49), (95, 89.5), (60.5, 89.5)])

# ④a 汇合 → 终端验证 R₂
poly([(23, 71), (23, 41), (50, 41), (50, 38.5)])

# ================= 双向验证与确认 =================
box(50, 34, 44, 9, "终端验证 R₂（双向）")
diamond(50, 19.5, 19, 6, "R₂ 一致？")
poly([(50, 29.5), (50, 25.5)])

label(53.5, 11.4, "一致")
stadium(87, 19.5, 24, 6.5, "阻断 BLOCKED", fill=RED)
poly([(69, 19.5), (75, 19.5)])
label(71.5, 24.8, "不一致")

box(50, 5.5, 34, 7, "⑥ 确认")
poly([(50, 13.5), (50, 9)])
stadium(50, -2, 32, 5.5, "双向认证完成", fill=GREEN)
poly([(50, 2), (50, 0.75)])

# ================= 口径 =================
# v5（10-26 用户定）：图内口径标注也删除，口径由正文与附录承载。

# ================= 导出（成品只留 png，10-27 用户定；需矢量时临时加回 pdf/svg 行） =================
out = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
fig.savefig(os.path.join(out, "fig2-6_auth_flow.png"), dpi=600, bbox_inches="tight", pad_inches=0.02)
print("done:", out)
