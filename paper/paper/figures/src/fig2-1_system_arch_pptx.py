# -*- coding: utf-8 -*-
"""图 2-1 系统整体架构 —— 真·PPT 制图管线（v8 全量重写；v9 换皮）。

v9（10-27 用户新基准回改，图表制作方案头部 10-27 变更）：
  字体 Times/黑体→Segoe UI/微软雅黑（同图1-1 栈）；去渐变——面板改平涂
  slot1 蓝族浅调 TINT2 + 墨边；芯片蓝底白字→白底墨字墨边；连线全墨；
  配色出自方案 §3 调色板族。版式、坐标、全部文字零改动（v8 定型不动）。

制图语言（学长图 2 像素实测 + 用户四轮反馈定型）：
  三区 Z 形布局；面板 = 平涂浅调圆角矩形 + 细墨边框；
  面板标题在框内：墨色粗体主名 + 墨色括号口径（全图无灰色小字）；
  模块 = 白底墨字芯片，宽度一律按自身字数（多少字多长条）；
  框内模块按数据流连接，箭头一律直线（仅顶层集成汇流用曲线）；
  区间连接 = 墨实线 S 曲线 + 双三角头 + 旁注深色标签（标签避开曲线放置）。
字体：中文微软雅黑 + 西文 Segoe UI。
管线：python-pptx 生成单页 pptx → PowerPoint COM 导出 PNG(~600dpi) + 矢量 PDF。
框内箭头数据流出处：
  终端：PUF→KDF（2.2.3(4)）；HF-IDA⇅Speck（(2)(3) R2）；
        KDF、Speck 曲线汇入顶层集成（(5) 集成各模块）。
  基站：串口→帧级状态机→模板库判决主链；帧级⇅HSM（2.3.2(2)）；
        注册入库→模板库（2.3.2(1)）；串口→Web 三面板（2.3.2(3)）。
  链路：PMOD 电平移位→USB 转串口（表 2-2）。
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

# v9 基准色（图表制作方案 §3 调色板族）：墨线 + 浅调填充 + 墨字，无渐变
INK = RGBColor(0x0B, 0x0B, 0x0B)     # 主墨：框线/文字/连线
INK2 = RGBColor(0x52, 0x51, 0x4E)    # 次墨：旁注标签
TINT2 = RGBColor(0xE8, 0xF2, 0xFE)   # 面板底：slot1 蓝族浅调
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

U = 0.176  # 1 设计单位 = 0.176cm（画布 100×41 单位 = 17.6×7.216cm）

prs = Presentation()
prs.slide_width = Cm(100 * U)
prs.slide_height = Cm(41 * U)
slide = prs.slides.add_slide(prs.slide_layouts[6])


def cm(v):
    return v * U


def set_run(run, text, fs, color, bold=False):
    """中文微软雅黑 + 西文 Segoe UI（10-27 新基准，同图1-1 栈）。"""
    run.text = text
    f = run.font
    f.size = Pt(fs)
    f.bold = bold
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


def est_cm(text, fs):
    """文字宽度估算（cm）：全角 1em、半角 0.52em、空格 0.30em。"""
    w = 0.0
    for ch in text:
        if ord(ch) > 0x2E7F:
            w += 1.0
        elif ch == " ":
            w += 0.30
        else:
            w += 0.52
    return w * fs * 1.06 * 0.03528


def chip_w(text, fs=7.0):
    """芯片宽度 = 自身字宽 + 留白（多少字多长条）。"""
    return est_cm(text, fs) * 1.12 + 0.10


def conn(kind, x1, y1, x2, y2, head=True, tail=True, lw=1.0, size="med"):
    """连接线：kind = 'line' 直线 / 'curve' 曲线；head/tail = 两端三角箭头。"""
    k = {"line": MSO_CONNECTOR.STRAIGHT, "curve": MSO_CONNECTOR.CURVE}[kind]
    cn = slide.shapes.add_connector(k, Cm(x1), Cm(y1), Cm(x2), Cm(y2))
    cn.line.color.rgb = INK
    cn.line.width = Pt(lw)
    cn.shadow.inherit = False
    ln = cn.line._get_or_add_ln()
    if head:
        ln.append(ln.makeelement(qn("a:headEnd"),
                                 {"type": "triangle", "w": size, "len": size}))
    if tail:
        ln.append(ln.makeelement(qn("a:tailEnd"),
                                 {"type": "triangle", "w": size, "len": size}))
    return cn


def label(cx, cy, text, fs=6.5, color=INK2):
    w = est_cm(text, fs) + 0.16
    tb = slide.shapes.add_textbox(Cm(cx - w / 2), Cm(cy - 0.14), Cm(w), Cm(0.28))
    _frame(tb.text_frame)
    tb.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    set_run(tb.text_frame.paragraphs[0].add_run(), text, fs, color)
    tb.fill.background()
    tb.line.fill.background()
    tb.shadow.inherit = False
    return tb


def panel(x0, y0, w, h, title, caliber, adj=0.06):
    """平涂浅调面板 + 框内标题（墨色粗体主名 + 墨色括号口径）。"""
    sp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                Cm(x0), Cm(y0), Cm(w), Cm(h))
    sp.fill.solid()
    sp.fill.fore_color.rgb = TINT2
    sp.line.color.rgb = INK
    sp.line.width = Pt(1.0)
    sp.shadow.inherit = False
    sp.adjustments[0] = adj
    _frame(sp.text_frame)
    tw = est_cm(title, 9) + est_cm("（" + caliber + "）", 7.5) + 0.3
    tb = slide.shapes.add_textbox(Cm(x0 + w / 2 - tw / 2), Cm(y0 + 0.22),
                                  Cm(tw), Cm(0.42))
    _frame(tb.text_frame)
    tb.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    p = tb.text_frame.paragraphs[0]
    set_run(p.add_run(), title, 9, INK, bold=True)
    set_run(p.add_run(), "（" + caliber + "）", 7.5, INK)
    tb.fill.background()
    tb.line.fill.background()
    tb.shadow.inherit = False
    return sp


def chip(cx, cy, text, fs=7.0):
    """模块芯片：白底墨字墨边小圆角矩形，宽度按自身字数。cx/cy 中心（cm）。"""
    w = chip_w(text, fs)
    h = 2.0 * U
    sp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                Cm(cx - w / 2), Cm(cy - h / 2), Cm(w), Cm(h))
    sp.fill.solid()
    sp.fill.fore_color.rgb = WHITE
    sp.line.color.rgb = INK
    sp.line.width = Pt(1.0)
    sp.shadow.inherit = False
    sp.adjustments[0] = 0.22
    _frame(sp.text_frame)
    sp.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    set_run(sp.text_frame.paragraphs[0].add_run(), text, fs, INK)
    return sp


# ================= 左面板：无人机终端 =================
LX, LY, LW, LH = cm(2), cm(8), cm(39.5), cm(19.4)
panel(LX, LY, LW, LH, "无人机终端", "ZC706 · PL 自研 RTL")
lc = ["PUF 指纹引擎", "HF-IDA 协议引擎",
      "设备密钥派生 KDF", "Speck64/96 轻量密码核"]
wmax1 = max(chip_w(lc[0]), chip_w(lc[2]))
wmax2 = max(chip_w(lc[1]), chip_w(lc[3]))
gap_c = cm(2.5)
gx = LX + (LW - (wmax1 + wmax2 + gap_c)) / 2
cx1 = gx + wmax1 / 2                      # 左列轴（PUF / KDF）
cx2 = gx + wmax1 + gap_c + wmax2 / 2      # 右列轴（HF-IDA / Speck）
r1, r2, r3 = LY + cm(6.0), LY + cm(10.6), LY + cm(16.6)
chip(cx1, r1, lc[0])
chip(cx2, r1, lc[1])
chip(cx1, r2, lc[2])
chip(cx2, r2, lc[3])
lfcx = LX + LW / 2
chip(lfcx, r3, "顶层集成")
conn("line", cx1, r1 + U, cx1, r2 - U, head=False, tail=True, lw=0.9, size="sm")
conn("line", cx2, r1 + U, cx2, r2 - U, head=True, tail=True, lw=0.9, size="sm")
# KDF、Speck 曲线汇入顶层集成（入芯点分列中线两侧）
conn("curve", cx1, r2 + U, lfcx - cm(1.3), r3 - U, head=False, tail=True, lw=0.9, size="sm")
conn("curve", cx2, r2 + U, lfcx + cm(1.3), r3 - U, head=False, tail=True, lw=0.9, size="sm")

# ================= 右上面板：PC 基站 =================
RX, RY, RW, RH = cm(59), cm(5.5), cm(40), cm(18)
panel(RX, RY, RW, RH, "PC 基站", "Python 基站软件")
rc = ["串口服务", "帧级状态机（协议驱动）", "指纹模板库与双阈值判决"]
rs = ["Web 可视化三面板", "HSM 密码模块", "注册入库"]
wr = [chip_w(t) for t in rc]
ws = [chip_w(t) for t in rs]
gap_c = cm(3.0)
gx = RX + (RW - (max(wr) + max(ws) + gap_c)) / 2
kx1 = gx + max(wr) / 2                    # 主链列轴
kx2 = gx + max(wr) + gap_c + max(ws) / 2  # 支撑列轴
rr = [RY + cm(6.0), RY + cm(10.6), RY + cm(15.2)]
for i in range(3):
    chip(kx1, rr[i], rc[i])
    chip(kx2, rr[i], rs[i])
# 主链纵箭头
conn("line", kx1, rr[0] + U, kx1, rr[1] - U, head=False, tail=True, lw=0.9, size="sm")
conn("line", kx1, rr[1] + U, kx1, rr[2] - U, head=False, tail=True, lw=0.9, size="sm")
# 跨列箭头：各按本行芯片实际边沿
conn("line", kx1 + wr[0] / 2, rr[0], kx2 - ws[0] / 2, rr[0],
     head=False, tail=True, lw=0.9, size="sm")   # 串口→Web
conn("line", kx1 + wr[1] / 2, rr[1], kx2 - ws[1] / 2, rr[1],
     head=True, tail=True, lw=0.9, size="sm")    # 帧级⇅HSM
conn("line", kx2 - ws[2] / 2, rr[2], kx1 + wr[2] / 2, rr[2],
     head=False, tail=True, lw=0.9, size="sm")   # 注册→模板库

# ================= 右下面板：UART 串口链路 =================
NX, NY, NW, NH = cm(66), cm(28.5), cm(33), cm(9)
panel(NX, NY, NW, NH, "UART 串口链路", "MAVLink v2 帧", adj=0.10)
kp = ["PMOD 电平移位模块", "USB 转串口线"]
wp = [chip_w(t) for t in kp]
pair = wp[0] + wp[1] + cm(3.0)
kx = NX + (NW - pair) / 2
ky = NY + cm(5.8)
chip(kx + wp[0] / 2, ky, kp[0])
chip(kx + wp[0] + cm(3.0) + wp[1] / 2, ky, kp[1])
conn("line", kx + wp[0], ky, kx + wp[0] + cm(3.0), ky,
     head=False, tail=True, lw=0.9, size="sm")

# ================= 区间连接（折线 + 三角头 + 旁注标签） =================
# 终端 ↔ 串口链路：S 曲线双头直连（出口下移至面板右下缘，弧线整段落空白带）
midL = LY + LH - cm(3.0)
conn("curve", LX + LW, midL, NX, ky, head=True, tail=True)
label(cm(45.5), cm(23.1), "PMOD1")
conn("line", cm(82.5), NY, cm(82.5), RY + RH, head=True, tail=True)
label(cm(85.2), cm(26.0), "USB")

# ---------- 保存 + PowerPoint 导出 ----------
# 成品只留 png（10-27 用户定）；pptx 为 COM 导出中间件，导出后即删（需手调时重跑本脚本再生）
pptx = os.path.join(OUT, "fig2-1_system_arch.pptx")
prs.save(pptx)

import win32com.client  # noqa: E402

app = win32com.client.Dispatch("PowerPoint.Application")
pres = app.Presentations.Open(pptx, ReadOnly=True, WithWindow=False)
pres.Slides(1).Export(os.path.join(OUT, "fig2-1_system_arch.png"), "PNG", 4157, 1706)
pres.Close()
app.Quit()
os.remove(pptx)
print("exported png")
