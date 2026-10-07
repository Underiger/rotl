/*
 * ROTL 的 RV32IM 實作(CP2),以及使用自訂指令的版本(CP3 比較用)。
 *
 * 呼叫慣例(ilp32):a0 = rs1(被旋轉的值),a1 = rs2(移位量),回傳值放 a0。
 * 只用到 caller-saved 暫存器(t0–t2),不需要存取堆疊。
 */
#include "rotl_isa.h"

    .text

/*
 * 版本 A:依規格逐字翻譯,n == 0 用分支處理。
 * 動態指令數:n == 0 時 3 條(含 ret),否則 8 條。
 */
    .globl rotl_branch
    .type  rotl_branch, @function
rotl_branch:
    andi    a1, a1, 31          # n = rs2 & 31
    beqz    a1, 1f              # n == 0 -> rd = rs1
    li      t0, 32
    sub     t0, t0, a1          # t0 = 32 - n(此時 1 <= n <= 31,不會出現移位 32)
    sll     t1, a0, a1          # t1 = rs1 << n
    srl     t2, a0, t0          # t2 = rs1 >> (32 - n)(邏輯右移)
    or      a0, t1, t2
1:
    ret
    .size  rotl_branch, .-rotl_branch

/*
 * 版本 B:無分支。利用 RV32I 的 sll/srl 只取 rs2 低 5 位元的特性:
 *   (-n) & 31 = (32 - n) & 31,n == 0 時為 0,此時 rs1 | rs1 = rs1。
 * 因此不需要 andi,也不需要 n == 0 的分支。
 * 動態指令數:固定 5 條(含 ret)。
 */
    .globl rotl_branchless
    .type  rotl_branchless, @function
rotl_branchless:
    sll     t0, a0, a1          # rs1 << (rs2 & 31)
    neg     t1, a1              # -rs2,低 5 位元 = (32 - n) & 31
    srl     t1, a0, t1          # rs1 >> ((32 - n) & 31)
    or      a0, t0, t1
    ret
    .size  rotl_branchless, .-rotl_branchless

/*
 * 版本 C:使用自訂指令 rotl(R-type,custom-0)。
 * 動態指令數:固定 2 條(含 ret)。實際使用時會被 inline,只剩 1 條。
 */
    .globl rotl_custom
    .type  rotl_custom, @function
rotl_custom:
    rotl    a0, a0, a1
    ret
    .size  rotl_custom, .-rotl_custom
