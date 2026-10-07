"""在模擬器上執行 RV32IM 程式,驗證正確性與指令數。"""

import random
import unittest

import kernels_golden as kg
import rv32sim
import rvbuild
from rotl_isa import load_vectors, rotl_golden


@unittest.skipUnless(rvbuild.toolchain_available(), "RISC-V toolchain not installed")
class TestRotlFunctions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = random.Random(2026)
        cls.inputs = [(v["rs1"], v["rs2"]) for v in load_vectors()]
        cls.inputs += [(rng.getrandbits(32), rng.getrandbits(32)) for _ in range(300)]
        cls.inputs += [(rng.getrandbits(32), s) for s in range(64)]
        sim = rv32sim.Sim(rvbuild.build_vectors())
        sim.write_words("vec_count", [len(cls.inputs)])
        sim.write_words("vec_rs1", [a for a, _ in cls.inputs])
        sim.write_words("vec_rs2", [b for _, b in cls.inputs])
        sim.run()
        cls.sim = sim

    def check_outputs(self, array):
        got = self.sim.read_words(array, len(self.inputs))
        for (a, b), g in zip(self.inputs, got):
            self.assertEqual(g, rotl_golden(a, b), f"rs1=0x{a:08X} rs2=0x{b:08X}")

    def test_c_reference(self):
        self.check_outputs("out_ref")

    def test_branch_version(self):
        self.check_outputs("out_branch")

    def test_branchless_version(self):
        self.check_outputs("out_branchless")

    def test_custom_instruction(self):
        self.check_outputs("out_custom")

    def test_dynamic_counts(self):
        """含 ret 的每次呼叫指令數:A 版 n=0 為 3、否則 8;B 版固定 5;自訂指令固定 2。"""
        for frame, (_, b) in zip(self.sim.calls_to("rotl_branch"), self.inputs):
            self.assertEqual(frame.insns, 3 if b & 31 == 0 else 8)
        self.assertEqual({f.insns for f in self.sim.calls_to("rotl_branchless")}, {5})
        self.assertEqual({f.insns for f in self.sim.calls_to("rotl_custom")}, {2})


@unittest.skipUnless(rvbuild.toolchain_available(), "RISC-V toolchain not installed")
class TestKernels(unittest.TestCase):
    def run_kernels(self, custom):
        sim = rv32sim.Sim(rvbuild.build_kernels(custom))
        sim.run()
        self.assertEqual(sim.read_words("chacha_out", 16), kg.CHACHA_RFC_OUT)
        self.assertEqual(sim.read_words("rc5_S", kg.RC5_TABLE), kg.rc5_setup(kg.RC5_KEY))
        self.assertEqual(sim.read_words("rc5_ct", 2), kg.RC5_PAPER_CT)
        return sim

    def test_baseline_correct_and_has_no_custom_instruction(self):
        sim = self.run_kernels(False)
        self.assertEqual(sim.stack[0].hist["rotl"], 0)

    def test_custom_correct_and_rotation_counts(self):
        sim = self.run_kernels(True)
        self.assertEqual(sim.calls_to("chacha20_block")[0].hist["rotl"], 10 * 8 * 4)
        self.assertEqual(sim.calls_to("rc5_setup")[0].hist["rotl"], 2 * 3 * kg.RC5_TABLE)
        self.assertEqual(sim.calls_to("rc5_encrypt")[0].hist["rotl"], 2 * kg.RC5_ROUNDS)

    def test_custom_never_slower_in_instruction_count(self):
        base, cust = self.run_kernels(False), self.run_kernels(True)
        for f in ("chacha20_block", "rc5_setup", "rc5_encrypt"):
            self.assertLess(cust.calls_to(f)[0].insns, base.calls_to(f)[0].insns)


class TestSimulatorAlu(unittest.TestCase):
    """M 擴充的邊界語意(RISC-V 規格書 13.2 節:除以 0 與溢位不產生例外)。"""

    def test_division_edge_cases(self):
        alu, M = rv32sim.Sim._alu, 0xFFFFFFFF
        self.assertEqual(alu("div", 7, 0) & M, M)
        self.assertEqual(alu("divu", 7, 0) & M, M)
        self.assertEqual(alu("rem", 7, 0) & M, 7)
        self.assertEqual(alu("remu", 7, 0) & M, 7)
        self.assertEqual(alu("div", 0x80000000, M) & M, 0x80000000)
        self.assertEqual(alu("rem", 0x80000000, M) & M, 0)
        self.assertEqual(alu("div", (-7) & M, 2) & M, (-3) & M)   # 向 0 取整
        self.assertEqual(alu("rem", (-7) & M, 2) & M, (-1) & M)

    def test_shift_uses_low_five_bits(self):
        alu = rv32sim.Sim._alu
        self.assertEqual(alu("sll", 1, 33) & 0xFFFFFFFF, 2)
        self.assertEqual(alu("srl", 0x80000000, 0xFFFFFFFF), 1)


if __name__ == "__main__":
    unittest.main()
