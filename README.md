# groupXX:ROTL(32-bit 循環左移)

計算機組織 2026 學期專題。課程說明見 [DevSecOpsLab-CSIE-NPU/2026-Computer-Architecture](https://github.com/DevSecOpsLab-CSIE-NPU/2026-Computer-Architecture)。

```
rotl rd, rs1, rs2      n = rs2 & 31;  rd = n == 0 ? rs1 : (rs1 << n) | (rs1 >> (32 − n))
```

R-type,custom-0(`0001011`)。funct3 / funct7 **待教師分配**,目前為暫定值(見 [`src/include/rotl_isa.h`](src/include/rotl_isa.h))。

## 組別資訊

| 項目 | 內容 |
|---|---|
| 組名 | (待填) |
| 組長 | (待填) |
| 組員 | (待填,4 人) |

## 目錄結構

```
.
├── README.md
├── CONTRIBUTIONS.md
├── Makefile
├── instructions/
│   ├── README.md
│   └── ROTL/README.md        語意規格、編碼、測試向量、參考資料
├── src/
│   ├── include/              rotl_isa.h:編碼常數(唯一設定來源)
│   ├── c_baseline/           CP1:C 參考實作與測試
│   ├── tests/                16 組測資 CSV
│   └── rv32im/               CP2–CP3:組合語言、密碼學核心
├── tools/                    黃金模型、RV32IM 模擬器、量測腳本、Python 測試
└── report/
    ├── CP1.md  CP2.md  CP3.md
    └── figures/              make counts 產生的數據表
```

## 執行方式

需要:`cc`(主機 C 編譯器)、`python3`(3.10 以上)、`riscv64-elf-gcc`。

```bash
make test      # C 測試 + UBSan + 22 項 Python 測試(含模擬器)
make counts    # 重新量測指令數,寫入 report/figures/
make encode    # 印出 rotl 的機器碼範例
make asm       # 產生編譯器輸出的組合語言 build/rotl_O0.s、build/rotl_O2.s
make ub-demo   # 反例:未處理 n = 0 的寫法(預期報錯)
```

## 目前結果

- C 參考實作:16 組測資、69,000 次交叉比對、UBSan 全部通過
- RV32IM:手寫無分支版 4 條指令(不含 `ret`),GCC `-O2` 為 5 條,自訂指令 1 條
- 動態指令數(模擬器實測,GCC 16.2.0 `-O2`):

| 核心 | RV32IM | ROTL | IC 比 |
|---|---:|---:|---:|
| ChaCha20 區塊 | 1919 | 1284 | 1.49x |
| RC5 金鑰排程 | 2467 | 2000 | 1.23x |
| RC5 加密一個區塊 | 227 | 131 | 1.73x |

## Git 規則(HOMEWORK.md 5.1)

- 每位組員在 `dev/<學號>` 分支開發,不直接推送到 `main`
- Checkpoint 截止前由組長開 PR 合併到 `main`,並打 tag:`cp1-submit`、`cp2-submit`、`cp3-submit`
