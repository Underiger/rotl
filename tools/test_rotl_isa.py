"""黃金模型、測資檔與編碼的測試(不需要 RISC-V 工具鏈的部分在任何電腦都能跑)。"""

import random
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import kernels_golden as kg
import rvbuild
from rotl_isa import (FUNCT3_ROTL, FUNCT7_ROTL, OPCODE_CUSTOM0, decode_rotl, encode_rotl,
                      fields, load_vectors, rotl_golden)


def rotl_bitloop(x, s):
    for _ in range(s & 31):
        x = ((x << 1) | (x >> 31)) & 0xFFFFFFFF
    return x


class TestGolden(unittest.TestCase):
    def test_homework_vectors(self):
        """HOMEWORK.md 6.4 給的三組測資。"""
        self.assertEqual(rotl_golden(0x80000001, 1), 0x00000003)
        self.assertEqual(rotl_golden(0x12345678, 0), 0x12345678)
        self.assertEqual(rotl_golden(0x000000FF, 8), 0x0000FF00)

    def test_csv_vectors(self):
        rows = load_vectors()
        self.assertGreaterEqual(len(rows), 10)
        self.assertGreaterEqual(sum(r["category"] == "boundary" for r in rows), 3)
        for r in rows:
            with self.subTest(id=r["id"]):
                self.assertEqual(rotl_golden(r["rs1"], r["rs2"]), r["expected"])

    def test_matches_bitloop(self):
        rng = random.Random(2026)
        for _ in range(500):
            x = rng.getrandbits(32)
            s = rng.choice([rng.randrange(64), rng.getrandbits(32)])
            self.assertEqual(rotl_golden(x, s), rotl_bitloop(x, s))

    def test_only_low_five_bits_of_rs2(self):
        for s in range(32):
            for hi in (0, 32, 0x100, 0xFFFFFFE0):
                self.assertEqual(rotl_golden(0xDEADBEEF, s | hi), rotl_golden(0xDEADBEEF, s))


class TestKernelGolden(unittest.TestCase):
    def test_chacha_quarter_round_rfc8439_2_1_1(self):
        s = [0x11111111, 0x01020304, 0x9B8D6F43, 0x01234567]
        kg.chacha_quarter_round(s, 0, 1, 2, 3)
        self.assertEqual(s, [0xEA2A92F4, 0xCB1CF8CE, 0x4581472E, 0x5881C4BB])

    def test_chacha_block_rfc8439_2_3_2(self):
        self.assertEqual(kg.chacha20_block(kg.CHACHA_IN), kg.CHACHA_RFC_OUT)

    def test_rc5_paper_vector(self):
        self.assertEqual(kg.rc5_encrypt(kg.rc5_setup(kg.RC5_KEY), kg.RC5_PT), kg.RC5_PAPER_CT)


class TestEncoding(unittest.TestCase):
    def test_fields(self):
        w = encode_rotl(10, 11, 12)  # rotl a0, a1, a2
        self.assertEqual(fields(w), {"funct7": FUNCT7_ROTL, "rs2": 12, "rs1": 11,
                                     "funct3": FUNCT3_ROTL, "rd": 10, "opcode": 0b0001011})
        self.assertEqual(OPCODE_CUSTOM0, 0x0B)

    def test_roundtrip(self):
        for rd in range(32):
            for rs1 in (0, 1, 15, 31):
                for rs2 in (0, 7, 31):
                    self.assertEqual(decode_rotl(encode_rotl(rd, rs1, rs2)), (rd, rs1, rs2))

    def test_rejects_other_instructions(self):
        w = encode_rotl(10, 11, 12)
        self.assertIsNone(decode_rotl(w ^ (1 << 12)))   # funct3 不同
        self.assertIsNone(decode_rotl(w ^ (1 << 25)))   # funct7 不同
        self.assertIsNone(decode_rotl(0x00C58533))      # add a0, a1, a2

    def test_register_range(self):
        with self.assertRaises(ValueError):
            encode_rotl(32, 0, 0)


@unittest.skipUnless(rvbuild.toolchain_available(), "RISC-V toolchain not installed")
class TestAssemblerEncoding(unittest.TestCase):
    def test_assembler_matches_python_encoder(self):
        """組譯器對 rotl 巨集產生的機器碼,必須與 Python 編碼器一致。"""
        cases = [("a0", "a1", "a2", 10, 11, 12), ("t0", "t1", "t2", 5, 6, 7),
                 ("zero", "s0", "s11", 0, 8, 27), ("t6", "zero", "ra", 31, 0, 1)]
        src = '#include "rotl_isa.h"\n' + "".join(f"rotl {a}, {b}, {c}\n" for a, b, c, *_ in cases)
        with tempfile.TemporaryDirectory() as d:
            s, o = Path(d) / "probe.S", Path(d) / "probe.o"
            s.write_text(src)
            subprocess.run([rvbuild.RV_GCC, "-march=rv32im", "-mabi=ilp32",
                            f"-I{rvbuild.SRC / 'include'}", "-c", str(s), "-o", str(o)], check=True)
            dump = subprocess.run([rvbuild.RV_OBJDUMP, "-d", str(o)], check=True,
                                  capture_output=True, text=True).stdout
        words = [int(m.group(1), 16) for m in re.finditer(r"^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s", dump, re.M)]
        self.assertEqual(words, [encode_rotl(rd, rs1, rs2) for *_, rd, rs1, rs2 in cases])


if __name__ == "__main__":
    unittest.main()
