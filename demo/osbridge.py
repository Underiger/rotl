"""桌寵與作業系統、專案之間的橋樑:所有 subprocess、osascript、sysctl、ctypes 都在這裡。

這個檔案不碰 Qt 繪圖。會卡住的呼叫(osascript、編譯、benchmark)由 pet.py 放到背景執行緒跑。
"""

import ctypes
import ctypes.util
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
BUILD = ROOT / "build"
TEST_LOG = BUILD / "pet_demo.log"
RUN_TESTS = ROOT / "demo" / "run_tests.sh"

sys.path.insert(0, str(TOOLS))
import rotl_isa  # noqa: E402  編碼常數從 src/include/rotl_isa.h 讀,與專案共用同一份設定

# experiments/README.md「另一次執行」的加速比;不是 ARM64 電腦、或影片輸出時使用
DOC_SPEEDUPS = [
    {"name": "ChaCha20 區塊", "speedup": 1.51},
    {"name": "RC5 金鑰排程", "speedup": 1.35},
    {"name": "RC5 加密", "speedup": 1.32},
]
BENCH_NAMES = {"ChaCha20": "ChaCha20 區塊", "RC5 key": "RC5 金鑰排程", "RC5 encrypt": "RC5 加密"}

# 偵測到這些指令在跑,桌寵就去爬終端機
TEST_PATTERNS = ("make test", "test_rotl", "unittest discover", "rv32sim", "run_tests.sh",
                 "test_rv32", "test_rotl_isa")


def run(cmd, timeout=15, cwd=ROOT):
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout if out.returncode == 0 else None


def osascript(script, timeout=8):
    out = run(["osascript", "-e", script], timeout=timeout)
    return out.strip() if out is not None else None


def _ints(text):
    return [int(v) for v in re.findall(r"-?\d+", text or "")]


# ---------------------------------------------------------------- 專案資料

def encoding_data(rd=10, rs1=11, rs2=12):
    """rotl a0, a1, a2 的機器碼與各欄位(來自 tools/rotl_isa.py)。"""
    word = rotl_isa.encode_rotl(rd, rs1, rs2)
    names = rotl_isa.ABI_NAMES
    return {
        "asm": f"rotl {names[rd]}, {names[rs1]}, {names[rs2]}",
        "word": word,
        "fields": rotl_isa.fields(word),
        "regs": {"rd": (names[rd], rd), "rs1": (names[rs1], rs1), "rs2": (names[rs2], rs2)},
        "le_bytes": word.to_bytes(4, "little"),
    }


def project_stats():
    """git ls-files 的檔案數、各語言行數與最新 commit,資料夾展示用。"""
    files = (run(["git", "ls-files"]) or "").split()
    if not files:
        files = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
                 if p.is_file() and ".git" not in p.parts and ".venv" not in p.parts]
    langs = {".c": "C", ".h": "C", ".S": "組合語言", ".py": "Python", ".md": "Markdown"}
    lines = {}
    for f in files:
        lang = langs.get(Path(f).suffix)
        if lang:
            try:
                lines[lang] = lines.get(lang, 0) + (ROOT / f).read_text(encoding="utf-8").count("\n")
            except (OSError, UnicodeDecodeError):
                pass
    per_top = {}
    for f in files:
        top = f.split("/")[0] + ("/" if "/" in f else "")
        per_top[top] = per_top.get(top, 0) + 1
    commit = (run(["git", "log", "-1", "--format=%h %s"]) or "").strip()
    return {"files": len(files), "lines": lines, "per_top": per_top, "commit": commit}


def objdump_rotl():
    """反組譯 build/kernels_custom.elf,找出所有 ROTL 機器碼(實際由 GCC + .insn 產生)。"""
    elf = BUILD / "kernels_custom.elf"
    try:
        import rvbuild
        if not elf.exists() and rvbuild.toolchain_available():
            rvbuild.build_kernels(custom=True)
        objdump = rvbuild.RV_OBJDUMP
    except Exception:
        objdump = None
    if not objdump or not elf.exists():
        return None
    out = run([objdump, "-d", str(elf)])
    if out is None:
        return None
    found, func = [], "?"
    for line in out.splitlines():
        m = re.match(r"^[0-9a-f]+ <(\w+)>:", line)
        if m:
            func = m.group(1)
            continue
        m = re.match(r"^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s", line)
        if m:
            word = int(m.group(2), 16)
            regs = rotl_isa.decode_rotl(word)
            if regs:
                n = rotl_isa.ABI_NAMES
                found.append({"addr": int(m.group(1), 16), "word": word, "func": func,
                              "asm": f"rotl {n[regs[0]]}, {n[regs[1]]}, {n[regs[2]]}"})
    per_func = {}
    for f in found:
        per_func[f["func"]] = per_func.get(f["func"], 0) + 1
    return {"count": len(found), "per_func": per_func, "examples": found[:3], "elf": elf.name}


