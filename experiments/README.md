# experiments/:ROTL 真的有讓效能變好嗎?

CP3 的指令數是本組模擬器算出來的,而執行時間 = IC × CPI × Clock Cycle Time。
這裡用三個彼此獨立的方法檢查「變快」這件事是否成立。

```bash
make verify     # 三個驗證一起跑(第 3 個需要 Apple Silicon 等 ARM64 電腦)
```

## 驗證 1:指令數(IC)不靠模擬器也算得出來

[`ic_crosscheck.py`](ic_crosscheck.py) 只用 `riscv64-elf-objdump` 的反組譯結果加上 C 原始碼的迴圈次數推算動態指令數:迴圈內的指令 × 迴圈次數,其他指令算一次。

| 核心 | 版本 | 推算(objdump) | 模擬器 | 一致 |
|---|---|---:|---:|:---:|
| chacha20_block | RV32IM | 1919 | 1919 | ✓ |
| rc5_setup | RV32IM | 2467 | 2467 | ✓ |
| rc5_encrypt | RV32IM | 227 | 227 | ✓ |
| chacha20_block | ROTL | 1284 | 1284 | ✓ |
| rc5_setup | ROTL | 2000 | 2000 | ✓ |
| rc5_encrypt | ROTL | 131 | 131 | ✓ |

`rc5_setup` 的迴圈被編譯器「旋轉」過:進入前先 `j` 跳到迴圈中間,所以迴圈第一條 `lw` 只執行 77 次。腳本有處理這種情況。

**結論:IC 數字正確。**

## 驗證 2:加入 CPI(5 級 pipeline 模型)

[`pipeline_cycles.py`](pipeline_cycles.py) 在模擬器上加入課本的 5 級循序 pipeline 時間模型:完整 forwarding、load-use stall 1 cycle、分支預測不跳(taken 分支與跳躍損失 1 或 2 cycle)。假設 ROTL 和 `sll` 一樣在 EX 一個 cycle 完成。

| 核心 | IC 比 | cycle 比(懲罰 1) | cycle 比(懲罰 2) | CPI RV32IM → ROTL(懲罰 2) |
|---|---:|---:|---:|---|
| ChaCha20 | 1.49x | 1.48x | 1.47x | 1.042 → 1.062 |
| RC5 金鑰排程 | 1.23x | 1.22x | 1.21x | 1.084 → 1.103 |
| RC5 加密 | 1.73x | 1.67x | 1.62x | 1.106 → 1.183 |

兩個版本的 stall cycle 數完全相同,stall 都來自迴圈分支,旋轉本身不會產生 hazard。指令變少後,固定的 stall 佔比變高,所以 CPI 略升,cycle 比略低於 IC 比。

**結論:在單發射 5 級 pipeline 上,cycle 數的改善幾乎等於 IC 的改善。** 前提是 ROTL 不拉長 clock period。

## 驗證 3:真實 CPU 上的時間(Apple M5,ARM64)

RISC-V 沒有現成的 ROTL 硬體可以量,但 ARM64 有旋轉指令 `ror`。[`arm64_rotate_bench.c`](arm64_rotate_bench.c) 用 inline assembly 強制產生兩個版本,其餘程式完全相同:

| 版本 | 常數旋轉 | 變數旋轉 | 相當於 |
|---|---|---|---|
| SHIFT | `lsl`、`lsr`、`orr`(3 條) | `lsl`、`neg`、`lsr`、`orr`(4 條) | RV32IM |
| ROR | `ror`(1 條) | `neg`、`ror`(2 條,ARM 只有右旋) | 有旋轉指令 |

量測方式:Apple clang 21 `-O2`,每個核心重複 15 次取最快,輸出接到下一次的輸入,避免被編譯器省略。執行四次的結果:

| 核心 | SHIFT(ns) | ROR(ns) | 實測加速 | RISC-V IC 比(對照) |
|---|---:|---:|---:|---:|
| ChaCha20 區塊 | 184 | 122 | **1.51x** | 1.49x |
| RC5 金鑰排程 | 286–297 | 220–221 | **1.29–1.35x** | 1.23x |
| RC5 加密一個區塊 | 47–48 | 36–37 | **1.29–1.34x** | 1.73x |

兩個版本的輸出都與 RFC 8439、RC5 論文一致。

**解讀**

- 三個核心在真實硬體上都確實變快,沒有一個變慢
- RC5 加密的加速(約 1.3x)比 RISC-V 的 IC 比(1.73x)小,原因有兩個:
  1. ARM 沒有左旋,變數旋轉仍需 `neg` + `ror` 兩條,本組的 ROTL 只要一條
  2. M5 是多發射、亂序執行的 CPU,`lsl` 和 `lsr` 可以同時執行。真正決定時間的是**相依鏈的長度**,不是指令數。RC5 每一步 `A = rotl(A ^ B, B) + S` 必須依序完成:SHIFT 版是 `eor → lsl/lsr → orr → add`,共 4 級;ROR 版是 `eor → ror → add`,共 3 級(`neg` 可以和 `eor` 同時做)。4 / 3 ≈ 1.33,與實測相符
- 這說明 IC × CPI × T 中的 CPI 會隨 CPU 結構改變。在課程的單發射 5 級 pipeline 上,IC 比幾乎等於 cycle 比(驗證 2);在亂序 CPU 上就不一定

## 尚未驗證的部分

- **Clock period**:假設 ROTL 不拉長 clock period。理由是旋轉可以用 5 級 2-to-1 多工器組成的桶型旋轉器實作,深度與現有的 `sll`/`srl` 移位器相同,通常比 32-bit 加法器的進位鏈短。實際影響要到 CP4–CP6 畫出 datapath 才能確認
- **硬體成本**:旋轉器的面積與控制訊號尚未分析(CP4–CP6)
- 驗證 3 是 ARM 的 `ror`,不是本組的 RISC-V `rotl`,只能當作「旋轉指令在真實 CPU 上有效」的旁證
