"""驗證 2:把 CPI 算進來,估計經典 5 級 pipeline(IF ID EX MEM WB)上的 cycle 數。

模型假設(課本 Patterson & Hennessy 的單發射、循序 pipeline):
  - 有完整 forwarding,一般 ALU 指令 CPI = 1
  - load-use hazard:load 的下一條指令讀取該暫存器時,stall 1 cycle
  - 分支預測「不跳」,分支在 EX 決定:taken 分支、jal、jalr 各損失 BRANCH_PENALTY cycle
  - ROTL 與 sll/srl 一樣在 EX 一個 cycle 完成,不改變 clock period(見 README 的討論)
  - mul 也假設 1 cycle(這兩個核心都沒用到乘除法)

    python3 experiments/pipeline_cycles.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import rv32sim  # noqa: E402
import rvbuild  # noqa: E402

KERNELS = ["chacha20_block", "rc5_setup", "rc5_encrypt"]
READS_RS1_RS2 = {0x33, 0x63, 0x23, 0x0B}   # R-type、branch、store、custom-0
READS_RS1 = {0x13, 0x03, 0x67}             # OP-IMM、load、jalr


class PipelineSim(rv32sim.Sim):
    def __init__(self, elf, branch_penalty):
        super().__init__(elf)
        self.penalty = branch_penalty
        self.prev_load_rd = 0

    def step(self) -> bool:
        pc = self.pc
        inst = self.read_word(pc)
        op, rd = inst & 0x7F, (inst >> 7) & 31
        rs1, rs2 = (inst >> 15) & 31, (inst >> 20) & 31
        reads = (rs1, rs2) if op in READS_RS1_RS2 else (rs1,) if op in READS_RS1 else ()

        stall = 1 if self.prev_load_rd and self.prev_load_rd in reads else 0
        frames = list(self.stack)  # 呼叫指令算呼叫者、ret 算被呼叫者
        done = super().step()
        if op in (0x6F, 0x67) or (op == 0x63 and self.pc != pc + 4):
            stall += self.penalty
        for f in frames:
            f.__dict__["stalls"] = f.__dict__.get("stalls", 0) + stall
        self.prev_load_rd = rd if op == 0x03 else 0
        return done


def measure(custom, penalty):
    sim = PipelineSim(rvbuild.build_kernels(custom), penalty)
    sim.run()
    out = {}
    for k in KERNELS:
        f = sim.calls_to(k)[0]
        out[k] = (f.insns, f.insns + f.__dict__.get("stalls", 0))
    return out


def main():
    print("| 核心 | 分支懲罰 | RV32IM 指令 / cycle / CPI | ROTL 指令 / cycle / CPI | IC 比 | cycle 比 |")
    print("|---|---:|---|---|---:|---:|")
    for penalty in (1, 2):
        base, cust = measure(False, penalty), measure(True, penalty)
        for k in KERNELS:
            (bi, bc), (ci, cc) = base[k], cust[k]
            print(f"| {k} | {penalty} | {bi} / {bc} / {bc / bi:.3f} | {ci} / {cc} / {cc / ci:.3f} "
                  f"| {bi / ci:.2f}x | {bc / cc:.2f}x |")


if __name__ == "__main__":
    main()
