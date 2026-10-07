# src/include/

[`rotl_isa.h`](rotl_isa.h) 是 ROTL 編碼的**唯一設定來源**:

- `ROTL_OPCODE`、`ROTL_FUNCT3`、`ROTL_FUNCT7`
- 組合語言巨集 `rotl rd, rs1, rs2`(展開為 `.insn r`)
- C 函式 `rotl_insn(rs1, rs2)`(以 inline assembly 發出一條 `rotl`)

`tools/rotl_isa.py` 也從這個檔案讀取 funct3 / funct7。教師分配編碼後,只需改這裡的兩行。
