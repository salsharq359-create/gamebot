"""
محاكي لاعبين لمقرر TM351: ينتج بيانات كافية للتحليل، بنفس قواعد الخادم الحقيقية.

ما هو حقيقي هنا:
  - الروبوت يلعب فعلاً بمحرك الألعاب نفسه (BFS، البحث الثنائي، Minimax)، فنتائج الألعاب حقيقية.
  - المكافآت والحدود اليومية تأتي من جدول المهام في قاعدة البيانات.
  - الجلسات بدون اتصال تُرسل عبر مسار المزامنة الحقيقي /api/bot/offline-sync/ (مع التوقيع)،
    فالخادم نفسه هو من يقبل السجلات أو يرفضها.
  - مدة الجلسة محسوبة من نفس التأخيرات التي يستخدمها خادم الروبوت (120 ms للحركة، 350 ms للحدث).

ما هو افتراض (سلوك المستخدمين):
  - ثلاث شخصيات (طالب، موظف، متقاعد) لكل منها ساعات لعب واحتمال نشاط يومي.
  - نسبة الجلسات بدون اتصال، وأخطاء أجهزة المستخدمين (ساعة خاطئة، إعادة إرسال، نسخة قديمة).

المخرجات:
  - قاعدة البيانات (المستخدمون، الأرباح، الجلسات، المنصات الخاصة ...)
  - data/raw/sync_requests.jsonl  : كل طلب مزامنة كما وصل للخادم (البيانات الخام «المتسخة»)
  - data/raw/bot_sessions.jsonl   : مستند لكل جلسة روبوت متصلة (للقاعدة المستندية MongoDB)

التشغيل:  python manage.py simulate_players --users 300 --days 30 --seed 351
"""
from __future__ import annotations

import hashlib
import hmac
import json
import random
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.test import Client
from django.test.utils import override_settings

from core.auth import make_token, sync_key
from core.models import (EarningRecord, GamePlatform, GameTask, PlaySession, Profile, UserGameAccount)

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "realtime"))
from realtime.bot import run_session  # noqa: E402

KW = ZoneInfo("Asia/Kuwait")
MOVE_S, EVENT_S = 0.12, 0.35

# ------------------------------------------------------------------ الافتراضات
PERSONAS = {
    #            نسبة   نشاط يومي  ساعات اللعب (توزيع)                  جلسات/يوم  حد يومي محتمل
    "student":  (0.5, 0.65, [(16, 23, 0.8), (12, 15, 0.2)],             (1, 4), [60, 90, 120, 0]),
    "employee": (0.35, 0.5, [(6, 8, 0.4), (17, 22, 0.6)],               (1, 2), [30, 60]),
    "retiree":  (0.15, 0.45, [(9, 13, 0.7), (15, 19, 0.3)],             (1, 2), [30, 60, 90]),
}
OFFLINE_SHARE = {"student": 0.15, "employee": 0.3, "retiree": 0.1}   # الموظف يلعب في المواصلات
EXTERNAL = [  # منصات يضيفها المستخدمون بأنفسهم، بأسماء غير موحدة (مصدر حقيقي للبيانات المتسخة)
    ["PUBG Mobile", "pubg mobile ", "PUBG", "Pubg-Mobile", "ببجي"],
    ["Free Fire", "freefire", "FREE FIRE", "Free-Fire"],
    ["Fortnite", "fortnite ", "FORTNITE"],
    ["Clash of Clans", "clash of clans", "COC", "Clash Of Clans"],
    ["Roblox", "roblox", "ROBLOX "],
]


