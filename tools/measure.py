"""量測靜態與動態指令數,輸出到 report/figures/instruction_counts.{md,csv}。

    python3 tools/measure.py      (或 make counts)

所有動態指令數都來自 tools/rv32sim.py 實際執行 GCC 產生的 RV32 執行檔,
並在執行後與 Python 黃金模型及公開測試向量比對,結果不符即中止。
"""

import csv
import sys
from pathlib import Path

import kernels_golden as kg
import rv32sim
import rvbuild
from rotl_isa import FUNCT3_ROTL, FUNCT7_ROTL, load_vectors, rotl_golden

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "report" / "figures"

ROTL_FUNCS = [
    ("rotl_ref", "C 參考實作(GCC -O2)"),
    ("rotl_branch", "手寫 A:逐字翻譯(含分支)"),
    ("rotl_branchless", "手寫 B:無分支"),
    ("rotl_custom", "自訂指令 rotl"),
]
OUTPUTS = {"rotl_ref": "out_ref", "rotl_branch": "out_branch",
           "rotl_branchless": "out_branchless", "rotl_custom": "out_custom"}
KERNELS = [
    ("chacha20_block", "ChaCha20 區塊(常數旋轉)"),
    ("rc5_setup", "RC5 金鑰排程(常數 + 變數旋轉)"),
    ("rc5_encrypt", "RC5 加密一個區塊(變數旋轉)"),
]
SHIFT_FAMILY = ["sll", "srl", "slli", "srli", "or", "andi", "sub", "rotl"]


def measure_functions():
    sim = rv32sim.Sim(rvbuild.build_vectors())
    vectors = load_vectors()
    sim.write_words("vec_count", [len(vectors)])
    sim.write_words("vec_rs1", [v["rs1"] for v in vectors])
    sim.write_words("vec_rs2", [v["rs2"] for v in vectors])
    sim.run()

    rows = []
    for func, label in ROTL_FUNCS:
        got = sim.read_words(OUTPUTS[func], len(vectors))
        for v, g in zip(vectors, got):
            if g != v["expected"] or g != rotl_golden(v["rs1"], v["rs2"]):
                sys.exit(f"{func} wrong on {v['id']}: got 0x{g:08X}")
        calls = sim.calls_to(func)
        static = rv32sim.static_profile(sim, func)
        dyn_n0 = {c.insns for c, v in zip(calls, vectors) if v["rs2"] & 31 == 0}
        dyn_other = {c.insns for c, v in zip(calls, vectors) if v["rs2"] & 31 != 0}
        rows.append({
            "func": func, "label": label,
            "static": static["insns"], "static_branches": static["branches"],
            "dyn_n0": "/".join(map(str, sorted(dyn_n0))),
            "dyn_other": "/".join(map(str, sorted(dyn_other))),
            "dyn_total": sum(c.insns for c in calls),
            "branches": sum(c.branches for c in calls),
            "taken": sum(c.taken for c in calls),
            "vectors": len(vectors),
        })
    return rows


def run_kernels(custom: bool):
    sim = rv32sim.Sim(rvbuild.build_kernels(custom))
    sim.run()
    if sim.read_words("chacha_out", 16) != kg.CHACHA_RFC_OUT:
        sys.exit("ChaCha20 output does not match RFC 8439")
    if sim.read_words("rc5_ct", 2) != kg.RC5_PAPER_CT:
        sys.exit("RC5 output does not match the published test vector")
    if sim.read_words("rc5_S", kg.RC5_TABLE) != kg.rc5_setup(kg.RC5_KEY):
        sys.exit("RC5 key schedule does not match the Python model")
    return sim


def measure_kernels():
    base, cust = run_kernels(False), run_kernels(True)
    rows = []
    for func, label in KERNELS:
        (b,), (c,) = base.calls_to(func), cust.calls_to(func)
        rotations = c.hist["rotl"]
        rows.append({
            "func": func, "label": label, "rotations": rotations,
            "static_base": rv32sim.static_profile(base, func)["insns"],
            "static_custom": rv32sim.static_profile(cust, func)["insns"],
            "dyn_base": b.insns, "dyn_custom": c.insns,
            "branches_base": b.branches, "branches_custom": c.branches,
            "saved_per_rot": (b.insns - c.insns) / rotations,
            "hist_base": b.hist, "hist_custom": c.hist,
        })
    return rows


