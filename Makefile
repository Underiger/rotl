CC      ?= cc
CFLAGS  ?= -std=c11 -Wall -Wextra -Werror -O2

BUILD   = build
VECTORS = src/tests/rotl_vectors.csv

.PHONY: all test test-c test-ubsan ub-demo clean

all: test

test: test-c test-ubsan

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

$(BUILD):
	mkdir -p $(BUILD)

clean:
	rm -rf $(BUILD)
