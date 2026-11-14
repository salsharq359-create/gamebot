"""
تصدير بيانات جيم بوت للتحليل (TM351 — جمع البيانات، وأخلاقيات البيانات).

مبدأ «تقليل البيانات» و«الاسم المستعار» (pseudonymisation):
  - لا يُصدَّر اسم المستخدم أبداً. كل مستخدم يأخذ معرّفاً مستعاراً ثابتاً: HMAC(المفتاح السري، المعرّف).
    بدون المفتاح السري لا يمكن الرجوع من المعرّف المستعار إلى الحساب.
  - تاريخ التسجيل يُقرَّب إلى اليوم فقط، والملاحظات النصية الحرة تُحذف، وتواقيع HMAC تُحذف.
  - البيانات الخام (طلبات المزامنة ومستندات الجلسات) تُصدَّر بنفس المعرّفات المستعارة.

التشغيل:  python manage.py export_dataset --out ../data/export
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from core.models import EarningRecord, GamePlatform, GameTask, PlaySession, Profile

ROOT = Path(__file__).resolve().parents[4]


def pseudonym(user_id) -> str:
    digest = hmac.new(settings.SECRET_KEY.encode(), f"export:{user_id}".encode(), hashlib.sha256).hexdigest()
    return "u_" + digest[:10]


class Command(BaseCommand):
    help = "يصدّر جداول CSV وملفات JSONL بمعرّفات مستعارة للتحليل"

    def add_arguments(self, parser):
        parser.add_argument("--out", default=str(ROOT / "data" / "export"))
        parser.add_argument("--raw", default=str(ROOT / "data" / "raw"))

    def handle(self, *args, **o):
        out = Path(o["out"])
        out.mkdir(parents=True, exist_ok=True)
        counts = {}

        users = get_user_model().objects.annotate(
            linked=Count("game_accounts", filter=Q(game_accounts__linked=True, game_accounts__platform__is_demo=True)))
        profiles = {p.user_id: p for p in Profile.objects.all()}
        rows = []
        for u in users:
            p = profiles.get(u.pk)
            rows.append({"user": pseudonym(u.pk), "joined_date": u.date_joined.date().isoformat(),
                         "daily_limit_min": p.daily_limit_min if p else 60,
                         "leaderboard": int(bool(p and p.leaderboard)), "dark_mode": int(bool(p and p.dark)),
                         "text_scale": p.text_scale if p else 1.0, "demo_games_linked": u.linked})
        counts["users"] = self._csv(out / "users.csv", rows)

        rows = [{"platform_id": p.pk, "key": p.key, "name": p.name, "is_demo": int(p.is_demo),
                 "owner": pseudonym(p.owner_id) if p.owner_id else ""}
                for p in GamePlatform.objects.all().order_by("pk")]
        counts["platforms"] = self._csv(out / "platforms.csv", rows)

        rows = [{"task_id": t.pk, "platform_id": t.platform_id, "key": t.key, "kind": t.kind,
                 "reward_cents": t.reward_cents, "minutes": t.minutes, "max_per_day": t.max_per_day}
                for t in GameTask.objects.all().order_by("pk")]
        counts["tasks"] = self._csv(out / "tasks.csv", rows)

        qs = EarningRecord.objects.values_list("pk", "user_id", "platform_id", "task_id", "cents", "source",
                                               "client_id", "created_at").order_by("pk")
        rows = ({"earning_id": pk, "user": pseudonym(uid), "platform_id": pid or "", "task_id": tid or "",
                 "cents": cents, "source": src, "offline": int(bool(cid and cid.startswith("off-"))),
                 "client_id": cid if cid and cid.startswith("off-") else "",
                 "created_at": at.isoformat()} for pk, uid, pid, tid, cents, src, cid, at in qs.iterator())
        counts["earnings"] = self._csv(out / "earnings.csv", rows)

        rows = ({"session_id": pk, "user": pseudonym(uid), "started_at": at.isoformat(), "seconds": s}
                for pk, uid, at, s in PlaySession.objects.values_list("pk", "user_id", "started_at", "seconds")
                .order_by("pk").iterator())
        counts["sessions"] = self._csv(out / "sessions.csv", rows)

        raw = Path(o["raw"])
        if (raw / "sync_requests.jsonl").exists():
            counts["raw_sync_requests"] = self._jsonl(raw / "sync_requests.jsonl", out / "raw_sync_requests.jsonl",
                                                      self._clean_sync)
        if (raw / "bot_sessions.jsonl").exists():
            counts["raw_bot_sessions"] = self._jsonl(raw / "bot_sessions.jsonl", out / "raw_bot_sessions.jsonl",
                                                     self._clean_doc)
        self.stdout.write(json.dumps(counts))

    @staticmethod
    def _clean_sync(d):
        d["user"] = pseudonym(d.pop("user_id"))
        for r in d["body"]["records"]:
            r.pop("mac", None)          # التوقيع لا فائدة منه في التحليل
        return d

    @staticmethod
    def _clean_doc(d):
        d["user"] = pseudonym(d.pop("user_id"))
        return d

    @staticmethod
    def _csv(path: Path, rows) -> int:
        n = 0
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = None
            for r in rows:
                if w is None:
                    w = csv.DictWriter(f, fieldnames=list(r))
                    w.writeheader()
                w.writerow(r)
                n += 1
        return n

    @staticmethod
    def _jsonl(src: Path, dst: Path, fn) -> int:
        n = 0
        with open(src, encoding="utf-8") as fi, open(dst, "w", encoding="utf-8") as fo:
            for line in fi:
                fo.write(json.dumps(fn(json.loads(line)), ensure_ascii=False) + "\n")
                n += 1
        return n