# ---------------------------------------------------------------- 硬體(sysctl)

def sysctl(name):
    out = run(["sysctl", "-n", name], timeout=3)
    return out.strip() if out else None


def _size(n):
    n = int(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:g} {unit}"
        n /= 1024


def hardware_info():
    """用 sysctl 讀晶片、核心叢集、快取與記憶體(不讀序號等可識別個人的資訊)。"""
    info = {"chip": sysctl("machdep.cpu.brand_string") or platform.processor() or "?",
            "arch": platform.machine(), "model": sysctl("hw.model") or "?",
            "os": f"macOS {platform.mac_ver()[0]}" if sys.platform == "darwin" else platform.system()}
    clusters = []
    for i in range(int(sysctl("hw.nperflevels") or 0)):
        name = sysctl(f"hw.perflevel{i}.name") or f"L{i}"
        cores = sysctl(f"hw.perflevel{i}.physicalcpu")
        l2 = sysctl(f"hw.perflevel{i}.l2cachesize")
        l1d = sysctl(f"hw.perflevel{i}.l1dcachesize")
        clusters.append({"name": name, "cores": int(cores or 0),
                         "l2": _size(l2) if l2 else "?", "l1d": _size(l1d) if l1d else "?"})
    info["clusters"] = clusters
    info["cores"] = " + ".join(f"{c['cores']} {c['name']}" for c in clusters) or (sysctl("hw.ncpu") or "?")
    mem, page, line = sysctl("hw.memsize"), sysctl("hw.pagesize"), sysctl("hw.cachelinesize")
    info["mem"] = _size(mem) if mem else "?"
    info["page"] = _size(page) if page else "?"
    info["line"] = _size(line) if line else "?"
    feats = []
    for feat in ("FEAT_SHA3", "FEAT_BF16", "FEAT_SME2"):
        if sysctl(f"hw.optional.arm.{feat}") == "1":
            feats.append(feat[5:])
    info["features"] = feats
    return info


def hardware_lines(info):
    """晶片場景與「硬體資訊」選單共用的顯示文字。"""
    big = info["clusters"][0] if info.get("clusters") else None
    lines = [("晶片", f"{info['chip']} ({info['arch']})"), ("核心", info["cores"])]
    if big:
        lines.append(("快取", f"L1d {big['l1d']} · L2 {big['l2']}({big['name']})"))
    lines.append(("記憶體", f"{info['mem']} · 分頁 {info['page']} · 快取行 {info['line']}"))
    if info.get("features"):
        lines.append(("ISA", "FEAT_" + " / ".join(info["features"])))
    return lines


# ---------------------------------------------------------------- ARM64 實機量測

def bench_available():
    return platform.machine() in ("arm64", "aarch64") and run(["which", "cc"]) is not None


