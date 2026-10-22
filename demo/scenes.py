"""有時間軸的動畫場景:桌寵把它畫在舞台卡片上,render_media.py 把它輸出成 MP4 / GIF。

每個場景都畫在 960 x 540 的座標系上,draw(p, t, wall, card):
  t     場景時間(秒),決定動畫進度
  wall  真實時間,只用來做眨眼、光暈脈動這類不影響進度的小動作
  card  True 時畫成半透明圓角卡片(桌寵),False 時鋪滿背景(影片)
"""

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen

from sprites import (BG, CLAY, FIELD_COLORS, GOLD, GREEN, INK, MUTED, PAPER, Confetti,
                     draw_badge, draw_bubble, draw_chip, draw_chip_glow, draw_clawd, draw_file, draw_folder,
                     draw_sparkle, draw_tag, font, text_width, with_alpha)

W, H = 960, 540
FLOOR = 482
PX = 7                      # 場景裡吉祥物的藝術像素大小
HANDS = FLOOR - 11 * PX     # 站在地上、雙手舉高時,手的頂端


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def seg(t, a, b):
    return clamp((t - a) / (b - a)) if b > a else float(t >= a)


def lerp(a, b, u):
    return a + (b - a) * u


def ease_io(u):
    return u * u * (3 - 2 * u)


def ease_out(u):
    return 1 - (1 - u) ** 3


def ease_back(u, s=1.8):
    u -= 1
    return 1 + u * u * ((s + 1) * u + s)


def typed(text, u):
    return text[:int(round(len(text) * clamp(u)))]


def lerp_rect(a: QRectF, b: QRectF, u):
    return QRectF(lerp(a.x(), b.x(), u), lerp(a.y(), b.y(), u), lerp(a.width(), b.width(), u),
                  lerp(a.height(), b.height(), u))


