# references/

本指令的參考資料,例如 RISC-V ISA 規格書的章節、論文、課本頁碼、公開的演算法說明。

## 規定

- 每筆參考資料需註明來源(書名或網址、章節或頁碼、存取日期)
- 不要放入他組的作業內容或他人未授權的完整文件
- 大型檔案不放入倉庫,改為連結

## 參考清單

| 編號 | 名稱 | 來源(網址、章節或頁碼、存取日期) | 用途 |
|---|---|---|---|
| R1 | The RISC-V Instruction Set Manual, Volume I: Unprivileged Architecture, Version 20240411 | <https://github.com/riscv/riscv-isa-manual/releases/tag/20240411>。§2.4(p. 27):SLL/SRL 只取 `rs2` 的低 5 位元;第 13 章 "M" Extension(p. 65):除以 0 的結果;§28.5.31 `rol`(p. 247):Zbb 的旋轉指令與編碼;第 34 章 Table 70(p. 553):base opcode map 中的 custom-0。存取日期 2026-10-08 | 編碼、baseline 寫法、模擬器、與 Zbb `rol` 對照 |
| R2 | ISO/IEC 9899:2011(C11) | 以公開的委員會草案 N1570(2011-04-12)核對:<https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf>,§6.5.7 第 3 段(pp. 94–95):右運算元為負或大於等於左運算元寬度時,行為未定義。存取日期 2026-10-08 | `n = 0` 必須單獨處理的依據 |
| R3 | RFC 8439, ChaCha20 and Poly1305 for IETF Protocols(2018 年 6 月) | <https://www.rfc-editor.org/rfc/rfc8439>,§2.1.1(quarter round 測試向量)、§2.3.2(區塊函式測試向量)。存取日期 2026-10-08 | ChaCha20 核心與測試向量 |
| R4 | R. L. Rivest, "The RC5 Encryption Algorithm" | Fast Software Encryption(FSE 1994)論文集,pp. 86–96;作者網站版本 <https://people.csail.mit.edu/rivest/pubs/Riv94.pdf>。第 9 節附錄(p. 96)"RC5-32/12/16 examples" 第 1 組:key 與明文全為 0,密文印為 `EEDBA521 6D8F4B15`(兩個 32-bit word)。存取日期 2026-10-08 | RC5 核心與測試向量 |
| R5 | Using as(GNU Assembler 手冊),§9.38.5 RISC-V Instruction Formats | <https://sourceware.org/binutils/docs/as/RISC_002dV_002dFormats.html>,R type:`.insn r opcode7, funct3, funct7, rd, rs1, rs2`。存取日期 2026-10-08 | 以 `.insn r` 產生自訂指令 |
| R6 | D. A. Patterson, J. L. Hennessy, *Computer Organization and Design RISC-V Edition: The Hardware/Software Interface*, Morgan Kaufmann | 第 4 章 The Processor:pipelining 概論、data hazards(forwarding 與 stall)、control hazards 各節。**版次與頁碼請依課程用書補上** | `experiments/pipeline_cycles.py` 的 5 級 pipeline 時間模型 |
| R7 | Arm Architecture Reference Manual for A-profile architecture(Arm DDI 0487),A64 指令 `ROR`/`RORV`、`LSLV`、`LSRV` | <https://developer.arm.com/documentation/ddi0487/latest>。網頁需要 JavaScript,本組未能直接存取原文;所用指令的行為以 `experiments/arm64_rotate_bench.c` 兩個版本的輸出皆符合 R3、R4 的測試向量間接驗證 | `experiments/` 驗證 3(ARM64 實機量測) |
