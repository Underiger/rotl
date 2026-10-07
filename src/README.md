# src/

| 目錄 | 對應 Checkpoint | 內容 |
|---|---|---|
| [`c_baseline/`](c_baseline/) | CP1 | C 參考實作 `rotl_ref`、主機測試程式、未定義行為反例 |
| [`tests/`](tests/) | CP1–CP3 | 測資 CSV(16 組,含 10 組邊界值) |
| [`rv32im/`](rv32im/) | CP2–CP3 | RV32IM 組合語言、自訂指令版本、密碼學核心、啟動程式與連結腳本 |
| [`include/`](include/) | CP3 | `rotl_isa.h`:ROTL 的編碼常數、組合語言巨集與 C inline 函式 |