class Command(BaseCommand):
    help = "يولّد لاعبين وجلسات بقواعد جيم بوت الحقيقية (بيانات لمقرر TM351)"

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=300)
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--seed", type=int, default=351)
        parser.add_argument("--end", default="2026-10-05", help="آخر يوم في المحاكاة (بتوقيت الكويت)")
        parser.add_argument("--out", default=str(ROOT / "data" / "raw"))

    def handle(self, *args, **o):
        rng = random.Random(o["seed"])
        self.out = Path(o["out"])
        self.out.mkdir(parents=True, exist_ok=True)
        end = datetime.combine(datetime.fromisoformat(o["end"]).date() + timedelta(days=1), time(0, 30), KW)
        start_day = datetime.fromisoformat(o["end"]).date() - timedelta(days=o["days"] - 1)
        self.tasks = {(t.platform.key, t.key): t for t in GameTask.objects.filter(platform__is_demo=True,
                                                                                    platform__owner__isnull=True)
                      .select_related("platform")}
        self.demo = {p.key: p for p in GamePlatform.objects.filter(is_demo=True, owner__isnull=True)}
        self.client = Client()
        self.sync_log = open(self.out / "sync_requests.jsonl", "w", encoding="utf-8")
        self.docs = open(self.out / "bot_sessions.jsonl", "w", encoding="utf-8")
        self.stats = Counter()
        users = self._make_users(o["users"], start_day, rng)
        for day_i in range(o["days"]):
            day = start_day + timedelta(days=day_i)
            with transaction.atomic():
                for u in users:
                    if day >= u["joined"].date():
                        self._play_day(u, day, rng)
                # في نهاية اليوم: من لديه طابور ورجع له الاتصال يزامن
                for u in users:
                    if u["queue"] and rng.random() < 0.85:
                        self._sync(u, datetime.combine(day + timedelta(days=1), time(0, 10), KW), rng)
            self.stderr.write(f"day {day_i + 1}/{o['days']}")
        for u in users:      # آخر مزامنة قبل نهاية الفترة
            if u["queue"]:
                self._sync(u, end, rng)
        self.sync_log.close()
        self.docs.close()
        self.stdout.write(json.dumps(dict(self.stats), ensure_ascii=False))

    # ------------------------------------------------------------ المستخدمون
    def _make_users(self, n, start_day, rng):
        User = get_user_model()
        names = list(PERSONAS)
        weights = [PERSONAS[k][0] for k in names]
        users = []
        with transaction.atomic():
            for i in range(n):
                persona = rng.choices(names, weights)[0]
                joined = datetime.combine(start_day + timedelta(days=rng.randrange(0, 10)),
                                          time(rng.randrange(8, 23), rng.randrange(60)), KW)
                user = User.objects.create(username=f"sim{i:04d}", date_joined=joined)
                user.set_unusable_password()
                user.save(update_fields=["password"])
                limit = rng.choice(PERSONAS[persona][4])
                Profile.objects.create(user=user, daily_limit_min=limit, leaderboard=rng.random() < 0.25,
                                       dark=rng.random() < 0.4, text_scale=1.3 if persona == "retiree" else 1.0)
                games = ["coins", "guess"] + (["xo"] if rng.random() < 0.45 else [])
                for key, p in self.demo.items():
                    UserGameAccount.objects.create(user=user, platform=p, linked=key in games)
                old_app = rng.random() < 0.04          # نسخة قديمة ترسل أسماء المهام بحرف كبير
                u = {"user": user, "persona": persona, "games": games, "joined": joined, "limit": limit,
                     "queue": [], "old_app": old_app, "complies": rng.random() < 0.8,
                     "token": make_token(user), "key": sync_key(user), "custom": [], "counts": Counter()}
                if rng.random() < 0.3:
                    for group in rng.sample(EXTERNAL, rng.randint(1, 2)):
                        name = rng.choice(group)
                        slug = f"ext-{uuid.UUID(int=rng.getrandbits(128)).hex[:8]}"
                        p = GamePlatform.objects.create(key=slug, name=name, owner=user)
                        UserGameAccount.objects.create(user=user, platform=p, linked=True)
                        u["custom"].append(p)
                users.append(u)
        self.stats["users"] = n
        return users

    # ------------------------------------------------------------- يوم لعب
    def _play_day(self, u, day, rng):
        _, active, hours, (smin, smax), _ = PERSONAS[u["persona"]]
        if rng.random() > active:
            return
        played_min = 0.0
        for _ in range(rng.randint(smin, smax)):
            if u["limit"] and played_min >= u["limit"] and u["complies"]:
                self.stats["skipped_limit"] += 1
                break
            lo, hi, _w = rng.choices(hours, [h[2] for h in hours])[0]
            at = datetime.combine(day, time(rng.randint(lo, hi), rng.randrange(60), rng.randrange(60)), KW)
            if at <= u["joined"]:
                continue
            offline = rng.random() < OFFLINE_SHARE[u["persona"]]
            played_min += self._session(u, at, offline, rng) / 60
        for p in u["custom"]:                              # أرباح يدوية من المنصات الخاصة
            if rng.random() < 0.15:
                cents = rng.choice([50, 100, 150, 200, 300, 500, 1000])
                EarningRecord.objects.create(user=u["user"], platform=p, cents=cents, source="manual",
                                             note="يدوي", client_id=f"man-{uuid.UUID(int=rng.getrandbits(128))}",
                                             created_at=datetime.combine(day, time(rng.randint(8, 23), 0), KW))
                self.stats["manual"] += 1

    def _session(self, u, at, offline, rng) -> float:
        rounds = rng.randint(1, 5)
        tasks = {"daily": True, "challenges": True, "tournament": rng.random() < 0.3}
        seconds = 0.0
        doc = {"session_id": str(uuid.UUID(int=rng.getrandbits(128))), "user_id": u["user"].pk,
               "started_at": at.isoformat(), "mode": "offline" if offline else "online", "rounds_setting": rounds,
               "games": []}
        cur = None
        n = 0
        day0 = at.replace(hour=0, minute=0, second=0, microsecond=0)
        for ev in run_session(u["games"], rounds, tasks, rng):
            t = ev["type"]
            if t == "move":
                seconds += MOVE_S
                if cur is not None:
                    cur["moves"] += 1
                continue
            seconds += EVENT_S if t != "progress" else 0
            if t == "game":
                cur = {"game": ev["platform"], "tournament": ev["text"].startswith("بطولة"), "moves": 0, "logs": 0}
                doc["games"].append(cur)
            elif t == "log" and cur is not None:
                cur["logs"] += 1
                if ev["text"].startswith("تخمين"):
                    cur["guesses"] = cur.get("guesses", 0) + 1
            elif t == "task":
                n += 1
                played = at + timedelta(seconds=seconds)
                if ev["task"] in ("round", "tournament") and cur is not None:
                    cur["result"] = ev["note"].split(": ", 1)[-1]
                    cur["won"] = bool(ev.get("won"))
                if offline:
                    u["queue"].append({"platform": ev["platform"], "task": ev["task"], "note": ev["note"],
                                       "played_at": played})
                else:
                    cents = self._accept_online(u, ev, played, day0, f"{doc['session_id']}-{n}")
                    doc.setdefault("earned_cents", 0)
                    doc["earned_cents"] += cents
        if offline:
            u.setdefault("sessions", []).append({"started_at": at, "seconds": round(seconds)})
        else:
            PlaySession.objects.create(user=u["user"], started_at=at, seconds=round(seconds))
        doc["seconds"] = round(seconds)
        if not offline:
            self.docs.write(json.dumps(doc, ensure_ascii=False) + "\n")
        self.stats["sessions_" + doc["mode"]] += 1
        return seconds

    def _accept_online(self, u, ev, played, day0, cid) -> int:
        """نفس ما يفعله /api/internal/earnings/: المبلغ من الجدول، والحد اليومي لكل مهمة."""
        task = self.tasks.get((ev["platform"], ev["task"]))
        if not task:
            return 0
        key = (task.pk, day0.date())
        if u["counts"][key] >= task.max_per_day:
            self.stats["online_daily_limit"] += 1
            return 0
        u["counts"][key] += 1
        EarningRecord.objects.create(user=u["user"], platform=task.platform, task=task, cents=task.reward_cents,
                                     note=ev["note"], source="bot", client_id=cid, created_at=played)
        self.stats["online_accepted"] += 1
        return task.reward_cents

    # -------------------------------------------------------- المزامنة الحقيقية
    def _sync(self, u, when, rng):
        records = []
        skew = timedelta(days=2) if rng.random() < 0.02 else timedelta(0)        # ساعة الجهاز خاطئة
        stale = timedelta(days=9) if rng.random() < 0.01 else timedelta(0)      # طابور قديم جداً
        for q in u["queue"]:
            played = q["played_at"] + skew - stale
            fmt = rng.random()
            if fmt < 0.6:
                stamp = played.astimezone(ZoneInfo("UTC")).isoformat()
            elif fmt < 0.9:
                stamp = played.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")
            else:
                stamp = played.isoformat()                                       # توقيت الكويت +03:00
            task = q["task"].capitalize() if u["old_app"] else q["task"]
            rec = {"client_id": f"off-{uuid.UUID(int=rng.getrandbits(128))}", "platform": q["platform"],
                   "task": task, "played_at": stamp}
            if rng.random() > 0.05:
                rec["note"] = q["note"]
            rec["mac"] = _sign(u["key"], rec)
            records.append(rec)
        sessions = [{"started_at": s["started_at"].isoformat(), "seconds": s["seconds"]}
                    for s in u.get("sessions", [])]
        body = {"records": records, "sessions": sessions}
        sends = 2 if rng.random() < 0.06 else 1                                  # إعادة إرسال (انقطاع في المنتصف)
        for k in range(sends):
            with override_settings(ALLOWED_HOSTS=["testserver"]):
                with _frozen(when + timedelta(seconds=k * 20)):
                    r = self.client.post("/api/bot/offline-sync/", data=json.dumps(body, ensure_ascii=False),
                                         content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {u['token']}")
            res = r.json()
            self.sync_log.write(json.dumps({"received_at": (when + timedelta(seconds=k * 20)).isoformat(),
                                            "user_id": u["user"].pk, "app_version": "1.0" if u["old_app"] else "2.1",
                                            "status": r.status_code, "body": body,
                                            "response": {k2: res.get(k2) for k2 in
                                                         ("accepted", "duplicates", "rejected", "bad_mac")}},
                                           ensure_ascii=False) + "\n")
            for key in ("accepted", "duplicates", "rejected"):
                self.stats["sync_" + key] += res.get(key, 0)
        self.stats["sync_requests"] += sends
        u["queue"], u["sessions"] = [], []


def _sign(key: str, rec: dict) -> str:
    """نفس توقيع التطبيق (HMAC-SHA256 بمفتاح المزامنة)."""
    msg = "|".join(str(rec.get(f, "")) for f in ("client_id", "platform", "task", "played_at")).encode()
    return hmac.new(bytes.fromhex(key), msg, hashlib.sha256).hexdigest()


class _frozen:
    """يجعل «الآن» في الخادم هو وقت المزامنة المحاكى (حتى تُطبق قاعدة 7 أيام والتاريخ المستقبلي بشكل صحيح)."""

    def __init__(self, when):
        self.when = when

    def __enter__(self):
        from unittest import mock
        from django.utils import timezone as djtz
        self.p = mock.patch.object(djtz, "now", lambda: self.when.astimezone(ZoneInfo("UTC")))
        self.p.start()

    def __exit__(self, *a):
        self.p.stop()
