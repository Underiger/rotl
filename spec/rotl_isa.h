#ifndef ROTL_ISA_H
#define ROTL_ISA_H

/*
 * ROTL 自訂指令的編碼常數(R-type,custom-0)。
 *
 *   rotl rd, rs1, rs2      rd = rs1 循環左移 (rs2 & 31) 位
 *
 * funct3 / funct7 由教師分配。分配前先用下列暫定值,
 * 分配後只需修改這兩行,C、組合語言與 Python 工具都會讀這個檔案。
 */
#define ROTL_OPCODE 0x0B /* custom-0 = 0001011 */
#define ROTL_FUNCT3 0x0  /* 暫定,待教師分配 */
#define ROTL_FUNCT7 0x0F /* 暫定,待教師分配(0001111,取題號 15) */

#define ROTL_STR_(x) #x
#define ROTL_STR(x) ROTL_STR_(x)

#ifdef __ASSEMBLER__

/* 組合語言用法:rotl a0, a1, a2 */
.macro rotl rd, rs1, rs2
    .insn r ROTL_OPCODE, ROTL_FUNCT3, ROTL_FUNCT7, \rd, \rs1, \rs2
.endm

#else

#include <stdint.h>

/* C 用法:以 inline assembly 發出一條 rotl 指令 */
static inline uint32_t rotl_insn(uint32_t rs1, uint32_t rs2)
{
#if defined(__riscv)
    uint32_t rd;
    __asm__(".insn r " ROTL_STR(ROTL_OPCODE) ", " ROTL_STR(ROTL_FUNCT3) ", "
            ROTL_STR(ROTL_FUNCT7) ", %0, %1, %2"
            : "=r"(rd)
            : "r"(rs1), "r"(rs2));
    return rd;
#else
    uint32_t n = rs2 & 31u;
    return n == 0 ? rs1 : (rs1 << n) | (rs1 >> (32u - n));
#endif
}

#endif /* __ASSEMBLER__ */

#endif /* ROTL_ISA_H */
