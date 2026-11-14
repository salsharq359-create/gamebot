"""
قاعدة بيانات المستندات (TM351 — Document databases) لجلسات الروبوت.

كل جلسة روبوت مستند واحد فيه مصفوفة الألعاب، وكل لعبة فيها عدد الحركات والنتيجة:
  {"session_id", "user", "started_at", "mode", "seconds", "earned_cents",
   "games": [{"game": "coins", "moves": 24, "logs": 7, "result": "...", "won": true}, ...]}

في القاعدة العلائقية نحتاج جدولين وربطاً (sessions و session_games)، أما هنا فالمستند يُقرأ كاملاً مرة واحدة،
وهذا يناسب «اعرض لي جلسة» أو «حلّل الحركات». يستخدم MongoDB حقيقياً إذا ضُبط MONGO_URL،
وإلا mongomock (محاكي MongoDB في الذاكرة بنفس واجهة pymongo) — نفس الاستعلامات تعمل على الاثنين.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def collection(name: str = "bot_sessions"):
    url = os.environ.get("MONGO_URL")
    if url:
        import pymongo
        return pymongo.MongoClient(url)["gamebot"][name]
    import mongomock
    return mongomock.MongoClient()["gamebot"][name]


def load(coll, path: str | Path) -> int:
    coll.delete_many({})
    with open(path, encoding="utf-8") as f:
        docs = [json.loads(line) for line in f]
    if docs:
        coll.insert_many(docs)
    coll.create_index([("user", 1), ("started_at", 1)])
    coll.create_index("games.game")
    return len(docs)


# ------------------------------------------------------------------ الاستعلامات
def per_game_stats(coll) -> list[dict]:
    """تجميع (aggregation pipeline): فك مصفوفة الألعاب ثم التجميع حسب اللعبة."""
    return list(coll.aggregate([
        {"$unwind": "$games"},
        {"$group": {"_id": "$games.game", "rounds": {"$sum": 1},
                    "avg_moves": {"$avg": "$games.moves"}, "max_moves": {"$max": "$games.moves"},
                    "min_moves": {"$min": "$games.moves"},
                    "wins": {"$sum": {"$cond": [{"$eq": ["$games.won", True]}, 1, 0]}}}},
        {"$sort": {"_id": 1}},
    ]))


def guess_attempts(coll) -> dict[int, int]:
    """توزيع عدد محاولات «تخمين الرقم»: عدد التلميحات + 1 (المحاولة الصحيحة)."""
    rows = coll.aggregate([
        {"$unwind": "$games"},
        {"$match": {"games.game": "guess", "games.result": {"$exists": True}}},
        {"$group": {"_id": {"$add": [{"$ifNull": ["$games.guesses", 0]}, 1]}, "n": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ])
    return {int(r["_id"]): r["n"] for r in rows}


def xo_outcomes(coll) -> dict[str, int]:
    rows = coll.aggregate([
        {"$unwind": "$games"},
        {"$match": {"games.game": "xo", "games.result": {"$exists": True}}},
        {"$group": {"_id": "$games.result", "n": {"$sum": 1}}},
    ])
    return {r["_id"]: r["n"] for r in rows}


def top_sessions(coll, n: int = 5) -> list[dict]:
    """أعلى الجلسات ربحاً، مع إسقاط (projection) الحقول المطلوبة فقط."""
    return list(coll.find({}, {"_id": 0, "user": 1, "started_at": 1, "earned_cents": 1, "seconds": 1})
                .sort("earned_cents", -1).limit(n))


def sessions_with_tournament(coll) -> int:
    """استعلام على حقل داخل مصفوفة مستندات ($elemMatch)."""
    return coll.count_documents({"games": {"$elemMatch": {"tournament": True}}})
