#ifndef KERNELS_H
#define KERNELS_H

#include <stdint.h>

/*
 * 兩個使用循環左移的密碼學核心,用來比較「實際程式中」ROTL 省下多少指令。
 *   ChaCha20:旋轉量為常數(16、12、8、7)
 *   RC5-32/12/16:旋轉量由資料決定(變數)
 * 編譯時以 -DUSE_CUSTOM_ROTL=0 / 1 切換標準 RV32IM 與自訂指令版本。
 */

#define RC5_ROUNDS 12
#define RC5_TABLE (2 * (RC5_ROUNDS + 1)) /* 26 個子金鑰 */

void chacha20_block(uint32_t out[16], const uint32_t in[16]);
void rc5_setup(uint32_t S[RC5_TABLE], const uint32_t key[4]);
void rc5_encrypt(const uint32_t S[RC5_TABLE], const uint32_t pt[2], uint32_t ct[2]);

#endif
