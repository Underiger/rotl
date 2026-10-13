"""ROTL 自訂指令:編碼、解碼與黃金模型(golden model)。

    rotl rd, rs1, rs2   ->   rd = rs1 循環左移 (rs2 & 31) 位
    格式:R-type,custom-0(opcode 0001011 = 0x0B)

funct3 / funct7 從 src/include/rotl_isa.h 讀取,與 C 和組合語言共用同一份設定。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src" / "include" / "rotl_isa.h"
VECTORS_CSV = ROOT / "src" / "tests" / "rotl_vectors.csv"

MASK32 = 0xFFFF_FFFF


def _read_define(name: str) -> int:
    m = re.search(rf"^#define\s+{name}\s+(0x[0-9A-Fa-f]+|\d+)", HEADER.read_text(), re.M)
    if not m:
        raise RuntimeError(f"{name} not found in {HEADER}")
    return int(m.group(1), 0)


OPCODE_CUSTOM0 = _read_define("ROTL_OPCODE")
FUNCT3_ROTL = _read_define("ROTL_FUNCT3")
FUNCT7_ROTL = _read_define("ROTL_FUNCT7")

ABI_NAMES = ["zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2", "s0", "s1"] + \
    [f"a{i}" for i in range(8)] + [f"s{i}" for i in range(2, 12)] + [f"t{i}" for i in range(3, 7)]


def rotl_golden(rs1: int, rs2: int) -> int:
    """黃金模型:直接照 HOMEWORK.md 6.4 的公式寫。"""
    rs1 &= MASK32
    n = rs2 & 31
    if n == 0:
        return rs1
    return ((rs1 << n) | (rs1 >> (32 - n))) & MASK32


def encode_rotl(rd: int, rs1: int, rs2: int) -> int:
    for name, r in (("rd", rd), ("rs1", rs1), ("rs2", rs2)):
        if not 0 <= r <= 31:
            raise ValueError(f"{name} out of range: {r}")
    return (
        (FUNCT7_ROTL << 25)
        | (rs2 << 20)
        | (rs1 << 15)
        | (FUNCT3_ROTL << 12)
        | (rd << 7)
        | OPCODE_CUSTOM0
    )


def decode_rotl(word: int):
    """若 word 是 ROTL 指令則回傳 (rd, rs1, rs2),否則回傳 None。"""
    if word & 0x7F != OPCODE_CUSTOM0:
        return None
    if (word >> 12) & 0x7 != FUNCT3_ROTL or (word >> 25) & 0x7F != FUNCT7_ROTL:
        return None
    return (word >> 7) & 0x1F, (word >> 15) & 0x1F, (word >> 20) & 0x1F


def fields(word: int) -> dict:
    """把 32-bit 指令字拆成 R-type 各欄位,報告的編碼表用。"""
    return {
        "funct7": (word >> 25) & 0x7F,
        "rs2": (word >> 20) & 0x1F,
        "rs1": (word >> 15) & 0x1F,
        "funct3": (word >> 12) & 0x7,
        "rd": (word >> 7) & 0x1F,
        "opcode": word & 0x7F,
    }


def load_vectors(path: Path = VECTORS_CSV):
    """讀取 CSV 測資,回傳 dict 串列(rs1、rs2、expected 已轉成 int)。"""
    rows = []
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    for line in lines[1:]:
        if not line.strip():
            continue
        row = dict(zip(header, line.split(",", len(header) - 1)))
        for k in ("rs1", "rs2", "expected"):
            row[k] = int(row[k], 16)
        rows.append(row)
    return rows


if __name__ == "__main__":
    print(f"opcode=0b{OPCODE_CUSTOM0:07b} funct3=0b{FUNCT3_ROTL:03b} funct7=0b{FUNCT7_ROTL:07b}")
    for rd, rs1, rs2 in ((10, 11, 12), (5, 6, 7), (0, 10, 11)):
        w = encode_rotl(rd, rs1, rs2)
        print(f"rotl {ABI_NAMES[rd]}, {ABI_NAMES[rs1]}, {ABI_NAMES[rs2]}  ->  0x{w:08X}  {w:032b}")
