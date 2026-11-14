"""
نظرية المعلومات (TM355): كمية المعلومات، والإنتروبيا، وسعة القناة.

  المعلومات في رمز احتماله p:     I = -log2(p)  بت
  الإنتروبيا (متوسط المعلومات):  H = -Σ p·log2(p)  بت لكل رمز
  الإنتروبيا هي الحد الأدنى النظري لمتوسط طول أي ترميز بدون فقد (نظرية شانون للترميز).
  سعة شانون للقناة:             C = B·log2(1 + S/N)  بت/ثانية
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Hashable, Iterable


def probabilities(symbols: Iterable[Hashable]) -> dict:
    counts = Counter(symbols)
    total = sum(counts.values())
    return {s: c / total for s, c in counts.items()} if total else {}


def information(p: float) -> float:
    """كمية المعلومات (بت) في حدث احتماله p."""
    if not 0 < p <= 1:
        raise ValueError("p must be in (0, 1]")
    return -math.log2(p)


def entropy(symbols: Iterable[Hashable]) -> float:
    """الإنتروبيا (بت لكل رمز) لسلسلة رموز، من التكرارات الفعلية."""
    return -sum(p * math.log2(p) for p in probabilities(symbols).values())


def entropy_of_probs(probs: Iterable[float]) -> float:
    return -sum(p * math.log2(p) for p in probs if p > 0)


def min_bytes(data: bytes) -> float:
    """أقل حجم نظري (بايت) لهذه البيانات إذا رُمّز كل بايت مستقلاً (نموذج بدون ذاكرة)."""
    return entropy(data) * len(data) / 8


def db_to_linear(db: float) -> float:
    return 10 ** (db / 10)


def linear_to_db(x: float) -> float:
    return 10 * math.log10(x)


def shannon_capacity(bandwidth_hz: float, snr_db: float) -> float:
    """سعة شانون (بت/ثانية): أعلى معدل يمكن نقله بلا أخطاء نظرياً."""
    return bandwidth_hz * math.log2(1 + db_to_linear(snr_db))


def spectral_efficiency(snr_db: float) -> float:
    """الكفاءة الطيفية القصوى (بت/ثانية لكل هرتز)."""
    return math.log2(1 + db_to_linear(snr_db))