class Scene:
    duration = 10.0
    hold = None             # 需要等外部資料(例如現場 benchmark)時,時間停在這裡

    def __init__(self, data=None):
        self.data = data or {}
        self.pet_at = (0.0, 0.0)

    def ready(self):
        return True

    def waiting(self, t):
        return self.hold is not None and t >= self.hold and not self.ready()

    def draw(self, p: QPainter, t, wall, card=False):
        raise NotImplementedError

    # ---- 共用小工具 ----
    def pet(self, p, x, y, pose, t, wall, look=0):
        self.pet_at = (x, y)
        blink = (wall % 3.3) < 0.13 and pose not in ("happy", "climb")
        return draw_clawd(p, x, y, PX, pose, int(t * 9), look, blink)

    @staticmethod
    def backdrop(p: QPainter, card):
        rect = QRectF(0, 0, W, H)
        path = QPainterPath()
        if card:
            path.addRoundedRect(rect.adjusted(1, 1, -1, -1), 18, 18)
        else:
            path.addRect(rect)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillPath(path, QColor(BG.red(), BG.green(), BG.blue(), 244 if card else 255))
        p.setClipPath(path)
        p.setPen(QPen(QColor(255, 255, 255, 9), 1))
        for x in range(0, W, 24):
            p.drawLine(x, 0, x, H)
        for y in range(0, H, 24):
            p.drawLine(0, y, W, y)
        p.fillRect(QRectF(0, FLOOR, W, H - FLOOR), QColor(255, 255, 255, 7))
        p.setPen(QPen(QColor(255, 255, 255, 36), 2))
        p.drawLine(0, FLOOR, W, FLOOR)
        p.setClipping(False)
        if card:
            p.setPen(QPen(QColor(255, 255, 255, 50), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        p.restore()

    @staticmethod
    def caption(p: QPainter, text, alpha=1.0):
        if not text:
            return
        p.save()
        p.setOpacity(p.opacity() * alpha)
        p.setFont(font("ui", 16))
        p.setPen(with_alpha(PAPER, 0.85))
        p.drawText(QRectF(20, FLOOR + 10, W - 40, H - FLOOR - 16), Qt.AlignmentFlag.AlignCenter, text)
        p.restore()

    @staticmethod
    def title(p: QPainter, parts, sub=None, x=40, y=24, size=30, kind="mono"):
        """parts:[(文字, 顏色), ...];sub 是下方的灰色副標題。"""
        f = font(kind, size, True)
        p.setFont(f)
        for text, color in parts:
            p.setPen(color)
            p.drawText(QRectF(x, y, 2000, size * 1.5), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
            x += text_width(text, f)
        if sub:
            p.setFont(font("ui", 15))
            p.setPen(MUTED)
            p.drawText(QRectF(40, y + size * 1.55, W - 80, 24), Qt.AlignmentFlag.AlignLeft, sub)

    @staticmethod
    def pill(p: QPainter, right, y, text, color=MUTED):
        f = font("mono", 13, True)
        w = text_width(text, f) + 22
        r = QRectF(right - w, y, w, 28)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(color, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 14, 14)
        p.setFont(f)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
        p.restore()


# ====================================================================== ① 編碼組裝

class EncodeScene(Scene):
    """吉祥物把 funct7 / funct3 / opcode / rd / rs1 / rs2 方塊搬進 32-bit 指令,組出機器碼。"""

    LAYOUT = [("funct7", 31, 25), ("rs2", 24, 20), ("rs1", 19, 15),
              ("funct3", 14, 12), ("rd", 11, 7), ("opcode", 6, 0)]
    ORDER = ["funct7", "funct3", "opcode", "rd", "rs1", "rs2"]   # 先放固定欄位,再放暫存器
    PILE = ["rd", "opcode", "rs2", "funct3", "rs1", "funct7"]    # 地上方塊的擺放順序
    X0, BIT = 80, 25
    SLOT_Y, BH = 176, 54
    INTRO, STEP = 1.2, 1.75

    def __init__(self, data):
        super().__init__(data)
        enc = data["enc"]
        self.enc = enc
        self.objdump = data.get("objdump")
        self.f = {}
        for name, hi, lo in self.LAYOUT:
            n = hi - lo + 1
            self.f[name] = {"n": n, "bits": format(enc["fields"][name], f"0{n}b"),
                            "x": self.X0 + (31 - hi) * self.BIT, "w": n * self.BIT, "hi": hi, "lo": lo}
        x = 52
        for name in self.PILE:
            self.f[name]["pile"] = x
            x += self.f[name]["w"] + 12
        self.t_end = self.INTRO + len(self.ORDER) * self.STEP
        self.duration = self.t_end + 7.0

    def caption_for(self, name):
        f = self.f[name]
        if name in ("rd", "rs1", "rs2"):
            abi, num = self.enc["regs"][name]
            return f"{name} = {abi} = x{num} = {f['bits']}"
        return {
            "funct7": f"funct7 = {f['bits']} · 暫定值,待教師分配",
            "funct3": f"funct3 = {f['bits']} · 暫定值,待教師分配",
            "opcode": f"opcode = {f['bits']} · custom-0,RISC-V 保留給自訂指令",
        }[name]

    # ---- 時間軸 ----
    def slot_cx(self, name):
        f = self.f[name]
        return clamp(f["x"] + f["w"] / 2, 70, 890)

    def pile_cx(self, name):
        f = self.f[name]
        return f["pile"] + f["w"] / 2

    def track(self, t):
        """吉祥物在時間 t 的 (x, 往上跳的高度, 姿勢, 舉著的方塊, 眼睛方向)。"""
        if t < self.INTRO:
            return lerp(-60, 110, ease_io(seg(t, 0, self.INTRO))), 0, "walk", None, 1
        prev = 110
        for i, name in enumerate(self.ORDER):
            u = t - (self.INTRO + i * self.STEP)
            pile, slot = self.pile_cx(name), self.slot_cx(name)
            if u < self.STEP:
                if u < 0.55:
                    look = 1 if pile > prev else -1
                    return lerp(prev, pile, ease_io(u / 0.55)), 0, "walk", None, look
                if u < 0.75:
                    return pile, 0, "carry", name, 0
                if u < 1.30:
                    look = 1 if slot > pile else -1
                    return lerp(pile, slot, ease_io((u - 0.75) / 0.55)), 0, "carrywalk", name, look
                if u < 1.65:
                    return slot, math.sin(math.pi * (u - 1.30) / 0.35) * 26, "jump", None, 0
                return slot, 0, "idle", None, 0
            prev = slot
        u = t - self.t_end
        if u < 0.9:
            return lerp(prev, 870, ease_io(u / 0.9)), 0, "walk", None, 1
        if 2.6 < u < 5.0:
            return 870, abs(math.sin(math.pi * (u - 2.6) / 0.6)) * 26, "happy", None, 0
        return 870, 0, "happy" if u > 2.6 else "idle", None, -1 if u < 2.6 else 0

    def block_rect(self, name, t, pet_x, pet_dy):
        f = self.f[name]
        i = self.ORDER.index(name)
        u = t - (self.INTRO + i * self.STEP)
        pile = QRectF(f["pile"], FLOOR - self.BH, f["w"], self.BH)
        slot = QRectF(f["x"], self.SLOT_Y, f["w"], self.BH)
        carried = QRectF(pet_x - f["w"] / 2, HANDS - pet_dy - self.BH, f["w"], self.BH)
        if u < 0.55:
            return pile, False
        if u < 0.75:
            return lerp_rect(pile, carried, ease_out((u - 0.55) / 0.2)), False
        if u < 1.30:
            return carried, False
        if u < 1.65:
            v = (u - 1.30) / 0.35
            start = QRectF(self.slot_cx(name) - f["w"] / 2, HANDS - self.BH, f["w"], self.BH)
            r = lerp_rect(start, slot, ease_io(v))
            r.translate(0, -math.sin(math.pi * v) * 70)
            return r, False
        return slot, True

    # ---- 繪圖 ----
    def draw_block(self, p, name, r: QRectF, alpha=1.0, flash=0.0):
        f = self.f[name]
        color = FIELD_COLORS[name]
        p.save()
        p.setOpacity(p.opacity() * alpha)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(color.darker(150), 2))
        p.setBrush(color)
        p.drawRoundedRect(r, 6, 6)
        p.setPen(QPen(QColor(0, 0, 0, 40), 1))
        for k in range(1, f["n"]):
            x = r.left() + k * r.width() / f["n"]
            p.drawLine(QPointF(x, r.top() + 20), QPointF(x, r.bottom() - 4))
        p.setFont(font("ui", 12, True))
        p.setPen(with_alpha(INK, 0.75))
        p.drawText(QRectF(r.left(), r.top() + 2, r.width(), 18), Qt.AlignmentFlag.AlignCenter, name)
        p.setFont(font("mono", 20, True))
        p.setPen(INK)
        cw = r.width() / f["n"]
        for k, b in enumerate(f["bits"]):
            p.drawText(QRectF(r.left() + k * cw, r.top() + 18, cw, r.height() - 20), Qt.AlignmentFlag.AlignCenter, b)
        if flash > 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, int(170 * flash)))
            p.drawRoundedRect(r, 6, 6)
        p.restore()

    def draw_slots(self, p, alpha):
        p.save()
        p.setOpacity(p.opacity() * alpha)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for name, hi, lo in self.LAYOUT:
            f = self.f[name]
            r = QRectF(f["x"] + 2, self.SLOT_Y, f["w"] - 4, self.BH)
            pen = QPen(with_alpha(FIELD_COLORS[name], 0.75), 2, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(QColor(255, 255, 255, 6))
            p.drawRoundedRect(r, 6, 6)
            p.setFont(font("ui", 13, True))
            p.setPen(with_alpha(FIELD_COLORS[name], 0.8))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, name)
            p.setFont(font("mono", 11))
            p.setPen(MUTED)
            lab = QRectF(f["x"] + 3, self.SLOT_Y - 19, f["w"] - 6, 16)
            p.drawText(lab, Qt.AlignmentFlag.AlignLeft, str(hi))
            if hi != lo:
                p.drawText(lab, Qt.AlignmentFlag.AlignRight, str(lo))
        p.restore()

    def draw(self, p: QPainter, t, wall, card=False):
        self.backdrop(p, card)
        enc = self.enc
        asm = enc["asm"]
        head, rest = asm.split(" ", 1)
        shown = typed(asm, seg(t, 0.0, 0.7))
        self.title(p, [(shown[:len(head)], CLAY), (shown[len(head):], PAPER)],
                   "rd = rs1 循環左移 (rs2 & 31) 位   ·   R-type 32-bit 指令")
        self.pill(p, W - 40, 30, "custom-0 · opcode 0001011", CLAY)

        self.draw_slots(p, seg(t, 0.2, 0.9))

        x, dy, pose, carrying, look = self.track(t)
        placed = []
        for name in self.PILE:
            if name == carrying:
                continue
            r, done = self.block_rect(name, t, x, dy)
            if done:
                placed.append(name)
            else:
                self.draw_block(p, name, r)
        for name in placed:
            i = self.ORDER.index(name)
            land = self.INTRO + i * self.STEP + 1.65
            self.draw_block(p, name, self.block_rect(name, t, x, dy)[0], flash=1 - seg(t, land, land + 0.4))

        # 組好之後:由左到右掃過 32 個位元
        u_scan = seg(t, self.t_end + 0.2, self.t_end + 1.2)
        if 0 < u_scan < 1:
            k = u_scan * 32
            p.save()
            p.setPen(Qt.PenStyle.NoPen)
            for j in range(32):
                a = clamp(1 - (k - j) / 6) if j <= k else 0
                if a > 0:
                    p.setBrush(QColor(255, 255, 255, int(110 * a)))
                    p.drawRect(QRectF(self.X0 + j * self.BIT, self.SLOT_Y, self.BIT, self.BH))
            p.restore()

        word = enc["word"]
        hexd = f"{word:08X}"
        big = font("mono", 46, True)
        cw = text_width("0", big)
        start = W / 2 - 10 * cw / 2
        u_gather = ease_io(seg(t, self.t_end + 2.2, self.t_end + 2.9))
        for j in range(8):
            appear = self.t_end + 0.9 + j * 0.12
            if t < appear:
                continue
            pop = ease_back(seg(t, appear, appear + 0.35))
            x0, x1 = self.X0 + j * 100, self.X0 + (j + 1) * 100
            yb = self.SLOT_Y + self.BH + 8
            p.save()
            if u_gather < 1:
                p.setOpacity(1 - u_gather)
                p.setPen(QPen(MUTED, 2))
                p.drawLine(QPointF(x0 + 6, yb), QPointF(x1 - 6, yb))
                p.drawLine(QPointF(x0 + 6, yb - 5), QPointF(x0 + 6, yb))
                p.drawLine(QPointF(x1 - 6, yb - 5), QPointF(x1 - 6, yb))
                p.setOpacity(1)
            cx = lerp((x0 + x1) / 2, start + (2 + j) * cw + cw / 2, u_gather)
            cy = lerp(yb + 24, 330, u_gather)
            size = lerp(26, 46, u_gather) * max(pop, 0.01)
            p.setFont(font("mono", size, True))
            p.setPen(GOLD if u_gather < 1 else PAPER)
            p.drawText(QRectF(cx - 40, cy - 30, 80, 60), Qt.AlignmentFlag.AlignCenter, hexd[j])
            p.restore()

        if t >= self.t_end + 2.9:
            u = seg(t, self.t_end + 2.9, self.t_end + 3.3)
            p.save()
            p.setFont(big)
            p.setPen(with_alpha(MUTED, u))
            p.drawText(QRectF(start, 300, 2 * cw, 60), Qt.AlignmentFlag.AlignCenter, "0x")
            glow = 0.5 + 0.5 * math.sin(wall * 3)
            p.setPen(with_alpha(CLAY, 0.18 + 0.12 * glow))
            for ox, oy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                p.drawText(QRectF(start + 2 * cw + ox, 300 + oy, 8 * cw, 60), Qt.AlignmentFlag.AlignCenter, hexd)
            p.setPen(PAPER)
            p.drawText(QRectF(start + 2 * cw, 300, 8 * cw, 60), Qt.AlignmentFlag.AlignCenter, hexd)
            p.restore()

            le = " ".join(f"{b:02X}" for b in enc["le_bytes"])
            p.setFont(font("mono", 15))
            p.setPen(MUTED)
            p.drawText(QRectF(0, 366, W, 24), Qt.AlignmentFlag.AlignCenter,
                       typed(f"記憶體中(little-endian):{le}", seg(t, self.t_end + 3.2, self.t_end + 3.8)))
            if self.objdump:
                ex = self.objdump["examples"][0]
                line = (f"objdump {self.objdump['elf']}:{self.objdump['count']} 條 rotl · "
                        f"{ex['addr']:x}: {ex['word']:08x} {ex['asm']}")
                p.setPen(GREEN)
                p.drawText(QRectF(0, 394, W, 24), Qt.AlignmentFlag.AlignCenter,
                           typed(line, seg(t, self.t_end + 3.8, self.t_end + 5.0)))

        # 吉祥物和手上的方塊
        hands = self.pet(p, x, FLOOR - dy, pose, t, wall, look)
        if carrying:
            r, _ = self.block_rect(carrying, t, x, dy)
            self.draw_block(p, carrying, r)
        if t >= self.t_end + 2.9:
            for k in range(3):
                ph = (wall * 1.7 + k / 3) % 1
                if ph < 0.5:
                    a = k * 2.1 + 0.4
                    draw_sparkle(p, x + math.cos(a) * 64, hands - 6 + math.sin(a) * 30, 3,
                                 with_alpha(GOLD, 1 - ph * 2))

        if t < self.INTRO:
            cap = "把 6 個欄位搬進 32-bit 指令,組出 rotl 的機器碼"
        elif t < self.t_end:
            i = int((t - self.INTRO) // self.STEP)
            cap = self.caption_for(self.ORDER[min(i, 5)])
        else:
            cap = f"{asm}  =  0x{word:08X}   ·   C、組合語言、Python 都讀同一份 rotl_isa.h"
        self.caption(p, cap)


# ====================================================================== ② M5 晶片實測

class ChipScene(Scene):
    """吉祥物高舉發光的晶片,跳出 ChaCha20 與 RC5 的加速比。"""

    PET_X = 250
    CHARGE = 3.6

    def __init__(self, data):
        super().__init__(data)
        self.hw_lines = data["hw_lines"]
        self.results = data.get("results")
        self.progress = data.get("progress", [])
        self.live = data.get("live", False)
        self.chip_label = data.get("chip_label", "M5")
        self.hold = self.CHARGE if self.live else None
        self.duration = 11.5

    def ready(self):
        return self.results is not None

    def result(self, name):
        for r in self.results or []:
            if r["name"] == name:
                return r
        return None

    def draw(self, p: QPainter, t, wall, card=False):
        self.backdrop(p, card)
        self.title(p, [("M-series 晶片實測", PAPER)], "ARM64 的 ror(旋轉指令)vs lsl + lsr + orr(只能用移位),其餘程式完全相同",
                   size=28, kind="ui")
        self.pill(p, W - 40, 30, "experiments/arm64_rotate_bench.c", GOLD)

        # 吉祥物
        if t < 1.0:
            x, dy, pose = lerp(-60, self.PET_X, ease_io(seg(t, 0, 1.0))), 0, "walk"
        elif t > 6.0:
            x, dy, pose = self.PET_X, abs(math.sin(math.pi * (t - 6.0) / 0.65)) * 22, "happy"
        else:
            x, dy, pose = self.PET_X, 0, "carry"
        if 1.45 < t < 1.7:
            dy = -math.sin(math.pi * (t - 1.45) / 0.25) * 6      # 接住晶片時往下一沉
        cy_hold = FLOOR - dy - 11 * PX - 6 * 5 - 2     # 晶片底部的接腳剛好放在手上
        cy = lerp(-60, cy_hold, seg(t, 1.0, 1.45) ** 2)
        charging = t < self.CHARGE or not self.results       # 現場量測還沒結束時,停在充電畫面
        if t < self.CHARGE:
            glow = 0.15 + 0.5 * seg(t, 1.45, self.CHARGE)
        elif charging:
            glow = 0.55 + 0.15 * math.sin(wall * 5)
        else:
            glow = 0.88 + 0.12 * math.sin(wall * 4)
        if t >= 1.45:
            draw_chip_glow(p, x, cy, 5, glow, wall)
        self.pet(p, x, FLOOR - dy, pose, t, wall)
        if t >= 1.0:
            draw_chip(p, x, cy, 5, self.chip_label, glow if t >= 1.45 else 0)
            if not charging and t < self.CHARGE + 0.5:
                u = seg(t, self.CHARGE, self.CHARGE + 0.5)
                p.save()
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 240, 200, int(170 * (1 - u))))
                p.drawEllipse(QPointF(x, cy), 40 + 320 * u, 40 + 320 * u)
                p.restore()
            if not charging:
                for k in range(4):
                    ph = (wall * 1.3 + k / 4) % 1
                    if ph < 0.5:
                        a = k * 1.7 + 0.3
                        draw_sparkle(p, x + math.cos(a) * 95, cy + math.sin(a) * 70, 3,
                                     with_alpha(GOLD, 1 - ph * 2))

        # 右側:這台機器
        px0, pw = 520, 400
        p.setFont(font("ui", 15, True))
        p.setPen(PAPER)
        p.drawText(QRectF(px0, 104, pw, 22), Qt.AlignmentFlag.AlignLeft, "這台機器(sysctl 即時讀取)")
        for i, (label, value) in enumerate(self.hw_lines):
            u = seg(t, 1.5 + i * 0.3, 1.8 + i * 0.3)
            if u <= 0:
                break
            y = 132 + i * 22
            p.setFont(font("ui", 13))
            p.setPen(MUTED)
            p.drawText(QRectF(px0, y, 60, 20), Qt.AlignmentFlag.AlignLeft, label)
            p.setFont(font("mono", 13))
            p.setPen(PAPER)
            p.drawText(QRectF(px0 + 62, y, pw - 62, 20), Qt.AlignmentFlag.AlignLeft, typed(value, u))

        y0 = 132 + len(self.hw_lines) * 22 + 22
        p.setFont(font("ui", 15, True))
        p.setPen(PAPER)
        p.drawText(QRectF(px0, y0, pw, 22), Qt.AlignmentFlag.AlignLeft, "相對時間(SHIFT = 1.00,越短越快)")
        if charging:
            if t >= 1.6:
                dots = "." * (1 + int(wall * 3) % 3)
                p.setFont(font("ui", 14))
                p.setPen(GOLD)
                msg = "現場量測中" + dots if self.live else "量測中" + dots
                p.drawText(QRectF(px0, y0 + 30, pw, 20), Qt.AlignmentFlag.AlignLeft, msg)
                p.setFont(font("mono", 13))
                for i, r in enumerate(self.progress):
                    p.setPen(PAPER)
                    p.drawText(QRectF(px0, y0 + 56 + i * 22, pw, 20), Qt.AlignmentFlag.AlignLeft,
                               f"✓ {r['name']}  {r['speedup']:.2f}x")
        else:
            for i, r in enumerate(self.results):
                u = ease_out(seg(t, self.CHARGE + 1.4 + i * 0.35, self.CHARGE + 2.4 + i * 0.35))
                y = y0 + 32 + i * 50
                p.setFont(font("ui", 13))
                p.setPen(with_alpha(PAPER, clamp(u * 3)))
                p.drawText(QRectF(px0, y + 8, 120, 18), Qt.AlignmentFlag.AlignLeft, r["name"])
                bw = 170
                p.fillRect(QRectF(px0 + 120, y + 2, bw * clamp(u * 3), 12), QColor("#6B675F"))
                ror_w = bw / r["speedup"]
                p.fillRect(QRectF(px0 + 120, y + 20, lerp(bw, ror_w, u) * clamp(u * 3), 12), CLAY)
                p.setFont(font("mono", 11))
                p.setPen(with_alpha(MUTED, u))
                p.drawText(QRectF(px0 + 120 + bw + 6, y, 40, 16), Qt.AlignmentFlag.AlignLeft, "1.00")
                p.drawText(QRectF(px0 + 120 + lerp(bw, ror_w, u) + 6, y + 18, 40, 16), Qt.AlignmentFlag.AlignLeft,
                           f"{1 / r['speedup']:.2f}")
                p.setFont(font("mono", 18, True))
                p.setPen(with_alpha(GOLD, u))
                p.drawText(QRectF(px0 + pw - 66, y + 4, 66, 26), Qt.AlignmentFlag.AlignRight, f"{r['speedup']:.2f}x")

        # 從晶片跳出的加速比標籤
        if not charging:
            tags = [("ChaCha20 區塊", (128, 214), GOLD, INK), ("RC5 加密", (385, 200), CLAY, QColor("#FFFFFF"))]
            for i, (name, (tx, ty), color, tc) in enumerate(tags):
                r = self.result(name)
                if not r:
                    continue
                u = seg(t, self.CHARGE + 0.5 + i * 0.5, self.CHARGE + 1.3 + i * 0.5)
                if u <= 0:
                    continue
                cx, cyy = lerp(x, tx, ease_out(u)), lerp(cy, ty, ease_out(u)) - math.sin(math.pi * u) * 40
                bob = math.sin(wall * 2.2 + i) * 3 if u >= 1 else 0
                draw_tag(p, cx, cyy + bob, f"{r['speedup']:.2f}x", name, color, tc, scale=max(0.05, ease_back(u)))

        if charging:
            cap = ("Clawd 正在這台電腦上跑 benchmark(每個核心重複 15 次取最快)" if self.live
                   else "同一份 C 程式,只差旋轉的寫法:ror 一條 vs lsl/lsr/orr 三條")
        else:
            cap = "請看加速比,不要看 ns:絕對時間會隨核心種類與電源狀態變動"
        self.caption(p, cap)


