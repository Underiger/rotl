"""執行證據:在自己的電腦上跑 make test 與 make counts,把完整輸出存成一份 log。

    make evidence ID=<學號>      → report/figures/run_log_<學號>.txt

log 開頭記錄執行時間、執行者(git user.name)、作業系統與晶片、工具版本、
程式版本(git commit),接著是兩個指令的完整輸出與結束碼。
不記錄電腦名稱或使用者帳號等個人資訊。每位組員各自執行、各自 commit 自己的 log。
"""

import datetime
import platform
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "report" / "figures"


def run(cmd):
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        return p.returncode, (p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not found"


def first_line(cmd):
    code, out = run(cmd)
    return out.splitlines()[0] if code == 0 and out else f"(無法執行:{' '.join(cmd)})"


def machine():
    if sys.platform == "darwin":
        _, ver = run(["sw_vers", "-productVersion"])
        _, chip = run(["sysctl", "-n", "machdep.cpu.brand_string"])
        return f"macOS {ver} · {chip} · {platform.machine()}"
    return f"{platform.system()} {platform.release()} · {platform.machine()}"


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r"\d{10}", sys.argv[1]):
        sys.exit("用法:make evidence ID=<10 位數學號>")
    sid = sys.argv[1]

    _, commit = run(["git", "rev-parse", "--short", "HEAD"])
    _, dirty = run(["git", "status", "--porcelain", "--", "."])
    _, who = run(["git", "config", "user.name"])

    header = [
        "# ROTL 執行證據",
        f"學號:{sid}",
        f"執行者(git user.name):{who or '(未設定)'}",
        f"時間:{datetime.datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"機器:{machine()}",
        f"程式版本:git {commit}" + ("(有未 commit 的修改)" if dirty else ""),
        "工具版本:",
        f"  {first_line(['cc', '--version'])}",
        f"  {first_line(['riscv64-elf-gcc', '--version'])}",
        f"  {first_line(['python3', '--version'])}",
        f"  {first_line(['make', '--version'])}",
    ]

    sections, ok = [], True
    for target in ("test", "counts"):
        code, out = run(["make", target])
        ok &= code == 0
        sections += ["", f"$ make {target}", out, f"[結束碼 {code}]"]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"run_log_{sid}.txt"
    path.write_text("\n".join(header + sections) + "\n", encoding="utf-8")
    print(f"written: {path.relative_to(ROOT)}  ({'全部通過' if ok else '有指令失敗,請看 log'})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
