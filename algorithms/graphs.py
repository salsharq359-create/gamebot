"""
خوارزميات الرسوم البيانية على خريطة «جمع العملات» — M269.

الخريطة رسم بياني (graph): كل خلية غير جدار عقدة، وكل خليتين متجاورتين (أعلى/أسفل/يمين/يسار) بينهما حافة.
تكلفة الدخول إلى خلية = 1 للأرض العادية، وأكثر للتضاريس الصعبة (طين = 3) في نسخة «التضاريس».

  bfs        أقصر طريق بعدد الخطوات (كل الحواف بوزن 1)          O(V + E)
  reachable  الملء بالعمق أولاً (DFS بمكدس): كل ما يمكن الوصول إليه  O(V + E)
  dijkstra   أقل تكلفة مع أوزان موجبة (طابور أولوية)             O((V + E) log V)
  astar      Dijkstra + تقدير مقبول للمسافة المتبقية (مانهاتن)    نفس الرتبة، وعقد أقل عملياً
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field

from .structures import BinaryHeap, Queue, Stack

Cell = tuple[int, int]


@dataclass
class Grid:
    size: int
    walls: set = field(default_factory=set)
    cost: dict = field(default_factory=dict)      # خلية -> تكلفة الدخول (الافتراضي 1)

    def neighbors(self, cell: Cell):
        r, c = cell
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < self.size and 0 <= nc < self.size and (nr, nc) not in self.walls:
                yield (nr, nc)

    def step_cost(self, cell: Cell) -> int:
        return self.cost.get(cell, 1)

    @property
    def cells(self) -> int:
        return self.size * self.size - len(self.walls)


def random_grid(size: int = 8, walls: int = 10, mud: int = 0, rng: random.Random | None = None) -> Grid:
    rng = rng or random.Random()
    cells = [(r, c) for r in range(size) for c in range(size)]
    rng.shuffle(cells)
    g = Grid(size, set(cells[:walls]))
    for cell in cells[walls:walls + mud]:
        g.cost[cell] = 3
    return g


def _path(came_from: dict, goal: Cell) -> list[Cell]:
    out = []
    while goal is not None:
        out.append(goal)
        goal = came_from[goal]
    return out[::-1]


def bfs(g: Grid, start: Cell, goal: Cell) -> tuple[list[Cell] | None, int]:
    """يرجع (المسار من البداية للهدف، عدد العقد التي فُحصت)."""
    q, came, expanded = Queue(), {start: None}, 0
    q.enqueue(start)
    while not q.is_empty():
        cur = q.dequeue()
        expanded += 1
        if cur == goal:
            return _path(came, goal), expanded
        for n in g.neighbors(cur):
            if n not in came:
                came[n] = cur
                q.enqueue(n)
    return None, expanded


def bfs_distances(g: Grid, start: Cell) -> dict[Cell, int]:
    """المسافة (بالخطوات) من خلية إلى كل الخلايا الأخرى: BFS واحد."""
    q, dist = Queue(), {start: 0}
    q.enqueue(start)
    while not q.is_empty():
        cur = q.dequeue()
        for n in g.neighbors(cur):
            if n not in dist:
                dist[n] = dist[cur] + 1
                q.enqueue(n)
    return dist


def reachable(g: Grid, start: Cell) -> set[Cell]:
    """الملء بـ DFS ومكدس صريح (بدون استدعاء ذاتي حتى لا نتجاوز حد المكدس في الخرائط الكبيرة)."""
    s, seen = Stack(), {start}
    s.push(start)
    while not s.is_empty():
        cur = s.pop()
        for n in g.neighbors(cur):
            if n not in seen:
                seen.add(n)
                s.push(n)
    return seen


def dijkstra(g: Grid, start: Cell, goal: Cell) -> tuple[list[Cell] | None, int, int]:
    """يرجع (المسار، التكلفة، عدد العقد التي أُخرجت من الطابور)."""
    tie = itertools.count()
    h = BinaryHeap(key=lambda t: (t[0], t[1]))
    h.push((0, next(tie), start))
    dist, came, done, expanded = {start: 0}, {start: None}, set(), 0
    while not h.is_empty():
        d, _, cur = h.pop()
        if cur in done:
            continue                    # نسخة قديمة في الطابور (lazy deletion)
        done.add(cur)
        expanded += 1
        if cur == goal:
            return _path(came, goal), d, expanded
        for n in g.neighbors(cur):
            nd = d + g.step_cost(n)
            if nd < dist.get(n, float("inf")):
                dist[n], came[n] = nd, cur
                h.push((nd, next(tie), n))
    return None, float("inf"), expanded


def manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def astar(g: Grid, start: Cell, goal: Cell) -> tuple[list[Cell] | None, int, int]:
    """A*: الأولوية = التكلفة حتى الآن + مسافة مانهاتن. مسافة مانهاتن لا تبالغ أبداً (أقل تكلفة خطوة = 1)،
    لذلك التقدير «مقبول» (admissible) والمسار الناتج أمثل مثل Dijkstra."""
    tie = itertools.count()
    h = BinaryHeap(key=lambda t: (t[0], t[1]))
    h.push((manhattan(start, goal), next(tie), 0, start))
    dist, came, done, expanded = {start: 0}, {start: None}, set(), 0
    while not h.is_empty():
        _, _, d, cur = h.pop()
        if cur in done:
            continue
        done.add(cur)
        expanded += 1
        if cur == goal:
            return _path(came, goal), d, expanded
        for n in g.neighbors(cur):
            nd = d + g.step_cost(n)
            if nd < dist.get(n, float("inf")):
                dist[n], came[n] = nd, cur
                h.push((nd + manhattan(n, goal), next(tie), nd, n))
    return None, float("inf"), expanded


def path_cost(g: Grid, path: list[Cell]) -> int:
    return sum(g.step_cost(c) for c in path[1:])