def bench_rows(on_row=None):
    """編譯並執行 experiments/arm64_rotate_bench.c,每量完一個核心就呼叫 on_row(row)。

    用 script(1) 給程式一個偽終端機,stdout 才會逐行輸出,不會等到結束才一次吐出來。
    """
    src = ROOT / "experiments" / "arm64_rotate_bench.c"
    exe = BUILD / "arm64_rotate_bench"
    BUILD.mkdir(exist_ok=True)
    if not exe.exists() or exe.stat().st_mtime < src.stat().st_mtime:
        subprocess.run(["cc", "-O2", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-o", str(exe), str(src)], check=True, capture_output=True)
    cmd = ["script", "-q", "/dev/null", str(exe)] if sys.platform == "darwin" else [str(exe)]
    rows = []
    with subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL,
                          text=True, errors="replace") as proc:
        for raw in proc.stdout:
            line = re.sub(r"[\x00-\x08\r]", "", raw).strip()
            if "FAILED" in line:
                raise RuntimeError(line)
            m = re.match(r"\|\s*(.+?)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)x", line)
            if not m:
                continue
            name = next((zh for en, zh in BENCH_NAMES.items() if m.group(1).startswith(en)), m.group(1))
            row = {"name": name, "shift": float(m.group(2)), "ror": float(m.group(3)),
                   "speedup": float(m.group(4))}
            rows.append(row)
            if on_row:
                on_row(row)
    return rows


# ---------------------------------------------------------------- Finder / 終端機(AppleScript)

def finder_icon_pos():
    """rotl 資料夾在桌面上的圖示中心(螢幕座標);不在桌面上或沒有權限時回傳 None。"""
    if sys.platform != "darwin" or ROOT.parent != Path.home() / "Desktop":
        return None
    v = _ints(osascript(f'tell application "Finder" to get desktop position of item "{ROOT.name}" of desktop'))
    return (v[0], v[1]) if len(v) == 2 else None


def frontmost_app():
    return osascript('tell application "System Events" to get name of first application process '
                     'whose frontmost is true')


def terminal_open(command, bounds=None):
    """在 Terminal.app 開新視窗執行 command,回傳視窗 id。"""
    cmd = command.replace("\\", "\\\\").replace('"', '\\"')
    script = ['tell application "Terminal"', "activate", f'do script "{cmd}"', "delay 0.3"]
    if bounds:
        script.append("set bounds of front window to {%d, %d, %d, %d}" % tuple(bounds))
    script += ["return id of front window", "end tell"]
    v = _ints(osascript("\n".join(script)))
    return v[0] if v else None


def terminal_bounds(win_id=None):
    """Terminal 視窗的 (left, top, right, bottom),win_id 為 None 時取最前面的終端機視窗。"""
    if win_id is not None:
        v = _ints(osascript(f'tell application "Terminal" to get bounds of window id {win_id}', 3))
    else:
        app = frontmost_app()
        if app == "Terminal":
            v = _ints(osascript('tell application "Terminal" to get bounds of front window', 3))
        elif app == "iTerm2":
            v = _ints(osascript('tell application "iTerm2" to get bounds of current window', 3))
        else:
            v = []
    return tuple(v) if len(v) == 4 else None


def terminal_window_for_tty(tty):
    """找出 Terminal.app 裡 tty 相同的分頁所在的視窗 id(ps 的 tty 欄位 → 視窗)。"""
    script = f'''tell application "Terminal"
    repeat with w in windows
        repeat with t in tabs of w
            if tty of t is "{tty}" then return id of w
        end repeat
    end repeat
end tell'''
    v = _ints(osascript(script, 4))
    return v[0] if v else None


def terminal_contents(win_id=None, tty=None):
    if win_id is not None and tty:
        return osascript(f'tell application "Terminal" to get history of (first tab of window id {win_id} '
                         f'whose tty is "{tty}")')
    if win_id is not None:
        return osascript(f'tell application "Terminal" to get history of selected tab of window id {win_id}')
    app = frontmost_app()
    if app == "Terminal":
        return osascript('tell application "Terminal" to get history of selected tab of front window')
    if app == "iTerm2":
        return osascript('tell application "iTerm2" to get contents of current session of current window')
    return None


# ---------------------------------------------------------------- 行程監看

def test_processes():
    """列出終端機裡正在跑的測試指令 (pid, tty, command),排除桌寵自己和它的子行程。

    tty 是行程所在的終端機裝置(例如 /dev/ttys003),用來找出是哪一個終端機視窗在跑。
    """
    out = run(["ps", "-Ao", "pid=,ppid=,tty=,command="], timeout=3) or ""
    procs, parent = [], {}
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4:
            pid, ppid, tty, cmd = int(parts[0]), int(parts[1]), parts[2], parts[3]
            parent[pid] = ppid
            procs.append((pid, "/dev/" + tty if tty != "??" else None, cmd))

    def ours(pid):
        while pid > 1:
            if pid == os.getpid():
                return True
            pid = parent.get(pid, 0)
        return False

    # 只認有 tty 的行程:在終端機打的指令一定有,其他程式參數裡剛好出現 "make test" 的不算
    return [(pid, tty, cmd) for pid, tty, cmd in procs
            if tty and any(pat in cmd for pat in TEST_PATTERNS) and not ours(pid)]


def parse_test_output(text):
    """從 make test 的輸出整理出進度清單。"""
    text = text or ""
    csv = re.search(r"\[CSV\]\s+(\d+) vectors", text)
    cross = re.search(r"\[CROSS\]\s+(\d+) comparisons", text)
    ran = re.search(r"Ran (\d+) tests?", text)
    code = re.findall(r"PET_EXIT=(\d+)", text)
    res = {
        "csv": int(csv.group(1)) if csv else None,
        "cross": int(cross.group(1)) if cross else None,
        "c_pass": "ALL PASS" in text,
        "ubsan": "UBSan: no undefined behavior" in text,
        "py_ok": len(re.findall(r"\.\.\. ok\s*$", text, re.M)),
        "py_total": int(ran.group(1)) if ran else None,
        "py_pass": bool(ran and re.search(r"^OK\b", text[ran.end():], re.M)),
        "failed": bool(re.search(r"FAILED|^FAIL:|^ERROR:|Error \d|\*\*\*", text, re.M)),
        "exit": int(code[-1]) if code else None,
    }
    res["passed"] = res["exit"] == 0 if res["exit"] is not None else (
        res["c_pass"] and res["ubsan"] and res["py_pass"] and not res["failed"])
    return res


def checklist(res):
    """把 parse_test_output 的結果轉成 [(文字, 狀態)],狀態為 ok、run、wait、fail。"""
    def state(done, started=True):
        if done:
            return "ok"
        if res["failed"] or res["exit"] not in (None, 0):
            return "fail" if started else "wait"
        return "run" if started else "wait"

    n = res["py_total"] or 22
    return [
        (f"C 測資 {res['csv'] or 16} 組", state(res["c_pass"] and res["csv"] is not None)),
        (f"交叉比對 {res['cross'] or 69000:,} 次", state(res["c_pass"] and res["cross"] is not None)),
        ("UBSan 無未定義行為", state(res["ubsan"], res["c_pass"])),
        (f"Python + 模擬器 {min(res['py_ok'], n)}/{n}", state(res["py_pass"], res["ubsan"])),
    ]


# ---------------------------------------------------------------- macOS 視窗(ctypes 直接呼叫 Objective-C runtime)

def _objc_send(obj, selector, *args, restype=ctypes.c_void_p, argtypes=()):
    lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    lib.sel_registerName.restype = ctypes.c_void_p
    lib.sel_registerName.argtypes = [ctypes.c_char_p]
    proto = ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes)
    send = proto(("objc_msgSend", lib))
    return send(obj, lib.sel_registerName(selector.encode()), *args)


