#include "rotl.h"

uint32_t rotl_ref(uint32_t rs1, uint32_t rs2)
{
    uint32_t n = rs2 & 31u; /* 只看 rs2 的低 5 位元 */

    /* n == 0 必須單獨處理:否則會算 rs1 >> 32,
     * 在 C 中移位量 >= 型別寬度是未定義行為(C11 6.5.7)。 */
    if (n == 0)
        return rs1;

    /* 用 uint32_t,>> 才是邏輯右移(左邊補 0) */
    return (rs1 << n) | (rs1 >> (32u - n));
}
