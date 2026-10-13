# tools/

| 檔案 | 用途 |
|---|---|
| `rotl_isa.py` | 黃金模型 `rotl_golden`、編碼器 `encode_rotl`、解碼器 `decode_rotl`、讀取 CSV 測資 |
| `kernels_golden.py` | ChaCha20 與 RC5 的 Python 參考實作及公開測試向量 |
| `rvbuild.py` | 呼叫 `riscv64-elf-gcc` 編譯 RV32 執行檔到 `build/` |
| `rv32sim.py` | 精簡 RV32IM 指令集模擬器,計算每個函式的動態指令數與分支數 |
| `measure.py` | 產生 `report/figures/instruction_counts.{md,csv}` |
| `test_rotl_isa.py` | 黃金模型、CSV、編碼、組譯器輸出一致性的測試 |
| `test_rv32.py` | 在模擬器上驗證四個版本、兩個核心的正確性與指令數 |

## 模擬器 `rv32sim.py`

課程沒有要求使用 Spike,因此我們用 Python 寫了一個只做功能模擬的 ISS:

- 載入 ELF,從進入點執行到 `ebreak`
- 支援 RV32I、M 擴充,以及 custom-0 的 `rotl`(語意直接呼叫黃金模型)
- 不支援 CSR、例外、壓縮指令;不模擬 pipeline,**只算指令數,不算 cycle**
- 指令數以「包含式」歸屬到函式:`jal`/`jalr` 且 `rd = ra` 視為呼叫,`ret` 視為返回

可信度的依據:

1. GCC 產生的四個 ROTL 版本在 380 組輸入上與黃金模型一致
2. ChaCha20 與 RC5 的輸出與 RFC 8439、RC5 論文的公開答案一致
3. 手寫函式的動態指令數可以人工逐行核對(3 / 8、5、2)
