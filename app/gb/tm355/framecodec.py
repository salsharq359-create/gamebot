"""
ترميز إطارات خريطة اللعبة (TM355 — ترميز الصور والفيديو).

خريطة «جمع العملات» 8×8 تشبه إطار فيديو صغيراً: بين حركة وأخرى تتغير خليتان أو ثلاث فقط.
لذلك نستخدم فكرة ضغط الفيديو:
  - إطار مفتاحي (keyframe / I-frame): الخريطة كاملة. يُرسل أولاً ثم كل KEY_INTERVAL إطارات،
    حتى يستطيع جهاز اتصل في المنتصف أو فقد إطاراً أن يكمل.
  - إطار فرق (P-frame): فقط الخلايا التي تغيرت منذ الإطار السابق. كل تغيير 3 حروف:
    رقم الصف، رقم العمود، القيمة الجديدة. مثال "34.35R": الخلية (3،4) صارت فارغة و(3،5) صار فيها الروبوت.

صيغة الإطار (مفاتيح قصيرة لأن كل بايت يُحسب):
  مفتاحي: {"k":1,"s":رقم الإطار,"b":[صفوف الخريطة]}
  فرق:     {"s":رقم الإطار,"d":"التغييرات"}

نفس الملف موجود في خادم الروبوت (realtime/realtime/framecodec.py).
"""
from __future__ import annotations

import json

KEY_INTERVAL = 15


class Encoder:
    def __init__(self, key_interval: int = KEY_INTERVAL):
        self.key_interval = key_interval
        self.prev: list[str] | None = None
        self.count = 0
        self.full_bytes = 0      # لو أرسلنا كل إطار كاملاً
        self.sent_bytes = 0      # ما أُرسل فعلاً
        self.keyframes = 0

    def reset(self) -> None:
        self.prev = None

    def encode(self, rows: list[str]) -> dict:
        full = {"board": rows}
        if self.prev is None or len(self.prev) != len(rows) or self.count % self.key_interval == 0:
            frame = {"k": 1, "s": self.count, "b": rows}
            self.keyframes += 1
        else:
            delta = "".join(f"{r}{c}{ch}" for r, (old, new) in enumerate(zip(self.prev, rows))
                            for c, (a, ch) in enumerate(zip(old, new)) if a != ch)
            frame = {"s": self.count, "d": delta}
        self.prev = list(rows)
        self.count += 1
        self.full_bytes += _size(full)
        self.sent_bytes += _size(frame)
        return frame

    @property
    def stats(self) -> dict:
        ratio = self.full_bytes / self.sent_bytes if self.sent_bytes else 1.0
        return {"frames": self.count, "keyframes": self.keyframes, "full_bytes": self.full_bytes,
                "sent_bytes": self.sent_bytes, "ratio": round(ratio, 2)}


class Decoder:
    def __init__(self):
        self.board: list[list[str]] | None = None
        self.missing = False     # فقدنا إطاراً: ننتظر الإطار المفتاحي التالي
        self.next_seq = 0

    def decode(self, frame: dict) -> list[str] | None:
        """يرجع الخريطة بعد الإطار، أو None إذا لا يمكن بناؤها بعد."""
        seq = frame.get("s", self.next_seq)
        if frame.get("k"):
            self.board = [list(r) for r in frame["b"]]
            self.missing = False
        else:
            if self.board is None or seq != self.next_seq:
                self.missing = True
            if self.missing:
                self.next_seq = seq + 1
                return None
            d = frame.get("d", "")
            for i in range(0, len(d) - 2, 3):
                self.board[int(d[i])][int(d[i + 1])] = d[i + 2]
        self.next_seq = seq + 1
        return ["".join(r) for r in self.board]


def _size(obj) -> int:
    return len(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode())
