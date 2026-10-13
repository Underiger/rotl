/*
 * 核心執行程式:各跑一次 ChaCha20 區塊、RC5 金鑰排程與 RC5 加密,
 * 輸入使用公開標準的測試向量,輸出由模擬器讀出並與已知答案比對。
 */
#include "kernels.h"

/* RFC 8439 §2.3.2:key = 00 01 .. 1f,counter = 1,nonce = 00 00 00 09 00 00 00 4a 00 00 00 00 */
const uint32_t chacha_in[16] = {
    0x61707865, 0x3320646e, 0x79622d32, 0x6b206574, /* "expand 32-byte k" */
    0x03020100, 0x07060504, 0x0b0a0908, 0x0f0e0d0c,
    0x13121110, 0x17161514, 0x1b1a1918, 0x1f1e1d1c,
    0x00000001, 0x09000000, 0x4a000000, 0x00000000,
};

/* Rivest 1994 RC5-32/12/16 第一組測資:key 與明文皆為 0 */
const uint32_t rc5_key[4] = {0, 0, 0, 0};
const uint32_t rc5_pt[2] = {0, 0};

uint32_t chacha_out[16];
uint32_t rc5_S[RC5_TABLE];
uint32_t rc5_ct[2];

int main(void)
{
    chacha20_block(chacha_out, chacha_in);
    rc5_setup(rc5_S, rc5_key);
    rc5_encrypt(rc5_S, rc5_pt, rc5_ct);
    return 0;
}
