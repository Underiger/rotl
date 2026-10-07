#ifndef ROTL_H
#define ROTL_H

#include <stdint.h>

/*
 * ROTL 的 C 參考實作(CP1 baseline)。
 * 語意:n = rs2 & 31;n == 0 時 rd = rs1,否則 rd = (rs1 << n) | (rs1 >> (32 - n))。
 */
uint32_t rotl_ref(uint32_t rs1, uint32_t rs2);

#endif
