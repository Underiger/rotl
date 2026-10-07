/*
 * 反例示範:沒有處理 n == 0 的寫法。
 *
 *   make ub-demo
 *
 * 以 UndefinedBehaviorSanitizer 編譯後,n = 0 時會在執行期回報
 * "shift exponent 32 is too large",說明 rotl_ref 中 n == 0 分支的必要性。
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static uint32_t rotl_naive(uint32_t rs1, uint32_t rs2)
{
    uint32_t n = rs2 & 31u;
    return (rs1 << n) | (rs1 >> (32u - n)); /* n == 0 時變成 rs1 >> 32:未定義行為 */
}

int main(int argc, char **argv)
{
    uint32_t rs2 = argc > 1 ? (uint32_t)strtoul(argv[1], NULL, 0) : 0;
    printf("rotl_naive(0x12345678, %u) = 0x%08X\n", (unsigned)rs2,
           (unsigned)rotl_naive(0x12345678u, rs2));
    return 0;
}
