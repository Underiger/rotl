# src/rv32im/(CP2–CP3)

只使用 RV32IM 指令(`-march=rv32im -mabi=ilp32`)。自訂指令只出現在標示為 custom 的版本。

| 檔案 | 內容 |
|---|---|
| `rotl.S` | 三個手寫版本:`rotl_branch`(逐字翻譯,含分支)、`rotl_branchless`(無分支)、`rotl_custom`(自訂指令) |
| `vectors_main.c` | 把測資送進 C 參考實作與三個手寫版本,結果存到全域陣列 |
| `kernels.c` / `kernels.h` | ChaCha20 區塊函式與 RC5-32/12/16,以 `USE_CUSTOM_ROTL` 切換標準版與自訂指令版 |
| `kernels_main.c` | 以 RFC 8439 與 RC5 論文的測試向量呼叫核心 |
| `start.S` | 設定堆疊、呼叫 `main`、`ebreak` |
| `link.ld` | 連結腳本:程式從位址 0 開始 |
| `runtime.c` | `memcpy` / `memset`(無標準函式庫時 GCC 仍可能呼叫) |

建置與執行由 `tools/` 的 Python 腳本處理:

```bash
make test-py   # 在模擬器上驗證正確性與指令數
make counts    # 產生 report/figures/instruction_counts.md
make asm       # 產生 build/rotl_O0.s、build/rotl_O2.s(編譯器輸出)
```

## 在 Ripes 中執行

`rotl.S` 的 `rotl_branch` 與 `rotl_branchless` 只用 RV32I 指令,可以把函式本體貼進 Ripes。
在前面加上設定 `a0`、`a1` 的指令,就能觀察暫存器變化。Ripes 不認得 custom-0,所以 `rotl_custom` 無法在 Ripes 執行。
