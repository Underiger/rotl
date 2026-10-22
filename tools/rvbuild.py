"""用 riscv64-elf-gcc 編譯 RV32IM 測試程式(輸出到 build/)。"""

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C_BASELINE = ROOT / "c_baseline"
RV32IM = ROOT / "rv32im"
SPEC = ROOT / "spec"
BUILD = ROOT / "build"

RV_GCC = shutil.which("riscv64-elf-gcc")
RV_NM = shutil.which("riscv64-elf-nm")
RV_OBJDUMP = shutil.which("riscv64-elf-objdump")

RV_CFLAGS = [
    "-march=rv32im", "-mabi=ilp32",
    "-O2",
    "-ffreestanding", "-nostdlib", "-nostartfiles", "-static",
    "-fno-optimize-sibling-calls",         # 不做尾呼叫,模擬器才能正確歸屬每個函式的指令數
    "-fno-tree-loop-distribute-patterns",  # 不把迴圈換成 memcpy/memset 呼叫
    "-Wall", "-Wextra", "-Werror",
    f"-I{SPEC}", f"-I{C_BASELINE}", f"-I{RV32IM}",
    f"-T{RV32IM / 'link.ld'}", "-Wl,--no-relax", "-Wl,--no-warn-rwx-segments",
]

COMMON = [RV32IM / "start.S", RV32IM / "runtime.c"]


def toolchain_available() -> bool:
    return bool(RV_GCC and RV_NM and RV_OBJDUMP)


def gcc_version() -> str:
    out = subprocess.run([RV_GCC, "--version"], capture_output=True, text=True, check=True)
    return out.stdout.splitlines()[0]


def _compile(out: Path, sources, defines=()) -> Path:
    BUILD.mkdir(exist_ok=True)
    cmd = [RV_GCC, *RV_CFLAGS, *(f"-D{d}" for d in defines), "-o", str(out), *map(str, sources)]
    subprocess.run(cmd, check=True)
    return out


def build_vectors() -> Path:
    return _compile(BUILD / "vectors.elf", [
        *COMMON,
        RV32IM / "rotl.S",
        C_BASELINE / "rotl.c",
        RV32IM / "vectors_main.c",
    ])


def build_kernels(custom: bool) -> Path:
    name = "kernels_custom.elf" if custom else "kernels_base.elf"
    return _compile(BUILD / name, [
        *COMMON,
        RV32IM / "kernels.c",
        RV32IM / "kernels_main.c",
    ], defines=[f"USE_CUSTOM_ROTL={int(custom)}"])


def emit_asm(src: Path, out: Path, opt: str = "-O2") -> Path:
    """產生 .s 組合語言檔,供報告引用編譯器輸出。"""
    BUILD.mkdir(exist_ok=True)
    flags = [f for f in RV_CFLAGS if not f.startswith(("-T", "-Wl,", "-O"))]
    subprocess.run([RV_GCC, *flags, opt, "-S", "-o", str(out), str(src)], check=True)
    return out
