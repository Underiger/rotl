CC      ?= cc
CFLAGS  ?= -std=c11 -Wall -Wextra -Werror -O2
PYTHON  ?= python3
RV_GCC  ?= riscv64-elf-gcc
RV_FLAGS = -march=rv32im -mabi=ilp32 -ffreestanding -Isrc/include

BUILD   = build
VECTORS = src/tests/rotl_vectors.csv

.PHONY: all test test-c test-ubsan test-py ub-demo asm counts encode clean

all: test

test: test-c test-ubsan test-py

# CP1:主機上的 C baseline 測試
test-c: $(BUILD)/test_rotl
	./$(BUILD)/test_rotl $(VECTORS)

$(BUILD)/test_rotl: src/c_baseline/test_rotl.c src/c_baseline/rotl.c src/c_baseline/rotl.h | $(BUILD)
	$(CC) $(CFLAGS) -o $@ src/c_baseline/test_rotl.c src/c_baseline/rotl.c

# 同一組測試加上 UndefinedBehaviorSanitizer,確認 rotl_ref 沒有未定義行為
test-ubsan: | $(BUILD)
	$(CC) $(CFLAGS) -fsanitize=undefined -fno-sanitize-recover=all -o $(BUILD)/test_rotl_ubsan \
		src/c_baseline/test_rotl.c src/c_baseline/rotl.c
	./$(BUILD)/test_rotl_ubsan $(VECTORS) > /dev/null && echo "UBSan: no undefined behavior"

# 反例:沒處理 n = 0 的寫法,UBSan 會在執行期報錯(預期失敗)
ub-demo: | $(BUILD)
	$(CC) -std=c11 -O2 -fsanitize=undefined -fno-sanitize-recover=all -o $(BUILD)/ub_demo src/c_baseline/ub_demo.c
	./$(BUILD)/ub_demo 4
	-./$(BUILD)/ub_demo 0

# CP2 / CP3:模擬器上的正確性與指令數測試
test-py:
	$(PYTHON) -m unittest discover -s tools -p "test_*.py" -v

# CP2:編譯器輸出的組合語言,供報告比對
asm: | $(BUILD)
	$(RV_GCC) $(RV_FLAGS) -O0 -S -o $(BUILD)/rotl_O0.s src/c_baseline/rotl.c
	$(RV_GCC) $(RV_FLAGS) -O2 -S -o $(BUILD)/rotl_O2.s src/c_baseline/rotl.c
	@echo "written: $(BUILD)/rotl_O0.s $(BUILD)/rotl_O2.s"

# CP2 / CP3:量測靜態與動態指令數,輸出到 report/figures/
counts:
	$(PYTHON) tools/measure.py

# CP3:印出編碼範例
encode:
	$(PYTHON) tools/rotl_isa.py

$(BUILD):
	mkdir -p $(BUILD)

clean:
	rm -rf $(BUILD) tools/__pycache__
