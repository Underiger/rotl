/*
 * 驗證 3:在真實 CPU(Apple Silicon,ARM64)上量測「有旋轉指令」與「只能用移位組合」的時間差。
 *
 * RISC-V RV32IM 沒有旋轉指令,但 ARM64 有 ror。我們用 inline assembly 強制兩種寫法:
 *   ROR   版:常數旋轉 1 條(ror);變數旋轉 2 條(neg + ror,ARM 只有右旋)
 *   SHIFT 版:常數旋轉 3 條(lsl、lsr、orr);變數旋轉 4 條(lsl、neg、lsr、orr)
 * SHIFT 版的指令序列與 RV32IM 相同,ROR 版相當於加了一條旋轉指令。
 * 其餘程式碼兩版完全相同,所以時間差只來自旋轉的寫法。
 *
 *   make -C experiments bench    (或 cc -O2 -std=gnu11 arm64_rotate_bench.c && ./a.out)
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#if !defined(__aarch64__)
#error "this benchmark needs an ARM64 CPU (Apple Silicon)"
#endif

/* ---------- 兩種旋轉寫法 ---------- */

#define ROTC_ROR(x, k) ({ uint32_t r_; \
    __asm__("ror %w0, %w1, %2" : "=r"(r_) : "r"(x), "i"(32 - (k))); r_; })
#define ROTV_ROR(x, n) ({ uint32_t r_, t_; \
    __asm__("neg %w1, %w3\n\tror %w0, %w2, %w1" : "=r"(r_), "=&r"(t_) : "r"(x), "r"(n)); r_; })

#define ROTC_SHIFT(x, k) ({ uint32_t a_, b_; \
    __asm__("lsl %w0, %w2, %3\n\tlsr %w1, %w2, %4\n\torr %w0, %w0, %w1" \
            : "=&r"(a_), "=&r"(b_) : "r"(x), "i"(k), "i"(32 - (k))); a_; })
#define ROTV_SHIFT(x, n) ({ uint32_t a_, b_; \
    __asm__("lsl %w0, %w2, %w3\n\tneg %w1, %w3\n\tlsr %w1, %w2, %w1\n\torr %w0, %w0, %w1" \
            : "=&r"(a_), "=&r"(b_) : "r"(x), "r"(n)); a_; })

/* ---------- 同一份核心程式,依旋轉寫法產生兩個版本 ---------- */

#define RC5_T 26

#define DEFINE_KERNELS(SUFFIX, ROTC, ROTV)                                              \
    __attribute__((noinline)) void chacha_##SUFFIX(uint32_t out[16], const uint32_t in[16]) \
    {                                                                                   \
        uint32_t x[16];                                                                 \
        memcpy(x, in, sizeof x);                                                        \
        for (int i = 0; i < 10; i++) {                                                  \
            QR(ROTC, x[0], x[4], x[8], x[12]); QR(ROTC, x[1], x[5], x[9], x[13]);        \
            QR(ROTC, x[2], x[6], x[10], x[14]); QR(ROTC, x[3], x[7], x[11], x[15]);      \
            QR(ROTC, x[0], x[5], x[10], x[15]); QR(ROTC, x[1], x[6], x[11], x[12]);      \
            QR(ROTC, x[2], x[7], x[8], x[13]); QR(ROTC, x[3], x[4], x[9], x[14]);        \
        }                                                                               \
        for (int i = 0; i < 16; i++)                                                    \
            out[i] = x[i] + in[i];                                                      \
    }                                                                                   \
    __attribute__((noinline)) void rc5_setup_##SUFFIX(uint32_t S[RC5_T], const uint32_t key[4]) \
    {                                                                                   \
        uint32_t L[4] = {key[0], key[1], key[2], key[3]};                               \
        S[0] = 0xB7E15163u;                                                             \
        for (int i = 1; i < RC5_T; i++)                                                 \
            S[i] = S[i - 1] + 0x9E3779B9u;                                              \
        uint32_t A = 0, B = 0;                                                          \
        for (int k = 0, i = 0, j = 0; k < 3 * RC5_T; k++) {                             \
            A = S[i] = ROTC(S[i] + A + B, 3);                                           \
            B = L[j] = ROTV(L[j] + A + B, A + B);                                       \
            if (++i == RC5_T) i = 0;                                                    \
            j = (j + 1) & 3;                                                            \
        }                                                                               \
    }                                                                                   \
    __attribute__((noinline)) void rc5_enc_##SUFFIX(const uint32_t S[RC5_T], const uint32_t pt[2], uint32_t ct[2]) \
    {                                                                                   \
        uint32_t A = pt[0] + S[0], B = pt[1] + S[1];                                    \
        for (int i = 1; i <= 12; i++) {                                                 \
            A = ROTV(A ^ B, B) + S[2 * i];                                              \
            B = ROTV(B ^ A, A) + S[2 * i + 1];                                          \
        }                                                                               \
        ct[0] = A; ct[1] = B;                                                           \
    }

