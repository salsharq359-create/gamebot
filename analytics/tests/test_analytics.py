"""اختبارات خط بيانات TM351 (بدون قاعدة بيانات): التنظيف، والتحليل، والاستعلامات المستندية."""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics import analysis, clean, mongo, sqlrun  # noqa: E402


def test_platform_names_are_normalised():
    variants = ["PUBG Mobile", "pubg mobile ", "PUBG", "Pubg-Mobile", "ببجي", "COC", "clash of clans", "Roblox "]
    out = {clean.normalise_platform_name(v) for v in variants}
    assert out == {"PUBG Mobile", "Clash of Clans", "Roblox"}


def test_session_duplicates_removed():
    s = pd.DataFrame({"user": ["a", "a", "a", "b"], "seconds": [30, 30, 40, 30],
                      "started_at": ["2026-10-01T10:00:00+03:00", "2026-10-01T07:00:00Z",   # نفس اللحظة بصيغتين
                                     "2026-10-01T11:00:00+03:00", "2026-10-01T10:00:00+03:00"]})
    tidy, dups = clean.dedupe_sessions(s)
    assert dups == 1 and len(tidy) == 3


def _sync_file(tmp_path, requests):
    p = tmp_path / "sync.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in requests))
    return p


def test_classification_matches_server_rules(tmp_path):
    rec = lambda cid, task="round", played="2026-10-01T10:00:00Z": {"client_id": cid, "platform": "coins",
                                                                      "task": task, "played_at": played}
    reqs = [
        {"received_at": "2026-10-01T12:00:00Z", "user": "u1", "app_version": "2.1",
         "body": {"records": [rec("ok"), rec("cap", "daily"), rec("old", "Round"),
                              rec("fut", played="2026-10-03T10:00:00Z"), rec("st", played="2026-09-20T10:00:00Z")]},
         "response": {"accepted": 1, "duplicates": 0, "rejected": 4}},
        {"received_at": "2026-10-01T12:00:20Z", "user": "u1", "app_version": "2.1",       # إعادة إرسال
         "body": {"records": [rec("ok"), rec("cap", "daily")]},
         "response": {"accepted": 0, "duplicates": 1, "rejected": 1}},
    ]
    path = _sync_file(tmp_path, reqs)
    earnings = pd.DataFrame({"client_id": ["ok", ""]})
    c = clean.classify_sync(clean.load_sync_requests(path), earnings)
    assert c.set_index(["request", "client_id"])["reason"].to_dict() == {
        (0, "ok"): "accepted", (0, "cap"): "daily_cap", (0, "old"): "bad_task", (0, "fut"): "future",
        (0, "st"): "stale", (1, "ok"): "duplicate", (1, "cap"): "daily_cap"}
    assert clean.check_against_server(c, path)["match"].all()


def test_binary_search_theory():
    th = analysis.binary_search_theory()
    counts = {k: round(v * 1000) for k, v in th.items()}
    assert counts == {1: 1, 2: 2, 3: 4, 4: 8, 5: 16, 6: 32, 7: 64, 8: 128, 9: 256, 10: 489}


def test_k_anonymity_and_generalisation():
    users = pd.DataFrame({"user": list("abcd"), "joined_date": ["2026-09-07", "2026-09-08", "2026-09-08", "2026-09-09"],
                          "daily_limit_min": [60, 60, 60, 60], "dark_mode": [0, 1, 0, 1], "text_scale": [1.0] * 4,
                          "leaderboard": [0] * 4, "demo_games_linked": [2] * 4})
    before = analysis.k_anonymity(users, ["joined_date", "daily_limit_min", "dark_mode"])
    after = analysis.k_anonymity(analysis.generalise_users(users), ["joined_week", "daily_limit_min"])
    assert before["k"] == 1 and after["k"] == 4


def test_mongo_pipelines():
    c = mongo.collection("test_sessions")
    c.delete_many({})
    c.insert_many([
        {"user": "u1", "earned_cents": 300, "seconds": 20, "started_at": "t1",
         "games": [{"game": "coins", "moves": 10, "won": True, "result": "r", "tournament": False},
                   {"game": "guess", "moves": 0, "guesses": 9, "won": True, "result": "r", "tournament": True}]},
        {"user": "u2", "earned_cents": 100, "seconds": 10, "started_at": "t2",
         "games": [{"game": "coins", "moves": 20, "won": True, "result": "r", "tournament": False},
                   {"game": "xo", "moves": 0, "won": False, "result": "تعادل", "tournament": False}]},
    ])
    stats = {r["_id"]: r for r in mongo.per_game_stats(c)}
    assert stats["coins"]["avg_moves"] == 15 and stats["coins"]["rounds"] == 2
    assert mongo.guess_attempts(c) == {10: 1}
    assert mongo.xo_outcomes(c) == {"تعادل": 1}
    assert mongo.top_sessions(c, 1)[0]["user"] == "u1"
    assert mongo.sessions_with_tournament(c) == 1


def test_sql_file_parses():
    q = sqlrun.load_queries()
    assert list(q)[:2] == ["q1_daily_earnings_by_game", "q2_top_earners_window"]
    assert all(sql.lstrip().upper().startswith(("SELECT", "--")) for sql in q.values())
