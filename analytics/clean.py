"""
تنظيف بيانات جيم بوت وتجهيزها (TM351 — Data preparation) بمكتبة pandas.

كل دالة تأخذ بيانات «كما هي» وترجع جدولاً مرتباً (tidy): صف لكل ملاحظة، وعمود لكل متغير،
وتوثّق ما غيّرته في قاموس report حتى يظهر في الدفتر والتقرير.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

TZ = "Asia/Kuwait"
KNOWN_TASKS = {"round", "daily", "streak", "tournament"}
OFFLINE_MAX_AGE = pd.Timedelta(days=7)
FUTURE_GRACE = pd.Timedelta(minutes=5)


# ------------------------------------------------------------ تحميل الجداول
def load_tables(folder: str | Path) -> dict[str, pd.DataFrame]:
    folder = Path(folder)
    t = {name: pd.read_csv(folder / f"{name}.csv")
         for name in ("users", "platforms", "tasks", "earnings", "sessions")}
    return t


def tidy_earnings(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """يربط الأرباح بالمنصات والمهام، ويحوّل الأوقات إلى توقيت الكويت ويشتق أعمدة التحليل."""
    e = t["earnings"].copy()
    e["created_at"] = pd.to_datetime(e["created_at"], utc=True, format="ISO8601").dt.tz_convert(TZ)
    p = t["platforms"].rename(columns={"key": "platform_key", "name": "platform_name"})
    k = t["tasks"].rename(columns={"key": "task_key"})[["task_id", "task_key", "kind"]]
    e = e.merge(p[["platform_id", "platform_key", "platform_name", "is_demo"]], on="platform_id", how="left")
    e["task_id"] = pd.to_numeric(e["task_id"], errors="coerce").astype("Int64")
    e = e.merge(k.astype({"task_id": "Int64"}), on="task_id", how="left")
    e["dollars"] = e["cents"] / 100
    e["date"] = e["created_at"].dt.date
    e["hour"] = e["created_at"].dt.hour
    e["weekday"] = e["created_at"].dt.day_name()
    e["channel"] = e["source"].where(e["source"] == "manual", e["offline"].map({0: "online", 1: "offline"}))
    return e


def dedupe_sessions(sessions: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    مشكلة حقيقية وجدها التحليل: عند إعادة إرسال المزامنة يسجل الخادم مدة الجلسة مرتين،
    لأن الجلسات (بعكس الأرباح) لم يكن لها معرّف فريد. المستخدم لا يبدأ جلستين في نفس اللحظة،
    فنعدّ (المستخدم، وقت البداية) مفتاحاً طبيعياً.
    """
    s = sessions.copy()
    s["started_at"] = pd.to_datetime(s["started_at"], utc=True, format="ISO8601").dt.tz_convert(TZ)
    dup = s.duplicated(["user", "started_at"], keep="first")
    return s[~dup].reset_index(drop=True), int(dup.sum())


# ------------------------------------------------------ أسماء المنصات الخاصة
ALIASES = {"pubg": "PUBG Mobile", "pubgmobile": "PUBG Mobile", "ببجي": "PUBG Mobile",
           "freefire": "Free Fire", "fortnite": "Fortnite", "clashofclans": "Clash of Clans",
           "coc": "Clash of Clans", "roblox": "Roblox"}


def normalise_platform_name(name: str) -> str:
    """توحيد الأسماء التي يكتبها المستخدمون بأشكال مختلفة: المسافات، والحروف الكبيرة، والشرطات، والاختصارات."""
    key = re.sub(r"[\s\-_]+", "", str(name).strip().lower())
    return ALIASES.get(key, str(name).strip())


# -------------------------------------------------- طلبات المزامنة الخام
def load_sync_requests(path: str | Path) -> pd.DataFrame:
    """يحوّل ملف JSONL المتداخل إلى جدول مسطح: صف لكل سجل داخل كل طلب."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            req = json.loads(line)
            for r in req["body"]["records"]:
                rows.append({"request": i, "received_at": req["received_at"], "user": req["user"],
                             "app_version": req["app_version"], "client_id": r.get("client_id"),
                             "platform": r.get("platform"), "task": r.get("task"),
                             "played_at_raw": r.get("played_at"), "has_note": "note" in r})
    df = pd.DataFrame(rows)
    df["received_at"] = pd.to_datetime(df["received_at"], utc=True, format="ISO8601")
    df["played_at"] = pd.to_datetime(df["played_at_raw"], utc=True, format="ISO8601", errors="coerce")
    df["ts_format"] = df["played_at_raw"].str.extract(r"(Z|[+-]\d\d:\d\d)$", expand=False).fillna("none")
    return df


def classify_sync(records: pd.DataFrame, earnings: pd.DataFrame) -> pd.DataFrame:
    """
    يعيد اشتقاق قرار الخادم لكل سجل من البيانات وحدها:
      accepted   موجود في جدول الأرباح
      duplicate  قُبل من قبل في طلب سابق ثم أُعيد إرساله
      bad_task   اسم المهمة غير معروف (مثل "Round" من نسخة قديمة)
      future     تاريخ اللعب بعد وقت الاستلام (ساعة الجهاز خاطئة)
      stale      أقدم من 7 أيام
      daily_cap  تجاوز حد المرات اليومي للمهمة (مثل المكافأة اليومية مرة ثانية)
    """
    r = records.copy()
    accepted_ids = set(earnings.loc[earnings["client_id"].notna() & (earnings["client_id"] != ""), "client_id"])
    first_seen = r.groupby("client_id")["request"].transform("min")
    r["reason"] = "daily_cap"
    r.loc[(r["played_at"] - r["received_at"]) > FUTURE_GRACE, "reason"] = "future"
    r.loc[(r["received_at"] - r["played_at"]) > OFFLINE_MAX_AGE, "reason"] = "stale"
    r.loc[~r["task"].isin(KNOWN_TASKS), "reason"] = "bad_task"
    # إعادة الإرسال تُعدّ «مكررة» فقط إذا قُبل السجل في المرة الأولى؛ وإلا يرفضه الخادم بنفس السبب مرة أخرى
    r.loc[(r["request"] > first_seen) & r["client_id"].isin(accepted_ids), "reason"] = "duplicate"
    r.loc[r["client_id"].isin(accepted_ids) & (r["request"] == first_seen), "reason"] = "accepted"
    return r


def check_against_server(classified: pd.DataFrame, path: str | Path) -> pd.DataFrame:
    """يقارن تصنيفنا بما ردّ به الخادم فعلاً لكل طلب (accepted / duplicates / rejected)."""
    server = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            res = json.loads(line)["response"]
            server.append({"request": i, "srv_accepted": res["accepted"], "srv_duplicates": res["duplicates"],
                           "srv_rejected": res["rejected"]})
    s = pd.DataFrame(server).set_index("request")
    c = classified.assign(acc=classified.reason.eq("accepted"), dup=classified.reason.eq("duplicate"),
                          rej=~classified.reason.isin(["accepted", "duplicate"])) \
        .groupby("request")[["acc", "dup", "rej"]].sum()
    both = s.join(c, how="left").fillna(0)
    both["match"] = (both.srv_accepted == both.acc) & (both.srv_duplicates == both.dup) & (both.srv_rejected == both.rej)
    return both
