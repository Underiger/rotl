"""精簡的 RV32IM 指令集模擬器(ISS),用來計算動態指令數。

支援:RV32I 整數指令、M 擴充(乘除法)、custom-0 的 ROTL。
不支援:CSR、例外/中斷、壓縮指令(C 擴充)、虛擬記憶體。
程式從 ELF 的進入點開始執行,遇到 ebreak 停止。

指令數的歸屬方式:
  - 遇到 jal/jalr 且 rd = ra 視為函式呼叫,推入一個框(frame)
  - 遇到 ret(jalr x0, 0(ra))視為返回,彈出框
  - 每執行一條指令,呼叫堆疊上所有框的計數都加 1(包含式計數)
  - 呼叫指令本身算在呼叫者,ret 算在被呼叫者
"""

import struct
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from rotl_isa import FUNCT3_ROTL, FUNCT7_ROTL, MASK32, OPCODE_CUSTOM0, rotl_golden
from rvbuild import RV_NM

MEM_SIZE = 1 << 20

BRANCH = {0: "beq", 1: "bne", 4: "blt", 5: "bge", 6: "bltu", 7: "bgeu"}
LOAD = {0: "lb", 1: "lh", 2: "lw", 4: "lbu", 5: "lhu"}
STORE = {0: "sb", 1: "sh", 2: "sw"}
OP_IMM = {0: "addi", 2: "slti", 3: "sltiu", 4: "xori", 6: "ori", 7: "andi"}
OP = {(0, 0): "add", (0, 0x20): "sub", (1, 0): "sll", (2, 0): "slt", (3, 0): "sltu",
      (4, 0): "xor", (5, 0): "srl", (5, 0x20): "sra", (6, 0): "or", (7, 0): "and",
      (0, 1): "mul", (1, 1): "mulh", (2, 1): "mulhsu", (3, 1): "mulhu",
      (4, 1): "div", (5, 1): "divu", (6, 1): "rem", (7, 1): "remu"}
BRANCH_MNEMONICS = set(BRANCH.values())


class SimError(Exception):
    pass


