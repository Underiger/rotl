# groupXX:ROTL(32-bit 循環左移)

計算機組織 2026 學期專題。課程說明見 [DevSecOpsLab-CSIE-NPU/2026-Computer-Architecture](https://github.com/DevSecOpsLab-CSIE-NPU/2026-Computer-Architecture)。

> 本 repo 由 fork [Underiger/2026-Computer-Architecture](https://github.com/Underiger/2026-Computer-Architecture) 的 `group-ROTL/` 於 2026-10-08 搬移而來,保留了 commit 歷史。當時的 PR 討論(#1–#7)留在該 fork 中,fork 已不再更新,之後的修改都在本 repo 進行。

```
rotl rd, rs1, rs2      n = rs2 & 31;  rd = n == 0 ? rs1 : (rs1 << n) | (rs1 >> (32 − n))
```

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
│   └── ROTL/README.md        語意規格、測試向量、參考資料
├── src/
│   ├── c_baseline/           CP1:C 參考實作與測試
│   └── tests/                16 組測資 CSV
└── report/
    ├── CP1.md
    └── figures/
```

本 tag(`cp1-submit`)只包含 CP1 的內容;CP2 之後的進度會在後續 checkpoint 再合併進來。

## 執行方式

需要:`cc`(主機 C 編譯器)。

```bash
make test      # C 測試 + UBSan(16 組測資、69,000 次交叉比對、性質檢查)
make ub-demo   # 反例:未處理 n = 0 的寫法(預期報錯)
```

## 目前結果

- C 參考實作:16 組測資(含 10 組邊界值)全部通過
- 與逐位旋轉寫法交叉比對 69,000 次、性質檢查 2,000 組 × 3,全部一致
- UndefinedBehaviorSanitizer:無未定義行為

## Git 規則(HOMEWORK.md 5.1)

- 每位組員在 `dev/<學號>` 分支開發,不直接推送到 `main`
- `main` 已設定分支保護:只能透過 PR 合併,不能直接推送、force push 或刪除(擁有者也一樣)
- Checkpoint 截止前由組長開 PR 合併到 `main`,並打 tag:`cp1-submit`、`cp2-submit`、`cp3-submit`
