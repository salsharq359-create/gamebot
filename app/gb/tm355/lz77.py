"""
ضغط LZ77 (TM355 — الضغط بالقاموس).

بدل إرسال نص تكرر من قبل، نرسل «ارجع d بايت وانسخ l بايت». هذه فكرة zlib و ZIP و PNG و gzip.
هوفمان يستغل أن بعض الرموز أكثر تكراراً، و LZ77 يستغل أن **سلاسل كاملة** تتكرر
(مثل "platform" و "client_id" في كل سجل مزامنة). zlib يجمع الطريقتين معاً (DEFLATE).

الصيغة هنا هي نوع LZ77 المعروف باسم LZSS (مثل الذي يستخدمه DEFLATE قبل مرحلة هوفمان):
  كل 8 رموز يسبقها بايت «أعلام»: البت 0 = حرف حرفي (بايت واحد)، والبت 1 = نسخ (3 بايتات:
  مسافة الرجوع 2 بايت + الطول 1 بايت). النسخ يُستخدم فقط إذا كان الطول ≥ 4، وإلا فالحروف أوفر.
"""
from __future__ import annotations

WINDOW = 4096      # حجم النافذة المنزلقة (كم نرجع للخلف)
MAX_LEN = 255
MIN_MATCH = 4


def _tokens(data: bytes):
    """يولّد رموزاً: ("lit", بايت) أو ("copy", مسافة، طول)."""
    i, n = 0, len(data)
    index: dict[bytes, list[int]] = {}   # أول 3 بايتات -> المواقع السابقة (لتسريع البحث)
    while i < n:
        best_len, best_dist = 0, 0
        for j in reversed(index.get(data[i:i + 3], [])[-32:]):
            if i - j > WINDOW:
                break
            length = 0
            while length < MAX_LEN and i + length < n and data[j + length] == data[i + length]:
                length += 1
            if length > best_len:
                best_len, best_dist = length, i - j
                if length == MAX_LEN:
                    break
        if best_len >= MIN_MATCH:
            yield ("copy", best_dist, best_len)
            step = best_len
        else:
            yield ("lit", data[i])
            step = 1
        for k in range(i, min(i + step, n - 2)):
            index.setdefault(data[k:k + 3], []).append(k)
        i += step


def encode(data: bytes) -> bytes:
    out = bytearray()
    group: list[bytes] = []
    flags = 0
    for tok in _tokens(data):
        if tok[0] == "copy":
            flags |= 1 << len(group)
            group.append(tok[1].to_bytes(2, "big") + bytes([tok[2]]))
        else:
            group.append(bytes([tok[1]]))
        if len(group) == 8:
            out.append(flags)
            out += b"".join(group)
            group, flags = [], 0
    if group:
        out.append(flags)
        out += b"".join(group)
    return bytes(out)


def decode(blob: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(blob):
        flags = blob[i]
        i += 1
        for bit in range(8):
            if i >= len(blob):
                break
            if flags >> bit & 1:
                dist = int.from_bytes(blob[i:i + 2], "big")
                length = blob[i + 2]
                start = len(out) - dist
                if dist <= 0 or start < 0:
                    raise ValueError("مسافة غير صحيحة")
                for k in range(length):      # النسخ بايتاً بايتاً يسمح بالتداخل (تكرار نمط قصير)
                    out.append(out[start + k])
                i += 3
            else:
                out.append(blob[i])
                i += 1
    return bytes(out)
