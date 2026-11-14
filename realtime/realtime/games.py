"""
الألعاب التجريبية داخل تطبيق جيم بوت.

كل لعبة فيها روبوت يلعب فعلاً باستخدام خوارزمية حقيقية:
  - جمع العملات   : BFS للمسافات حول الجدران + برمجة ديناميكية (Held-Karp) لأفضل ترتيب لجمع العملات.
  - تخمين الرقم   : البحث الثنائي (Binary Search).
  - إكس أو        : خوارزمية Minimax (لا يخسر أبداً).

كل دالة play_round() عبارة عن مولّد (generator) يُرجع أحداثاً على شكل قاموس:
  {"type": "move" | "log" | "result", "text": ..., "points": ..., "board": ...}
بهذا تستطيع الواجهة عرض ما يفعله الروبوت خطوة بخطوة.
"""
from __future__ import annotations

import random
from collections import deque
from functools import lru_cache
from dataclasses import dataclass
from typing import Callable, Iterator, Protocol


@dataclass(frozen=True)
class GameInfo:
    key: str
    name: str
    category: str
    algorithm: str


GAMES: dict[str, GameInfo] = {
    "coins": GameInfo("coins", "جمع العملات", "مغامرات", "BFS + Held-Karp – المسار الأمثل"),
    "guess": GameInfo("guess", "تخمين الرقم", "ألغاز", "البحث الثنائي"),
    "xo": GameInfo("xo", "إكس أو", "استراتيجية", "Minimax"),
}


