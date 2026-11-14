"""
تجارب M269 القابلة للتكرار (بذور ثابتة). يستخدمها الدفتر والتقرير.
كل دالة ترجع بيانات بسيطة (قوائم وقواميس) حتى تُعرض أو تُرسم.
"""
from __future__ import annotations

import bisect
import itertools
import math
import random
import sys
from functools import lru_cache
from pathlib import Path

from . import complexity, graphs as G, knapsack, sorting, structures as S, tsp

ROOT = Path(__file__).resolve().parents[1]


def _engine():
    sys.path.insert(0, str(ROOT / "realtime"))
    from realtime.games import CoinCollector
    return CoinCollector


# --------------------------------------------------------------- 1) التعقيد
def sorting_growth(ns=(250, 500, 1000, 2000, 4000), seed=1) -> dict:
    rng = random.Random(seed)
    out = {name: {"n": [], "ms": [], "comparisons": []} for name in sorting.ALGORITHMS}
    for n in ns:
        data = [rng.randrange(1_000_000) for _ in range(n)]
        for name, fn in sorting.ALGORITHMS.items():
            if name == "insertion" and n > 2000:
                continue
            ms = complexity.time_it(lambda: fn(data), repeat=5)
            out[name]["n"].append(n)
            out[name]["ms"].append(ms)
            out[name]["comparisons"].append(fn(data)[1])
    for name, r in out.items():
        r["slope"] = round(complexity.loglog_slope(r["n"], r["ms"]), 2)
        r["slope_comparisons"] = round(complexity.loglog_slope(r["n"], r["comparisons"]), 2)
    return out


def search_growth(ns=(1_000, 10_000, 100_000, 1_000_000)) -> list[dict]:
    """البحث في قائمة مرتبة (مثل أرباح مرتبة): خطي مقابل ثنائي، بعدد المقارنات في أسوأ حالة."""
    rows = []
    for n in ns:
        data = list(range(n))
        target = n - 1
        lo, hi, steps = 0, n - 1, 0
        while lo <= hi:
            steps += 1
            mid = (lo + hi) // 2
            if data[mid] == target:
                break
            lo, hi = (mid + 1, hi) if data[mid] < target else (lo, mid - 1)
        assert bisect.bisect_left(data, target) == target
        rows.append({"n": n, "linear": n, "binary": steps, "log2n": round(math.log2(n), 1)})
    return rows


