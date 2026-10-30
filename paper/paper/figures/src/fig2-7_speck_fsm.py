# -*- coding: utf-8 -*-
"""图 2-7 Speck64/96 密码核状态机（10-27 五版竞标 E 版转正；PIL 直绘位图）。

事实源（src/rtl/common/speck64_96.v，一字不差）：
  3 个命名态 S_IDLE/S_KEY/S_ENC + default 回 S_IDLE（2 bit 编码共 4 态，
  对应正文 89 行"4 态有限状态机"）；S_IDLE--start-->S_KEY（装入 rk[0]/l0/l1
  与明文）；S_KEY 自环 rd_cnt < ROUNDS-1（L 滚动窗口生成轮密钥）；
  S_ENC 自环同条件，末轮输出密文置 done 回 S_IDLE；ROUNDS=26（正文常数）。
  53 cycles 属正文数值，不进图（示意不标实测值红线）。
语义色同图 2-6 v7：起点灰、过程蓝族浅调；图内零注释。
几何：1600×620 逻辑 px（与竞标期 vB/vC/vD 同构）；字体 msyh.ttc。
管线：4× 超采样画布（6400×2480）→ LANCZOS 缩到 3200×1240（抗锯齿全靠超采样），
  成品 462 dpi @17.6cm 打印宽。
"""
import os

from PIL import Image, ImageDraw, ImageFont

SS = 4                       # 超采样倍数
W, H = 1600, 620
INK = (11, 11, 11)
GRAY = (240, 239, 236)
BLUE = (205, 226, 251)
WHITE = (255, 255, 255)

img = Image.new("RGB", (W * SS, H * SS), WHITE)
d = ImageDraw.Draw(img)

F25 = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 25 * SS)
F24 = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 24 * SS)


def line(x1, y1, x2, y2, w=2.2, dash=None):
    x1, y1, x2, y2, lw = x1 * SS, y1 * SS, x2 * SS, y2 * SS, int(w * SS)
    if dash is None:
        d.line([x1, y1, x2, y2], fill=INK, width=lw)
        return
    import math
    on, off = dash[0] * SS, dash[1] * SS
    n = math.hypot(x2 - x1, y2 - y1)
    if n == 0:
        return
    ux, uy = (x2 - x1) / n, (y2 - y1) / n
    s = 0.0
    while s < n:
        e = min(s + on, n)
        d.line([x1 + ux * s, y1 + uy * s, x1 + ux * e, y1 + uy * e],
               fill=INK, width=lw)
        s = e + off


def head(x, y, ux, uy, w=11):
    """箭头三角：尖端在终点 (x,y)，底边在其后方。"""
    s = w * SS
    px, py = -uy, ux
    tip = (x * SS, y * SS)
    b1 = ((x - ux * w * 0.9) * SS + px * s * 0.5, (y - uy * w * 0.9) * SS + py * s * 0.5)
    b2 = ((x - ux * w * 0.9) * SS - px * s * 0.5, (y - uy * w * 0.9) * SS - py * s * 0.5)
    d.polygon([tip, b1, b2], fill=INK)


def arrow(x1, y1, x2, y2, dash=None):
    import math
    n = math.hypot(x2 - x1, y2 - y1)
    ux, uy = (x2 - x1) / n, (y2 - y1) / n
    line(x1, y1, x2 - ux * 9, y2 - uy * 9, dash=dash)   # 线止于箭头底
    head(x2, y2, ux, uy)


def rbox(x, y, w, h, fill, r=17, lw=2.0, dashed=False):
    if not dashed:
        d.rounded_rectangle([x * SS, y * SS, (x + w) * SS, (y + h) * SS],
                            radius=r * SS, fill=fill, outline=INK,
                            width=int(lw * SS))
        return
    # 虚线圆角框：四条虚直边 + 四段实圆角
    d.rounded_rectangle([x * SS, y * SS, (x + w) * SS, (y + h) * SS],
                        radius=r * SS, fill=fill)
    ri = r
    line(x + ri, y, x + w - ri, y, dash=(9, 7))
    line(x + ri, y + h, x + w - ri, y + h, dash=(9, 7))
    line(x, y + ri, x, y + h - ri, dash=(9, 7))
    line(x + w, y + ri, x + w, y + h - ri, dash=(9, 7))
    for cx, cy, a0, a1 in [(x + w - ri, y + ri, -90, 0), (x + w - ri, y + h - ri, 0, 90),
                           (x + ri, y + h - ri, 90, 180), (x + ri, y + ri, 180, 270)]:
        d.arc([(cx - ri) * SS, (cy - ri) * SS, (cx + ri) * SS, (cy + ri) * SS],
              a0, a1, fill=INK, width=int(lw * SS))


def text(cx, cy, s, font, anchor="mm"):
    d.text((cx * SS, cy * SS), s, font=font, fill=INK, anchor=anchor)


def state(x, y, w, name, action, fill, dashed=False):
    rbox(x, y, w, 112, fill, dashed=dashed)
    text(x + w / 2, y + 34, name, F25)
    text(x + w / 2, y + 78, action, F24)


# ================= 四态 =================
state(80, 200, 288, "IDLE", "等待 start", GRAY)
state(656, 200, 288, "KEY_EXPAND", "轮密钥扩展", BLUE)
state(1232, 200, 288, "ENCRYPT", "26 轮 ARX 迭代", BLUE)
rbox(80, 428, 288, 104, WHITE, dashed=True)
text(224, 462, "非法编码", F25)
text(224, 502, "默认回 IDLE", F24)

# ================= 流转箭头 =================
arrow(368, 256, 656, 256)
arrow(944, 256, 1232, 256)
text(512, 218, "start：装入密钥与明文", F24)
text(1088, 218, "轮密钥就绪", F24)

# 自环
arrow(744, 312, 744, 384)
line(744, 384, 856, 384)
arrow(856, 384, 856, 312)
text(800, 413, "rd_cnt < ROUNDS−1", F24)
arrow(1320, 312, 1320, 384)
line(1320, 384, 1432, 384)
arrow(1432, 384, 1432, 312)
text(1376, 413, "rd_cnt < ROUNDS−1", F24)

# 回环
arrow(1376, 200, 1376, 80)
line(1376, 80, 224, 80)
arrow(224, 80, 224, 200)
text(800, 51, "末轮：输出密文，done", F24)

# 非法编码 → IDLE（虚线 + 实线短接）
line(224, 428, 224, 405, dash=(9, 7))
arrow(224, 405, 224, 312)
text(312, 368, "default", F24)

# ================= 导出（超采样 → LANCZOS 缩回；成品只留 png） =================
out = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
img.resize((3200, 1240), Image.LANCZOS).save(os.path.join(out, "fig2-7_speck_fsm.png"))
print("done:", out)
