# نسخة من realtime/realtime/bot.py يستخدمها التطبيق عند اللعب بدون اتصال.
"""
جلسة الروبوت: يلعب الألعاب المرتبطة ويُرجع أحداثاً، منها أحداث «task» = مهمة مكتملة تستحق ربحاً.
المبلغ لا يُحدَّد هنا: خادم Django هو من يحدده من جدول المهام (كل جولة = 1$).

TM354:
  * run_session كانت دالة واحدة بتعقيد دوري 23. قُسّمت إلى دوال صغيرة لكل منها مسؤولية واحدة
    (الجدولة، لعب جولة، مكافأة الانتصارات المتتالية)، والسلوك نفسه تحفظه الاختبارات.
  * حالة الجلسة كانت قاموساً {"stop": bool} في الخادم، وثلاثة متغيرات منطقية في التطبيق
    (bot_running و local_running و local_stop = 8 تركيبات، معظمها لا معنى له). صارت آلة حالات صريحة
    BotSession بجدول انتقالات: أي انتقال غير موجود في الجدول خطأ برمجي يُكتشف فوراً.
"""
from __future__ import annotations

import random
from enum import Enum
from typing import Callable, Generator, Iterator

from .games import GAMES, new_game


# ------------------------------------------------------------ آلة الحالات
class State(str, Enum):
    IDLE = "idle"                    # لا توجد جلسة
    RUNNING = "running"              # الروبوت يلعب
    STOPPING = "stopping"            # طُلب الإيقاف، ينتظر انتهاء الحركة الحالية
    FINISHED = "finished"            # أنهى كل الجدول
    STOPPED = "stopped"              # أوقفه المستخدم
    INTERRUPTED = "interrupted"      # انقطع الاتصال: الخادم يوقف الروبوت، والتطبيق لن يصله «انتهت الجلسة»
    FAILED = "failed"                # خطأ غير متوقع


TERMINAL = {State.FINISHED, State.STOPPED, State.INTERRUPTED, State.FAILED}

# (الحالة، الحدث) -> الحالة التالية. هذا الجدول هو رسم آلة الحالات في التقرير حرفياً.
TRANSITIONS: dict[tuple[State, str], State] = {
    (State.IDLE, "start"): State.RUNNING,
    (State.RUNNING, "stop"): State.STOPPING,
    (State.STOPPING, "stop"): State.STOPPING,           # الضغط مرتين على «إيقاف» لا يضر
    (State.RUNNING, "done"): State.FINISHED,
    (State.STOPPING, "done"): State.STOPPED,
    (State.RUNNING, "connection_lost"): State.INTERRUPTED,
    (State.STOPPING, "connection_lost"): State.INTERRUPTED,
    (State.RUNNING, "error"): State.FAILED,
    (State.STOPPING, "error"): State.FAILED,
    **{(s, "reset"): State.IDLE for s in TERMINAL},
}


class IllegalTransition(RuntimeError):
    pass


class BotSession:
    """حالة جلسة روبوت واحدة. local = تعمل على الجهاز بدون اتصال (التطبيق فقط)."""

    def __init__(self) -> None:
        self.state = State.IDLE
        self.local = False
        self.history: list[tuple[State, str, State]] = []

    def fire(self, event: str) -> State:
        nxt = TRANSITIONS.get((self.state, event))
        if nxt is None:
            raise IllegalTransition(f"لا يمكن «{event}» في الحالة {self.state.value}")
        self.history.append((self.state, event, nxt))
        self.state = nxt
        return nxt

    def can(self, event: str) -> bool:
        return (self.state, event) in TRANSITIONS

    def start(self, local: bool = False) -> None:
        if self.state in TERMINAL:
            self.fire("reset")
        self.fire("start")
        self.local = local

    @property
    def active(self) -> bool:        # يعمل أو يتوقف: الواجهة تعرض «الروبوت يعمل» وتمنع جلسة ثانية
        return self.state in (State.RUNNING, State.STOPPING)

    @property
    def stop_requested(self) -> bool:
        return self.state is not State.RUNNING


# ---------------------------------------------------------------- الجلسة
def _board_rows(board: list[list[str]]) -> list[str]:
    return ["".join(row) for row in board]


def _schedule(games: list[str], rounds: int, tasks: dict) -> list[tuple[str, bool]]:
    """(اللعبة، هل هي بطولة) بالترتيب: كل الجولات العادية ثم بطولة لكل لعبة إذا طُلبت."""
    schedule = [(g, False) for g in games for _ in range(rounds)]
    if tasks.get("tournament"):
        schedule += [(g, True) for g in games]
    return schedule


def _play_round(g: str, rng: random.Random, stopped: Callable[[], bool]) -> Generator[dict, None, dict | None]:
    """
    يلعب جولة واحدة ويمرر أحداثها حركةً حركة (حتى يعمل «إيقاف» أثناء الجولة).
    قيمة الإرجاع (عبر yield from) هي حدث النتيجة، أو None إذا أُوقف قبل نهاية الجولة.
    """
    for ev in new_game(g, rng).play_round():
        if stopped():
            return None
        if ev["type"] == "result":
            return ev
        if ev["type"] == "move":
            yield {"type": "move", "platform": g, "board": _board_rows(ev["board"])}
        else:
            yield {**ev, "platform": g}
    return None


def _streak_bonus(g: str, won: bool, streak: dict[str, int]) -> dict | None:
    """تحدٍّ: 3 انتصارات متتالية في نفس اللعبة. «تخمين الرقم» مستثناة لأن الروبوت يفوز فيها دائماً."""
    if g == "guess":
        return None
    streak[g] = streak.get(g, 0) + 1 if won else 0
    if streak[g] < 3:
        return None
    streak[g] = 0
    return {"type": "task", "platform": g, "task": "streak", "note": f"{GAMES[g].name}: 3 انتصارات متتالية"}


def run_session(games: list[str], rounds: int = 3, tasks: dict | None = None,
                rng: random.Random | None = None, stopped: Callable[[], bool] = lambda: False) -> Iterator[dict]:
    tasks = tasks or {}
    rng = rng or random.Random()
    if not games:
        yield {"type": "log", "text": "لا توجد ألعاب مرتبطة. اربط لعبة أولاً."}
        return
    if tasks.get("daily", True):
        yield from ({"type": "task", "platform": g, "task": "daily", "note": f"المكافأة اليومية: {GAMES[g].name}"}
                    for g in games)
    schedule = _schedule(games, rounds, tasks)
    streak: dict[str, int] = {}
    for done, (g, tournament) in enumerate(schedule, 1):
        if stopped():
            yield {"type": "log", "text": "تم إيقاف الروبوت"}
            return
        name = GAMES[g].name
        yield {"type": "game", "platform": g, "text": f"{'بطولة: ' if tournament else ''}يلعب الآن: {name}"}
        result = yield from _play_round(g, rng, stopped)
        if result is None:
            continue
        yield {"type": "task", "platform": g, "task": "tournament" if tournament else "round",
               "note": f"{name}: {result['text']}", "won": result["won"]}
        bonus = _streak_bonus(g, result["won"], streak) if tasks.get("challenges", True) else None
        if bonus:
            yield bonus
        yield {"type": "progress", "value": done / len(schedule)}
