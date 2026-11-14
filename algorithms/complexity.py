"""قياس الزمن وتقدير رتبة النمو من القياسات — M269."""
from __future__ import annotations

import math
import statistics
import time
from typing import Callable


def time_it(fn: Callable[[], object], repeat: int = 5) -> float:
    """وسيط زمن التنفيذ بالملي ثانية."""
    times = []
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t) * 1000)
    return statistics.median(times)


def loglog_slope(ns: list[float], ts: list[float]) -> float:
    """ميل خط log(t) مقابل log(n) بالمربعات الصغرى: ≈ 1 لخطي، ≈ 2 لتربيعي."""
    xs, ys = [math.log(n) for n in ns], [math.log(t) for t in ts]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
