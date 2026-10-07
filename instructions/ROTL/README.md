# instructions/ROTL/

| 項目 | 內容 |
|---|---|
| 指令名稱 | `ROTL`(組合語言寫作 `rotl rd, rs1, rs2`) |
| 題目類別 | 密碼學 / 雜湊類 |
| 運算元類型 | 二元 |
| 指令格式 | R-type,custom-0(`0001011`) |
| 語意公式 | `n = rs2 & 31`;`n = 0` 時 `rd = rs1`,否則 `rd = (rs1 << n) \| (rs1 >> (32 − n))`,`>>` 為邏輯右移 |

依據:課程倉庫 HOMEWORK.md 第 6.4 節。

---

## 語意規格(HOMEWORK.md 第 6.7 節格式)

### ROTL
- **語意(公式)**:
  - `n = rs2[4:0]`(即 `rs2 & 31`)
  - 若 `n = 0`,`rd = rs1`
  - 否則 `rd = (rs1 << n) | (rs1 >> (32 − n))`,其中 `>>` 為**邏輯右移**,結果取低 32 位元
  - 等價的位元定義:`rd[i] = rs1[(i − n) mod 32]`,`i = 0 … 31`
- **運算元與定義域**:
  - `rs1`:任意 32-bit 位元向量,不區分有號或無號
  - `rs2`:任意 32-bit 值,**只使用低 5 位元**,高 27 位元忽略;因此 `rs2 = 32` 等同 `n = 0`,`rs2 = −1`(`0xFFFFFFFF`)等同 `n = 31`
- **結果範圍**:任意 32-bit 值。旋轉不會遺失位元,`rd` 中 1 的個數與 `rs1` 相同
- **邊界條件與溢位處理**:
  - `n = 0`:直接回傳 `rs1`。若照公式計算會出現 `rs1 >> 32`,在 C 語言中是未定義行為,必須單獨處理
  - 不會溢位:移出的位元從另一端繞回
  - `rd = x0`:結果丟棄(與其他 R-type 指令相同)
  - `rd` 與 `rs1` 或 `rs2` 為同一暫存器:先讀取來源,再寫回 `rd`
- **測試向量**(完整 16 組見 [`src/tests/rotl_vectors.csv`](../../src/tests/rotl_vectors.csv)):

  | rs1 | rs2 | rd | 說明 |
  |---|---|---|---|
  | `0x80000001` | `1` | `0x00000003` | 一般:最高位繞回最低位 |
  | `0x000000FF` | `8` | `0x0000FF00` | 一般 |
  | `0x12345678` | `0` | `0x12345678` | **邊界**:`n = 0` |
  | `0x12345678` | `32` | `0x12345678` | **邊界**:`rs2 ≥ 32` 只取低 5 位元 |
  | `0x12345678` | `31` | `0x091A2B3C` | **邊界**:最大移位量 |

- **對應的 RV32IM baseline 片段與指令數**:

  ```asm
  # a0 = rs1, a1 = rs2,結果放 a0(無分支版,4 條)
  sll   t0, a0, a1      # rs1 << (rs2 & 31)
  neg   t1, a1          # (−rs2) 的低 5 位元 = (32 − n) & 31
  srl   t1, a0, t1      # n = 0 時移 0 位
  or    a0, t0, t1      # n = 0 時 rs1 | rs1 = rs1
  ```

  | 寫法 | 每次旋轉的指令數 |
  |---|---:|
  | 手寫無分支版(上方) | 4 |
  | 手寫逐字翻譯版(含 `n = 0` 分支) | 7(`n = 0` 時 2) |
  | GCC 16.2 `-O2` 編譯 C 參考實作 | 5 |
  | 旋轉量為常數時(`slli`、`srli`、`or`/`add`) | 3 |
  | 自訂指令 `rotl` | 1 |

  上表不含函式呼叫的 `call` / `ret`。量測方法與完整數據見 [`report/CP2.md`](../../report/CP2.md)、[`report/CP3.md`](../../report/CP3.md)。

---

## 編碼

```
31      25 24   20 19   15 14  12 11    7 6       0
+----------+-------+-------+------+-------+---------+
|  funct7  |  rs2  |  rs1  |funct3|  rd   | 0001011 |
+----------+-------+-------+------+-------+---------+
  0001111*                   000*
```

\* `funct3`、`funct7` 由教師分配,上面是**暫定值**。分配後只需修改 [`src/include/rotl_isa.h`](../../src/include/rotl_isa.h) 的兩個 `#define`,再執行 `make test counts`。

---

## 小組資訊

| 項目 | 內容 |
|---|---|
| 組名 | (待填) |
| 組長 | (待填) |
| 組員 | (待填) |
| 分支 | `dev/<學號>`(各組員自行填寫) |

---

## 參考資料

| 編號 | 名稱 | 來源 | 用途 |
|---|---|---|---|
| R1 | The RISC-V Instruction Set Manual, Volume I: Unprivileged ISA | riscv.org 規格書,RV32I 章節(移位指令只取 `rs2` 低 5 位元)、opcode map(custom-0)、M 擴充章節(除以 0 的語意)、B 擴充 Zbb 章節(`rol` / `ror` / `rori`)。存取日期 2026-10-06 | 編碼、baseline 寫法、與 Zbb `rol` 對照 |
| R2 | ISO/IEC 9899:2011(C11) | §6.5.7 Bitwise shift operators | 移位量 ≥ 型別寬度為未定義行為 |
| R3 | RFC 8439, ChaCha20 and Poly1305 for IETF Protocols | rfc-editor.org,§2.1.1、§2.3.2。存取日期 2026-10-06 | ChaCha20 核心與測試向量 |
| R4 | R. L. Rivest, "The RC5 Encryption Algorithm" | Fast Software Encryption (FSE) 1994,附錄測試向量 | RC5 核心與測試向量 |
| R5 | GNU Assembler 手冊,RISC-V `.insn` 指令 | sourceware.org binutils 文件。存取日期 2026-10-06 | 以 `.insn r` 產生自訂指令 |