# ====================================================================== ③ 終端機(影片版備案)

class TerminalScene(Scene):
    """現場 Demo 的影片備案:吉祥物爬上終端機,make test 全數通過後頭頂跳出 All Passed!"""

    WIN = QRectF(60, 240, 560, 230)

    def __init__(self, data):
        super().__init__(data)
        self.lines = data["lines"]
        self.checks = data["checks"]           # [(文字, "ok")...],依序揭曉
        self.duration = 11.0
        self.confetti = Confetti(seed=7)
        self.last_t = None
        self.burst = False

    def draw(self, p: QPainter, t, wall, card=False):
        self.backdrop(p, card)
        self.title(p, [("make test", PAPER)], "C 測資 + 69,000 次交叉比對 + UBSan + Python / RV32IM 模擬器測試",
                   size=28, kind="mono")
        win = self.WIN
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1.5))
        p.setBrush(QColor("#0E0E0D"))
        p.drawRoundedRect(win, 10, 10)
        bar = QRectF(win.left(), win.top(), win.width(), 26)
        path = QPainterPath()
        path.addRoundedRect(bar, 10, 10)
        path.addRect(QRectF(bar.left(), bar.top() + 12, bar.width(), 14))
        p.fillPath(path.simplified(), QColor("#2B2A28"))
        for i, c in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
            p.setBrush(QColor(c))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(win.left() + 16 + i * 18, win.top() + 13), 5.5, 5.5)
        p.setFont(font("mono", 12))
        p.setPen(MUTED)
        p.drawText(bar, Qt.AlignmentFlag.AlignCenter, "rotl — zsh")

        lh = 15.5
        rows = int((win.height() - 40) / lh)
        n = int(len(self.lines) * seg(t, 0.8, 3.2))
        visible = [f"$ {typed('make test', seg(t, 0.15, 0.7))}"] + self.lines[:n]
        visible = visible[-rows:]
        p.setFont(font("mono", 11.5))
        for i, line in enumerate(visible):
            ok = any(k in line for k in ("PASS", "... ok", "OK", "no undefined"))
            p.setPen(GREEN if ok else QColor("#D6D3CC"))
            p.drawText(QRectF(win.left() + 12, win.top() + 34 + i * lh, win.width() - 24, lh),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line[:76])
        p.restore()

        # 吉祥物:走過去、沿著右邊爬上去、跳到標題列上
        side_x = win.right() + 8 * PX
        top_x = win.right() - 90
        if t < 0.3:
            x, y, pose, look = 860, FLOOR, "idle", -1
        elif t < 1.1:
            x, y, pose, look = lerp(860, side_x, ease_io(seg(t, 0.3, 1.1))), FLOOR, "walk", -1
        elif t < 3.4:
            x, y, pose, look = side_x, lerp(FLOOR, win.top() + 22, ease_io(seg(t, 1.2, 3.4))), "climb", -1
        elif t < 3.85:
            u = seg(t, 3.4, 3.85)
            x = lerp(side_x, top_x, ease_io(u))
            y = lerp(win.top() + 22, win.top(), u) - math.sin(math.pi * u) * 46
            pose, look = "jump", -1
        else:
            x, y, pose, look = top_x, win.top(), "idle", 0
        passed_at = 3.9 + len(self.checks) * 0.45 + 0.2
        if t >= passed_at:
            pose = "happy"
            y -= abs(math.sin(math.pi * (t - passed_at) / 0.6)) * 20
        hands = self.pet(p, x, y, pose, t, wall, look)
        head = hands + PX

        if t >= 3.9:
            lines = []
            for i, (text, _) in enumerate(self.checks):
                shown = t >= 3.9 + (i + 1) * 0.45
                lines.append([("✓ " if shown else "… ", GREEN if shown else MUTED), (text, INK if shown else MUTED)])
            draw_bubble(p, x + 8 * PX, head + 30, lines, 14, side="right",
                        bounds=QRectF(10, 90, W - 20, FLOOR - 100))

        # 彩帶用固定的 1/60 秒步進,影片每次輸出都一樣
        if self.last_t is None or t < self.last_t:
            self.confetti = Confetti(seed=7)
            self.last_t, self.burst = t, False
        steps = int((t - self.last_t) * 60)
        for _ in range(steps):
            self.confetti.update(1 / 60)
        self.last_t += steps / 60
        if t >= passed_at:
            if not self.burst:
                self.confetti.burst(x, head - 40, 60, 560)
                self.burst = True
        self.confetti.draw(p, 4)
        if t >= passed_at:
            draw_badge(p, x, head - 12, "All Passed!", scale=ease_back(seg(t, passed_at, passed_at + 0.45)))
        self.caption(p, "make test 在 2.5 秒內跑完:69,000 次交叉比對 + 22 項測試全部通過")


