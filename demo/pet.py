"""Claude 吉祥物桌寵:跳去桌面拿 rotl 資料夾,現場展示編碼、M5 實測與 make test。

    .venv/bin/python demo/pet.py            (或 make pet)
    .venv/bin/python demo/pet.py --tour     啟動後直接開始導覽

操作:
  雙擊吉祥物          開始導覽:去桌面拿 rotl 資料夾,依序展示 ① 指令怎麼變成 0 和 1 ② 實測快多少 ③ 自動測試
  左鍵點吉祥物        導覽中:下一步;動畫播放中:快轉;平常:講一個專案小知識
  拖曳                把吉祥物抓起來丟到別的地方
  右鍵 / 選單列圖示    選單:個別展示、硬體資訊、監看終端機、結束

系統操作都在 osbridge.py:AppleScript(Finder 圖示位置、開 Terminal、讀視窗位置與內容)、
sysctl(硬體)、ps(偵測測試指令)、cc + script(現場 benchmark)、objdump(機器碼)、
ctypes 直接呼叫 Objective-C runtime(視窗浮在所有桌面空間上方、不顯示 Dock 圖示)。
"""

import argparse
import math
import random
import shlex
import sys
import threading
import time
import traceback

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

import osbridge as osb
import scenes
from scenes import FLOOR, clamp, ease_back, ease_io, lerp, seg
from sprites import (CLAY, GOLD, GREEN, INK, MUTED, RED, Confetti, clawd_rect, draw_badge, draw_bubble,
                     draw_chip, draw_chip_glow, draw_clawd, draw_file, draw_folder, draw_sparkle,
                     with_alpha)

GRAVITY = 2600
WALK = 260
CLIMB = 210

FACTS = [
    ["ROTL 是「循環左移」:", "往左推,掉出去的位元從右邊補回來"],
    ["沒有 ROTL 要 4 條指令才拼得出來,", "有了它 1 條就搞定"],
    ["轉 0 格是 C 語言的陷阱:", "會變成「右移 32 格」,結果沒有保證"],
    ["ChaCha20 加密一次,", "要跑的指令從 1919 條減到 1284 條"],
    ["RC5 加密一次,", "要跑的指令從 227 條減到 131 條"],
    ["新指令放在 RISC-V 預留的", "「自訂指令專區」,不會跟別的指令撞號"],
    ["make test 會自動對答案 69,000 次,", "確認每個結果都正確"],
    ["換算成 CPU 的時脈數,", "大約快 1.2 到 1.7 倍"],
    ["在這台 M5 上實際計時:", "有旋轉指令快 1.3 到 1.5 倍"],
]


class Job:
    """在背景執行緒跑一次會卡住的系統呼叫,主執行緒每個影格檢查 done。"""

    def __init__(self, fn, *args):
        self.done, self.result, self.error = False, None, None
        threading.Thread(target=self._run, args=(fn, args), daemon=True).start()

    def _run(self, fn, args):
        try:
            self.result = fn(*args)
        except Exception as e:  # 背景工作失敗不能讓桌寵當掉
            self.error = e
        finally:
            self.done = True


class Poller:
    """背景執行緒每隔 interval 秒呼叫 fn,value 保留最新一次不是 None 的結果。"""

    def __init__(self, fn, interval):
        self.fn, self.interval = fn, interval
        self.value, self.count, self.alive = None, 0, True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while self.alive:
            try:
                v = self.fn()
                if v is not None:
                    self.value = v
            except Exception:
                pass
            self.count += 1
            time.sleep(self.interval)

    def stop(self):
        self.alive = False


def prefetch():
    return {"hw": osb.hardware_info(), "stats": osb.project_stats(),
            "objdump": osb.objdump_rotl(), "enc": osb.encoding_data()}


# ====================================================================== 視窗

