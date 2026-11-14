"""
تحليل بيانات جيم بوت (TM351 — Data analysis) بمكتبة pandas.
كل دالة ترجع جدولاً صغيراً جاهزاً للعرض في الدفتر أو التقرير.
"""
from __future__ import annotations

import math

import pandas as pd

DAYS = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def headline(e: pd.DataFrame, users: pd.DataFrame, sessions: pd.DataFrame) -> dict:
    return {"users": len(users), "earning_records": len(e), "dollars": round(e["dollars"].sum(), 2),
            "sessions": len(sessions), "days": e["date"].nunique(),
            "dollars_per_user_day": round(e.groupby(["user", "date"])["dollars"].sum().mean(), 2)}


def earnings_by_game_task(e: pd.DataFrame) -> pd.DataFrame:
    demo = e[e["is_demo"] == 1]
    t = demo.pivot_table(index="platform_key", columns="task_key", values="dollars", aggfunc="sum", fill_value=0)
    t["total"] = t.sum(axis=1)
    return t.sort_values("total", ascending=False).round(2)


def channel_share(e: pd.DataFrame) -> pd.DataFrame:
    g = e.groupby("channel").agg(records=("cents", "size"), dollars=("dollars", "sum"))
    g["pct_dollars"] = (100 * g["dollars"] / g["dollars"].sum()).round(1)
    return g.sort_values("dollars", ascending=False).round(2)


def hour_weekday(sessions: pd.DataFrame) -> pd.DataFrame:
    s = sessions.assign(hour=sessions["started_at"].dt.hour, weekday=sessions["started_at"].dt.day_name())
    t = s.pivot_table(index="weekday", columns="hour", values="seconds", aggfunc="size", fill_value=0)
    return t.reindex(DAYS)


def minutes_per_day(sessions: pd.DataFrame, users: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    s = sessions.assign(date=sessions["started_at"].dt.date)
    d = s.groupby(["user", "date"])["seconds"].sum().div(60).rename("minutes").reset_index()
    d = d.merge(users[["user", "daily_limit_min"]], on="user", how="left")
    d["over_limit"] = (d["daily_limit_min"] > 0) & (d["minutes"] >= d["daily_limit_min"])
    summary = {"user_days": len(d), "mean_min": round(d["minutes"].mean(), 2),
               "p95_min": round(d["minutes"].quantile(0.95), 2), "max_min": round(d["minutes"].max(), 2),
               "over_limit_pct": round(100 * d["over_limit"].mean(), 2),
               "session_mean_s": round(sessions["seconds"].mean(), 1), "session_max_s": int(sessions["seconds"].max())}
    return d, summary


def binary_search_theory(n: int = 1000, max_tries: int = 10) -> dict[int, float]:
    """كم رقماً من 1..n يجده البحث الثنائي في k محاولة بالضبط (يحسب بالمحاكاة الدقيقة لكل الأرقام)."""
    counts: dict[int, int] = {}
    for secret in range(1, n + 1):
        lo, hi = 1, n
        for k in range(1, max_tries + 1):
            g = (lo + hi) // 2
            if g == secret:
                counts[k] = counts.get(k, 0) + 1
                break
            lo, hi = (g + 1, hi) if g < secret else (lo, g - 1)
    return {k: counts[k] / n for k in sorted(counts)}


def compare_guess(observed: dict[int, int]) -> pd.DataFrame:
    theory = binary_search_theory()
    total = sum(observed.values())
    df = pd.DataFrame({"attempts": list(theory), "theory_pct": [100 * v for v in theory.values()],
                       "observed": [observed.get(k, 0) for k in theory]})
    df["observed_pct"] = 100 * df["observed"] / total
    df["expected"] = df["theory_pct"] / 100 * total
    chi2 = float(((df["observed"] - df["expected"]) ** 2 / df["expected"]).sum())
    df.attrs["chi2"], df.attrs["dof"], df.attrs["n"] = round(chi2, 2), len(df) - 1, total
    return df.round(2)


def sync_quality(classified: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    reasons = classified["reason"].value_counts().rename("records").to_frame()
    reasons["pct"] = (100 * reasons["records"] / reasons["records"].sum()).round(1)
    by_version = pd.crosstab(classified["app_version"], classified["reason"], normalize="index").mul(100).round(1)
    return reasons, by_version


def platform_names(platforms: pd.DataFrame, normalise) -> pd.DataFrame:
    c = platforms[platforms["is_demo"] == 0].copy()
    c["canonical"] = c["name"].map(normalise)
    t = c.groupby("canonical").agg(platforms=("name", "size"), spellings=("name", "nunique"),
                                   examples=("name", lambda s: " | ".join(sorted(set(s))[:4])))
    return t.sort_values("platforms", ascending=False)


def k_anonymity(users: pd.DataFrame, quasi: list[str]) -> dict:
    """أصغر مجموعة تشترك في نفس قيم المعرّفات شبه الشخصية، ونسبة المستخدمين المتفردين (k = 1)."""
    sizes = users.groupby(quasi, dropna=False)["user"].transform("size")
    return {"quasi": quasi, "k": int(sizes.min()), "unique_pct": round(100 * (sizes == 1).mean(), 1),
            "groups": int(users.groupby(quasi, dropna=False).ngroups)}


def generalise_users(users: pd.DataFrame) -> pd.DataFrame:
    """تعميم المعرّفات شبه الشخصية: أسبوع التسجيل بدل اليوم، وحذف إعدادات المظهر."""
    u = users.copy()
    u["joined_week"] = pd.to_datetime(u["joined_date"]).dt.to_period("W").astype(str)
    return u.drop(columns=["joined_date", "dark_mode", "text_scale"])