# ====================================================================== 資料夾(桌寵導覽)

class FolderScene(Scene):
    """吉祥物把桌面上的 rotl 資料夾打開,內容一個個飛出來;點吉祥物就抽出下一個檔案。"""

    FOLDER_X, PET_X = 150, 290
    ROWS = [
        ("c_baseline/", "C 參考實作與測試", None),
        ("rv32im/", "RV32IM 組語、密碼學核心", None),
        ("spec/", "語意規格與編碼", None),
        ("  └ rotl_isa.h", "編碼常數(唯一設定來源)", "encode"),
        ("experiments/", "IC 驗證、pipeline、ARM64 實測", None),
        ("  └ arm64_rotate_bench.c", "Apple M5 實機量測", "chip"),
        ("report/", "CP1–CP3 報告與數據", None),
        ("Makefile", "make test / counts / verify", "terminal"),
    ]
    FILE_LABEL = {"encode": (".h", QColor("#4F9BE8")), "chip": (".c", GOLD), "terminal": ("MK", GREEN)}

    def __init__(self, data):
        super().__init__(data)
        self.stats = data["stats"]
        self.duration = 2.4
        self.pick = None            # (動作名稱, 開始時間)
        self.done = set()

    def row_y(self, i):
        return 136 + i * 36

    def pick_rect(self, action):
        i = next(k for k, r in enumerate(self.ROWS) if r[2] == action)
        return QRectF(400, self.row_y(i), 520, 32)

    def draw(self, p: QPainter, t, wall, card=False):
        self.backdrop(p, card)
        self.title(p, [("ROTL 自訂指令", PAPER)], "計算機組織 2026 · 32-bit 循環左移 · Clawd 從桌面拿來的資料夾",
                   size=26, kind="ui")

        folder_open = seg(t, 0.15, 0.55)
        draw_folder(p, self.FOLDER_X, FLOOR, 7, "rotl", folder_open)

        p.save()
        p.setFont(font("mono", 20, True))
        p.setPen(CLAY)
        p.drawText(QRectF(400, 100, 300, 28), Qt.AlignmentFlag.AlignLeft, "rotl/")
        commit = self.stats.get("commit", "")
        p.setFont(font("mono", 12))
        p.setPen(MUTED)
        p.drawText(QRectF(480, 104, 440, 24), Qt.AlignmentFlag.AlignRight, ("git " + commit)[:52])
        per_top = self.stats.get("per_top", {})
        for i, (name, desc, action) in enumerate(self.ROWS):
            appear = 0.5 + i * 0.12
            u = ease_out(seg(t, appear, appear + 0.45))
            if u <= 0:
                continue
            ry = self.row_y(i)
            sx, sy = self.FOLDER_X, FLOOR - 70
            x = lerp(sx, 400, u)
            y = lerp(sy, ry, u)
            p.setOpacity(u)
            r = QRectF(x, y, 520, 32)
            if action:
                on = self.pick and self.pick[0] == action
                pulse = 0.5 + 0.5 * math.sin(wall * 8) if on else 0
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(217, 119, 87, int(40 + 90 * pulse)) if action not in self.done else QColor(63, 185, 80, 40))
                p.drawRoundedRect(r, 8, 8)
            p.setFont(font("mono", 15, True))
            p.setPen(PAPER if not name.startswith(" ") else GOLD)
            p.drawText(QRectF(x + 12, y, 250, 32), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
            p.setFont(font("ui", 13))
            p.setPen(MUTED)
            count = per_top.get(name)
            tail = f"  ·  {count} 檔" if count else ""
            if action:
                tail = "  ✓" if action in self.done else "  ★"
            p.drawText(QRectF(x + 250, y, 266, 32), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       desc + tail)
        p.setOpacity(seg(t, 1.6, 2.2))
        lines = self.stats.get("lines", {})
        summary = (f"{self.stats.get('files', 0)} 個檔案 · C {lines.get('C', 0):,} 行 · Python {lines.get('Python', 0):,} 行"
                   f" · 組合語言 {lines.get('組合語言', 0):,} 行")
        p.setFont(font("ui", 13))
        p.setPen(MUTED)
        p.drawText(QRectF(400, 432, 520, 22), Qt.AlignmentFlag.AlignLeft, summary)
        p.restore()

        pose, carried = "idle", None
        if self.pick:
            action, t0 = self.pick
            u = seg(wall, t0, t0 + 0.7)
            pose = "carry"
            src = self.pick_rect(action)
            label, color = self.FILE_LABEL[action]
            hands_y = HANDS
            sx, sy = src.left() + 30, src.bottom()
            fx = lerp(sx, self.PET_X, ease_io(u))
            fy = lerp(sy, hands_y, ease_io(u)) - math.sin(math.pi * u) * 90
            carried = (fx, fy, label, color)
        self.pet(p, self.PET_X, FLOOR, pose, t, wall, -1 if t < 1.0 else 1)
        if carried:
            draw_file(p, carried[0], carried[1], 4, carried[2], carried[3])
        self.caption(p, "點 Clawd 繼續:① 編碼組裝 → ② M5 晶片實測 → ③ 終端機 make test")