def to_markdown(func_rows, kernel_rows) -> str:
    out = []
    out.append(f"<!-- 由 tools/measure.py 產生,請勿手動修改。{rvbuild.gcc_version()};"
               f"暫定編碼 funct3=0b{FUNCT3_ROTL:03b}、funct7=0b{FUNCT7_ROTL:07b} -->")
    out.append("")
    out.append("## 表 1:單一 ROTL 運算(呼叫一次函式)")
    out.append("")
    out.append("| 版本 | 函式 | 靜態指令數 | 靜態分支數 | 動態指令數(n = 0) | 動態指令數(n ≠ 0) "
               f"| {func_rows[0]['vectors']} 組測資動態總數 | 動態分支數(taken) |")
    out.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for r in func_rows:
        out.append(f"| {r['label']} | `{r['func']}` | {r['static']} | {r['static_branches']} "
                   f"| {r['dyn_n0']} | {r['dyn_other']} | {r['dyn_total']} "
                   f"| {r['branches']}({r['taken']}) |")
    out.append("")
    out.append("指令數皆包含 `ret`,不含呼叫端的 `call`。")
    out.append("")
    out.append("## 表 2:密碼學核心(GCC -O2,各執行一次)")
    out.append("")
    out.append("| 核心 | 旋轉次數 | 靜態 RV32IM | 靜態 ROTL | 動態 RV32IM | 動態 ROTL "
               "| 動態減少 | IC 比(RV32IM / ROTL) | 每次旋轉省下 | 動態分支數 |")
    out.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in kernel_rows:
        red = 1 - r["dyn_custom"] / r["dyn_base"]
        out.append(f"| {r['label']} | {r['rotations']} | {r['static_base']} | {r['static_custom']} "
                   f"| {r['dyn_base']} | {r['dyn_custom']} | {red:.1%} "
                   f"| {r['dyn_base'] / r['dyn_custom']:.2f}x | {r['saved_per_rot']:.2f} "
                   f"| {r['branches_base']} / {r['branches_custom']} |")
    out.append("")
    out.append("## 表 3:動態指令組成(移位相關指令)")
    out.append("")
    out.append("| 核心 | 版本 | " + " | ".join(f"`{m}`" for m in SHIFT_FAMILY) + " | 其他 | 合計 |")
    out.append("|---|---|" + "---:|" * (len(SHIFT_FAMILY) + 2))
    for r in kernel_rows:
        for tag, hist in (("RV32IM", r["hist_base"]), ("ROTL", r["hist_custom"])):
            total = sum(hist.values())
            other = total - sum(hist[m] for m in SHIFT_FAMILY)
            out.append(f"| {r['func']} | {tag} | " + " | ".join(str(hist[m]) for m in SHIFT_FAMILY)
                       + f" | {other} | {total} |")
    out.append("")
    out.append("`neg` 是 `sub rd, zero, rs` 的虛擬指令,計入 `sub`;`li` 小常數是 `addi`,計入其他。")
    return "\n".join(out) + "\n"


def write_csv(func_rows, kernel_rows, path: Path):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["table", "name", "metric", "rv32im", "rotl"])
        for r in func_rows:
            for k in ("static", "static_branches", "dyn_n0", "dyn_other", "dyn_total", "branches", "taken"):
                w.writerow(["function", r["func"], k, r[k], ""])
        for r in kernel_rows:
            w.writerow(["kernel", r["func"], "rotations", r["rotations"], r["rotations"]])
            w.writerow(["kernel", r["func"], "static_insns", r["static_base"], r["static_custom"]])
            w.writerow(["kernel", r["func"], "dynamic_insns", r["dyn_base"], r["dyn_custom"]])
            w.writerow(["kernel", r["func"], "dynamic_branches", r["branches_base"], r["branches_custom"]])


def main():
    if not rvbuild.toolchain_available():
        sys.exit("riscv64-elf-gcc / nm / objdump not found")
    func_rows = measure_functions()
    kernel_rows = measure_kernels()
    md = to_markdown(func_rows, kernel_rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "instruction_counts.md").write_text(md, encoding="utf-8")
    write_csv(func_rows, kernel_rows, OUT_DIR / "instruction_counts.csv")
    print(md)
    print(f"written: {OUT_DIR / 'instruction_counts.md'}")


if __name__ == "__main__":
    main()