def mac_pin_window(widget):
    """讓視窗出現在所有桌面空間(包含全螢幕簡報)上方,App 失去焦點時也不隱藏。"""
    if sys.platform != "darwin":
        return False
    try:
        win = _objc_send(int(widget.winId()), "window")
        # CanJoinAllSpaces | Stationary | IgnoresCycle | FullScreenAuxiliary
        _objc_send(win, "setCollectionBehavior:", 1 | 16 | 64 | 256, restype=None, argtypes=(ctypes.c_ulong,))
        _objc_send(win, "setLevel:", 101, restype=None, argtypes=(ctypes.c_long,))  # NSPopUpMenuWindowLevel
        _objc_send(win, "setHidesOnDeactivate:", False, restype=None, argtypes=(ctypes.c_bool,))
        return True
    except Exception:
        return False


def mac_accessory_app():
    """不在 Dock 顯示圖示(NSApplicationActivationPolicyAccessory),改由選單列圖示控制。"""
    if sys.platform != "darwin":
        return False
    try:
        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        lib.objc_getClass.restype = ctypes.c_void_p
        lib.objc_getClass.argtypes = [ctypes.c_char_p]
        app = _objc_send(lib.objc_getClass(b"NSApplication"), "sharedApplication")
        _objc_send(app, "setActivationPolicy:", 1, restype=ctypes.c_bool, argtypes=(ctypes.c_long,))
        return True
    except Exception:
        return False