# --------------------------------------------------------------------------
# 1) لعبة جمع العملات
# --------------------------------------------------------------------------
class CoinCollector:
    """
    شبكة فيها جدران وعملات. الروبوت يجمع كل العملات بأقل عدد خطوات ممكن.

    M269: كانت النسخة السابقة تذهب دائماً «لأقرب عملة» (خوارزمية جشعة)، والقياس على 3,000 خريطة أظهر أنها
    ليست الأقصر في 46% من الخرائط. الآن: BFS من الروبوت ومن كل عملة يعطي المسافات الحقيقية حول الجدران،
    ثم برمجة ديناميكية على المجموعات الجزئية (Held-Karp، O(2^k · k²)) تختار أفضل ترتيب. مع 6 عملات = 186 حالة بدل 720 ترتيباً.
    """

    EMPTY, WALL, COIN, BOT = ".", "#", "$", "R"
    POINTS_PER_COIN = 10

    def __init__(self, size: int = 8, coins: int = 6, walls: int = 10, rng: random.Random | None = None):
        self.size = size
        self.rng = rng or random.Random()
        self._build(coins, walls)

    def _build(self, coins: int, walls: int) -> None:
        cells = [(r, c) for r in range(self.size) for c in range(self.size)]
        while True:
            self.rng.shuffle(cells)
            self.bot = cells[0]
            self.walls = set(cells[1:1 + walls])
            self.coins = set(cells[1 + walls:1 + walls + coins])
            # نتأكد أن كل العملات يمكن الوصول إليها: بحث واحد O(V + E) بدل BFS لكل عملة
            if self.coins <= set(self._distances(self.bot)):
                return

    def _neighbors(self, cell):
        r, c = cell
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < self.size and 0 <= nc < self.size and (nr, nc) not in self.walls:
                yield (nr, nc)

    def _path(self, start, targets: set):
        """BFS: يرجع أقصر طريق من start إلى أقرب خلية في targets."""
        queue = deque([start])
        came_from = {start: None}
        while queue:
            cur = queue.popleft()
            if cur in targets:
                path = []
                while cur != start:
                    path.append(cur)
                    cur = came_from[cur]
                return path[::-1]
            for nxt in self._neighbors(cur):
                if nxt not in came_from:
                    came_from[nxt] = cur
                    queue.append(nxt)
        return None

    def _distances(self, start) -> dict:
        """BFS واحد: المسافة من start إلى كل خلية يمكن الوصول إليها."""
        dist, queue = {start: 0}, deque([start])
        while queue:
            cur = queue.popleft()
            for nxt in self._neighbors(cur):
                if nxt not in dist:
                    dist[nxt] = dist[cur] + 1
                    queue.append(nxt)
        return dist

    def plan(self) -> tuple[list, int, int]:
        """يرجع (ترتيب العملات الأمثل، عدد خطواته، عدد خطوات «الأقرب أولاً»)."""
        pts = [self.bot] + sorted(self.coins)
        k = len(pts) - 1
        dists = [self._distances(p) for p in pts]            # k + 1 عمليات BFS
        d = [[dist[q] for q in pts] for dist in dists]
        # Held-Karp: dp[S][j] = أقل خطوات لزيارة مجموعة العملات S والانتهاء عند j
        inf = float("inf")
        dp = [[inf] * (k + 1) for _ in range(1 << k)]
        par = [[0] * (k + 1) for _ in range(1 << k)]
        for j in range(1, k + 1):
            dp[1 << (j - 1)][j] = d[0][j]
        for S in range(1, 1 << k):
            for j in range(1, k + 1):
                bit = 1 << (j - 1)
                if not S & bit or S == bit:
                    continue
                for i in range(1, k + 1):
                    if (S ^ bit) & (1 << (i - 1)):
                        cand = dp[S ^ bit][i] + d[i][j]
                        if cand < dp[S][j]:
                            dp[S][j], par[S][j] = cand, i
        full = (1 << k) - 1
        last = min(range(1, k + 1), key=lambda j: dp[full][j])
        order, S, j = [], full, last
        while j:
            order.append(pts[j])
            S, j = S ^ (1 << (j - 1)), par[S][j]
        # للمقارنة: الجشع (الأقرب أولاً) على نفس المسافات
        cur, left, greedy = 0, set(range(1, k + 1)), 0
        while left:
            nxt = min(left, key=lambda x: (d[cur][x], x))
            greedy += d[cur][nxt]
            left.discard(nxt)
            cur = nxt
        return order[::-1], int(dp[full][last]), greedy

    def board(self) -> list[list[str]]:
        grid = [[self.EMPTY] * self.size for _ in range(self.size)]
        for r, c in self.walls:
            grid[r][c] = self.WALL
        for r, c in self.coins:
            grid[r][c] = self.COIN
        grid[self.bot[0]][self.bot[1]] = self.BOT
        return grid

    def play_round(self):
        total, steps = 0, 0
        yield {"type": "log", "text": f"بدأت الجولة: {len(self.coins)} عملات على الخريطة"}
        order, best, greedy = self.plan()
        note = f" (الأقرب أولاً كان سيحتاج {greedy})" if greedy > best else ""
        yield {"type": "log", "text": f"المسار الأمثل: {best} خطوة{note}"}
        for target in order:
            if target not in self.coins:
                continue                       # جُمعت في الطريق
            for cell in self._path(self.bot, {target}):
                self.bot = cell
                steps += 1
                yield {"type": "move", "board": self.board()}
                if cell in self.coins:
                    self.coins.discard(cell)
                    total += self.POINTS_PER_COIN
                    yield {"type": "log", "text": "جمع عملة"}
        yield {"type": "result", "won": True, "points": total,
               "text": f"جمع كل العملات في {steps} خطوة"}


# --------------------------------------------------------------------------
# 2) لعبة تخمين الرقم
# --------------------------------------------------------------------------
class NumberGuess:
    """اللعبة تختار رقماً سرياً، والروبوت يخمّنه بالبحث الثنائي."""

    MAX_TRIES = 10

    def __init__(self, low: int = 1, high: int = 1000, rng: random.Random | None = None):
        self.low, self.high = low, high
        self.secret = (rng or random.Random()).randint(low, high)

    def check(self, guess: int) -> int:
        """-1 إذا كان التخمين أصغر، 1 إذا كان أكبر، 0 إذا كان صحيحاً."""
        return (guess > self.secret) - (guess < self.secret)

    def play_round(self):
        lo, hi = self.low, self.high
        yield {"type": "log", "text": f"اختارت اللعبة رقماً بين {lo} و {hi}"}
        for attempt in range(1, self.MAX_TRIES + 1):
            guess = (lo + hi) // 2
            answer = self.check(guess)
            if answer == 0:
                points = 5 * (self.MAX_TRIES - attempt + 1)
                yield {"type": "result", "won": True, "points": points,
                       "text": f"وجد الرقم {guess} من المحاولة {attempt}"}
                return
            hint = "أكبر" if answer < 0 else "أصغر"
            yield {"type": "log", "text": f"تخمين {guess}: الرقم {hint}"}
            if answer < 0:
                lo = guess + 1
            else:
                hi = guess - 1
        yield {"type": "result", "won": False, "points": 0, "text": "انتهت المحاولات"}


