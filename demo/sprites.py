"""像素風的 Claude 吉祥物(Clawd)與道具。桌寵 pet.py 與影片輸出 render_media.py 共用。

座標慣例:
  - 吉祥物以「腳底中心」(x, y) 為錨點,方便站在地板、視窗頂端或場景的地面上
  - px 是一個「藝術像素」的邊長;同一張圖改 px 就能放大縮小,邊緣保持銳利
"""

import math
import random

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen,
                         QRadialGradient)

CLAY = QColor("#D97757")
CLAY_DARK = QColor("#B4583C")
CLAY_LIGHT = QColor("#EFA488")
INK = QColor("#1F1E1D")
OUTLINE = QColor(45, 22, 14, 235)
PAPER = QColor("#F5F0E8")
MUTED = QColor("#A39E93")
BG = QColor("#191817")
GREEN = QColor("#3FB950")
RED = QColor("#F85149")
GOLD = QColor("#F2C14E")

# R-type 六個欄位的顏色(編碼動畫與說明共用)
FIELD_COLORS = {
    "funct7": QColor("#E8A33D"),
    "rs2": QColor("#5FB878"),
    "rs1": QColor("#4F9BE8"),
    "funct3": QColor("#B07FE0"),
    "rd": QColor("#E8677A"),
    "opcode": CLAY,
}

GRID_W, GRID_H = 16, 10          # 吉祥物格子:身體 12 x 8,左右各 2 格手,下面 2 格腳
LEGS = (3, 5, 10, 12)


def font(kind="ui", size=14, bold=False):
    f = QFont("Menlo" if kind == "mono" else "PingFang TC")
    f.setPixelSize(max(1, int(size)))
    f.setBold(bold)
    return f


def text_width(text, fnt):
    return QFontMetricsF(fnt).horizontalAdvance(text)


def with_alpha(color, a):
    c = QColor(color)
    c.setAlphaF(max(0.0, min(1.0, c.alphaF() * a)))
    return c


# ---------------------------------------------------------------- 吉祥物

def clawd_rect(x, y, px):
    """吉祥物(含舉高的手)的外框,桌寵用來算點擊範圍與重繪範圍。"""
    return QRectF(x - GRID_W * px / 2, y - (GRID_H + 2) * px, GRID_W * px, (GRID_H + 2) * px)


