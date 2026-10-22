/*
 * CP1 測試程式:在主機上驗證 rotl_ref。
 *
 *   ./test_rotl ../tests/rotl_vectors.csv
 *
 * 1. CSV 測資:逐筆比對預期輸出
 * 2. 交叉驗證:與「每次旋 1 位、重複 n 次」的獨立寫法比對
 * 3. 性質檢查:rotl(rotl(x, a), b) == rotl(x, a + b) 等
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rotl.h"

static int failures = 0;

static void check(const char *what, uint32_t rs1, uint32_t rs2, uint32_t got, uint32_t want)
{
    if (got != want) {
        failures++;
        printf("  FAIL %s: rs1=0x%08X rs2=0x%08X got=0x%08X want=0x%08X\n",
               what, (unsigned)rs1, (unsigned)rs2, (unsigned)got, (unsigned)want);
    }
}

/* 獨立的參考寫法:每次只旋 1 位,不會碰到移位 32 的問題 */
static uint32_t rotl_bitloop(uint32_t x, uint32_t rs2)
{
    for (uint32_t i = 0; i < (rs2 & 31u); i++)
        x = (x << 1) | (x >> 31);
    return x;
}

static uint32_t xorshift32(uint32_t *s)
{
    *s ^= *s << 13;
    *s ^= *s >> 17;
    *s ^= *s << 5;
    return *s;
}

static int run_csv(const char *path)
{
    FILE *f = fopen(path, "r");
    if (!f) {
        perror(path);
        return -1;
    }

    char line[512];
    int n = 0;
    if (!fgets(line, sizeof line, f)) { /* 跳過標題列 */
        fclose(f);
        return -1;
    }
    printf("[CSV] %s\n", path);
    printf("  %-4s %-10s %-10s %-10s %-10s %s\n", "id", "rs1", "rs2", "expected", "got", "result");
    while (fgets(line, sizeof line, f)) {
        char id[16];
        char *p = strtok(line, ",");
        if (!p)
            continue;
        snprintf(id, sizeof id, "%s", p);
        uint32_t rs1 = (uint32_t)strtoul(strtok(NULL, ","), NULL, 16);
        uint32_t rs2 = (uint32_t)strtoul(strtok(NULL, ","), NULL, 16);
        uint32_t want = (uint32_t)strtoul(strtok(NULL, ","), NULL, 16);
        uint32_t got = rotl_ref(rs1, rs2);
        printf("  %-4s 0x%08X 0x%08X 0x%08X 0x%08X %s\n", id, (unsigned)rs1, (unsigned)rs2,
               (unsigned)want, (unsigned)got, got == want ? "PASS" : "FAIL");
        check(id, rs1, rs2, got, want);
        n++;
    }
    fclose(f);
    return n;
}

int main(int argc, char **argv)
{
    const char *csv = argc > 1 ? argv[1] : "../tests/rotl_vectors.csv";

    int n = run_csv(csv);
    if (n < 0)
        return 2;

    /* 交叉驗證:特殊資料值 + 亂數資料,rs2 走過 0..63 以及接近 2^32 的值 */
    static const uint32_t special[] = {0x00000000, 0xFFFFFFFF, 0x80000000, 0x00000001,
                                       0x7FFFFFFF, 0xFFFFFFFE, 0x12345678, 0xA5A5A5A5};
    static const uint32_t big_rs2[] = {0xFFFFFFE0, 0xFFFFFFE1, 0xFFFFFFFF, 0x80000000, 0x7FFFFFFF};
    uint32_t seed = 2026;
    long cross = 0;
    for (int i = 0; i < 1000; i++) {
        uint32_t x = i < 8 ? special[i] : xorshift32(&seed);
        for (uint32_t s = 0; s < 64; s++, cross++)
            check("bitloop", x, s, rotl_ref(x, s), rotl_bitloop(x, s));
        for (size_t k = 0; k < sizeof big_rs2 / sizeof big_rs2[0]; k++, cross++)
            check("bitloop", x, big_rs2[k], rotl_ref(x, big_rs2[k]), rotl_bitloop(x, big_rs2[k]));
    }

    /* 性質:旋 a 再旋 b = 旋 a+b;旋 n 再旋 32-n 回到原值;1 的個數不變 */
    long props = 0;
    for (int i = 0; i < 2000; i++, props++) {
        uint32_t x = xorshift32(&seed);
        uint32_t a = xorshift32(&seed) & 31u, b = xorshift32(&seed) & 31u;
        check("compose", x, a + b, rotl_ref(rotl_ref(x, a), b), rotl_ref(x, a + b));
        check("inverse", x, a, rotl_ref(rotl_ref(x, a), 32u - a), x);
        check("popcount", x, a, (uint32_t)__builtin_popcount(rotl_ref(x, a)),
              (uint32_t)__builtin_popcount(x));
    }

    printf("[CSV]   %d vectors\n", n);
    printf("[CROSS] %ld comparisons with bit-by-bit rotation\n", cross);
    printf("[PROP]  %ld random cases x 3 properties\n", props);
    printf("%s (%d failures)\n", failures ? "FAILED" : "ALL PASS", failures);
    return failures ? 1 : 0;
}
