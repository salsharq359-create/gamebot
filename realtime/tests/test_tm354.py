"""TM354: آلة حالات جلسة الروبوت، واختبار انحدار (regression) يثبت أن إعادة الهيكلة لم تغيّر السلوك."""
import hashlib
import itertools
import json
import random
from pathlib import Path

import pytest

from realtime.bot import TERMINAL, TRANSITIONS, BotSession, IllegalTransition, State, run_session

EVENTS = ("start", "stop", "done", "connection_lost", "error", "reset")


def test_every_state_event_pair_is_either_allowed_or_rejected():
    """تغطية كل خلايا جدول الانتقالات: 7 حالات × 6 أحداث = 42 حالة اختبار."""
    allowed = 0
    for state, event in itertools.product(State, EVENTS):
        s = BotSession()
        s.state = state
        if (state, event) in TRANSITIONS:
            assert s.fire(event) is TRANSITIONS[(state, event)]
            allowed += 1
        else:
            with pytest.raises(IllegalTransition):
                s.fire(event)
            assert s.state is state                    # الانتقال المرفوض لا يغيّر شيئاً
    assert allowed == len(TRANSITIONS) == 13


def test_typical_paths():
    paths = {
        ("start", "done"): State.FINISHED,
        ("start", "stop", "stop", "done"): State.STOPPED,
        ("start", "connection_lost"): State.INTERRUPTED,
        ("start", "stop", "error"): State.FAILED,
    }
    for events, final in paths.items():
        s = BotSession()
        for e in events:
            s.fire(e)
        assert s.state is final and not s.active
        s.start()                                      # من أي حالة نهائية تبدأ جلسة جديدة
        assert s.state is State.RUNNING


def test_cannot_start_twice_or_finish_without_starting():
    s = BotSession()
    with pytest.raises(IllegalTransition):
        s.fire("done")
    s.start()
    with pytest.raises(IllegalTransition):
        s.start()


def test_every_non_terminal_state_can_reach_a_terminal_state():
    """لا توجد حالة «عالقة»: من كل حالة غير نهائية يوجد مسار إلى حالة نهائية (بحث بالعرض في الجدول)."""
    for start in set(State) - TERMINAL:
        seen, frontier = {start}, [start]
        while frontier:
            frontier = [n for (s, _), n in TRANSITIONS.items() if s in frontier and n not in seen]
            seen.update(frontier)
        assert seen & TERMINAL, start


def test_stop_during_a_round_gives_no_reward_for_that_round():
    """الأحداث تمر حركةً حركة: الإيقاف في منتصف الجولة يمنع ربحها."""
    s = BotSession()
    s.start()
    events = []
    for ev in run_session(["coins"], 3, {"daily": False}, random.Random(4), stopped=lambda: s.stop_requested):
        events.append(ev)
        if ev["type"] == "move" and sum(e["type"] == "move" for e in events) == 3:
            s.fire("stop")
    assert not [e for e in events if e["type"] == "task"]


def test_refactored_session_matches_golden_output():
    """
    اختبار انحدار: قبل تقسيم run_session (تعقيد 23 → 13) حُفظت بصمة SHA-256 لأحداث 36 جلسة
    (بذور وألعاب وخيارات مختلفة، بعضها يُوقف في المنتصف). النسخة الجديدة يجب أن تعطي نفس البصمات.
    """
    golden = json.loads((Path(__file__).parent / "golden_sessions.json").read_text())
    for key, digest in golden.items():
        seed, games, rounds, tasks = key.split("|")
        seed = int(seed)
        n = {"i": 0}

        def stopped(limit=40 + seed * 7):
            n["i"] += 1
            return seed % 3 == 0 and n["i"] > limit
        ev = list(run_session(games.split(","), int(rounds), json.loads(tasks), random.Random(seed), stopped))
        assert hashlib.sha256(json.dumps(ev, ensure_ascii=False, sort_keys=True).encode()).hexdigest() == digest, key


def test_offline_copy_of_bot_is_identical():
    """إدارة التهيئة: التطبيق يحمل نسخة من bot.py للعب بدون اتصال؛ أي اختلاف = خطأ في إدارة النسخ."""
    root = Path(__file__).resolve().parents[2]
    app = (root / "app/gb/engine/bot.py").read_text()
    assert app.split("\n", 1)[1] == (root / "realtime/realtime/bot.py").read_text()


def test_every_listed_game_has_a_factory_and_honours_the_game_interface():
    from realtime.games import FACTORIES, GAMES, new_game
    assert set(GAMES) == set(FACTORIES)
    for key in GAMES:
        events = list(new_game(key, random.Random(1)).play_round())
        assert events[-1]["type"] == "result" and {"won", "text"} <= set(events[-1])
        assert {e["type"] for e in events} <= {"move", "log", "result"}
    with pytest.raises(ValueError):
        new_game("chess")
