"""
هياكل بيانات مجردة (ADTs) منفذة من الصفر — M269.

كل هيكل يعدّ العمليات الأساسية (ops) حتى نتحقق من التعقيد بالقياس:
  Stack       push/pop/peek                       O(1)
  Queue       enqueue/dequeue بمصفوفة دائرية        O(1) مطفأ (amortised)
  BinaryHeap  push/pop  O(log n)،  heapify  O(n)،  peek O(1)
  HashMap     put/get/delete  O(1) في المتوسط، بسلاسل منفصلة وتكبير عند حمل 0.75
"""
from __future__ import annotations

from typing import Any, Callable, Iterator


class Stack:
    def __init__(self):
        self._items: list = []

    def push(self, x) -> None:
        self._items.append(x)

    def pop(self):
        if not self._items:
            raise IndexError("pop from empty stack")
        return self._items.pop()

    def peek(self):
        if not self._items:
            raise IndexError("peek at empty stack")
        return self._items[-1]

    def __len__(self) -> int:
        return len(self._items)

    def is_empty(self) -> bool:
        return not self._items


class Queue:
    """طابور FIFO بمصفوفة دائرية: الرأس يتحرك بدل نقل العناصر، ويتضاعف الحجم عند الامتلاء."""

    def __init__(self, capacity: int = 8):
        self._data: list = [None] * max(1, capacity)
        self._head = 0
        self._size = 0
        self.resizes = 0

    def enqueue(self, x) -> None:
        if self._size == len(self._data):
            self._grow()
        self._data[(self._head + self._size) % len(self._data)] = x
        self._size += 1

    def dequeue(self):
        if not self._size:
            raise IndexError("dequeue from empty queue")
        x = self._data[self._head]
        self._data[self._head] = None
        self._head = (self._head + 1) % len(self._data)
        self._size -= 1
        return x

    def _grow(self) -> None:
        old = [self._data[(self._head + i) % len(self._data)] for i in range(self._size)]
        self._data = old + [None] * len(old)
        self._head = 0
        self.resizes += 1

    def __len__(self) -> int:
        return self._size

    def is_empty(self) -> bool:
        return self._size == 0


class BinaryHeap:
    """كومة صغرى (min-heap) في مصفوفة: الأب في i والأبناء في 2i+1 و 2i+2."""

    def __init__(self, items: list | None = None, key: Callable[[Any], Any] = lambda x: x):
        self._a: list = list(items or [])
        self._key = key
        self.comparisons = 0
        if self._a:
            self._heapify()

    def _less(self, i: int, j: int) -> bool:
        self.comparisons += 1
        return self._key(self._a[i]) < self._key(self._a[j])

    def _heapify(self) -> None:
        """بناء الكومة من الأسفل للأعلى: O(n) وليس O(n log n)."""
        for i in range(len(self._a) // 2 - 1, -1, -1):
            self._sift_down(i)

    def push(self, x) -> None:
        self._a.append(x)
        i = len(self._a) - 1
        while i > 0:
            parent = (i - 1) // 2
            if self._less(i, parent):
                self._a[i], self._a[parent] = self._a[parent], self._a[i]
                i = parent
            else:
                break

    def pop(self):
        if not self._a:
            raise IndexError("pop from empty heap")
        top = self._a[0]
        last = self._a.pop()
        if self._a:
            self._a[0] = last
            self._sift_down(0)
        return top

    def peek(self):
        if not self._a:
            raise IndexError("peek at empty heap")
        return self._a[0]

    def _sift_down(self, i: int) -> None:
        n = len(self._a)
        while True:
            smallest, left, right = i, 2 * i + 1, 2 * i + 2
            if left < n and self._less(left, smallest):
                smallest = left
            if right < n and self._less(right, smallest):
                smallest = right
            if smallest == i:
                return
            self._a[i], self._a[smallest] = self._a[smallest], self._a[i]
            i = smallest

    def __len__(self) -> int:
        return len(self._a)

    def is_empty(self) -> bool:
        return not self._a


class HashMap:
    """جدول تجزئة بسلاسل منفصلة (separate chaining). يتضاعف عدد الخانات إذا تجاوز الحمل 0.75."""

    MAX_LOAD = 0.75

    def __init__(self, buckets: int = 8):
        self._b: list[list] = [[] for _ in range(buckets)]
        self._n = 0
        self.probes = 0          # عدد المقارنات داخل السلاسل
        self.resizes = 0

    def _bucket(self, key) -> list:
        return self._b[hash(key) % len(self._b)]

    def put(self, key, value) -> None:
        b = self._bucket(key)
        for i, (k, _) in enumerate(b):
            self.probes += 1
            if k == key:
                b[i] = (key, value)
                return
        b.append((key, value))
        self._n += 1
        if self._n / len(self._b) > self.MAX_LOAD:
            self._resize()

    def get(self, key, default=None):
        for k, v in self._bucket(key):
            self.probes += 1
            if k == key:
                return v
        return default

    def __contains__(self, key) -> bool:
        sentinel = object()
        return self.get(key, sentinel) is not sentinel

    def delete(self, key) -> None:
        b = self._bucket(key)
        for i, (k, _) in enumerate(b):
            if k == key:
                del b[i]
                self._n -= 1
                return
        raise KeyError(key)

    def _resize(self) -> None:
        items = list(self.items())
        self._b = [[] for _ in range(len(self._b) * 2)]
        self._n = 0
        self.resizes += 1
        for k, v in items:
            b = self._bucket(k)
            b.append((k, v))
            self._n += 1

    def items(self) -> Iterator[tuple]:
        for b in self._b:
            yield from b

    @property
    def load_factor(self) -> float:
        return self._n / len(self._b)

    def longest_chain(self) -> int:
        return max(len(b) for b in self._b)

    def __len__(self) -> int:
        return self._n
