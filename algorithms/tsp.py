"""
ترتيب جمع العملات — M269 (الجشع، والبرمجة الديناميكية، والبحث الشامل، والتعقيد).

المسألة: الروبوت في خلية ومعه k عملة؛ ما ترتيب الزيارة الذي يجمعها كلها بأقل عدد خطوات؟
هذه نسخة مفتوحة من «مسألة البائع المتجول» (TSP): لا نرجع لنقطة البداية. TSP من نوع NP-hard،
فلا نعرف خوارزمية زمنها كثير حدود (polynomial) لكل k.

  nearest_neighbour  جشع: اذهب دائماً لأقرب عملة                  O(k² ) بعد حساب المسافات — غير أمثل
  brute_force        جرّب كل الترتيبات                              O(k!)  — أمثل
  held_karp          برمجة ديناميكية على المجموعات الجزئية           O(2^k · k²) — أمثل، وأسرع كثيراً من k!

المسافات بين النقاط تأتي من BFS (أو Dijkstra في خريطة التضاريس)، وهي مسافات حقيقية حول الجدران.
"""
from __future__ import annotations

import itertools

INF = float("inf")


def nearest_neighbour(dist: list[list[float]]) -> tuple[float, list[int]]:
    """dist[i][j]: المسافة بين النقطة i والنقطة j، والنقطة 0 هي مكان الروبوت."""
    k = len(dist) - 1
    order, cur, total, left = [], 0, 0, set(range(1, k + 1))
    while left:
        nxt = min(left, key=lambda j: (dist[cur][j], j))
        total += dist[cur][nxt]
        order.append(nxt)
        left.remove(nxt)
        cur = nxt
    return total, order


def brute_force(dist: list[list[float]]) -> tuple[float, list[int], int]:
    """يرجع (أقل تكلفة، الترتيب، عدد الترتيبات التي جُربت)."""
    k = len(dist) - 1
    best, best_order, tried = INF, [], 0
    for perm in itertools.permutations(range(1, k + 1)):
        tried += 1
        cost, cur = 0, 0
        for p in perm:
            cost += dist[cur][p]
            if cost >= best:            # تقليم (pruning): لا فائدة من إكمال ترتيب صار أسوأ
                break
            cur = p
        else:
            best, best_order = cost, list(perm)
    return best, best_order, tried


def held_karp(dist: list[list[float]]) -> tuple[float, list[int], int]:
    """
    dp[S][j] = أقل تكلفة لنبدأ من الروبوت، ونزور كل عملات المجموعة S، وننتهي عند العملة j (j ضمن S).
    المجموعة S مخزنة كقناع بتات (bitmask): البت i-1 يعني العملة i.
      dp[{j}][j] = dist[0][j]
      dp[S][j]   = min( dp[S - {j}][i] + dist[i][j] )   لكل i في S - {j}
    الجواب = min_j dp[الكل][j]. يرجع (التكلفة، الترتيب، عدد الحالات المحسوبة).
    """
    k = len(dist) - 1
    if k == 0:
        return 0, [], 0
    full = (1 << k) - 1
    dp = [[INF] * (k + 1) for _ in range(1 << k)]
    parent = [[0] * (k + 1) for _ in range(1 << k)]
    for j in range(1, k + 1):
        dp[1 << (j - 1)][j] = dist[0][j]
    states = 0
    for S in range(1, full + 1):
        for j in range(1, k + 1):
            bit = 1 << (j - 1)
            if not S & bit or S == bit:
                continue
            prev = S ^ bit
            best, arg = INF, 0
            for i in range(1, k + 1):
                if prev & (1 << (i - 1)):
                    cand = dp[prev][i] + dist[i][j]
                    if cand < best:
                        best, arg = cand, i
            dp[S][j], parent[S][j] = best, arg
            states += 1
    last = min(range(1, k + 1), key=lambda j: dp[full][j])
    cost = dp[full][last]
    order, S, j = [], full, last
    while j:
        order.append(j)
        S, j = S ^ (1 << (j - 1)), parent[S][j]
    return cost, order[::-1], states
