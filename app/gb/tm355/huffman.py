"""
ترميز هوفمان (TM355 — الضغط بدون فقد).

الفكرة: الرموز الأكثر تكراراً تأخذ رموزاً أقصر. الخوارزمية:
  1. ضع كل رمز في طابور أولوية حسب تكراره.
  2. اسحب أقل عقدتين تكراراً، وادمجهما في عقدة واحدة مجموعها تكرارهما.
  3. كرر حتى تبقى عقدة واحدة (الجذر). الفرع الأيسر = 0 والأيمن = 1.

النتيجة ترميز بادئة (لا يوجد رمز هو بداية رمز آخر)، فيُفك بدون فواصل.
ومتوسط الطول L يحقق دائماً:  H ≤ L < H + 1   حيث H الإنتروبيا.
"""
from __future__ import annotations

import heapq
import itertools
import json
from collections import Counter


def build_code(data: bytes) -> dict[int, str]:
    """يرجع {بايت: سلسلة بتات}."""
    counts = Counter(data)
    if not counts:
        return {}
    if len(counts) == 1:                      # رمز واحد فقط: نعطيه بتاً واحداً
        return {next(iter(counts)): "0"}
    tie = itertools.count()                   # لكسر التعادل بترتيب ثابت
    heap = [(c, next(tie), {s: ""}) for s, c in sorted(counts.items())]
    heapq.heapify(heap)
    while len(heap) > 1:
        c1, _, left = heapq.heappop(heap)
        c2, _, right = heapq.heappop(heap)
        merged = {s: "0" + code for s, code in left.items()}
        merged.update({s: "1" + code for s, code in right.items()})
        heapq.heappush(heap, (c1 + c2, next(tie), merged))
    return heap[0][2]


def average_length(data: bytes, code: dict[int, str]) -> float:
    counts = Counter(data)
    total = sum(counts.values())
    return sum(c * len(code[s]) for s, c in counts.items()) / total if total else 0.0


def encode(data: bytes) -> tuple[bytes, dict[int, str], int]:
    """يرجع (البايتات المضغوطة، جدول الترميز، عدد البتات الفعلي)."""
    code = build_code(data)
    bits = "".join(code[b] for b in data)
    n = len(bits)
    bits += "0" * (-n % 8)                    # حشو حتى آخر بايت
    packed = bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))
    return packed, code, n


def decode(packed: bytes, code: dict[int, str], nbits: int) -> bytes:
    reverse = {v: k for k, v in code.items()}
    bits = "".join(f"{b:08b}" for b in packed)[:nbits]
    out, cur = bytearray(), ""
    for bit in bits:
        cur += bit
        if cur in reverse:
            out.append(reverse[cur])
            cur = ""
    if cur:
        raise ValueError("بتات زائدة في نهاية البيانات")
    return bytes(out)


def table_size(code: dict[int, str]) -> int:
    """حجم جدول الترميز إذا أُرسل مع البيانات: بايت للرمز + بايت للطول + البتات نفسها."""
    return sum(2 + (len(c) + 7) // 8 for c in code.values())


def compressed_size(data: bytes) -> int:
    """الحجم الكامل بعد الضغط بما فيه الجدول (لمقارنة عادلة مع zlib)."""
    packed, code, _ = encode(data)
    return len(packed) + table_size(code) + 4


def code_table_json(code: dict[int, str], limit: int = 12) -> str:
    """أقصر الرموز أولاً، للعرض في الواجهة والتقرير."""
    items = sorted(code.items(), key=lambda kv: (len(kv[1]), kv[0]))[:limit]
    return json.dumps({chr(k) if 32 <= k < 127 else f"0x{k:02x}": v for k, v in items}, ensure_ascii=False)