def sext(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def s32(v: int) -> int:
    return sext(v, 32)


def mnemonic(inst: int) -> str:
    """只解碼出助憶符(靜態分析與統計用)。"""
    op, f3, f7 = inst & 0x7F, (inst >> 12) & 7, inst >> 25
    if inst & 3 != 3:
        raise SimError(f"compressed instruction 0x{inst:04x} not supported")
    if op == 0x37: return "lui"
    if op == 0x17: return "auipc"
    if op == 0x6F: return "jal"
    if op == 0x67: return "jalr"
    if op == 0x63 and f3 in BRANCH: return BRANCH[f3]
    if op == 0x03 and f3 in LOAD: return LOAD[f3]
    if op == 0x23 and f3 in STORE: return STORE[f3]
    if op == 0x13:
        if f3 == 1 and f7 == 0: return "slli"
        if f3 == 5 and f7 == 0: return "srli"
        if f3 == 5 and f7 == 0x20: return "srai"
        if f3 in OP_IMM: return OP_IMM[f3]
    if op == 0x33 and (f3, f7) in OP: return OP[(f3, f7)]
    if op == 0x0F: return "fence"
    if inst == 0x00000073: return "ecall"
    if inst == 0x00100073: return "ebreak"
    if op == OPCODE_CUSTOM0 and f3 == FUNCT3_ROTL and f7 == FUNCT7_ROTL: return "rotl"
    raise SimError(f"illegal instruction 0x{inst:08x}")


@dataclass
class Frame:
    name: str
    return_addr: int
    hist: Counter = field(default_factory=Counter)
    taken: int = 0

    @property
    def insns(self) -> int:
        return sum(self.hist.values())

    @property
    def branches(self) -> int:
        return sum(n for m, n in self.hist.items() if m in BRANCH_MNEMONICS)


def read_symbols(elf_path):
    """以 nm 讀取符號表:name -> (addr, size, type)。"""
    out = subprocess.run([RV_NM, "-S", "--defined-only", str(elf_path)],
                         capture_output=True, text=True, check=True).stdout
    syms = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 4:
            addr, size, typ, name = parts
            syms[name] = (int(addr, 16), int(size, 16), typ)
        elif len(parts) == 3:
            addr, typ, name = parts
            syms[name] = (int(addr, 16), 0, typ)
    return syms


def load_elf(path, mem: bytearray) -> int:
    data = Path(path).read_bytes()
    if data[:4] != b"\x7fELF" or data[4] != 1 or data[5] != 1:
        raise SimError("not a 32-bit little-endian ELF")
    (_, machine, _, entry, phoff, _, _, _, phentsize, phnum, _, _, _) = \
        struct.unpack_from("<HHIIIIIHHHHHH", data, 16)
    if machine != 243:
        raise SimError("not a RISC-V ELF")
    for i in range(phnum):
        p_type, p_offset, p_vaddr, _, p_filesz, p_memsz, _, _ = \
            struct.unpack_from("<IIIIIIII", data, phoff + i * phentsize)
        if p_type != 1:  # PT_LOAD
            continue
        if p_vaddr + p_memsz > len(mem):
            raise SimError("segment does not fit in simulator memory")
        mem[p_vaddr:p_vaddr + p_filesz] = data[p_offset:p_offset + p_filesz]
    return entry


class Sim:
    def __init__(self, elf_path, mem_size: int = MEM_SIZE):
        self.mem = bytearray(mem_size)
        self.pc = load_elf(elf_path, self.mem)
        self.symbols = read_symbols(elf_path)
        self.functions = sorted(
            (addr, addr + size, name) for name, (addr, size, typ) in self.symbols.items()
            if typ in "Tt" and size > 0)
        self.x = [0] * 32
        self.stack = [Frame("<top>", 0)]
        self.calls = []          # 每次完成的函式呼叫:Frame
        self.steps = 0

    # ---- 記憶體與符號 ----
    def addr(self, name: str) -> int:
        return self.symbols[name][0]

    def read_word(self, a: int) -> int:
        return int.from_bytes(self.mem[a:a + 4], "little")

    def write_word(self, a: int, v: int):
        self.mem[a:a + 4] = (v & MASK32).to_bytes(4, "little")

    def read_words(self, name: str, n: int):
        base = self.addr(name)
        return [self.read_word(base + 4 * i) for i in range(n)]

    def write_words(self, name: str, values):
        base = self.addr(name)
        for i, v in enumerate(values):
            self.write_word(base + 4 * i, v)

    def function_at(self, a: int) -> str:
        for lo, hi, name in self.functions:
            if lo <= a < hi:
                return name
        return f"0x{a:x}"

    def function_words(self, name: str):
        addr, size, _ = self.symbols[name]
        return [self.read_word(addr + i) for i in range(0, size, 4)]

    # ---- 執行 ----
    def run(self, max_steps: int = 5_000_000) -> int:
        while self.steps < max_steps:
            if self.step():
                return s32(self.x[10])
        raise SimError("step limit reached")

    def step(self) -> bool:
        x, mem, pc = self.x, self.mem, self.pc
        if pc + 4 > len(mem) or pc & 3:
            raise SimError(f"bad pc 0x{pc:x}")
        inst = int.from_bytes(mem[pc:pc + 4], "little")
        m = mnemonic(inst)
        for frame in self.stack:
            frame.hist[m] += 1
        self.steps += 1

        op = inst & 0x7F
        rd, f3 = (inst >> 7) & 31, (inst >> 12) & 7
        rs1, rs2 = (inst >> 15) & 31, (inst >> 20) & 31
        a, b = x[rs1], x[rs2]
        imm_i = sext(inst >> 20, 12)
        next_pc = (pc + 4) & MASK32
        result = None

        if op == 0x37:  # lui
            result = inst & 0xFFFFF000
        elif op == 0x17:  # auipc
            result = (pc + (inst & 0xFFFFF000)) & MASK32
        elif op == 0x6F:  # jal
            imm = sext(((inst >> 31) & 1) << 20 | ((inst >> 12) & 0xFF) << 12 |
                       ((inst >> 20) & 1) << 11 | ((inst >> 21) & 0x3FF) << 1, 21)
            result, next_pc = next_pc, (pc + imm) & MASK32
        elif op == 0x67:  # jalr
            result, next_pc = next_pc, (a + imm_i) & ~1 & MASK32
        elif op == 0x63:  # branch
            imm = sext(((inst >> 31) & 1) << 12 | ((inst >> 7) & 1) << 11 |
                       ((inst >> 25) & 0x3F) << 5 | ((inst >> 8) & 0xF) << 1, 13)
            taken = {"beq": a == b, "bne": a != b, "blt": s32(a) < s32(b),
                     "bge": s32(a) >= s32(b), "bltu": a < b, "bgeu": a >= b}[m]
            if taken:
                next_pc = (pc + imm) & MASK32
                for frame in self.stack:
                    frame.taken += 1
        elif op == 0x03:  # load
            ea = (a + imm_i) & MASK32
            width = {"lb": 1, "lbu": 1, "lh": 2, "lhu": 2, "lw": 4}[m]
            v = int.from_bytes(mem[ea:ea + width], "little")
            result = sext(v, 8 * width) & MASK32 if m in ("lb", "lh") else v
        elif op == 0x23:  # store
            imm = sext(((inst >> 25) << 5) | ((inst >> 7) & 31), 12)
            ea = (a + imm) & MASK32
            width = {"sb": 1, "sh": 2, "sw": 4}[m]
            mem[ea:ea + width] = (b & ((1 << 8 * width) - 1)).to_bytes(width, "little")
        elif op == 0x13:  # op-imm
            sh = rs2
            result = {
                "addi": lambda: a + imm_i, "slti": lambda: int(s32(a) < imm_i),
                "sltiu": lambda: int(a < (imm_i & MASK32)), "xori": lambda: a ^ imm_i,
                "ori": lambda: a | imm_i, "andi": lambda: a & imm_i,
                "slli": lambda: a << sh, "srli": lambda: a >> sh, "srai": lambda: s32(a) >> sh,
            }[m]() & MASK32
        elif op == 0x33:  # op / M 擴充
            result = self._alu(m, a, b)
        elif op == OPCODE_CUSTOM0:  # rotl
            result = rotl_golden(a, b)
        elif m == "ebreak":
            return True
        elif m in ("ecall", "fence"):
            pass

        if result is not None and rd != 0:
            x[rd] = result & MASK32

        # 呼叫/返回的歸屬
        if op in (0x6F, 0x67) and rd == 1:
            self.stack.append(Frame(self.function_at(next_pc), (pc + 4) & MASK32))
        elif op == 0x67 and rd == 0 and rs1 == 1 and imm_i == 0:
            frame = self.stack.pop()
            if frame.return_addr != next_pc:
                raise SimError(f"return from {frame.name} to unexpected address 0x{next_pc:x}")
            self.calls.append(frame)

        self.pc = next_pc
        return False

    @staticmethod
    def _alu(m: str, a: int, b: int) -> int:
        sa, sb = s32(a), s32(b)
        if m == "add": return a + b
        if m == "sub": return a - b
        if m == "sll": return a << (b & 31)
        if m == "slt": return int(sa < sb)
        if m == "sltu": return int(a < b)
        if m == "xor": return a ^ b
        if m == "srl": return a >> (b & 31)
        if m == "sra": return sa >> (b & 31)
        if m == "or": return a | b
        if m == "and": return a & b
        if m == "mul": return a * b
        if m == "mulh": return (sa * sb) >> 32
        if m == "mulhsu": return (sa * b) >> 32
        if m == "mulhu": return (a * b) >> 32
        if m in ("div", "rem"):
            if b == 0:
                return MASK32 if m == "div" else a
            if a == 0x80000000 and b == MASK32:
                return 0x80000000 if m == "div" else 0
            q = abs(sa) // abs(sb) * (1 if (sa < 0) == (sb < 0) else -1)
            return q if m == "div" else sa - q * sb
        if m == "divu": return a // b if b else MASK32
        if m == "remu": return a % b if b else a
        raise SimError(m)

    # ---- 統計 ----
    def calls_to(self, name: str):
        return [f for f in self.calls if f.name == name]


def static_profile(sim: Sim, name: str) -> dict:
    """靜態統計:函式本體的指令數、條件分支數與各助憶符次數。"""
    hist = Counter(mnemonic(w) for w in sim.function_words(name))
    return {
        "insns": sum(hist.values()),
        "branches": sum(n for m, n in hist.items() if m in BRANCH_MNEMONICS),
        "hist": hist,
    }