#define QR(ROTC, a, b, c, d)                       \
    do {                                           \
        a += b; d ^= a; d = ROTC(d, 16);           \
        c += d; b ^= c; b = ROTC(b, 12);           \
        a += b; d ^= a; d = ROTC(d, 8);            \
        c += d; b ^= c; b = ROTC(b, 7);            \
    } while (0)

DEFINE_KERNELS(ror, ROTC_ROR, ROTV_ROR)
DEFINE_KERNELS(shift, ROTC_SHIFT, ROTV_SHIFT)

/* ---------- 量測 ---------- */

static const uint32_t CHACHA_IN[16] = {
    0x61707865, 0x3320646e, 0x79622d32, 0x6b206574, 0x03020100, 0x07060504, 0x0b0a0908, 0x0f0e0d0c,
    0x13121110, 0x17161514, 0x1b1a1918, 0x1f1e1d1c, 0x00000001, 0x09000000, 0x4a000000, 0x00000000};

static double now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return ts.tv_sec * 1e9 + ts.tv_nsec;
}

#define REPEATS 15

typedef double (*bench_fn)(long n);

/* 每次的輸出都餵給下一次,避免編譯器把重複的呼叫省略 */
#define BENCH(SUFFIX)                                                            \
    static double chacha_bench_##SUFFIX(long n)                                  \
    {                                                                            \
        uint32_t in[16], out[16];                                                \
        memcpy(in, CHACHA_IN, sizeof in);                                        \
        double t0 = now_ns();                                                    \
        for (long i = 0; i < n; i++) {                                           \
            chacha_##SUFFIX(out, in);                                            \
            in[12] += out[0] | 1;                                                \
        }                                                                        \
        return (now_ns() - t0) / n;                                              \
    }                                                                            \
    static double setup_bench_##SUFFIX(long n)                                   \
    {                                                                            \
        uint32_t key[4] = {0, 0, 0, 0}, S[RC5_T];                                \
        double t0 = now_ns();                                                    \
        for (long i = 0; i < n; i++) {                                           \
            rc5_setup_##SUFFIX(S, key);                                          \
            key[0] ^= S[25];                                                     \
        }                                                                        \
        return (now_ns() - t0) / n;                                              \
    }                                                                            \
    static double enc_bench_##SUFFIX(long n)                                     \
    {                                                                            \
        uint32_t key[4] = {0, 0, 0, 0}, S[RC5_T], b[2] = {0, 0};                 \
        rc5_setup_##SUFFIX(S, key);                                              \
        double t0 = now_ns();                                                    \
        for (long i = 0; i < n; i++)                                             \
            rc5_enc_##SUFFIX(S, b, b);                                           \
        return (now_ns() - t0) / n;                                              \
    }

BENCH(ror)
BENCH(shift)

static double best(bench_fn f, long n)
{
    double m = 1e30;
    for (int r = 0; r < REPEATS; r++) {
        double t = f(n);
        if (t < m)
            m = t;
    }
    return m;
}

static int check(void)
{
    static const uint32_t rfc0 = 0xe4e7f110, rfc15 = 0x4e3c50a2;
    uint32_t a[16], b[16], S1[RC5_T], S2[RC5_T], c1[2], c2[2], z[4] = {0}, p[2] = {0};
    chacha_ror(a, CHACHA_IN);
    chacha_shift(b, CHACHA_IN);
    rc5_setup_ror(S1, z);
    rc5_setup_shift(S2, z);
    rc5_enc_ror(S1, p, c1);
    rc5_enc_shift(S2, p, c2);
    return a[0] == rfc0 && a[15] == rfc15 && !memcmp(a, b, sizeof a) && !memcmp(S1, S2, sizeof S1) &&
           c1[0] == 0xEEDBA521 && c1[1] == 0x6D8F4B15 && c2[0] == c1[0] && c2[1] == c1[1];
}

int main(void)
{
    if (!check()) {
        puts("correctness check FAILED");
        return 1;
    }
    puts("correctness: ChaCha20 matches RFC 8439, RC5 matches the paper, both versions agree");

    struct { const char *name; bench_fn ror, shift; long n; } cases[] = {
        {"ChaCha20 block (constant rotations)", chacha_bench_ror, chacha_bench_shift, 400000},
        {"RC5 key setup (constant + variable)", setup_bench_ror, setup_bench_shift, 200000},
        {"RC5 encrypt one block (variable)", enc_bench_ror, enc_bench_shift, 4000000},
    };
    printf("| kernel | shift ns | ror ns | speedup |\n|---|---:|---:|---:|\n");
    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        best(cases[i].shift, cases[i].n / 10); /* warm-up */
        best(cases[i].ror, cases[i].n / 10);
        double s = best(cases[i].shift, cases[i].n);
        double r = best(cases[i].ror, cases[i].n);
        printf("| %s | %.1f | %.1f | %.2fx |\n", cases[i].name, s, r, s / r);
    }
    return 0;
}
