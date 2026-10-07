"""驗證 1:不使用模擬器,從反組譯結果與迴圈次數獨立推算動態指令數。

做法:用 riscv64-elf-objdump 反組譯每個核心函式,
找出所有「往回跳」的分支(迴圈),迴圈範圍內的指令乘上 C 原始碼中的迴圈次數,
其餘指令執行一次。若函式中還有其他分支或跳躍,代表無法用這個方法推算,直接報錯。

    python3 experiments/ic_crosscheck.py
"""

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import rv32sim  # noqa: E402  (只用來取得對照值)
import rvbuild  # noqa: E402

# C 原始碼中的迴圈次數,依迴圈在程式中的先後順序
TRIP_COUNTS = {
    "chacha20_block": [16, 10, 16],  # 複製狀態、10 次 double round、輸出相加
    "rc5_setup": [25, 78],           # S[i] 初始化(i = 1..25)、3 × 26 次混合
    "rc5_encrypt": [12],             # 12 rounds
}
CONTROL = {"beq", "bne", "blt", "bge", "bltu", "bgeu", "beqz", "bnez", "blez", "bgez",
           "bltz", "bgtz", "bgt", "ble", "bgtu", "bleu", "j", "jal", "jr", "jalr", "call", "tail"}


def disassemble(elf: Path, func: str):
    dump = subprocess.run([rvbuild.RV_OBJDUMP, "-d", "--no-show-raw-insn", str(elf)],
                          capture_output=True, text=True, check=True).stdout
    body = dump.split(f"<{func}>:\n", 1)[1].split("\n\n", 1)[0]
    insns = []
    for line in body.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\s+(\S+)\s*(.*)", line)
        if m:
            insns.append((int(m.group(1), 16), m.group(2), m.group(3)))
    return insns


def analytic_count(elf: Path, func: str) -> int:
    insns = disassemble(elf, func)
    assert insns[-1][1] == "ret", f"{func} does not end with ret"
    loops, entries = [], {}
    for addr, mn, ops in insns[:-1]:
        if mn not in CONTROL:
            continue
        target = re.search(r"\b([0-9a-f]+) <", ops)
        if mn in ("jal", "jr", "jalr", "call", "tail") or not target:
            sys.exit(f"{func}: unexpected control transfer '{mn} {ops}' at 0x{addr:x}")
        t = int(target.group(1), 16)
        if mn == "j" and t > addr:
            # 編譯器的迴圈旋轉:緊接在迴圈前的 j 直接跳進迴圈中間,
            # 迴圈開頭到跳入點之間的指令少執行一次
            entries[addr + 4] = t
            continue
        if t >= addr:
            sys.exit(f"{func}: forward branch at 0x{addr:x}; cannot count analytically")
        loops.append((t, addr))
    for lo in entries:
        if lo not in {l for l, _ in loops}:
            sys.exit(f"{func}: j at 0x{lo - 4:x} does not enter a loop")
    trips = TRIP_COUNTS[func]
    if len(loops) != len(trips):
        sys.exit(f"{func}: found {len(loops)} loops, expected {len(trips)}")
    total = 0
    for addr, _, _ in insns:
        k = 1
        for (lo, hi), n in zip(loops, trips):
            if lo <= addr <= hi:
                k = n - 1 if addr < entries.get(lo, lo) else n
        total += k
    return total, loops


def main():
    print("| 核心 | 版本 | 迴圈(起點–分支,次數) | 推算(objdump) | 模擬器 | 一致 |")
    print("|---|---|---|---:|---:|:---:|")
    ok = True
    for custom in (False, True):
        elf = rvbuild.build_kernels(custom)
        sim = rv32sim.Sim(elf)
        sim.run()
        for func in TRIP_COUNTS:
            n, loops = analytic_count(elf, func)
            s = sim.calls_to(func)[0].insns
            loop_desc = "、".join(f"0x{lo:x}–0x{hi:x}×{t}" for (lo, hi), t in zip(loops, TRIP_COUNTS[func]))
            ok &= n == s
            print(f"| {func} | {'ROTL' if custom else 'RV32IM'} | {loop_desc} | {n} | {s} | "
                  f"{'✓' if n == s else '✗'} |")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
