/*
 * 沒有 C 標準函式庫(-nostdlib),但 GCC 仍可能自行產生 memcpy / memset 呼叫,
 * 因此在這裡提供最簡單的版本。
 */
#include <stddef.h>

void *memcpy(void *dst, const void *src, size_t n)
{
    unsigned char *d = dst;
    const unsigned char *s = src;
    while (n--)
        *d++ = *s++;
    return dst;
}

void *memset(void *dst, int c, size_t n)
{
    unsigned char *d = dst;
    while (n--)
        *d++ = (unsigned char)c;
    return dst;
}
