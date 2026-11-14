import random

from realtime.bot import run_session
from realtime.games import CoinCollector, NumberGuess, TicTacToe


def last(game):
    return list(game.play_round())[-1]


def test_bfs_collects_all_coins():
    for seed in range(30):
        g = CoinCollector(rng=random.Random(seed))
        assert last(g)["type"] == "result" and not g.coins


def test_binary_search_within_10():
    assert all(last(NumberGuess(rng=random.Random(s)))["won"] for s in range(300))


def test_minimax_never_loses():
    for s in range(300):
        g = TicTacToe(rng=random.Random(s))
        last(g)
        assert g.winner() in ("X", "draw")


def test_session_tasks_and_board_rows():
    events = list(run_session(["coins", "guess"], 2, {"tournament": True}, random.Random(7)))
    tasks = [e for e in events if e["type"] == "task"]
    assert sum(t["task"] == "round" for t in tasks) == 4
    assert sum(t["task"] == "daily" for t in tasks) == 2
    assert sum(t["task"] == "tournament" for t in tasks) == 2
    moves = [e for e in events if e["type"] == "move"]
    assert moves and all(isinstance(r, str) and len(r) == 8 for r in moves[0]["board"])
    assert [e for e in events if e["type"] == "progress"][-1]["value"] == 1


def test_stop_flag():
    n = {"i": 0}

    def stopped():
        n["i"] += 1
        return n["i"] > 15

    events = list(run_session(["guess"], 10, {}, random.Random(1), stopped))
    assert any(e.get("text") == "تم إيقاف الروبوت" for e in events)


def test_coin_robot_takes_the_optimal_route():
    """M269: الروبوت يجمع العملات بأقل عدد خطوات ممكن (نقارنه ببحث شامل على كل الترتيبات)."""
    import itertools
    rng = random.Random(269)
    for _ in range(200):
        g = CoinCollector(rng=rng)
        pts = [g.bot] + sorted(g.coins)
        d = [[g._distances(p)[q] for q in pts] for p in pts]
        best = min(sum(d[a][b] for a, b in zip((0,) + perm, perm))
                   for perm in itertools.permutations(range(1, len(pts))))
        events = list(g.play_round())
        assert sum(e["type"] == "move" for e in events) == best
        assert not g.coins and events[-1]["type"] == "result"