class Overlay(QWidget):
    """蓋住整個螢幕、滑鼠會穿透的透明圖層;吉祥物和所有特效都畫在這裡。"""

    def __init__(self, pet):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        for attr in (Qt.WidgetAttribute.WA_TranslucentBackground, Qt.WidgetAttribute.WA_ShowWithoutActivating,
                     Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow):
            self.setAttribute(attr)
        self.pet = pet
        self.setGeometry(pet.geo.toRect())

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(ev.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.translate(-self.pet.geo.left(), -self.pet.geo.top())
        try:
            self.pet.paint(p)
        except Exception:
            traceback.print_exc()
        p.end()


class HitBox(QWidget):
    """跟著吉祥物移動的小視窗,負責接收點擊、拖曳與右鍵(圖層本身不接收滑鼠)。"""

    def __init__(self, pet):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        for attr in (Qt.WidgetAttribute.WA_TranslucentBackground, Qt.WidgetAttribute.WA_ShowWithoutActivating,
                     Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow):
            self.setAttribute(attr)
        self.pet = pet
        self.press = None
        self.dragged = False
        self.single = QTimer(self, singleShot=True, interval=QApplication.doubleClickInterval())
        self.single.timeout.connect(pet.on_click)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 2))   # 完全透明的地方 macOS 會讓滑鼠穿透
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.press = e.globalPosition()
            self.dragged = False

    def mouseMoveEvent(self, e):
        if self.press is None:
            return
        g = e.globalPosition()
        if not self.dragged and (g - self.press).manhattanLength() > 6:
            self.dragged = self.pet.drag_start()
        if self.dragged:
            self.pet.drag_move(g.x(), g.y())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self.pet.menu.popup(e.globalPosition().toPoint())
            return
        if e.button() != Qt.MouseButton.LeftButton or self.press is None:
            return
        if self.dragged:
            self.pet.drag_end()
        else:
            self.single.start()
        self.press = None

    def mouseDoubleClickEvent(self, e):
        self.single.stop()
        self.press = None
        self.pet.on_double_click()

    def contextMenuEvent(self, e):
        # macOS 在「按下」右鍵時就送出這個事件;吉祥物站在螢幕底部,選單會往上開,
        # 最後一項「結束」剛好在游標下,放開右鍵就會誤按。所以改成放開右鍵時才打開選單。
        e.accept()


# ====================================================================== 桌寵