def bfs_growth(sizes=(10, 20, 40, 80, 160), seed=2) -> dict:
    rng = random.Random(seed)
    v, ms = [], []
    for s in sizes:
        g = G.random_grid(s, s * s // 10, rng=rng)
        start = next((r, c) for r in range(s) for c in range(s) if (r, c) not in g.walls)
        v.append(g.cells)
        ms.append(complexity.time_it(lambda: G.bfs_distances(g, start), repeat=3))
    return {"V": v, "ms": ms, "slope": round(complexity.loglog_slope(v, ms), 2)}


def heap_build(ns=(1_000, 10_000, 100_000), seed=3) -> list[dict]:
    """heapify (من الأسفل للأعلى) مقابل n عمليات push: عدد المقارنات."""
    rng = random.Random(seed)
    rows = []
    for n in ns:
        data = [rng.random() for _ in range(n)]
        h1 = S.BinaryHeap(data)
        h2 = S.BinaryHeap()
        for x in data:
            h2.push(x)
        rows.append({"n": n, "heapify": h1.comparisons, "pushes": h2.comparisons,
                     "heapify_per_n": round(h1.comparisons / n, 2), "push_per_n": round(h2.comparisons / n, 2)})
    return rows


def hashmap_probes(n=50_000, seed=4) -> dict:
    rng = random.Random(seed)
    m = S.HashMap()
    keys = [f"u_{rng.getrandbits(40):010x}" for _ in range(n)]
    for i, k in enumerate(keys):
        m.put(k, i)
    m.probes = 0
    for k in keys:
        m.get(k)
    return {"n": n, "avg_probes_per_get": round(m.probes / n, 2), "load": round(m.load_factor, 2),
            "longest_chain": m.longest_chain(), "resizes": m.resizes}


# --------------------------------------------- 2) المسار: الجشع مقابل الأمثل
def coin_routes(maps=3000, seed=269) -> dict:
    CoinCollector = _engine()
    rng = random.Random(seed)
    gaps = []
    for _ in range(maps):
        cc = CoinCollector(rng=rng)
        _, best, greedy = cc.plan()
        gaps.append(greedy - best)
    worse = [g for g in gaps if g > 0]
    return {"maps": maps, "worse_pct": round(100 * len(worse) / maps, 1), "avg_gap": round(sum(gaps) / maps, 2),
            "max_gap": max(gaps), "avg_gap_when_worse": round(sum(worse) / len(worse), 2),
            "hist": {k: gaps.count(k) for k in sorted(set(gaps))}}


def coin_route_steps(maps=3000, seed=269) -> dict:
    """الخطوات الفعلية التي يمشيها الروبوت (يجمع العملات في الطريق): الجديد مقابل القديم (الأقرب أولاً)."""
    CoinCollector = _engine()
    rng = random.Random(seed)
    new = old = 0
    for _ in range(maps):
        state = rng.getstate()
        cc = CoinCollector(rng=rng)
        new += sum(e["type"] == "move" for e in cc.play_round())
        rng2 = random.Random()
        rng2.setstate(state)
        cc2 = CoinCollector(rng=rng2)
        steps = 0
        while cc2.coins:                                # المحرك القديم: BFS لأقرب عملة
            path = cc2._path(cc2.bot, cc2.coins)
            steps += len(path)
            cc2.bot = path[-1]
            cc2.coins.discard(cc2.bot)
        old += steps
    return {"maps": maps, "old_avg": round(old / maps, 2), "new_avg": round(new / maps, 2),
            "saving_pct": round(100 * (old - new) / old, 1)}


def tsp_growth(ks_hk=range(4, 15), ks_bf=range(4, 10), seed=5) -> dict:
    rng = random.Random(seed)

    def dist(k):
        pts = [(rng.randrange(30), rng.randrange(30)) for _ in range(k + 1)]
        return [[G.manhattan(p, q) for q in pts] for p in pts]
    hk, bf = [], []
    for k in ks_hk:
        d = dist(k)
        hk.append({"k": k, "ms": complexity.time_it(lambda: tsp.held_karp(d), repeat=1),
                   "states": tsp.held_karp(d)[2]})
    for k in ks_bf:
        d = dist(k)
        bf.append({"k": k, "ms": complexity.time_it(lambda: tsp.brute_force(d), repeat=1),
                   "orders": math.factorial(k), "tried": tsp.brute_force(d)[2]})
    return {"held_karp": hk, "brute_force": bf}


# --------------------------------------------- 3) الرسوم البيانية مع التضاريس
def terrain_search(maps=500, size=12, seed=6) -> dict:
    rng = random.Random(seed)
    excess, exp_b, exp_d, exp_a, n, bfs_worse = 0, 0, 0, 0, 0, 0
    while n < maps:
        g = G.random_grid(size, size * size // 8, mud=size * size // 4, rng=rng)
        free = [(r, c) for r in range(size) for c in range(size) if (r, c) not in g.walls]
        a, b = rng.sample(free, 2)
        pb, eb = G.bfs(g, a, b)
        if pb is None:
            continue
        _, cd, ed = G.dijkstra(g, a, b)
        _, ca, ea = G.astar(g, a, b)
        assert cd == ca
        cb = G.path_cost(g, pb)
        excess += cb - cd
        bfs_worse += cb > cd
        exp_b, exp_d, exp_a = exp_b + eb, exp_d + ed, exp_a + ea
        n += 1
    return {"maps": maps, "bfs_worse_pct": round(100 * bfs_worse / maps, 1),
            "bfs_extra_cost": round(excess / maps, 2), "expanded_bfs": round(exp_b / maps, 1),
            "expanded_dijkstra": round(exp_d / maps, 1), "expanded_astar": round(exp_a / maps, 1),
            "astar_saving_pct": round(100 * (1 - exp_a / exp_d), 1)}


# ---------------------------------------------------- 4) المستشار (حقيبة الظهر)
def knapsack_compare(instances=2000, seed=7) -> dict:
    """مهام مثل جدول جيم بوت (جولة 1$/1د، بطولة 2$/3د، تحدي 1$/3د) ومنصات خاصة بمكافآت ومدد عشوائية."""
    rng = random.Random(seed)
    worse, gap, nodes, cells = 0, 0.0, 0, 0
    for _ in range(instances):
        items = []
        for _ in range(rng.randint(2, 6)):
            items += [(rng.choice([100, 200, 50, 150, 270, 400, 500]), rng.randint(1, 6))] * rng.randint(1, 3)
        T = rng.randint(5, 40)
        best, c = knapsack.dp(items, T)
        g = knapsack.greedy(items, T)
        bt, nd = knapsack.backtrack(items, T)
        assert bt == best >= g
        worse += g < best
        gap += (best - g) / best if best else 0
        nodes += nd
        cells += c
    return {"instances": instances, "greedy_worse_pct": round(100 * worse / instances, 1),
            "greedy_avg_loss_pct": round(100 * gap / instances, 2), "avg_dp_cells": round(cells / instances),
            "avg_backtrack_nodes": round(nodes / instances)}


def knapsack_pseudo_poly(Ts=(60, 120, 240, 480, 960, 1920), seed=8) -> dict:
    rng = random.Random(seed)
    items = [(rng.randint(50, 500), rng.randint(1, 10)) for _ in range(40)]
    ms = [complexity.time_it(lambda T=T: knapsack.dp(items, T), repeat=3) for T in Ts]
    return {"T": list(Ts), "ms": ms, "slope": round(complexity.loglog_slope(list(Ts), ms), 2), "n": len(items)}


# --------------------------------------------------------- 5) Minimax
def minimax_nodes() -> dict:
    """عدد العقد التي يزورها Minimax لإكس أو من لوحة فارغة: بدون ذاكرة، ومع ذاكرة (memoisation)."""
    lines = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]

    def winner(b):
        for x, y, z in lines:
            if b[x] != " " and b[x] == b[y] == b[z]:
                return b[x]
        return "draw" if " " not in b else None

    calls = 0

    def plain(b, p):
        nonlocal calls
        calls += 1
        w = winner(b)
        if w:
            return {"X": 1, "O": -1, "draw": 0}[w]
        scores = [plain(b[:i] + (p,) + b[i + 1:], "O" if p == "X" else "X") for i in range(9) if b[i] == " "]
        return max(scores) if p == "X" else min(scores)

    empty = tuple(" " * 9)
    value = plain(empty, "X")
    plain_calls = calls

    @lru_cache(maxsize=None)
    def memo(b, p):
        w = winner(b)
        if w:
            return {"X": 1, "O": -1, "draw": 0}[w]
        scores = [memo(b[:i] + (p,) + b[i + 1:], "O" if p == "X" else "X") for i in range(9) if b[i] == " "]
        return max(scores) if p == "X" else min(scores)
    memo(empty, "X")
    info = memo.cache_info()
    return {"value_from_empty": value, "calls_without_memo": plain_calls, "unique_states_with_memo": info.currsize,
            "cache_hits": info.hits, "reduction": round(plain_calls / info.currsize, 1)}