def draw_clawd(p: QPainter, x, y, px, pose="idle", frame=0, look=0, blink=False, outline=True):
    """畫吉祥物,回傳雙手頂端的 y:舉東西時,道具的底部就放在這裡。

    pose:idle、walk、carry(雙手舉高)、carrywalk(舉著東西走)、climb、jump、happy、sad、wave、dangle
    frame:動畫影格(走路、爬牆、揮手用)
    look:眼睛方向,-1 左、0 前、1 右
    outline:深色描邊,放在彩色方塊或亮色桌布前面也看得清楚
    """
    px = max(1, int(px))
    ox = int(round(x)) - GRID_W * px // 2
    oy = int(round(y)) - GRID_H * px
    cells = []

    def cell(cx, cy, color, w=1, h=1):
        cells.append((cx, cy, color, w, h))

    lifted = set()
    bob = 0
    if pose in ("walk", "carrywalk", "climb"):
        phase = frame % 4
        lifted = {3, 10} if phase == 0 else {5, 12} if phase == 2 else set()
        bob = 1 if phase in (1, 3) else 0
    elif pose == "jump":
        lifted = set(LEGS)

    # 腳
    for lx in LEGS:
        cell(lx, 8, CLAY_DARK, 1, 1 if lx in lifted else 2)

    # 身體
    cell(2, bob, CLAY, 12, 8)
    cell(2, bob + 7, CLAY_DARK, 12, 1)
    cell(3, bob, CLAY_LIGHT, 3, 1)

    # 手
    def arm(side, kind):
        c = 0 if side < 0 else 14
        if kind == "rest":
            cell(c, bob + 4, CLAY, 2, 2)
        elif kind == "mid":
            cell(c, bob + 3, CLAY, 2, 2)
        elif kind == "up":
            cell(c, bob - 1, CLAY, 2, 7)
        elif kind == "down":
            cell(c, bob + 5, CLAY, 2, 2)

    if pose in ("carry", "carrywalk", "happy", "jump", "dangle"):
        arms = ("up", "up")
    elif pose == "climb":
        arms = ("up", "down") if frame % 4 < 2 else ("down", "up")
    elif pose == "walk":
        arms = {0: ("mid", "rest"), 2: ("rest", "mid")}.get(frame % 4, ("rest", "rest"))
    elif pose == "wave":
        arms = ("rest", "up" if frame % 2 else "mid")
    elif pose == "sad":
        arms = ("down", "down")
    else:
        arms = ("rest", "rest")
    arm(-1, arms[0])
    arm(1, arms[1])

    # 眼睛
    for ex in (5 + look, 10 + look):
        if pose == "happy":
            cell(ex - 1, bob + 3, INK)
            cell(ex, bob + 2, INK)
            cell(ex + 1, bob + 3, INK)
        elif blink:
            cell(ex, bob + 3, INK)
        elif pose == "sad":
            cell(ex, bob + 3, INK, 1, 2)
        elif pose == "climb":
            cell(ex - 1 if ex < 8 else ex, bob + 3, INK, 2, 1)
        else:
            cell(ex, bob + 2, INK, 1, 2)

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    if outline:
        o = max(1, px // 3)
        for cx, cy, _, w, h in cells:
            p.fillRect(ox + cx * px - o, oy + cy * px - o, w * px + 2 * o, h * px + 2 * o, OUTLINE)
    for cx, cy, color, w, h in cells:
        p.fillRect(ox + cx * px, oy + cy * px, w * px, h * px, color)
    p.restore()
    return oy + (bob - 1) * px


# ---------------------------------------------------------------- 道具

def draw_folder(p: QPainter, cx, bottom, px, label="", open_amount=0.0):
    """Finder 風格的像素資料夾,open_amount 0..1 會把前蓋往下打開、露出紙張。"""
    px = max(1, int(px))
    W, H = 18, 13
    ox = int(round(cx)) - W * px // 2
    oy = int(round(bottom)) - H * px
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    def cell(x, y, color, w=1, h=1):
        p.fillRect(ox + x * px, oy + y * px, w * px, h * px, color)

    back, front, hi, edge = QColor("#3D8FD1"), QColor("#69B4EE"), QColor("#93CBF4"), QColor("#2B6EA6")
    cell(0, 0, back, 7, 2)
    cell(0, 1, back, W, H - 1)
    if open_amount > 0:
        rise = int(round(3 * open_amount))
        cell(2, 2 - rise, QColor("#FBFAF7"), 13, 5)
        cell(4, 3 - rise, QColor("#D8D3CA"), 9, 1)
        cell(4, 5 - rise, QColor("#D8D3CA"), 7, 1)
    top = 3 + int(round(4 * open_amount))
    cell(0, top, front, W, H - top)
    cell(0, top, hi, W, 1)
    cell(0, H - 1, edge, W, 1)
    p.restore()

    if label:
        f = font("mono", px * 3, True)
        p.setFont(f)
        p.setPen(QColor("#FFFFFF"))
        r = QRectF(ox, oy + (top + 1) * px, W * px, (H - top - 2) * px)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)
    return QRectF(ox, oy, W * px, H * px)


def draw_file(p: QPainter, cx, bottom, px, label, color=CLAY):
    """摺角的文件圖示,label 寫在色帶上(例如 .h、.c、MK)。"""
    px = max(1, int(px))
    W, H = 10, 12
    ox = int(round(cx)) - W * px // 2
    oy = int(round(bottom)) - H * px
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    def cell(x, y, c, w=1, h=1):
        p.fillRect(ox + x * px, oy + y * px, w * px, h * px, c)

    cell(0, 0, QColor("#FBFAF7"), 7, H)
    cell(7, 3, QColor("#FBFAF7"), 3, H - 3)
    cell(7, 0, QColor("#D8D3CA"), 1, 3)
    cell(8, 1, QColor("#D8D3CA"), 1, 2)
    cell(9, 2, QColor("#D8D3CA"), 1, 1)
    cell(7, 2, QColor("#C9C3B8"), 3, 1)
    cell(0, 6, color, W, 4)
    p.restore()
    p.setFont(font("mono", px * 2.6, True))
    p.setPen(QColor("#FFFFFF"))
    p.drawText(QRectF(ox, oy + 6 * px, W * px, 4 * px), Qt.AlignmentFlag.AlignCenter, label)
    return QRectF(ox, oy, W * px, H * px)


def draw_chip_glow(p: QPainter, cx, cy, px, glow, t=0.0):
    """晶片後面的光暈與旋轉光芒(先畫,吉祥物才會擋在光芒前面)。"""
    if glow <= 0:
        return
    px = max(1, int(px))
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    r = px * (11 + 6 * glow + 0.8 * math.sin(t * 6))
    g = QRadialGradient(QPointF(cx, cy), r)
    g.setColorAt(0.0, QColor(255, 222, 140, int(230 * glow)))
    g.setColorAt(0.45, QColor(255, 176, 90, int(120 * glow)))
    g.setColorAt(1.0, QColor(255, 150, 60, 0))
    p.setBrush(g)
    p.drawEllipse(QPointF(cx, cy), r, r)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    ray = QColor(255, 226, 150, int(220 * glow))
    for k in range(8):
        a = t * 0.9 + k * math.pi / 4
        for d in range(9, 9 + int(3 + 5 * glow)):
            if (d + k) % 2:
                continue
            x = cx + math.cos(a) * d * px
            y = cy + math.sin(a) * d * px
            p.fillRect(int(x - px / 2), int(y - px / 2), px, px, ray)
    p.restore()


