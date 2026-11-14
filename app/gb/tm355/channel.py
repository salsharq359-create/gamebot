"""
محاكي القناة والتعديل الرقمي (TM355).

نرسل بتات بيانات المزامنة عبر قناة فيها ضوضاء بيضاء جاوسية (AWGN)، بثلاثة أنواع تعديل:
  BPSK   — بت واحد لكل رمز (±1)
  QPSK   — بتان لكل رمز (I و Q مستقلان)، نفس BER لـ BPSK لكل بت، وضعف المعدل
  16-QAM — 4 بتات لكل رمز (شبكة 4×4 بترميز Gray)، معدل أعلى لكن يحتاج نسبة إشارة أعلى

  Eb/N0  = طاقة البت إلى كثافة الضوضاء (dB)
  BER النظري:
    BPSK / QPSK:  Pb = Q(√(2·Eb/N0))
    16-QAM:       Pb ≈ (3/4)·Q(√((4/5)·Eb/N0))      (تقريب Gray المعروف)
  احتمال خطأ الحزمة (PER) لحزمة من n بت بدون ترميز:  PER = 1 − (1 − Pb)^n
  وعدد مرات الإرسال المتوقع مع إعادة الإرسال (ARQ):     1 / (1 − PER)
"""
from __future__ import annotations

import math
import random

from .infotheory import db_to_linear

MODS = {"BPSK": 1, "QPSK": 2, "16-QAM": 4}


def q_function(x: float) -> float:
    return 0.5 * math.erfc(x / math.sqrt(2))


def theoretical_ber(mod: str, ebn0_db: float) -> float:
    g = db_to_linear(ebn0_db)
    if mod in ("BPSK", "QPSK"):
        return q_function(math.sqrt(2 * g))
    if mod == "16-QAM":
        return 0.75 * q_function(math.sqrt(0.8 * g))
    raise ValueError(mod)


# ترميز Gray لمحور واحد في 16-QAM: بتان -> مستوى من {-3,-1,1,3}
_GRAY = {(0, 0): -3, (0, 1): -1, (1, 1): 1, (1, 0): 3}
_UNGRAY = {v: k for k, v in _GRAY.items()}


def _nearest_level(x: float) -> int:
    return min((-3, -1, 1, 3), key=lambda lv: abs(x - lv))


def simulate_ber(mod: str, ebn0_db: float, bits: list[int], seed: int = 3) -> tuple[float, int]:
    """محاكاة مونت كارلو: يرجع (BER المقاس، عدد الأخطاء)."""
    rng = random.Random(seed)
    k = MODS[mod]
    g = db_to_linear(ebn0_db)
    errors = 0
    n = len(bits) - len(bits) % k
    if mod == "16-QAM":
        es = 10.0                        # متوسط طاقة الرمز للمستويات ±1، ±3 في I و Q
        sigma = math.sqrt(es / (2 * k * g))
        for i in range(0, n, 4):
            b = bits[i:i + 4]
            i_lv, q_lv = _GRAY[(b[0], b[1])], _GRAY[(b[2], b[3])]
            ri = i_lv + rng.gauss(0, sigma)
            rq = q_lv + rng.gauss(0, sigma)
            rb = _UNGRAY[_nearest_level(ri)] + _UNGRAY[_nearest_level(rq)]
            errors += sum(x != y for x, y in zip(b, rb))
    else:
        # BPSK: رمز ±1 بطاقة 1 لكل بت. QPSK = قناتان BPSK متعامدتان، فنفس الحساب لكل بت.
        sigma = math.sqrt(1 / (2 * g))
        for b in bits[:n]:
            s = 1.0 if b else -1.0
            errors += ((s + rng.gauss(0, sigma)) > 0) != bool(b)
    return errors / n if n else 0.0, errors


def packet_error_rate(ber: float, nbits: int) -> float:
    return 1 - (1 - ber) ** nbits


def expected_transmissions(per: float) -> float:
    return math.inf if per >= 1 else 1 / (1 - per)


def ber_curve(mod: str, points: list[float]) -> list[tuple[float, float]]:
    return [(x, theoretical_ber(mod, x)) for x in points]
