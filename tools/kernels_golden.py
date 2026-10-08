"""ChaCha20 與 RC5 的 Python 參考實作,用來驗證 RV32 程式的輸出。"""

from rotl_isa import MASK32, rotl_golden as rotl

# RFC 8439 §2.3.2 的輸入與輸出
CHACHA_IN = [
    0x61707865, 0x3320646E, 0x79622D32, 0x6B206574,
    0x03020100, 0x07060504, 0x0B0A0908, 0x0F0E0D0C,
    0x13121110, 0x17161514, 0x1B1A1918, 0x1F1E1D1C,
    0x00000001, 0x09000000, 0x4A000000, 0x00000000,
]
CHACHA_RFC_OUT = [
    0xE4E7F110, 0x15593BD1, 0x1FDD0F50, 0xC47120A3,
    0xC7F4D1C7, 0x0368C033, 0x9AAA2204, 0x4E6CD4C3,
    0x466482D2, 0x09AA9F07, 0x05D7C214, 0xA2028BD9,
    0xD19C12B5, 0xB94E16DE, 0xE883D0CB, 0x4E3C50A2,
]

# Rivest 1994,RC5-32/12/16,key = 0、明文 = 0
RC5_KEY = [0, 0, 0, 0]
RC5_PT = [0, 0]
RC5_PAPER_CT = [0xEEDBA521, 0x6D8F4B15]  # 論文附錄(p. 96)第 1 組:印出的兩個 32-bit word

RC5_ROUNDS = 12
RC5_TABLE = 2 * (RC5_ROUNDS + 1)


def chacha_quarter_round(s, a, b, c, d):
    s[a] = (s[a] + s[b]) & MASK32; s[d] ^= s[a]; s[d] = rotl(s[d], 16)
    s[c] = (s[c] + s[d]) & MASK32; s[b] ^= s[c]; s[b] = rotl(s[b], 12)
    s[a] = (s[a] + s[b]) & MASK32; s[d] ^= s[a]; s[d] = rotl(s[d], 8)
    s[c] = (s[c] + s[d]) & MASK32; s[b] ^= s[c]; s[b] = rotl(s[b], 7)


def chacha20_block(state):
    x = list(state)
    for _ in range(10):
        for a, b, c, d in ((0, 4, 8, 12), (1, 5, 9, 13), (2, 6, 10, 14), (3, 7, 11, 15),
                           (0, 5, 10, 15), (1, 6, 11, 12), (2, 7, 8, 13), (3, 4, 9, 14)):
            chacha_quarter_round(x, a, b, c, d)
    return [(x[i] + state[i]) & MASK32 for i in range(16)]


def rc5_setup(key):
    S = [0xB7E15163]
    for _ in range(1, RC5_TABLE):
        S.append((S[-1] + 0x9E3779B9) & MASK32)
    L = list(key)
    A = B = i = j = 0
    for _ in range(3 * RC5_TABLE):
        A = S[i] = rotl((S[i] + A + B) & MASK32, 3)
        B = L[j] = rotl((L[j] + A + B) & MASK32, (A + B) & MASK32)
        i = (i + 1) % RC5_TABLE
        j = (j + 1) % 4
    return S


def rc5_encrypt(S, pt):
    A = (pt[0] + S[0]) & MASK32
    B = (pt[1] + S[1]) & MASK32
    for i in range(1, RC5_ROUNDS + 1):
        A = (rotl(A ^ B, B) + S[2 * i]) & MASK32
        B = (rotl(B ^ A, A) + S[2 * i + 1]) & MASK32
    return [A, B]