# --------------------------------------------------------------------------
# 3) لعبة إكس أو
# --------------------------------------------------------------------------
class TicTacToe:
    """الروبوت (X) يلعب بخوارزمية Minimax ضد خصم عشوائي (O)."""

    LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
    WIN_POINTS, DRAW_POINTS = 40, 15

    def __init__(self, rng: random.Random | None = None):
        self.cells = [" "] * 9
        self.rng = rng or random.Random()

    def winner(self):
        return self._winner_of(tuple(self.cells))

    @staticmethod
    def _winner_of(cells):
        for a, b, c in TicTacToe.LINES:
            if cells[a] != " " and cells[a] == cells[b] == cells[c]:
                return cells[a]
        return "draw" if " " not in cells else None

    @staticmethod
    @lru_cache(maxsize=None)
    def _minimax(cells: tuple, player: str):
        """يرجع (أفضل نتيجة, أفضل خانة). النتائج محفوظة في ذاكرة مؤقتة لتسريع البحث."""
        w = TicTacToe._winner_of(cells)
        if w == "X":
            return 1, None
        if w == "O":
            return -1, None
        if w == "draw":
            return 0, None
        best = (-2, None) if player == "X" else (2, None)
        for i in range(9):
            if cells[i] == " ":
                nxt = cells[:i] + (player,) + cells[i + 1:]
                score, _ = TicTacToe._minimax(nxt, "O" if player == "X" else "X")
                if (player == "X" and score > best[0]) or (player == "O" and score < best[0]):
                    best = (score, i)
        return best

    def best_move(self) -> int:
        return self._minimax(tuple(self.cells), "X")[1]

    def play_round(self):
        yield {"type": "log", "text": "بدأت مباراة إكس أو ضد خصم"}
        turn = self.rng.choice(["X", "O"])
        while self.winner() is None:
            if turn == "X":
                move = self.best_move()
                self.cells[move] = "X"
                yield {"type": "log", "text": f"الروبوت لعب في الخانة {move + 1}"}
            else:
                move = self.rng.choice([i for i in range(9) if self.cells[i] == " "])
                self.cells[move] = "O"
            turn = "O" if turn == "X" else "X"
        w = self.winner()
        if w == "X":
            yield {"type": "result", "won": True, "points": self.WIN_POINTS, "text": "فاز الروبوت بالمباراة"}
        elif w == "draw":
            yield {"type": "result", "won": False, "points": self.DRAW_POINTS, "text": "انتهت المباراة بالتعادل"}
        else:  # لن يحدث مع Minimax، لكن نتعامل معه للأمان
            yield {"type": "result", "won": False, "points": 0, "text": "خسر الروبوت"}


class Game(Protocol):
    """
    TM354: الواجهة المشتركة لكل الألعاب (نمط الاستراتيجية Strategy). جلسة الروبوت لا تعرف أي لعبة تلعب:
    تستدعي play_round فقط، وتقرأ أحداثاً من نوع move / log / result.
    """
    def play_round(self) -> Iterator[dict]: ...


# نمط المصنع (Factory): إضافة لعبة = صنف جديد + سطر هنا + سطر في GAMES، دون تعديل bot.py
FACTORIES: dict[str, Callable[..., Game]] = {"coins": CoinCollector, "guess": NumberGuess, "xo": TicTacToe}


def new_game(key: str, rng: random.Random | None = None) -> Game:
    try:
        return FACTORIES[key](rng=rng)
    except KeyError:
        raise ValueError(f"لعبة غير معروفة: {key}") from None
