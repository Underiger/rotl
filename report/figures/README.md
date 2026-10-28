# report/figures/

| 檔案 | 內容 | 產生方式 |
|---|---|---|
| `instruction_counts.md` | 靜態 / 動態指令數表(表 1–3) | `make counts` |
| `instruction_counts.csv` | 同上,CSV 格式 | `make counts` |
| `run_log_<學號>.txt` | 執行證據:時間、機器、工具版本、`make test` 與 `make counts` 的完整輸出 | 各組員在自己的電腦上 `make evidence ID=<學號>` |

`instruction_counts.*` 由 `tools/measure.py` 自動產生,`run_log_*.txt` 由 `tools/run_log.py` 產生,請勿手動修改。
Ripes 的執行截圖等圖片也放在這個目錄,並在此表補上說明。