class Pet:
    def __init__(self, qapp, args):
        screen = qapp.primaryScreen()
        self.geo = QRectF(screen.geometry())
        self.avail = QRectF(screen.availableGeometry())
        self.floor = self.avail.bottom() - 1
        self.px = args.scale
        self.x, self.y, self.vy = self.avail.center().x(), self.avail.top() - 40, 0.0
        self.pose, self.look, self.anim = "jump", 0, 0.0
        self.carry = None             # ("folder",)、("file", 標籤, 顏色)、("chip",)
        self.visible = True
        self.bubble = None            # {"lines", "until", "side"}
        self.badge = None             # {"text", "t0", "color", "icon"}
        self.sparkles = []            # [x, y, t0]
        self.confetti = Confetti()
        self.stage = None
        self.perch = None             # 坐在終端機視窗上:(位置 Poller, 靠右?, 水平偏移)
        self.script, self.kind = None, None
        self.wait_click = self.clicked = False
        self.dragging = False
        self.auto = args.auto
        self.handled = set()
        self.time = 0.0
        self.next_idle = 4.0
        self.painted = QRectF()
        self.painted_now = QRectF()
        self.data = Job(prefetch)
        self.procs = Poller(osb.test_processes, 1.0) if args.watch else None

        self.overlay = Overlay(self)
        self.hit = HitBox(self)
        self.menu = self.build_menu()
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.icon())
            self.tray.setToolTip("Clawd · rotl 桌寵")
            self.tray.setContextMenu(self.menu)
            self.tray.show()

        self.overlay.show()
        self.hit.show()
        osb.mac_pin_window(self.overlay)
        osb.mac_pin_window(self.hit)

        self.last = time.monotonic()
        self.timer = QTimer(timeout=self.tick, interval=16)
        self.timer.start()
        self.say(["嗨!我是 Clawd", [("雙擊我", CLAY), ("開始導覽,右鍵看選單", INK)]], 6)
        if args.tour:
            QTimer.singleShot(1500, lambda: self.start(self.tour(), "tour"))

    # ---------------------------------------------------------------- 選單
    def icon(self):
        pm = QPixmap(64, 64)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        draw_clawd(p, 32, 52, 4, outline=False)
        p.end()
        return QIcon(pm)

    def build_menu(self):
        menu = QMenu()

        def add(text, fn, checkable=False, checked=False):
            act = QAction(text, menu, checkable=checkable, checked=checked)
            act.triggered.connect(fn)
            menu.addAction(act)
            return act

        add("🗂  拿資料夾展示(完整導覽)", lambda: self.start(self.tour(), "tour"))
        menu.addSeparator()
        add("①  指令怎麼變成 0 和 1(編碼)", lambda: self.start(self.standalone("encode"), "show"))
        add("②  在這台電腦上實測快多少", lambda: self.start(self.standalone("chip"), "show"))
        add("③  跑自動測試(make test)", lambda: self.start(self.run_terminal(), "terminal"))
        menu.addSeparator()
        add("💻  這台電腦的硬體規格", lambda: self.start(self.show_hw(), "show"))
        add("📂  在 Finder 打開 rotl", lambda: Job(osb.run, ["open", str(osb.ROOT)]))
        menu.addSeparator()
        self.watch_act = add("我在終端機跑測試時,Clawd 也來看", self.toggle_watch, True, self.procs is not None)
        add("導覽自動播放(不用點)", lambda c: setattr(self, "auto", c), True, self.auto)
        add("停止目前動作", self.stop)
        menu.addSeparator()
        # 結束放在子選單裡,要多點一下,避免誤按就把桌寵關掉
        quit_menu = menu.addMenu("結束桌寵")
        act = QAction("確定結束", quit_menu)
        act.triggered.connect(self.quit)
        quit_menu.addAction(act)
        return menu

    def quit(self):
        print("Clawd:收到選單的「結束」,關閉桌寵", flush=True)
        QApplication.quit()

    def toggle_watch(self, on):
        if on and not self.procs:
            self.procs = Poller(osb.test_processes, 1.0)
        elif not on and self.procs:
            self.procs.stop()
            self.procs = None

    # ---------------------------------------------------------------- 腳本
    def start(self, gen, kind):
        self.stop()
        self.kind = kind
        self.script = gen
        self.step(None)

    def step(self, dt):
        try:
            self.script.send(dt)
        except StopIteration:
            self.script, self.kind = None, None
            self.wait_click = False
        except Exception:
            traceback.print_exc()
            self.stop()

    def stop(self):
        if self.script:
            try:
                self.script.close()
            except Exception:
                traceback.print_exc()
        self.script, self.kind = None, None
        self.wait_click = False
        self.perch = None
        self.carry = None
        if self.stage:
            if not self.visible:
                sx, sy = self.stage["scene"].pet_at
                self.x, self.y = self.stage_to_global(sx, sy)
            self.stage["closing"] = True
        self.visible = True

    def wait(self, secs):
        t = 0.0
        while t < secs:
            t += yield

    def job(self, fn, *args):
        j = Job(fn, *args)
        while not j.done:
            yield
        return j

    def wait_data(self):
        while not self.data.done:
            yield
        return self.data.result or {}

    def wait_for_click(self, hint="▶ 點我繼續"):
        if self.auto:
            yield from self.wait(3.0)
            return
        self.clicked = False
        self.wait_click = True
        self.say([[(hint, MUTED)]], 1e9)
        while not self.clicked:
            yield
        self.wait_click = False
        self.bubble = None

    def land(self):
        if self.y < self.floor and not self.perch:
            yield from self.fall()

    def walk_to(self, x, speed=WALK):
        x = clamp(x, self.avail.left() + 8 * self.px, self.avail.right() - 8 * self.px)
        while abs(self.x - x) > 1:
            dt = yield
            self.look = 1 if x > self.x else -1
            self.x += clamp(x - self.x, -speed * dt, speed * dt)
            self.pose = "carrywalk" if self.carry else "walk"
            self.anim += dt
        self.pose = "carry" if self.carry else "idle"
        self.look = 0

    def jump_to(self, x, y, dur=0.7, height=80):
        x0, y0 = self.x, self.y
        t = 0.0
        while t < dur:
            t += yield
            u = clamp(t / dur)
            self.x = lerp(x0, x, ease_io(u))
            self.y = lerp(y0, y, u) - math.sin(math.pi * u) * height
            self.pose = "jump"
        self.x, self.y = x, y
        self.pose = "carry" if self.carry else "idle"

    def fall(self):
        self.vy = 0.0
        while self.y < self.floor:
            dt = yield
            self.vy += GRAVITY * dt
            self.y = min(self.floor, self.y + self.vy * dt)
            self.pose = "jump"
        self.vy = 0.0
        self.pose = "carry" if self.carry else "idle"

    def say(self, lines, secs=3.0, side="up"):
        if isinstance(lines, str):
            lines = [lines]
        self.bubble = {"lines": lines, "until": self.time + secs, "side": side}

    def sparkle_burst(self, x, y, n=6):
        for k in range(n):
            a = k * 2 * math.pi / n
            self.sparkles.append([x + math.cos(a) * 44, y + math.sin(a) * 30, self.time + k * 0.05])

    # ---------------------------------------------------------------- 舞台(卡片)
    def open_stage(self, scene, paused=True):
        scale = min(1.0, self.avail.width() * 0.92 / scenes.W, self.avail.height() * 0.86 / scenes.H)
        w, h = scenes.W * scale, scenes.H * scale
        rect = QRectF(self.avail.center().x() - w / 2, self.avail.center().y() - h / 2, w, h)
        self.stage = {"scene": scene, "t": 0.0, "rect": rect, "scale": scale, "alpha": 0.0,
                      "closing": False, "paused": paused}

    def stage_to_global(self, sx, sy):
        st = self.stage
        return st["rect"].left() + sx * st["scale"], st["rect"].top() + sy * st["scale"]

    def set_scene(self, scene, t=0.0):
        self.stage.update(scene=scene, t=t, paused=False)

    def play_scene(self, scene):
        self.set_scene(scene)
        while self.stage and self.stage["scene"] is scene and self.stage["t"] < scene.duration:
            yield

    def enter_stage(self, scene, sx, sy):
        """從桌面跳進舞台卡片,落地後換成場景裡的吉祥物。"""
        self.open_stage(scene)
        gx, gy = self.stage_to_global(sx, sy)
        yield from self.jump_to(gx, gy, 0.8, 140)
        self.visible = False
        self.carry = None

    def leave_stage(self):
        """從舞台跳回桌面,卡片淡出。"""
        if not self.stage:
            return
        if not self.visible:
            sx, sy = self.stage["scene"].pet_at
            self.x, self.y = self.stage_to_global(sx, sy)
            self.visible = True
        self.stage["closing"] = True
        yield from self.fall()

    def update_stage(self, dt):
        st = self.stage
        if not st:
            return
        target = 0.0 if st["closing"] else 1.0
        st["alpha"] += clamp(target - st["alpha"], -dt * 4, dt * 4)
        if st["closing"] and st["alpha"] <= 0:
            self.stage = None
            return
        sc = st["scene"]
        if not st["paused"] and not sc.waiting(st["t"]):
            st["t"] = min(st["t"] + dt, sc.duration)

    # ---------------------------------------------------------------- 腳本:導覽
    def tour(self):
        yield from self.land()
        data = yield from self.wait_data()
        self.say("我去桌面拿 rotl 資料夾!", 2.0)
        yield from self.wait(0.8)
        j = yield from self.job(osb.finder_icon_pos)
        icon = j.result
        if icon:
            ix, iy = icon
            yield from self.walk_to(ix)
            yield from self.jump_to(ix, iy + 34 + 11 * self.px, 0.75, 70)
            self.sparkle_burst(ix, iy)
        else:
            self.say("桌面上沒看到圖示,我直接從專案路徑拿!", 2.5)
            yield from self.wait(0.6)
        self.carry = ("folder",)
        yield from self.wait(0.3)
        yield from self.fall()
        self.say("找到了!一起來看看裡面有什麼", 2.0)
        yield from self.wait(1.2)

        folder = scenes.FolderScene({"stats": data.get("stats", {})})
        yield from self.enter_stage(folder, folder.PET_X, FLOOR)
        yield from self.play_scene(folder)
        stats = data.get("stats", {})
        self.say(f"ROTL 專案:{stats.get('files', '?')} 個檔案", 2.5)
        yield from self.wait(1.5)

        for action in ("encode", "chip", "terminal"):
            yield from self.wait_for_click("▶ 點我抽出檔案")
            if self.stage and self.stage["scene"] is not folder:
                self.set_scene(folder, folder.duration)
            folder.pick = (action, self.time)
            yield from self.wait(1.0)
            folder.pick = None
            folder.done.add(action)
            if action == "encode":
                yield from self.play_scene(self.encode_scene(data))
            elif action == "chip":
                yield from self.play_chip(data)
            else:
                yield from self.run_terminal()
                yield from self.wait_for_click("▶ 點我把資料夾放回去")
                break
            yield from self.wait_for_click()
            self.set_scene(folder, folder.duration)

        yield from self.leave_stage()
        self.carry = ("folder",)
        self.say("Demo 結束,資料夾放回桌面!", 2.5)
        yield from self.wait(1.0)
        if icon:
            yield from self.walk_to(icon[0])
            yield from self.jump_to(icon[0], icon[1] + 34 + 11 * self.px, 0.75, 70)
            self.carry = None
            self.sparkle_burst(icon[0], icon[1])
            yield from self.wait(0.3)
            yield from self.fall()
        self.carry = None
        self.pose = "wave"
        for k in range(8):
            self.anim = k
            yield from self.wait(0.18)
        self.pose = "idle"

    def standalone(self, kind):
        yield from self.land()
        data = yield from self.wait_data()
        scene = self.encode_scene(data) if kind == "encode" else self.chip_scene(data)
        yield from self.enter_stage(scene, -30, FLOOR)
        if kind == "encode":
            yield from self.play_scene(scene)
        else:
            yield from self.play_chip(data, scene)
        yield from self.wait_for_click("▶ 點我收起來")
        yield from self.leave_stage()

    def encode_scene(self, data):
        return scenes.EncodeScene({"enc": data.get("enc") or osb.encoding_data(), "objdump": data.get("objdump")})

    def chip_scene(self, data):
        hw = data.get("hw") or {}
        label = next((w for w in hw.get("chip", "").split() if w[:1] == "M" and w[1:2].isdigit()), "CPU")
        return scenes.ChipScene({"hw_lines": osb.hardware_lines(hw) if hw else [], "results": None,
                                 "progress": [], "live": True, "chip_label": label})

    def play_chip(self, data, scene=None):
        """晶片場景:吉祥物舉著晶片「充電」,背景同時在這台電腦上編譯並執行 benchmark。"""
        scene = scene or self.chip_scene(data)
        if osb.bench_available():
            bench = Job(osb.bench_rows, scene.progress.append)
        else:
            bench = None
            scene.live, scene.hold = False, None
            scene.results = [dict(r) for r in osb.DOC_SPEEDUPS]
        self.set_scene(scene)
        while self.stage and self.stage["scene"] is scene and self.stage["t"] < scene.duration:
            if bench and bench.done and scene.results is None:
                scene.results = bench.result or [dict(r) for r in osb.DOC_SPEEDUPS]
            yield

    # ---------------------------------------------------------------- 腳本:終端機
    def run_terminal(self, launch=True, tty=None):
        """開 Terminal 跑 make test,爬上視窗等結果。

        launch=False:使用者自己在終端機打了測試指令,tty 是那個行程的終端機裝置。
        """
        pollers = []
        try:
            if self.stage:
                yield from self.leave_stage()
            if self.y < self.floor and not self.perch:
                yield from self.fall()
            if launch:
                try:
                    osb.TEST_LOG.unlink()
                except FileNotFoundError:
                    pass
                a = self.avail
                w, h = min(820, a.width() * 0.5), min(500, a.height() * 0.5)
                left, top = a.left() + 70, a.top() + a.height() * 0.24
                self.say("我來跑自動測試(make test)!", 2.5)
                j = yield from self.job(osb.terminal_open, f"clear; sh {shlex.quote(str(osb.RUN_TESTS))}",
                                        (left, top, left + w, top + h))
                win = j.result
                if win is None:
                    self.say(["打不開 Terminal 😢",
                              [("系統設定 → 隱私權與安全性 → 自動化", MUTED)], "允許控制 Terminal 後再試一次"], 6)
                    return
                text = Poller(lambda: osb.TEST_LOG.read_text(errors="replace") if osb.TEST_LOG.exists() else "", 0.25)
                bounds = Poller(lambda: osb.terminal_bounds(win), 0.35)
            else:
                win = None
                if tty:
                    j = yield from self.job(osb.terminal_window_for_tty, tty)
                    win = j.result
                if win is not None:
                    text = Poller(lambda: self.since_command(osb.terminal_contents(win, tty)), 1.0)
                    bounds = Poller(lambda: osb.terminal_bounds(win), 0.4)
                else:   # 不是 Terminal.app(例如 iTerm2):改用最前面的終端機視窗
                    text = Poller(lambda: self.since_command(osb.terminal_contents(None)), 1.0)
                    bounds = Poller(lambda: osb.terminal_bounds(None), 0.6)
            pollers += [text, bounds]

            t = 0.0
            while bounds.value is None and t < 4:
                t += yield
            if bounds.value:
                yield from self.climb(bounds)
            else:
                self.say("看不到終端機視窗,我在這裡等結果", 3)

            shown, last, t, idle_polls = 0, self.time, 0.0, None
            res = osb.parse_test_output("")
            while t < 180:
                t += yield
                res = osb.parse_test_output(text.value or "")
                items = osb.checklist(res)
                ready = sum(1 for _, s in items if s in ("ok", "fail"))
                if shown < ready and self.time - last > 0.4:
                    shown, last = shown + 1, self.time
                self.show_checklist(items, shown)
                if launch:
                    finished = res["exit"] is not None
                else:
                    running = bool(self.procs and self.procs.value)
                    if running:
                        idle_polls = None
                    elif idle_polls is None:
                        idle_polls = text.count
                    finished = idle_polls is not None and text.count >= idle_polls + 2
                if finished and shown >= ready and self.time - last > 0.4:
                    break

            hx, hy = self.head()
            if not launch and not (text.value or "").strip():
                self.say("測試跑完了(讀不到這個終端機的內容)", 4)
                yield from self.wait(2.0)
            elif res["passed"]:
                cross, total = res["cross"], res["py_total"]
                self.badge = {"text": "All Passed!", "t0": self.time, "color": GREEN, "icon": "check"}
                self.confetti.burst(hx, hy - 50, 70, 620)
                summary = f"對答案 {cross:,} 次 + {total} 項測試,全部正確" if cross and total else "測試全部通過"
                self.say([[("✓ ", GREEN), (summary, INK)]], 6, self.bubble_side())
                for k in range(5):
                    yield from self.hop(30, "happy")
            else:
                self.badge = {"text": "FAILED", "t0": self.time, "color": RED, "icon": "cross"}
                self.pose = "sad"
                self.say("有測試沒過,看一下終端機的輸出", 6, self.bubble_side())
                yield from self.wait(2.0)
            yield from self.wait(2.5)
        finally:
            for pl in pollers:
                pl.stop()
        self.badge = None
        self.perch = None
        yield from self.fall()

    @staticmethod
    def since_command(text):
        """終端機內容只取最後一次下測試指令之後的部分,避免讀到以前的結果。"""
        if text is None:
            return None
        # 依序找:測試名稱(test_rotl_isa…)也會出現在輸出裡,所以先找使用者實際打的指令
        for pat in ("make test", "run_tests.sh", "unittest discover", "rv32sim", "test_rotl "):
            cut = text.rfind(pat)
            if cut >= 0:
                return text[cut:]
        return text

    def climb(self, bounds):
        """走到終端機視窗旁,沿著側邊爬上去,再翻到標題列上坐好。"""
        b = bounds.value
        right = b[2] + 18 * self.px < self.avail.right()

        def edge():
            b = bounds.value
            return b[2] + 8 * self.px if right else b[0] - 8 * self.px

        self.say("我去終端機那邊看!", 2)
        yield from self.walk_to(edge())
        b = bounds.value
        if b[3] < self.floor - 6:
            yield from self.jump_to(edge(), b[3], 0.55, 50)
        while True:
            dt = yield
            b = bounds.value
            self.x = edge()
            self.look = -1 if right else 1
            self.pose = "climb"
            self.anim += dt
            self.y = max(b[1] + 2 * self.px, self.y - CLIMB * dt)
            if self.y <= b[1] + 2 * self.px:
                break
        target = b[2] - 90 if right else b[0] + 90
        yield from self.jump_to(target, b[1], 0.45, 46)
        self.perch = (bounds, right, self.x - (b[2] if right else b[0]))
        self.pose, self.look = "idle", 0

    def hop(self, height=24, pose="happy", dur=0.42):
        base = self.y
        t = 0.0
        while t < dur:
            t += yield
            self.y = (self.perch_y() if self.perch else base) - math.sin(math.pi * clamp(t / dur)) * height
            self.pose = pose
        self.y = self.perch_y() if self.perch else base

    def perch_y(self):
        return self.perch[0].value[1]

    def bubble_side(self):
        return "right" if self.x + 8 * self.px + 380 < self.avail.right() else "left"

    def show_checklist(self, items, shown):
        lines = []
        for i, (label, state) in enumerate(items):
            if i < shown and state == "ok":
                lines.append([("✓ ", GREEN), (label, INK)])
            elif i < shown and state == "fail":
                lines.append([("✗ ", RED), (label, INK)])
            else:
                lines.append([("… ", MUTED), (label, MUTED)])
        self.say(lines, 0.5, self.bubble_side())

    # ---------------------------------------------------------------- 腳本:小動作
    def show_hw(self):
        yield from self.land()
        data = yield from self.wait_data()
        hw = data.get("hw") or {}
        self.carry = ("chip",)
        lines = [[("這台電腦的規格", INK)]]
        lines += [[(f"{k}  ", MUTED), (v, INK)] for k, v in osb.hardware_lines(hw)]
        self.say(lines, 1e9)
        yield from self.hop(26, "carry")
        if self.auto:
            yield from self.wait(8)
        else:
            self.wait_click, self.clicked = True, False
            t = 0.0
            while not self.clicked and t < 15:
                t += yield
            self.wait_click = False
        self.bubble = None
        self.carry = None

    def react(self):
        yield from self.land()
        self.say(random.choice(FACTS), 3.5)
        yield from self.hop(26)
        self.pose = "idle"

    def wander(self):
        yield from self.land()
        r = random.random()
        if r < 0.55:
            x = random.uniform(self.avail.left() + 80, self.avail.right() - 80)
            yield from self.walk_to(x, WALK * 0.45)
        elif r < 0.75:
            self.pose = "wave"
            for k in range(6):
                self.anim = k
                yield from self.wait(0.2)
            self.pose = "idle"
        else:
            for look in (-1, 1, 0):
                self.look = look
                yield from self.wait(0.6)

    # ---------------------------------------------------------------- 滑鼠
    def on_click(self):
        if self.wait_click:
            self.clicked = True
        elif self.kind in (None, "idle"):
            self.start(self.react(), "idle")
        elif self.stage and not self.stage["closing"]:
            sc, t = self.stage["scene"], self.stage["t"]
            if not sc.waiting(t) and t < sc.duration - 1.5 and not isinstance(sc, scenes.FolderScene):
                self.stage["t"] = sc.duration - 1.5      # 動畫快轉到結尾

    def on_double_click(self):
        if self.kind in (None, "idle"):
            self.start(self.tour(), "tour")

    def drag_start(self):
        if self.kind not in (None, "idle") or self.stage:
            return False
        self.stop()
        self.dragging = True
        self.bubble = None
        return True

    def drag_move(self, gx, gy):
        self.x, self.y = gx, gy + 6 * self.px
        self.pose = "dangle"
        self.anim += 0.016

    def drag_end(self):
        self.dragging = False
        self.vy = 0.0
        self.say("哇啊——", 1.0)

    # ---------------------------------------------------------------- 每個影格
    def tick(self):
        now = time.monotonic()
        dt = min(0.05, now - self.last)
        self.last = now
        self.time += dt

        if self.script:
            self.step(dt)
        elif not self.dragging:
            self.idle(dt)

        if self.perch and self.perch[0].value and self.pose not in ("jump",):
            bounds, right, off = self.perch
            b = bounds.value
            self.x = (b[2] if right else b[0]) + off
            if self.pose != "happy":
                self.y = b[1]

        if self.procs and not self.dragging:
            procs = self.procs.value or []
            fresh = [(pid, tty) for pid, tty, _ in procs if pid not in self.handled]
            self.handled |= {pid for pid, _, _ in procs}
            if fresh and self.kind in (None, "idle"):
                tty = next((tty for _, tty in fresh if tty), None)
                self.start(self.run_terminal(launch=False, tty=tty), "terminal")

        self.update_stage(dt)
        self.confetti.update(dt)
        if self.bubble and self.time > self.bubble["until"]:
            self.bubble = None
        self.sparkles = [s for s in self.sparkles if self.time - s[2] < 0.8]
        self.place_hitbox()

        # 閒置時畫面幾乎不變:沒有變化就不重畫,計時器也放慢,桌寵才不會吃 CPU
        busy = bool(self.script and self.kind != "idle") or self.stage or self.dragging or self.confetti.parts \
            or self.sparkles or self.badge or self.y < self.floor
        blink = (self.time % 3.7) < 0.13
        look = (round(self.x), round(self.y), self.pose, int(self.anim * 9), self.look, blink,
                id(self.bubble), self.carry, self.visible)
        if busy or look != getattr(self, "last_look", None):
            dirty = self.painted.united(self.estimate())
            self.overlay.update(dirty.toAlignedRect().translated(-int(self.geo.left()), -int(self.geo.top())))
        self.last_look = look
        self.timer.setInterval(16 if busy or self.script else 50)

    def idle(self, dt):
        if self.y < self.floor:
            self.vy += GRAVITY * dt
            self.y = min(self.floor, self.y + self.vy * dt)
            self.pose = "jump"
            if self.y >= self.floor:
                self.vy = 0.0
                self.pose = "idle"
            return
        self.next_idle -= dt
        if self.next_idle <= 0:
            self.next_idle = random.uniform(5, 11)
            self.start(self.wander(), "idle")

    def head(self):
        """對話框與標籤對準的頭頂(全域座標)。"""
        if self.visible or not self.stage:
            top = self.y - 10 * self.px
            if self.carry:
                top -= self.px + 56        # 手上舉著東西時,對準道具的上緣
            return self.x, top
        sx, sy = self.stage["scene"].pet_at
        return self.stage_to_global(sx, sy - 10 * scenes.PX)

    def place_hitbox(self):
        if self.visible or not self.stage:
            cx, cy, s = self.x, self.y, self.px
        else:
            sx, sy = self.stage["scene"].pet_at
            cx, cy = self.stage_to_global(sx, sy)
            s = scenes.PX * self.stage["scale"]
        w, h = int(16 * s + 16), int(12 * s + 14)
        geo = (int(cx - w / 2), int(cy - h + 6), w, h)
        if self.hit.geometry().getRect() != geo:
            self.hit.setGeometry(*geo)

    def estimate(self):
        """這個影格可能會畫到的範圍(加上一影格前畫過的範圍,就是要重畫的區域)。"""
        hx, hy = self.head()
        r = QRectF(hx - 320, hy - 300, 640, 300 + 14 * self.px)
        r = r.united(clawd_rect(self.x, self.y, self.px).adjusted(-40, -120, 40, 10))
        if self.stage:
            r = r.united(self.stage["rect"].adjusted(-4, -4, 4, 4))
        return r.united(self.confetti.bounds())

    # ---------------------------------------------------------------- 繪圖
    def paint(self, p: QPainter):
        painted = QRectF()
        st = self.stage
        if st:
            p.save()
            p.setOpacity(clamp(st["alpha"]))
            p.setClipRect(st["rect"].adjusted(-2, -2, 2, 2))
            p.translate(st["rect"].topLeft())
            p.scale(st["scale"], st["scale"])
            st["scene"].draw(p, st["t"], self.time, card=True)
            p.restore()
            painted = painted.united(st["rect"].adjusted(-4, -4, 4, 4))

        if self.visible:
            if self.carry and self.carry[0] == "chip":
                draw_chip_glow(p, self.x, self.y - 11 * self.px - 26, 4, 0.8, self.time)
            blink = (self.time % 3.7) < 0.13 and self.pose in ("idle", "walk", "carry", "carrywalk")
            hands = draw_clawd(p, self.x, self.y, self.px, self.pose, int(self.anim * 9), self.look, blink)
            if self.carry:
                self.draw_prop(p, hands)
            painted = painted.united(clawd_rect(self.x, self.y, self.px).adjusted(-30, -110, 30, 6))

        for x, y, t0 in self.sparkles:
            u = self.time - t0
            if 0 <= u < 0.8:
                draw_sparkle(p, x, y - u * 20, 3, with_alpha(GOLD, 1 - u / 0.8))
                painted = painted.united(QRectF(x - 12, y - 30, 24, 40))

        hx, hy = self.head()
        if self.badge:
            u = seg(self.time, self.badge["t0"], self.badge["t0"] + 0.45)
            painted = painted.united(draw_badge(p, hx, hy - 14, self.badge["text"], ease_back(u) if u < 1 else 1.0,
                                                self.badge["color"], self.badge["icon"]))
        if self.bubble:
            side = self.bubble["side"]
            ax = hx + (8 * self.px if side == "right" else -8 * self.px if side == "left" else 0)
            ay = hy + (4 * self.px if side != "up" else 0)
            if side == "up" and self.badge:
                ay -= 64
            painted = painted.united(draw_bubble(p, ax, ay, self.bubble["lines"], 15, self.avail, 1.0, side))
        self.confetti.draw(p, 4)
        painted = painted.united(self.confetti.bounds())
        self.painted = painted

    def draw_prop(self, p, hands):
        kind = self.carry[0]
        if kind == "folder":
            draw_folder(p, self.x, hands, 4, "rotl")
        elif kind == "file":
            draw_file(p, self.x, hands, 4, self.carry[1], self.carry[2])
        elif kind == "chip":
            draw_chip(p, self.x, hands - 6 * 4 - 2, 4, "M5", 0.8)


def main():
    ap = argparse.ArgumentParser(description="Claude 吉祥物桌寵(rotl 專案 Demo)")
    ap.add_argument("--scale", type=int, default=6, help="吉祥物的像素大小(預設 6)")
    ap.add_argument("--tour", action="store_true", help="啟動後直接開始導覽")
    ap.add_argument("--auto", action="store_true", help="導覽自動播放,不用點擊")
    ap.add_argument("--no-watch", dest="watch", action="store_false", help="不偵測終端機的測試指令")
    args = ap.parse_args()

    qapp = QApplication(sys.argv[:1])
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setApplicationName("Clawd")
    osb.mac_accessory_app()
    pet = Pet(qapp, args)  # noqa: F841  Qt 物件要一直留著
    print("Clawd 已啟動:雙擊吉祥物開始導覽;右鍵或選單列圖示 →「結束桌寵」→「確定結束」關閉", flush=True)
    sys.exit(qapp.exec())


if __name__ == "__main__":
    main()
