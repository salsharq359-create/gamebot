"""
خطة المستشار كمسألة «حقيبة الظهر 0/1» — M269 (الجشع، والبرمجة الديناميكية، والتراجع).

كل عنصر = (المكافأة بالسنت، الدقائق). الميزانية T دقيقة.
  greedy      الأعلى ربحاً لكل دقيقة أولاً                 O(n log n) — قد يخطئ
  dp          جدول dp[t] لكل الدقائق من 0 إلى T            O(n · T)   — أمثل
  backtrack   بحث شامل بالتراجع مع حد أعلى للتقليم          O(2^n) في أسوأ حالة — أمثل، للتحقق

ملاحظة التعقيد: حقيبة الظهر NP-complete، لكن O(n·T) ليست كثيرة حدود في حجم المدخلات لأن T رقم
(يحتاج log T بت فقط). هذا يسمى «شبه كثير حدود» (pseudo-polynomial)، وهو مناسب هنا لأن T ≤ 240 دقيقة.
"""
from __future__ import annotations


def greedy(items: list[tuple[int, int]], T: int) -> int:
    total, left = 0, T
    for reward, minutes in sorted(items, key=lambda x: (-x[0] / x[1], -x[0])):
        if minutes <= left:
            total += reward
            left -= minutes
    return total


def dp(items: list[tuple[int, int]], T: int) -> tuple[int, int]:
    """يرجع (أعلى ربح، عدد الخانات المحسوبة)."""
    best = [0] * (T + 1)
    cells = 0
    for reward, minutes in items:
        for t in range(T, minutes - 1, -1):
            cells += 1
            if best[t - minutes] + reward > best[t]:
                best[t] = best[t - minutes] + reward
    return best[T], cells


def backtrack(items: list[tuple[int, int]], T: int) -> tuple[int, int]:
    """يرجع (أعلى ربح، عدد العقد في شجرة البحث). الحد الأعلى = ربح كسري (fractional) لما تبقى."""
    order = sorted(items, key=lambda x: -x[0] / x[1])
    best, nodes = 0, 0

    def bound(i, left, value):
        for reward, minutes in order[i:]:
            if minutes <= left:
                left -= minutes
                value += reward
            else:
                return value + reward * left / minutes
        return value

    def go(i, left, value):
        nonlocal best, nodes
        nodes += 1
        best = max(best, value)
        if i == len(order) or bound(i, left, value) <= best:
            return
        reward, minutes = order[i]
        if minutes <= left:
            go(i + 1, left - minutes, value + reward)
        go(i + 1, left, value)

    go(0, T, 0)
    return best, nodes
