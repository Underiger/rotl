/*
 * 測資執行程式:把每組 (rs1, rs2) 依序送進四個版本,結果存到全域陣列。
 * 測資由模擬器在執行前寫入 vec_count / vec_rs1 / vec_rs2,
 * 執行後再讀出 out_* 與 Python 黃金模型比對。
 */
#include <stdint.h>

#include "rotl.h"

uint32_t rotl_branch(uint32_t rs1, uint32_t rs2);
uint32_t rotl_branchless(uint32_t rs1, uint32_t rs2);
uint32_t rotl_custom(uint32_t rs1, uint32_t rs2);

#define MAX_VECTORS 1024

uint32_t vec_count;
uint32_t vec_rs1[MAX_VECTORS];
uint32_t vec_rs2[MAX_VECTORS];

uint32_t out_ref[MAX_VECTORS];        /* C 參考實作,由 GCC -O2 編譯 */
uint32_t out_branch[MAX_VECTORS];     /* 手寫版本 A */
uint32_t out_branchless[MAX_VECTORS]; /* 手寫版本 B */
uint32_t out_custom[MAX_VECTORS];     /* 自訂指令 */

int main(void)
{
    uint32_t n = vec_count < MAX_VECTORS ? vec_count : MAX_VECTORS;
    for (uint32_t i = 0; i < n; i++) {
        out_ref[i] = rotl_ref(vec_rs1[i], vec_rs2[i]);
        out_branch[i] = rotl_branch(vec_rs1[i], vec_rs2[i]);
        out_branchless[i] = rotl_branchless(vec_rs1[i], vec_rs2[i]);
        out_custom[i] = rotl_custom(vec_rs1[i], vec_rs2[i]);
    }
    return 0;
}
