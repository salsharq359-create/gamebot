"""
مستشار الروبوت (فكرة Copilot): يحلل المهام المتاحة ويقترح أفضل خطة لعب.

المشكلة: لدى المستخدم وقت محدود اليوم (أقل قيمة بين ما يطلبه وبين ما تبقى من حدّه اليومي).
كل مهمة لها مكافأة ومدة وعدد مرات أقصى في اليوم. المطلوب اختيار مجموعة مهام
تعطي أكبر ربح ممكن دون تجاوز الوقت.

هذه مسألة حقيبة الظهر 0/1 (0/1 Knapsack)، ونحلّها بالبرمجة الديناميكية:
  dp[t] = أكبر ربح ممكن في t دقيقة
  الزمن O(n × T) حيث n = عدد نسخ المهام، T = الدقائق المتاحة.
ثم نرتّب الخطة: المهام الأعلى ربحاً لكل دقيقة أولاً.
"""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import ensures, requires


@dataclass(frozen=True)
class TaskOption:
    task_id: int
    platform: str
    title: str
    reward_cents: int
    minutes: int
    remaining_today: int   # كم مرة يمكن تنفيذها بعد اليوم


def _plan_is_consistent(result, options, minutes_budget) -> bool:
    """الشرط اللاحق: الخطة تحقق المبلغ المعلن بالضبط، ولا تتجاوز الوقت، ولا حد المرات لكل مهمة."""
    total, plan = result
    allowed = {o.task_id: o.remaining_today for o in options}
    return (sum(p["total_cents"] for p in plan) == total
            and sum(p["total_minutes"] for p in plan) <= minutes_budget
            and all(0 < p["times"] <= allowed.get(p["task_id"], 0) for p in plan))


@requires(lambda options, minutes_budget: isinstance(minutes_budget, int) and minutes_budget >= 0,
          "الدقائق المتاحة عدد صحيح غير سالب")
@ensures(_plan_is_consistent, "مجموع الخطة = الربح المعلن، ضمن الوقت وحدود المرات")
def best_plan(options: list[TaskOption], minutes_budget: int) -> tuple[int, list[dict]]:
    """
    يرجع (أعلى ربح بالسنت، الخطة المرتبة).
    العقد (TM354): شرط مسبق: minutes_budget ≥ 0.  شرط لاحق: _plan_is_consistent.
    """
    items: list[TaskOption] = []
    for o in options:
        if o.minutes <= 0 or o.reward_cents <= 0:
            continue
        items.extend([o] * max(0, min(o.remaining_today, minutes_budget // o.minutes)))

    budget = max(0, int(minutes_budget))
    dp = [0] * (budget + 1)
    take = [[False] * (budget + 1) for _ in items]
    for i, it in enumerate(items):
        for t in range(budget, it.minutes - 1, -1):
            cand = dp[t - it.minutes] + it.reward_cents
            if cand > dp[t]:
                dp[t] = cand
                take[i][t] = True

    chosen: list[TaskOption] = []
    t = budget
    for i in range(len(items) - 1, -1, -1):
        if take[i][t]:
            chosen.append(items[i])
            t -= items[i].minutes

    grouped: dict[int, dict] = {}
    for c in chosen:
        g = grouped.setdefault(c.task_id, {
            "task_id": c.task_id, "platform": c.platform, "title": c.title, "times": 0,
            "reward_cents": c.reward_cents, "minutes": c.minutes,
            "cents_per_minute": round(c.reward_cents / c.minutes, 1)})
        g["times"] += 1
    plan = sorted(grouped.values(), key=lambda g: (-g["cents_per_minute"], -g["reward_cents"]))
    for step in plan:
        step["total_cents"] = step["times"] * step["reward_cents"]
        step["total_minutes"] = step["times"] * step["minutes"]
        step["reason"] = f"ربح {step['cents_per_minute'] / 100:.2f}$ لكل دقيقة"
    return dp[budget], plan
