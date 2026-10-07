# src/c_baseline/(CP1)

| 檔案 | 內容 |
|---|---|
| `rotl.h` / `rotl.c` | C 參考實作 `uint32_t rotl_ref(uint32_t rs1, uint32_t rs2)`,與規格逐字對應 |
| `test_rotl.c` | 主機測試:CSV 測資、與逐位旋轉寫法交叉比對、性質檢查 |
| `ub_demo.c` | 反例:未處理 `n = 0` 的寫法,在 UBSan 下會報出移位 32 的未定義行為 |

```bash
make test-c       # 編譯並執行 test_rotl
make test-ubsan   # 同一組測試加上 -fsanitize=undefined
make ub-demo      # 反例(n = 0 時預期報錯)
```

`rotl.c` 也會被 RISC-V 工具鏈編譯,作為 CP2 的「編譯器基準」(見 `../rv32im/vectors_main.c`)。
