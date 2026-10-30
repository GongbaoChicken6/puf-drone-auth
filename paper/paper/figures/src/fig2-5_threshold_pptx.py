# -*- coding: utf-8 -*-
"""图 2-5 双阈值灰区判决示意（10-27 竞标 C 版转正；python-pptx→COM 管线，同图 2-1）。

内容锚点与共享设计同 vB（正文 02 一字不差：通过阈值 6/拒绝阈值 16/
灰区追加 3 组种子加测后再判；术语=海明距离 HD；阈值=STATIC 标定参数）。
几何与 vB 一致（100×38 单位，pptx 自上而下 y' = 38 - y_mpl）。
管线：单页 pptx → COM 导出 PNG（pptx 导出后即删，成品只留 png 纪律）。
"""
import os

from pptx import Presentation
from pptx.util import Cm, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, ".."))
os.makedirs(OUT, exist_ok=True)

INK = RGBColor(0x0B, 0x0B, 0x0B)
GREEN = RGBColor(0xD3, 0xF0, 0xE4)
GRAY = RGBColor(0xF0, 0xEF, 0xEC)
RED = RGBColor(0xF9, 0xD7, 0xD6)

U = 0.176  # 画布 100×38 单位 = 17.6×6.688cm
prs = Presentation()
prs.slide_width = Cm(100 * U)
prs.slide_height = Cm(38 * U)
slide = prs.slides.add_slide(prs.slide_layouts[6])


def cm(v):
    # 返回 Length（EMU）——裸 float 会被截断成原始整数，形状塌到原点（PowerPoint 拒收）
    return Cm(v * U)


def set_run(run, text, fs, color):
    run.text = text
    f = run.font
    f.size = Pt(fs)
    f.color.rgb = color
    f.name = "Segoe UI"
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = rPr.makeelement(qn("a:ea"), {})
        rPr.append(ea)
    ea.set("typeface", "微软雅黑")


def _frame(tf):
    tf.word_wrap = False
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0


def text_c(cx, cy, text, fs=8.0):
    """cx,cy 中心（自上而下单位）；透明文本框居中。"""
    w = cm(len(text) * 1.05 + 2.5)
    tb = slide.shapes.add_textbox(cm(cx) - w / 2, cm(cy) - Cm(0.15), w, Cm(0.3))
    _frame(tb.text_frame)
    tb.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    set_run(tb.text_frame.paragraphs[0].add_run(), text, fs, INK)
    tb.fill.background()
    tb.line.fill.background()
    tb.shadow.inherit = False
    return tb


def rect(x0, y0, w, h, fill):
    sp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, cm(x0), cm(y0), cm(w), cm(h))
    sp.fill.solid()
    sp.fill.fore_color.rgb = fill
    sp.line.fill.background()
    sp.shadow.inherit = False
    return sp


def seg(x1, y1, x2, y2, lw=1.0, arrow=False, curve=False):
    k = MSO_CONNECTOR.CURVE if curve else MSO_CONNECTOR.STRAIGHT
    cn = slide.shapes.add_connector(k, cm(x1), cm(y1), cm(x2), cm(y2))
    cn.line.color.rgb = INK
    cn.line.width = Pt(lw)
    cn.shadow.inherit = False
    if arrow:
        ln = cn.line._get_or_add_ln()
        ln.append(ln.makeelement(qn("a:tailEnd"),
                                 {"type": "triangle", "w": "med", "len": "med"}))
    return cn


def X(hd):
    return 12 + hd * (76 / 64)


# ================= 三区色带（自上而下 y'：8..13） =================
rect(X(0), 8, X(6) - X(0), 5, GREEN)
rect(X(6), 8, X(16) - X(6), 5, GRAY)
rect(X(16), 8, X(64) - X(16), 5, RED)
text_c(X(3), 10.5, "通过区")
text_c((X(6) + X(16)) / 2, 10.5, "灰区")
text_c((X(16) + X(64)) / 2, 10.5, "拒绝区")

# ================= 阈值发丝线 + 标签（y' 5..17；标签 y'=3.2） =================
for hd, lab in [(6, "通过阈值 6"), (16, "拒绝阈值 16")]:
    seg(X(hd), 5, X(hd), 17, lw=1.2)
    text_c(X(hd), 3.2, lab)

# ================= HD 数轴（y'=17，箭头向右） =================
seg(12, 17, 90, 17, arrow=True)
for hd in (0, 6, 16, 64):
    seg(X(hd), 16.5, X(hd), 17.5, lw=1.0)
    text_c(X(hd), 19.0, str(hd), fs=7.5)
text_c(50, 21.4, "海明距离 HD（64 bit）", fs=7.5)

# ================= 三态芯片 + 判决箭头（芯片 y' 28..34） =================
def chip(cx, w, text, fill):
    sp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                cm(cx - w / 2), cm(28), cm(w), cm(6))
    sp.fill.solid()
    sp.fill.fore_color.rgb = fill
    sp.line.color.rgb = INK
    sp.line.width = Pt(1.0)
    sp.shadow.inherit = False
    sp.adjustments[0] = 0.16
    _frame(sp.text_frame)
    sp.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    set_run(sp.text_frame.paragraphs[0].add_run(), text, 8.0, INK)
    return sp


def jarrow(hd):
    seg(X(hd), 13, X(hd), 27.4, arrow=True)


chip(13.0, 10.5, "判决通过", GREEN)
jarrow(4.5)
chip(26.5, 15.5, "追加 3 组种子加测", GRAY)
jarrow(11)
chip(57.0, 10.5, "判决拒绝", RED)
jarrow(40)

# ================= 灰区回环（加测后再判；芯片右缘 → 带底） =================
seg(34.6, 31, 37.2, 13.6, arrow=True, curve=True)

# ================= 导出（PNG-only；pptx 为 COM 中间件即删） =================
pptx = os.path.join(OUT, "fig2-5_threshold.pptx")
prs.save(pptx)

import win32com.client  # noqa: E402

app = win32com.client.Dispatch("PowerPoint.Application")
pres = app.Presentations.Open(pptx, ReadOnly=True, WithWindow=False)
pres.Slides(1).Export(os.path.join(OUT, "fig2-5_threshold.png"), "PNG", 4157, 1581)
pres.Close()
app.Quit()
os.remove(pptx)
print("done:", OUT)
