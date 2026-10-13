#!/bin/sh
# 桌寵的終端機 Demo:執行 make test,同時把輸出存到 build/pet_demo.log,
# 桌寵讀這個檔案顯示進度,最後一行 PET_EXIT=<結束碼> 告訴它成功或失敗。
#
#   sh demo/run_tests.sh
cd "$(dirname "$0")/.." || exit 1
mkdir -p build
{ make test 2>&1; echo "PET_EXIT=$?"; } | tee build/pet_demo.log
