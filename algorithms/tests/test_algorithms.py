"""اختبارات مكتبة M269: كل خوارزمية تُقارن بمرجع بسيط أو بمكتبة بايثون أو بالبحث الشامل."""
import heapq
import itertools
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from algorithms import complexity, graphs as G, knapsack, sorting, structures as S, tsp  # noqa: E402

rng = random.Random(269)


# ------------------------------------------------------------------ الهياكل
def test_stack_and_queue_order():
    s, q = S.Stack(), S.Queue(capacity=2)
    for i in range(10):
        s.push(i)
        q.enqueue(i)
    assert [s.pop() for _ in range(10)] == list(range(9, -1, -1))     # LIFO
    assert [q.dequeue() for _ in range(10)] == list(range(10))        # FIFO
    assert q.resizes == 3                                             # 2 → 4 → 8 → 16
    with pytest.raises(IndexError):
        q.dequeue()


def test_queue_wraps_around():
    q = S.Queue(capacity=4)
    out = []
    for i in range(20):                  # إضافة وحذف متداخلان: الرأس يلتف حول المصفوفة
        q.enqueue(i)
        if i % 2:
            out.append(q.dequeue())
    out += [q.dequeue() for _ in range(len(q))]
    assert out == list(range(20))


def test_heap_matches_heapq_and_heapify_is_linear():
    data = [rng.randrange(10_000) for _ in range(2000)]
    h = S.BinaryHeap(data)
    assert h.comparisons < 2 * len(data)                              # heapify أقل من 2n مقارنة
    assert [h.pop() for _ in range(len(data))] == sorted(data)
    h2, ref = S.BinaryHeap(), []
    for x in data[:300]:
        h2.push(x)
        heapq.heappush(ref, x)
        assert h2.peek() == ref[0]


def test_hashmap_behaves_like_dict():
    m, ref = S.HashMap(), {}
    for i in range(3000):
        k = f"user-{rng.randrange(1000)}"
        m.put(k, i)
        ref[k] = i
    assert len(m) == len(ref) and all(m.get(k) == v for k, v in ref.items())
    assert m.load_factor <= S.HashMap.MAX_LOAD and m.resizes >= 7
    m.delete("user-1") if "user-1" in m else None
    assert "user-1" not in m


# ------------------------------------------------------------------ الترتيب
@pytest.mark.parametrize("name", list(sorting.ALGORITHMS))
def test_sorts_match_sorted(name):
    fn = sorting.ALGORITHMS[name]
    for n in (0, 1, 2, 17, 300):
        data = [rng.randrange(50) for _ in range(n)]
        assert fn(data)[0] == sorted(data)
        assert fn(data, reverse=True)[0] == sorted(data, reverse=True)


def test_stability():
    rows = [(rng.randrange(5), i) for i in range(200)]                 # (الأرباح، ترتيب التسجيل)
    for name in ("insertion", "merge"):
        out = sorting.ALGORITHMS[name](rows, key=lambda r: r[0])[0]
        assert out == sorted(rows, key=lambda r: r[0])                 # sorted() في بايثون مستقر


def test_top_k():
    data = [rng.randrange(10_000) for _ in range(5000)]
    assert sorting.top_k(data, 10)[0] == sorted(data, reverse=True)[:10]


# ------------------------------------------------------------- الرسوم البيانية
def test_bfs_dijkstra_astar_agree_on_unit_costs():
    for _ in range(50):
        g = G.random_grid(10, 25, rng=rng)
        free = [(r, c) for r in range(10) for c in range(10) if (r, c) not in g.walls]
        a, b = rng.sample(free, 2)
        p1, _ = G.bfs(g, a, b)
        p2, c2, _ = G.dijkstra(g, a, b)
        p3, c3, _ = G.astar(g, a, b)
        if p1 is None:
            assert p2 is None and p3 is None and b not in G.reachable(g, a)
        else:
            assert len(p1) - 1 == c2 == c3


def test_dijkstra_avoids_mud_and_astar_expands_less():
    expanded_d = expanded_a = 0
    for _ in range(100):
        g = G.random_grid(12, 20, mud=40, rng=rng)
        free = [(r, c) for r in range(12) for c in range(12) if (r, c) not in g.walls]
        a, b = rng.sample(free, 2)
        pb, _ = G.bfs(g, a, b)
        pd, cd, ed = G.dijkstra(g, a, b)
        pa, ca, ea = G.astar(g, a, b)
        if pb is None:
            continue
        assert cd == ca <= G.path_cost(g, pb)       # BFS يجد أقل خطوات، ليس أقل تكلفة
        expanded_d += ed
        expanded_a += ea
    assert expanded_a < expanded_d


# --------------------------------------------------------------- جمع العملات
def _random_dist(k):
    pts = [(rng.randrange(20), rng.randrange(20)) for _ in range(k + 1)]
    return [[G.manhattan(p, q) for q in pts] for p in pts]


def test_held_karp_equals_brute_force_and_beats_or_ties_greedy():
    for k in range(1, 8):
        for _ in range(20):
            d = _random_dist(k)
            hk, order, _ = tsp.held_karp(d)
            bf, _, _ = tsp.brute_force(d)
            nn, _ = tsp.nearest_neighbour(d)
            assert hk == bf <= nn
            assert sorted(order) == list(range(1, k + 1))
            assert sum(d[a][b] for a, b in zip([0] + order, order)) == hk


def test_held_karp_state_count():
    _, _, states = tsp.held_karp(_random_dist(10))
    assert states == 10 * (2 ** 9 - 1)              # k · (2^(k-1) − 1)


# ----------------------------------------------------------------- المستشار
def test_knapsack_dp_equals_backtracking():
    for _ in range(200):
        items = [(rng.randint(10, 400), rng.randint(1, 6)) for _ in range(rng.randint(1, 12))]
        T = rng.randint(1, 20)
        best, _ = knapsack.dp(items, T)
        assert best == knapsack.backtrack(items, T)[0] >= knapsack.greedy(items, T)


def test_knapsack_greedy_counterexample():
    items = [(400, 4), (270, 3), (270, 3)]          # نفس مثال المستشار في التقرير
    assert knapsack.greedy(items, 6) == 400 and knapsack.dp(items, 6)[0] == 540


def test_loglog_slope():
    ns = [100, 200, 400, 800]
    assert abs(complexity.loglog_slope(ns, [n * n for n in ns]) - 2) < 1e-9


def test_vendored_copies_are_identical():
    """المكتبة منسوخة داخل التطبيق (لأنه يُبنى وحده)، والمحرك منسوخ للعب بدون اتصال: النسخ يجب أن تتطابق."""
    root = Path(__file__).resolve().parents[2]
    for name in ("structures", "sorting", "graphs", "tsp", "knapsack", "complexity"):
        assert (root / "algorithms" / f"{name}.py").read_text() == (root / "app/gb/algorithms" / f"{name}.py").read_text()
    server = (root / "realtime/realtime/games.py").read_text()
    app = (root / "app/gb/engine/games.py").read_text()
    assert app.split("\n", 1)[1] == server
