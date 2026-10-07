#include "kernels.h"

#include "rotl_isa.h"

#ifndef USE_CUSTOM_ROTL
#define USE_CUSTOM_ROTL 0
#endif

/* 兩個版本只差在這個函式 */
static inline uint32_t rotl32(uint32_t x, uint32_t n)
{
#if USE_CUSTOM_ROTL
    return rotl_insn(x, n); /* 1 條 rotl */
#else
    return (x << (n & 31u)) | (x >> (-n & 31u)); /* 編譯器產生 sll/srl/or(或 slli/srli/or) */
#endif
}

/* ---------------- ChaCha20 區塊函式(RFC 8439 §2.3) ---------------- */

#define QR(a, b, c, d)                         \
    do {                                       \
        a += b; d ^= a; d = rotl32(d, 16);     \
        c += d; b ^= c; b = rotl32(b, 12);     \
        a += b; d ^= a; d = rotl32(d, 8);      \
        c += d; b ^= c; b = rotl32(b, 7);      \
    } while (0)

__attribute__((noinline)) void chacha20_block(uint32_t out[16], const uint32_t in[16])
{
    uint32_t x[16];
    for (int i = 0; i < 16; i++)
        x[i] = in[i];

    for (int i = 0; i < 10; i++) { /* 10 次 double round = 20 rounds */
        QR(x[0], x[4], x[8], x[12]);
        QR(x[1], x[5], x[9], x[13]);
        QR(x[2], x[6], x[10], x[14]);
        QR(x[3], x[7], x[11], x[15]);
        QR(x[0], x[5], x[10], x[15]);
        QR(x[1], x[6], x[11], x[12]);
        QR(x[2], x[7], x[8], x[13]);
        QR(x[3], x[4], x[9], x[14]);
    }

    for (int i = 0; i < 16; i++)
        out[i] = x[i] + in[i];
}

/* ---------------- RC5-32/12/16(Rivest 1994) ---------------- */

#define RC5_P32 0xB7E15163u
#define RC5_Q32 0x9E3779B9u

__attribute__((noinline)) void rc5_setup(uint32_t S[RC5_TABLE], const uint32_t key[4])
{
    uint32_t L[4] = {key[0], key[1], key[2], key[3]};

    S[0] = RC5_P32;
    for (int i = 1; i < RC5_TABLE; i++)
        S[i] = S[i - 1] + RC5_Q32;

    uint32_t A = 0, B = 0;
    int i = 0, j = 0;
    for (int k = 0; k < 3 * RC5_TABLE; k++) {
        A = S[i] = rotl32(S[i] + A + B, 3);
        B = L[j] = rotl32(L[j] + A + B, A + B); /* 旋轉量由資料決定 */
        if (++i == RC5_TABLE)
            i = 0;
        j = (j + 1) & 3;
    }
}

__attribute__((noinline)) void rc5_encrypt(const uint32_t S[RC5_TABLE], const uint32_t pt[2],
                                           uint32_t ct[2])
{
    uint32_t A = pt[0] + S[0];
    uint32_t B = pt[1] + S[1];
    for (int i = 1; i <= RC5_ROUNDS; i++) {
        A = rotl32(A ^ B, B) + S[2 * i];
        B = rotl32(B ^ A, A) + S[2 * i + 1];
    }
    ct[0] = A;
    ct[1] = B;
}
