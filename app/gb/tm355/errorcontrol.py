"""
التحكم في الأخطاء (TM355).

1) CRC-32 — كشف الأخطاء:
   نعامل البيانات كمتعدد حدود ثنائي ونقسمه على متعدد حدود ثابت (المولّد)، والباقي هو الـ CRC.
   المستقبل يعيد الحساب: إذا اختلف الباقي فهناك خطأ، فيطلب إعادة الإرسال (ARQ).
   نفس CRC-32 المستخدم في Ethernet و ZIP و PNG، والمولّد بالترتيب المعكوس 0xEDB88320.

2) كود هامنغ (7,4) — تصحيح الأخطاء (FEC):
   كل 4 بتات بيانات + 3 بتات تحقق = 7 بتات. المسافة الدنيا 3، فيصحح أي خطأ في بت واحد
   داخل الكلمة، ويكشف خطأين (لكنه قد يصححهما خطأً). المعدل = 4/7 ≈ 0.57.
   ترتيب البتات: p1 p2 d1 p3 d2 d3 d4 (المواقع 1..7)، ومتلازمة الخطأ تعطي موقع البت الخاطئ مباشرة.
"""
from __future__ import annotations

import random

# ---------------------------------------------------------------- CRC-32
_POLY = 0xEDB88320
_TABLE = []
for _n in range(256):
    _c = _n
    for _ in range(8):
        _c = (_c >> 1) ^ _POLY if _c & 1 else _c >> 1
    _TABLE.append(_c)


def crc32(data: bytes, value: int = 0) -> int:
    """CRC-32 بجدول من 256 قيمة (يطابق zlib.crc32)."""
    crc = value ^ 0xFFFFFFFF
    for b in data:
        crc = _TABLE[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


def crc32_bitwise(data: bytes) -> int:
    """نفس الحساب بتاً بتاً (القسمة الثنائية كما في الكتاب)، أبطأ لكنه أوضح."""
    crc = 0xFFFFFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ _POLY if crc & 1 else crc >> 1
    return crc ^ 0xFFFFFFFF


def flip_bits(data: bytes, positions: list[int]) -> bytes:
    out = bytearray(data)
    for p in positions:
        out[p // 8] ^= 1 << (7 - p % 8)
    return bytes(out)


def crc_detection_trial(data: bytes, errors: int, trials: int, rng: random.Random | None = None) -> int:
    """كم مرة كشف CRC الخطأ من trials محاولة، مع قلب errors بت عشوائي كل مرة."""
    rng = rng or random.Random(1)
    good = crc32(data)
    detected = 0
    for _ in range(trials):
        bad = flip_bits(data, rng.sample(range(len(data) * 8), errors))
        detected += crc32(bad) != good
    return detected


# ------------------------------------------------------------ هامنغ (7,4)
def hamming74_encode_nibble(d: list[int]) -> list[int]:
    d1, d2, d3, d4 = d
    p1 = d1 ^ d2 ^ d4
    p2 = d1 ^ d3 ^ d4
    p3 = d2 ^ d3 ^ d4
    return [p1, p2, d1, p3, d2, d3, d4]


def hamming74_decode_word(w: list[int]) -> tuple[list[int], int]:
    """يرجع (4 بتات البيانات، موقع البت المصحح أو 0)."""
    w = list(w)
    s1 = w[0] ^ w[2] ^ w[4] ^ w[6]
    s2 = w[1] ^ w[2] ^ w[5] ^ w[6]
    s3 = w[3] ^ w[4] ^ w[5] ^ w[6]
    pos = s1 + 2 * s2 + 4 * s3            # المتلازمة = موقع الخطأ (1..7)
    if pos:
        w[pos - 1] ^= 1
    return [w[2], w[4], w[5], w[6]], pos


def bytes_to_bits(data: bytes) -> list[int]:
    return [(b >> (7 - i)) & 1 for b in data for i in range(8)]


def bits_to_bytes(bits: list[int]) -> bytes:
    return bytes(int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits) - len(bits) % 8, 8))


def hamming74_encode(data: bytes) -> list[int]:
    bits = bytes_to_bits(data)
    out: list[int] = []
    for i in range(0, len(bits), 4):
        out += hamming74_encode_nibble(bits[i:i + 4])
    return out


def hamming74_decode(code: list[int]) -> tuple[bytes, int]:
    """يرجع (البيانات، عدد البتات التي صُححت)."""
    bits: list[int] = []
    fixed = 0
    for i in range(0, len(code), 7):
        d, pos = hamming74_decode_word(code[i:i + 7])
        bits += d
        fixed += pos > 0
    return bits_to_bytes(bits), fixed


def bsc(bits: list[int], p: float, rng: random.Random) -> tuple[list[int], int]:
    """قناة ثنائية متماثلة: كل بت ينقلب باحتمال p. يرجع (البتات، عدد الأخطاء)."""
    out, errs = [], 0
    for b in bits:
        if rng.random() < p:
            out.append(b ^ 1)
            errs += 1
        else:
            out.append(b)
    return out, errs


def compare_over_bsc(data: bytes, p: float, seed: int = 7) -> dict:
    """نرسل نفس البيانات عبر قناة فيها أخطاء: مرة بدون ترميز ومرة بهامنغ (7,4)."""
    rng = random.Random(seed)
    raw = bytes_to_bits(data)
    rx, raw_errs = bsc(raw, p, rng)
    left_raw = sum(a != b for a, b in zip(raw, rx))
    coded = hamming74_encode(data)
    rx_coded, ch_errs = bsc(coded, p, rng)
    decoded, fixed = hamming74_decode(rx_coded)
    left_coded = sum(a != b for a, b in zip(raw, bytes_to_bits(decoded)))
    return {"p": p, "data_bits": len(raw), "coded_bits": len(coded),
            "raw_errors": left_raw, "channel_errors_coded": ch_errs, "corrected_words": fixed,
            "residual_errors_coded": left_coded,
            "raw_ber": left_raw / len(raw), "coded_ber": left_coded / len(raw)}
