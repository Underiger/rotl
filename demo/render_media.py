"""把動畫場景輸出成 MP4 與 GIF(demo/media/),README 頂部與簡報用。

    .venv/bin/python demo/render_media.py                 輸出全部(或 make media)
    .venv/bin/python demo/render_media.py encode chip     只輸出指定場景
    .venv/bin/python demo/render_media.py --png 12.5 encode   只存某個時間點的 PNG(檢查畫面用)
    .venv/bin/python demo/render_media.py --live chip     晶片場景改用這台電腦現場量到的加速比

場景:encode(① 指令怎麼變成 0 和 1)、chip(② 在這台電腦上實測快多少)、terminal(③ 自動測試的影片備案)。
晶片場景預設使用 experiments/README.md 記錄的加速比(ChaCha20 1.51x、RC5 加密 1.32x)。
需要 ffmpeg。
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402

import osbridge as osb  # noqa: E402
import scenes  # noqa: E402

MEDIA = Path(__file__).resolve().parent / "media"
NAMES = {"encode": "rotl_encode", "chip": "m5_speedup", "terminal": "make_test_all_passed"}
FPS = 30
SIZE = (1920, 1080)
GIF_WIDTH = 960


def chip_label(hw):
    m = re.search(r"\bM\d+\w*", hw.get("chip", ""))
    return m.group(0) if m else "CPU"


def terminal_lines():
    """實際執行 make test,把輸出整理成終端機畫面要顯示的行。"""
    out = subprocess.run(["make", "test"], cwd=osb.ROOT, capture_output=True, text=True)
    text = out.stdout + out.stderr + f"\nPET_EXIT={out.returncode}\n"
    lines = []
    for line in (out.stdout + out.stderr).splitlines():
        line = line.replace("\t", " ").rstrip()
        if not line or line.startswith(("cc ", "./build", "python3 -m")) or line.lstrip().startswith("c_baseline/"):
            continue
        lines.append(re.sub(r" \(test_[\w.]+\)", "", line))
    return lines, osb.checklist(osb.parse_test_output(text))


def build(name, live):
    if name == "encode":
        return scenes.EncodeScene({"enc": osb.encoding_data(), "objdump": osb.objdump_rotl()})
    if name == "chip":
        hw = osb.hardware_info()
        if live and osb.bench_available():
            results = osb.bench_rows(lambda r: print(f"  {r['name']}: {r['speedup']:.2f}x"))
        else:
            results = [dict(r) for r in osb.DOC_SPEEDUPS]
        return scenes.ChipScene({"hw_lines": osb.hardware_lines(hw), "results": results,
                                 "chip_label": chip_label(hw)})
    if name == "terminal":
        lines, checks = terminal_lines()
        return scenes.TerminalScene({"lines": lines, "checks": checks})
    raise SystemExit(f"unknown scene: {name}")


def render(scene, t, size=SIZE):
    img = QImage(size[0], size[1], QImage.Format.Format_RGBA8888)
    img.fill(Qt.GlobalColor.black)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.scale(size[0] / scenes.W, size[1] / scenes.H)
    scene.draw(p, t, t, card=False)
    p.end()
    return img


def encode(scene, stem):
    MEDIA.mkdir(exist_ok=True)
    mp4, gif = MEDIA / f"{stem}.mp4", MEDIA / f"{stem}.gif"
    frames = int(round(scene.duration * FPS))
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{SIZE[0]}x{SIZE[1]}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", str(mp4)],
        stdin=subprocess.PIPE)
    for i in range(frames):
        img = render(scene, i / FPS)
        ff.stdin.write(img.constBits().asstring(img.sizeInBytes()))
    ff.stdin.close()
    if ff.wait():
        raise SystemExit("ffmpeg failed")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vf",
         f"fps=15,scale={GIF_WIDTH}:-1:flags=area,split[a][b];"
         "[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle",
         str(gif)], check=True)
    for f in (mp4, gif):
        print(f"written: {f.relative_to(osb.ROOT)}  ({f.stat().st_size / 1e6:.1f} MB)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenes", nargs="*", default=list(NAMES), help="encode / chip / terminal")
    ap.add_argument("--png", type=float, action="append", help="只存這個時間點(秒)的 PNG")
    ap.add_argument("--live", action="store_true", help="晶片場景使用現場量測")
    args = ap.parse_args()

    app = QGuiApplication(sys.argv[:1])  # noqa: F841  QPainter 畫字需要 QGuiApplication
    for name in args.scenes:
        scene = build(name, args.live)
        if args.png:
            MEDIA.mkdir(exist_ok=True)
            for t in args.png:
                out = MEDIA / f"{NAMES[name]}_{t:05.2f}s.png"
                render(scene, t).save(str(out))
                print(f"written: {out}")
        else:
            print(f"{name}: {scene.duration:.1f} s")
            encode(scene, NAMES[name])


if __name__ == "__main__":
    main()