def draw_chip(p: QPainter, cx, cy, px, label="M5", glow=0.0):
    """像素晶片;glow 高的時候晶粒變成暖色。光暈另外用 draw_chip_glow 畫。"""
    px = max(1, int(px))
    N = 12
    ox = int(round(cx)) - N * px // 2
    oy = int(round(cy)) - N * px // 2
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    def cell(x, y, c, w=1, h=1):
        p.fillRect(ox + x * px, oy + y * px, w * px, h * px, c)

    pin = QColor("#D9B25F")
    for i in (2, 4, 7, 9):
        cell(i, 0, pin)
        cell(i, N - 1, pin)
        cell(0, i, pin)
        cell(N - 1, i, pin)
    cell(1, 1, QColor("#2D2C30"), 10, 10)
    cell(1, 1, QColor("#4A4950"), 10, 1)
    die = QColor("#3C3B42") if glow < 0.5 else QColor("#5A4636")
    cell(3, 3, die, 6, 6)
    cell(3, 3, QColor("#6B6A72"), 6, 1)
    p.restore()
    p.setFont(font("mono", px * 2.4, True))
    p.setPen(QColor("#FFFFFF") if glow < 0.5 else QColor("#FFE6A8"))
    p.drawText(QRectF(ox + 3 * px, oy + 3 * px, 6 * px, 6 * px), Qt.AlignmentFlag.AlignCenter, label)
    return QRectF(ox, oy, N * px, N * px)


