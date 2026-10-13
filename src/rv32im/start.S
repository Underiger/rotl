/*
 * 最小的啟動程式:設定堆疊、呼叫 main、以 ebreak 結束。
 * 模擬器(tools/rv32sim.py)在 ebreak 停止,a0 為 main 的回傳值。
 * 不清除 .bss:模擬器的記憶體一開始就是 0,且執行前會寫入測資。
 */
    .section .text.start, "ax"
    .globl _start
_start:
    li      sp, 0x00100000      # 堆疊頂端 = 1 MiB(模擬器記憶體大小)
    call    main
    ebreak
