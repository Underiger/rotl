# src/tests/(CP1–CP3)

[`rotl_vectors.csv`](rotl_vectors.csv):16 組測資,欄位為 `id, rs1, rs2, expected, category, note`。

| 類別 | 數量 | 涵蓋 |
|---|---:|---|
| `spec` | 2 | HOMEWORK.md 6.4 的公告測資(第三組 `n = 0` 歸在 boundary) |
| `boundary` | 10 | `n = 0`、`n = 31`、`rs2 = 32 / 33`、`rs2` 為負值、全 0、全 1、最高位繞回、最低位旋到最高位 |
| `general` | 4 | 旋轉 16 位(交換半字)、旋轉 4 位、一般值、交錯位元樣式 |

同一份 CSV 由三處讀取:

- `src/c_baseline/test_rotl.c`(主機 C 測試)
- `tools/test_rotl_isa.py`(黃金模型測試)
- `tools/test_rv32.py`、`tools/measure.py`(在 RV32 模擬器上執行)