def draw_sparkle(p: QPainter, x, y, px, color=GOLD, size=2):
    """十字形的像素閃光。"""
    px = max(1, int(px))
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    x, y = int(x), int(y)
    p.fillRect(x - px // 2, y - px // 2 - size * px, px, (2 * size + 1) * px, color)
    p.fillRect(x - px // 2 - size * px, y - px // 2, (2 * size + 1) * px, px, color)
    p.restore()


# ---------------------------------------------------------------- 對話框、標籤

def _segments(line):
    if isinstance(line, str):
        return [(line, INK)]
    return line


def draw_bubble(p: QPainter, ax, ay, lines, size=15, bounds=None, alpha=1.0, side="up"):
    """對話框,尾巴指向 (ax, ay)。

    lines:每行是字串,或 [(文字, 顏色), ...] 的片段串列
    side:"up" 對話框在錨點上方;"right" / "left" 在錨點右邊 / 左邊
    bounds:QRectF,對話框會被推回這個範圍內
    回傳對話框的 QRectF。
    """
    fnt = font("ui", size)
    fm = QFontMetricsF(fnt)
    pad, lh = size * 0.8, size * 1.45
    w = max(sum(fm.horizontalAdvance(t) for t, _ in _segments(l)) for l in lines) + 2 * pad
    h = len(lines) * lh + 2 * pad - (lh - size * 1.15)
    if side == "right":
        rect = QRectF(ax + 16, ay - h / 2, w, h)
    elif side == "left":
        rect = QRectF(ax - 16 - w, ay - h / 2, w, h)
    else:
        rect = QRectF(ax - w / 2, ay - 14 - h, w, h)
    if bounds is not None:
        dx = max(bounds.left() - rect.left(), 0) - max(rect.right() - bounds.right(), 0)
        dy = max(bounds.top() - rect.top(), 0) - max(rect.bottom() - bounds.bottom(), 0)
        rect.translate(dx, dy)

    path = QPainterPath()
    path.addRoundedRect(rect, 9, 9)
    tail = QPainterPath()
    if side == "right":
        ty = min(max(ay, rect.top() + 12), rect.bottom() - 12)
        tail.moveTo(rect.left() + 1, ty - 7)
        tail.lineTo(ax + 4, ay)
        tail.lineTo(rect.left() + 1, ty + 7)
    elif side == "left":
        ty = min(max(ay, rect.top() + 12), rect.bottom() - 12)
        tail.moveTo(rect.right() - 1, ty - 7)
        tail.lineTo(ax - 4, ay)
        tail.lineTo(rect.right() - 1, ty + 7)
    else:
        tx = min(max(ax, rect.left() + 14), rect.right() - 14)
        tail.moveTo(tx - 8, rect.bottom() - 1)
        tail.lineTo(ax, min(ay - 2, rect.bottom() + 12))
        tail.lineTo(tx + 8, rect.bottom() - 1)
    path = path.united(tail)

    p.save()
    p.setOpacity(p.opacity() * alpha)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(INK, 2.5))
    p.setBrush(PAPER)
    p.drawPath(path)
    p.setFont(fnt)
    y = rect.top() + pad
    for line in lines:
        x = rect.left() + pad
        for text, color in _segments(line):
            p.setPen(color)
            p.drawText(QRectF(x, y, 2000, lh), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, text)
            x += fm.horizontalAdvance(text)
        y += lh
    p.restore()
    return rect.adjusted(-4, -4, 4, 18)


def draw_badge(p: QPainter, cx, bottom, text, scale=1.0, color=GREEN, icon="check", alpha=1.0):
    """頭頂跳出的圓角標籤,左邊是打勾或打叉圖示。"""
    if scale <= 0.01:
        return QRectF(cx, bottom, 0, 0)
    fnt = font("ui", 22 * scale, True)
    h = 44 * scale
    w = text_width(text, fnt) + h + 22 * scale
    rect = QRectF(cx - w / 2, bottom - h, w, h)
    p.save()
    p.setOpacity(p.opacity() * alpha)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(INK, 2.5 * scale))
    p.setBrush(color)
    p.drawRoundedRect(rect, h / 2, h / 2)
    c = QPointF(rect.left() + h / 2 + 2 * scale, rect.center().y())
    p.setBrush(QColor("#FFFFFF"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(c, h * 0.34, h * 0.34)
    pen = QPen(color, 4.2 * scale)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    s = h * 0.17
    if icon == "check":
        path = QPainterPath(QPointF(c.x() - s, c.y()))
        path.lineTo(c.x() - s * 0.25, c.y() + s * 0.8)
        path.lineTo(c.x() + s * 1.05, c.y() - s * 0.75)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
    else:
        p.drawLine(QPointF(c.x() - s, c.y() - s), QPointF(c.x() + s, c.y() + s))
        p.drawLine(QPointF(c.x() - s, c.y() + s), QPointF(c.x() + s, c.y() - s))
    p.setFont(fnt)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(QRectF(rect.left() + h + 4 * scale, rect.top(), w - h - 4 * scale, h),
               Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
    p.restore()
    return rect.adjusted(-4, -4, 4, 4)


def draw_tag(p: QPainter, cx, cy, big, small, color, text_color=INK, scale=1.0, alpha=1.0):
    """加速比標籤:上面一行小字(核心名稱),下面大字(例如 1.51x)。"""
    if scale <= 0.01:
        return
    fb = font("mono", 34 * scale, True)
    fs = font("ui", 14 * scale, True)
    w = max(text_width(big, fb), text_width(small, fs)) + 30 * scale
    h = 78 * scale
    rect = QRectF(cx - w / 2, cy - h / 2, w, h)
    p.save()
    p.setOpacity(p.opacity() * alpha)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(INK, 3 * scale))
    p.setBrush(color)
    p.drawRoundedRect(rect, 12 * scale, 12 * scale)
    p.setPen(text_color)
    p.setFont(fs)
    p.drawText(QRectF(rect.left(), rect.top() + 8 * scale, w, 20 * scale), Qt.AlignmentFlag.AlignCenter, small)
    p.setFont(fb)
    p.drawText(QRectF(rect.left(), rect.top() + 26 * scale, w, 46 * scale), Qt.AlignmentFlag.AlignCenter, big)
    p.restore()


class Confetti:
    """彩帶粒子。seed 固定時,每次輸出的影片都一樣。"""

    COLORS = [CLAY, GOLD, GREEN, QColor("#4F9BE8"), QColor("#E8677A"), QColor("#B07FE0"), PAPER]

    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.parts = []

    def burst(self, x, y, n=48, speed=520):
        for _ in range(n):
            a = self.rng.uniform(-math.pi * 0.95, -math.pi * 0.05)
            v = self.rng.uniform(0.35, 1.0) * speed
            self.parts.append([x, y, math.cos(a) * v, math.sin(a) * v,
                               self.rng.choice(self.COLORS), self.rng.uniform(1.6, 2.6),
                               self.rng.uniform(0, 6.28)])

    def update(self, dt):
        for q in self.parts:
            q[2] *= 0.985
            q[3] = q[3] * 0.985 + 900 * dt
            q[0] += q[2] * dt
            q[1] += q[3] * dt
            q[5] -= dt
            q[6] += dt * 12
        self.parts = [q for q in self.parts if q[5] > 0]

    def draw(self, p: QPainter, px=4):
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for x, y, _, _, color, life, spin in self.parts:
            w = px if math.sin(spin) > 0 else px * 2
            p.fillRect(int(x), int(y), w, px * 3 - w, with_alpha(color, min(1.0, life * 2)))
        p.restore()

    def bounds(self):
        if not self.parts:
            return QRectF()
        xs = [q[0] for q in self.parts]
        ys = [q[1] for q in self.parts]
        return QRectF(min(xs) - 10, min(ys) - 10, max(xs) - min(xs) + 20, max(ys) - min(ys) + 20)
