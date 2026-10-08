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

量測方式:Apple clang 21 `-O2`,每個核心重複 15 次取最快,輸出接到下一次的輸入,避免被編譯器省略。前五次執行的範圍:

| 核心 | SHIFT(ns) | ROR(ns) | 實測加速 | RISC-V IC 比(對照) |
|---|---:|---:|---:|---:|
| ChaCha20 區塊 | 184–185 | 121–123 | **1.51–1.52x** | 1.49x |
| RC5 金鑰排程 | 286–297 | 220–221 | **1.29–1.35x** | 1.23x |
| RC5 加密一個區塊 | 47–48 | 36–37 | **1.29–1.34x** | 1.73x |

兩個版本的輸出都與 RFC 8439、RC5 論文一致。

**請看加速比,不要看 ns 的絕對值。** 絕對時間會隨 CPU 核心種類(效能核心或節能核心)與電源狀態變動。
例如另一次執行時,ChaCha20 為 96.0 ns / 63.4 ns,約是上表的一半,但加速比同樣是 1.51x;
RC5 金鑰排程為 1.35x、RC5 加密為 1.32x,也都在上表的範圍內。
兩個版本在同一次執行中依序量測,處在相同的 CPU 狀態下,所以比值是穩定的。
該次以 `/usr/bin/time -l` 檢查:程式沒有發生 swap(`swaps = 0`),工作資料只有幾百 bytes,完全在快取內。

**背景:亂序執行**(讀「解讀」之前先看)

- 多發射 CPU 搭配重排序緩衝區(ROB),能大幅發掘指令級平行度(ILP)。Apple M 系列的大核屬於很寬的亂序架構;Apple 沒有公開發射寬度等細節,所以這裡不引用具體數字
- 現代 CPU(例如 Intel、AMD、Apple)大多是亂序執行處理器。順序執行的處理器遇到一條執行時間長的指令時,後面不相關的簡單指令也只能跟著等;亂序執行的處理器讓指令在保留站(reservation station)等待運算元,**誰的資料先準備好,誰就先執行**。因此平行度高的程式碼能大幅壓低整體耗時。但要分清楚兩種相依:
  - **資料相依:亂序執行也繞不過。** 例如 `t = a ^ b` 之後接 `t = rotl(t, b)`,第二條需要第一條算出的數值,只能等它完成;CPU 能做的是在等待期間先執行其他不相關的指令。RC5 就是這種情況,見下方「解讀」
  - **控制相依:可以靠投機執行(speculative execution)。** 例如遇到 `bne` 這類分支時,CPU 還不知道要不要跳。它用分支預測先猜一個方向,搶先執行那條路上的指令,結果先暫存在 ROB,不寫回暫存器。猜對了就依序提交(commit)生效;猜錯了就把 ROB 裡那些結果全部丟棄,從正確的位置重新執行。分支預測猜的是**跳不跳**,不是運算的**數值**

**解讀**

- 三個核心在真實硬體上都確實變快,沒有一個變慢
- RC5 加密的加速(約 1.3x)比 RISC-V 的 IC 比(1.73x)小,原因有兩個:
  1. ARM 沒有左旋,變數旋轉仍需 `neg` + `ror` 兩條,本組的 ROTL 只要一條
  2. M5 是多發射、亂序執行的 CPU,`lsl` 和 `lsr` 可以同時執行。RC5 每一步 `A = rotl(A ^ B, B) + S` 都要等上一步的結果,完全串行,所以時間由**相依鏈的長度**決定:SHIFT 版是 `eor → lsl/lsr → orr → add`,共 4 級;ROR 版是 `eor → ror → add`,共 3 級(`neg` 可以和 `eor` 同時做)。4 / 3 ≈ 1.33,與實測相符
- ChaCha20 的情況不同,相依鏈與指令數**都有影響**。每個 quarter round 的一步 `a += b; d ^= a; d = rotl(d, k)`:

  | 推算方式 | SHIFT 版 | ROR 版 | 比值 |
  |---|---|---|---:|
  | 相依鏈 | `add → eor → lsl/lsr → orr`,4 級 | `add → eor → ror`,3 級 | 1.33x |
  | 指令數 | `add eor lsl lsr orr`,5 條 | `add eor ror`,3 條 | 1.67x |

  實測 1.51x 介於兩者之間。原因是每一輪有 4 個互相獨立的 quarter round 可以同時執行,M5 的執行單元會被大量指令填滿,所以不只受相依鏈限制,指令數也會影響時間。這是從數字推得的解釋,沒有用硬體效能計數器實際量測
- 結論:在多發射 CPU 上,時間由相依鏈長度與指令數(執行單元夠不夠用)共同決定,哪一個是瓶頸取決於程式的平行度。RC5 平行度低,受相依鏈限制;ChaCha20 平行度高,指令數的影響變大
- 這說明 IC × CPI × T 中的 CPI 會隨 CPU 結構改變。在課程的單發射 5 級 pipeline 上,每個 cycle 只能發一條指令,IC 比幾乎等於 cycle 比(驗證 2);在多發射、亂序的 CPU 上就不一定

## 尚未驗證的部分

- **Clock period**:假設 ROTL 不拉長 clock period。理由是旋轉可以用 5 級 2-to-1 多工器組成的桶型旋轉器實作,深度與現有的 `sll`/`srl` 移位器相同,通常比 32-bit 加法器的進位鏈短。實際影響要到 CP4–CP6 畫出 datapath 才能確認
- **硬體成本**:旋轉器的面積與控制訊號尚未分析(CP4–CP6)
- 驗證 3 是 ARM 的 `ror`,不是本組的 RISC-V `rotl`,只能當作「旋轉指令在真實 CPU 上有效」的旁證

## 參考資料

完整書目見 [`instructions/ROTL/README.md`](../instructions/ROTL/README.md#參考資料)。

| 驗證 | 引用 |
|---|---|
| 驗證 1 | R1(RV32I 指令格式) |
| 驗證 2 | R6(Patterson & Hennessy 第 4 章的 5 級 pipeline、forwarding、stall、分支懲罰) |
| 驗證 3 | R3、R4(測試向量)、R7(ARM A64 的 `ROR`/`RORV`、`LSLV`、`LSRV`) |
