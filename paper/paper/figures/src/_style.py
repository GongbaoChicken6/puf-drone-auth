# -*- coding: utf-8 -*-
"""论文数据图统一样式（图表制作方案 §4）。
调色板 = 方案 §3（已过 dataviz 验证器，勿改 hex）。数据图 import 后调 use_science()；
结构图只 import PAL/INK* 常量，不用 science 样式。
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PAL = {
    "c1": "#2a78d6",   # slot1 蓝：默认系列/主角
    "c2": "#eb6834",   # slot2 橙
    "c3": "#1baf7a",   # slot3 青绿（浅底对比<3:1，须配直接标注/marker）
    "mute": "#898781",
    "grid": "#e1e0d9",
}
INK, INK2, INK3 = "#0b0b0b", "#52514e", "#898781"
TINT1, TINT2 = "#cde2fb", "#e8f2fe"


def use_science():
    """数据图管线：IEEE 版式 + 已验证配色（无 LaTeX 环境）。"""
    import scienceplots  # noqa: F401

    plt.style.use(["science", "ieee", "no-latex"])
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["SimSun", "Times New Roman"],
        "axes.unicode_minus": False,
        "grid.color": PAL["grid"],
        "grid.linewidth": 0.6,
        "grid.linestyle": "-",
        "axes.prop_cycle": plt.cycler(color=[PAL["c1"], PAL["c2"], PAL["c3"]]),
    })
