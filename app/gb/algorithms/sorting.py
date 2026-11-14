"""
خوارزميات الترتيب — M269. كل دالة ترجع (القائمة المرتبة، عدد المقارنات) ولا تغيّر المدخلات.
key تحدد ما نرتب حسبه (مثل الأرباح في لوحة المتصدرين)، و reverse للترتيب التنازلي.

  insertion  O(n²) أسوأ حالة، O(n) إذا كانت شبه مرتبة، مستقرة
  merge      O(n log n) دائماً، مستقرة، تحتاج ذاكرة إضافية O(n)
  quick      O(n log n) في المتوسط، O(n²) أسوأ حالة، غير مستقرة (محور = وسيط ثلاثة)
  heap       O(n log n) دائماً، غير مستقرة
"""
from __future__ import annotations

from typing import Any, Callable

from .structures import BinaryHeap


class _Cmp:
    def __init__(self, key, reverse):
        self.key, self.reverse, self.n = key, reverse, 0

    def le(self, a, b) -> bool:
        """a يأتي قبل b أو معه (تحافظ على الاستقرار)."""
        self.n += 1
        ka, kb = self.key(a), self.key(b)
        return ka >= kb if self.reverse else ka <= kb


def insertion_sort(items: list, key: Callable[[Any], Any] = lambda x: x, reverse: bool = False):
    a, c = list(items), _Cmp(key, reverse)
    for i in range(1, len(a)):
        x, j = a[i], i - 1
        while j >= 0 and not c.le(a[j], x):
            a[j + 1] = a[j]
            j -= 1
        a[j + 1] = x
    return a, c.n


def merge_sort(items: list, key: Callable[[Any], Any] = lambda x: x, reverse: bool = False):
    c = _Cmp(key, reverse)

    def sort(a):
        if len(a) <= 1:
            return a
        mid = len(a) // 2
        left, right = sort(a[:mid]), sort(a[mid:])
        out, i, j = [], 0, 0
        while i < len(left) and j < len(right):
            if c.le(left[i], right[j]):        # <= : العنصر الأيسر أولاً عند التساوي = مستقر
                out.append(left[i]); i += 1
            else:
                out.append(right[j]); j += 1
        return out + left[i:] + right[j:]
    return sort(list(items)), c.n


def quick_sort(items: list, key: Callable[[Any], Any] = lambda x: x, reverse: bool = False):
    a, c = list(items), _Cmp(key, reverse)

    def median3(lo, hi):
        mid = (lo + hi) // 2
        trio = sorted([(lo, a[lo]), (mid, a[mid]), (hi, a[hi])], key=lambda t: key(t[1]), reverse=reverse)
        c.n += 3
        return trio[1][0]

    def sort(lo, hi):
        while lo < hi:
            p = median3(lo, hi)
            a[p], a[hi] = a[hi], a[p]
            pivot, store = a[hi], lo
            for i in range(lo, hi):
                if c.le(a[i], pivot):
                    a[i], a[store] = a[store], a[i]
                    store += 1
            a[store], a[hi] = a[hi], a[store]
            # الاستدعاء الذاتي على الجزء الأصغر والتكرار على الأكبر: عمق المكدس O(log n)
            if store - lo < hi - store:
                sort(lo, store - 1); lo = store + 1
            else:
                sort(store + 1, hi); hi = store - 1
    sort(0, len(a) - 1)
    return a, c.n


def heap_sort(items: list, key: Callable[[Any], Any] = lambda x: x, reverse: bool = False):
    k = (lambda x: _Neg(key(x))) if reverse else key
    h = BinaryHeap(list(items), key=k)
    out = [h.pop() for _ in range(len(h))]
    return out, h.comparisons


class _Neg:
    """يعكس الترتيب لأي قيمة قابلة للمقارنة (حتى نستخدم الكومة الصغرى للترتيب التنازلي)."""
    __slots__ = ("v",)

    def __init__(self, v):
        self.v = v

    def __lt__(self, other):
        return other.v < self.v


def top_k(items: list, k: int, key: Callable[[Any], Any] = lambda x: x):
    """أعلى k عناصر بكومة صغرى حجمها k: O(n log k) بدل ترتيب الكل O(n log n)."""
    h = BinaryHeap(key=key)
    for x in items:
        if len(h) < k:
            h.push(x)
        elif key(x) > key(h.peek()):
            h.pop()
            h.push(x)
    return sorted([h.pop() for _ in range(len(h))], key=key, reverse=True), h.comparisons


ALGORITHMS = {"insertion": insertion_sort, "merge": merge_sort, "quick": quick_sort, "heap": heap_sort}
