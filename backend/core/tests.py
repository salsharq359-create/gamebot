"""اختبارات خادم Django: المصادقة والأمن والخصوصية والمستشار وأرباح الروبوت."""
import hashlib
import hmac
import json
import zlib
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from .advisor import TaskOption, best_plan
from .models import EarningRecord, GamePlatform, GameTask, PlaySession

INTERNAL = "test-internal-key"


@override_settings(INTERNAL_API_KEY=INTERNAL)
class ApiTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        """
        TM354: الوقت ثابت عند ظهر اليوم. كانت عدة اختبارات تفترض أن «قبل ساعة» و«قبل دقيقتين» من نفس اليوم،
        ففشلت عند تشغيلها بين 00:00 و 01:00 (اختبارات متقلبة flaky). اكتُشف ذلك بتشغيل الاختبارات بعد منتصف الليل.
        """
        super().setUpClass()
        noon = timezone.localtime().replace(hour=12, minute=0, second=0, microsecond=0)
        patcher = mock.patch("django.utils.timezone.now", return_value=noon)
        patcher.start()
        cls.addClassCleanup(patcher.stop)

    def call(self, method, url, data=None, token=None, internal=False):
        headers = {}
        if token:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        if internal:
            headers["HTTP_X_INTERNAL_KEY"] = INTERNAL
        fn = getattr(self.client, method)
        r = fn(url, data=json.dumps(data or {}), content_type="application/json", **headers) \
            if method != "get" else fn(url, data or {}, **headers)
        return r.status_code, (r.json() if r.content else {})

    def register(self, username="salem", password="correct horse battery"):
        status, data = self.call("post", "/api/auth/register/", {"username": username, "password": password})
        self.assertEqual(status, 201, data)
        self.sync_key = data["sync_key"]
        return data["token"]


class AuthTests(ApiTestCase):
    def test_password_policy_follows_nist(self):
        for bad in ("short1", "password123", "12345678", "salem123"):
            status, _ = self.call("post", "/api/auth/register/", {"username": "salem", "password": bad})
            self.assertEqual(status, 400, bad)
        # لا قواعد تركيب: عبارة مرور طويلة من حروف فقط مقبولة
        self.register(password="correct horse battery staple")

    def test_lockout_after_five_failures(self):
        self.register()
        for _ in range(4):
            status, _ = self.call("post", "/api/auth/login/", {"username": "salem", "password": "wrong pass word"})
            self.assertEqual(status, 401)
        status, data = self.call("post", "/api/auth/login/", {"username": "salem", "password": "wrong pass word"})
        self.assertEqual(status, 423)
        status, _ = self.call("post", "/api/auth/login/", {"username": "salem", "password": "correct horse battery"})
        self.assertEqual(status, 423)   # حتى الصحيحة مرفوضة أثناء القفل
        later = timezone.now() + timedelta(minutes=6)
        with mock.patch("django.utils.timezone.now", return_value=later):
            status, _ = self.call("post", "/api/auth/login/",
                                  {"username": "salem", "password": "correct horse battery"})
        self.assertEqual(status, 200)

    def test_token_required_and_invalidated_by_password_change(self):
        token = self.register()
        self.assertEqual(self.call("get", "/api/me/")[0], 401)
        self.assertEqual(self.call("get", "/api/me/", token="forged")[0], 401)
        self.assertEqual(self.call("get", "/api/me/", token=token)[0], 200)
        status, data = self.call("post", "/api/me/password/",
                                 {"old": "correct horse battery", "new": "another long phrase"}, token=token)
        self.assertEqual(status, 200)
        self.assertEqual(self.call("get", "/api/me/", token=token)[0], 401)       # القديم بطل
        self.assertEqual(self.call("get", "/api/me/", token=data["token"])[0], 200)


class PrivacyTests(ApiTestCase):
    def test_export_has_no_password_and_delete_removes_everything(self):
        token = self.register()
        status, data = self.call("get", "/api/me/export/", token=token)
        self.assertEqual(status, 200)
        self.assertNotIn("password", json.dumps(data))
        self.assertEqual(self.call("delete", "/api/me/", {"password": "nope"}, token=token)[0], 403)
        self.assertEqual(self.call("delete", "/api/me/", {"password": "correct horse battery"}, token=token)[0], 200)
        self.assertEqual(EarningRecord.objects.count(), 0)
        self.assertEqual(self.call("get", "/api/me/", token=token)[0], 401)


class AdvisorTests(ApiTestCase):
    def test_knapsack_is_optimal(self):
        opts = [TaskOption(1, "A", "سريعة", 400, 4, 1), TaskOption(2, "B", "متوسطة", 270, 3, 2)]
        best, plan = best_plan(opts, 6)
        # الاختيار الجشع (الأعلى ربحاً لكل دقيقة أولاً) يأخذ «سريعة» (4 دقائق = 4$) ولا يبقى وقت لغيرها.
        # البرمجة الديناميكية تجد الأفضل: «متوسطة» مرتين = 6 دقائق = 5.40$
        self.assertEqual(best, 540)
        self.assertEqual({p["title"]: p["times"] for p in plan}, {"متوسطة": 2})

    def test_strategy_respects_daily_limit(self):
        token = self.register()
        self.call("patch", "/api/me/prefs/", {"daily_limit_min": 20}, token=token)
        user_id = self.call("get", "/api/me/", token=token)[1]["id"]
        PlaySession.objects.create(user_id=user_id, started_at=timezone.now(), seconds=15 * 60)
        status, data = self.call("get", "/api/bot/strategy/", {"minutes": 60}, token=token)
        self.assertEqual(status, 200)
        self.assertEqual(data["minutes_budget"], 5)
        self.assertIsNotNone(data["note"])
        self.assertLessEqual(sum(p["total_minutes"] for p in data["plan"]), 5)

    def test_custom_platform_tasks_and_manual_earnings(self):
        token = self.register()
        status, p = self.call("post", "/api/platforms/", {"name": "منصتي"}, token=token)
        self.assertEqual(status, 201)
        status, t = self.call("post", "/api/tasks/", {"platform_id": p["id"], "title": "مهمة يومية",
                                                      "reward": 0.3, "minutes": 10}, token=token)
        self.assertEqual(status, 201)
        demo = GamePlatform.objects.get(key="coins")
        self.assertEqual(self.call("post", "/api/tasks/", {"platform_id": demo.id, "reward": 9, "minutes": 1},
                                   token=token)[0], 403)
        status, e = self.call("post", "/api/earnings/", {"platform_id": p["id"], "amount": 0.3}, token=token)
        self.assertEqual((status, e["balance_cents"]), (200, 30))
        self.assertEqual(self.call("post", "/api/earnings/", {"platform_id": demo.id, "amount": 50},
                                   token=token)[0], 403)


class BotEarningTests(ApiTestCase):
    def setUp(self):
        self.token = self.register()
        self.uid = self.call("get", "/api/me/", token=self.token)[1]["id"]

    def report(self, task="round", platform="coins", cid="c1", key=True):
        return self.call("post", "/api/internal/earnings/",
                         {"user_id": self.uid, "platform": platform, "task": task, "client_id": cid},
                         internal=key)

    def test_server_decides_amount_and_rejects_duplicates(self):
        status, data = self.report()
        self.assertEqual((status, data["cents"]), (200, 100))   # كل لعبة = 1$
        status, data = self.report()                            # نفس client_id
        self.assertFalse(data["accepted"])
        self.assertEqual(EarningRecord.objects.filter(user_id=self.uid).count(), 1)

    def test_internal_key_required_and_unlinked_game_rejected(self):
        self.assertEqual(self.call("post", "/api/internal/earnings/", {"user_id": self.uid}, )[0], 403)
        self.assertEqual(self.report(platform="xo", cid="x1")[0], 403)    # إكس أو غير مرتبطة افتراضياً

    def test_daily_reward_once_per_day(self):
        self.assertEqual(self.report(task="daily", cid="d1")[0], 200)
        status, data = self.report(task="daily", cid="d2")
        self.assertEqual((status, data["reason"]), (409, "daily_limit"))

    def test_session_logs_play_time_and_notifies(self):
        status, data = self.call("post", "/api/internal/sessions/",
                                 {"user_id": self.uid, "seconds": 120, "session_cents": 600}, internal=True)
        self.assertEqual((status, data["minutes_today"]), (200, 2.0))
        _, n = self.call("get", "/api/notifications/", token=self.token)
        self.assertTrue(any("جلسة" in x["title"] for x in n["notifications"]))


class SeedTests(TestCase):
    def test_demo_games_seeded(self):
        self.assertEqual(GamePlatform.objects.filter(is_demo=True).count(), 3)
        self.assertEqual(GameTask.objects.get(platform__key="coins", key="round").reward_cents, 100)


class SyncTestBase(ApiTestCase):
    def setUp(self):
        self.token = self.register()

    def sync(self, records, sessions=None):
        return self.call("post", "/api/bot/offline-sync/", {"records": records, "sessions": sessions or []},
                         token=self.token)

    def rec(self, cid, task="round", platform="coins", ago=timedelta(hours=1), cents=99999, key=None):
        # cents مزوّر عمداً: الخادم يتجاهله ويأخذ المبلغ من جدول المهام
        r = {"client_id": cid, "platform": platform, "task": task, "cents": cents,
             "played_at": (timezone.now() - ago).isoformat()}
        msg = "|".join(str(r[f]) for f in ("client_id", "platform", "task", "played_at")).encode()
        r["mac"] = hmac.new(bytes.fromhex(key or self.sync_key), msg, hashlib.sha256).hexdigest()
        return r

    def raw_sync(self, payload: bytes, **headers):
        r = self.client.post("/api/bot/offline-sync/", data=payload, content_type="application/json",
                             HTTP_AUTHORIZATION=f"Bearer {self.token}", **headers)
        return r.status_code, r.json()


class OfflineSyncTests(SyncTestBase):
    """الوحدة 1: نتائج الروبوت التي لُعبت بدون اتصال تُرسل لاحقاً، والخادم يتحقق منها."""

    def test_amount_from_server_and_resend_is_idempotent(self):
        status, d = self.sync([self.rec("a1"), self.rec("a2")])
        self.assertEqual((status, d["accepted"], d["accepted_cents"]), (200, 2, 200))
        status, d = self.sync([self.rec("a1"), self.rec("a2")])
        self.assertEqual((d["accepted"], d["duplicates"]), (0, 2))
        self.assertEqual(d["balance_cents"], 200)

    def test_rejects_old_future_unlinked_and_over_daily_limit(self):
        status, d = self.sync([
            self.rec("old", ago=timedelta(days=8)),
            self.rec("future", ago=-timedelta(hours=2)),
            self.rec("xo", platform="xo"),               # إكس أو غير مرتبطة افتراضياً
            self.rec("d1", task="daily"), self.rec("d2", task="daily"),
        ])
        self.assertEqual((d["accepted"], d["rejected"]), (1, 4))
        self.assertEqual(len(d["processed_ids"]), 5)

    def test_daily_limit_counts_the_day_it_was_played(self):
        _, d = self.sync([self.rec("y", task="daily", ago=timedelta(days=1)), self.rec("t", task="daily")])
        self.assertEqual(d["accepted"], 2)   # مكافأة الأمس ومكافأة اليوم

    def test_sessions_logged(self):
        self.sync([], sessions=[{"started_at": timezone.now().isoformat(), "seconds": 180}])
        self.assertEqual(self.call("get", "/api/me/", token=self.token)[1]["minutes_today"], 3.0)


class TM355SyncTests(SyncTestBase):
    """TM355: ضغط DEFLATE، وكشف الأخطاء بـ CRC-32، وتوقيع السجلات بـ HMAC-SHA256."""

    def test_compressed_payload_with_valid_crc_is_accepted(self):
        plain = json.dumps({"records": [self.rec(f"c{i}") for i in range(10)], "sessions": []}).encode()
        packed = zlib.compress(plain, 9)
        self.assertLess(len(packed), len(plain) / 2)
        status, d = self.raw_sync(packed, HTTP_CONTENT_ENCODING="deflate",
                                  HTTP_X_PAYLOAD_CRC32=f"{zlib.crc32(packed):08x}")
        self.assertEqual((status, d["accepted"]), (200, 10))

    def test_corrupted_payload_fails_crc_and_changes_nothing(self):
        packed = zlib.compress(json.dumps({"records": [self.rec("x1")]}).encode())
        crc = f"{zlib.crc32(packed):08x}"
        corrupted = bytearray(packed)
        corrupted[len(corrupted) // 2] ^= 0x04          # بت واحد انقلب في الطريق
        status, d = self.raw_sync(bytes(corrupted), HTTP_CONTENT_ENCODING="deflate", HTTP_X_PAYLOAD_CRC32=crc)
        self.assertEqual((status, d.get("crc_failed")), (400, True))
        self.assertFalse(EarningRecord.objects.exists())
        status, d = self.raw_sync(packed, HTTP_CONTENT_ENCODING="deflate", HTTP_X_PAYLOAD_CRC32=crc)   # إعادة الإرسال
        self.assertEqual(d["accepted"], 1)

    def test_tampered_or_unsigned_records_are_rejected(self):
        tampered = self.rec("t1")
        tampered["task"] = "tournament"                   # غُيّر بعد التوقيع ليأخذ 2$
        unsigned = self.rec("t2")
        del unsigned["mac"]
        _, d = self.sync([tampered, unsigned, self.rec("ok")])
        self.assertEqual((d["accepted"], d["bad_mac"]), (1, 2))

    def test_sync_key_changes_with_password(self):
        old_key = self.sync_key
        _, d = self.call("post", "/api/me/password/", {"old": "correct horse battery", "new": "another long phrase"},
                         token=self.token)
        self.token, new_key = d["token"], d["sync_key"]
        self.assertNotEqual(old_key, new_key)
        _, d = self.sync([self.rec("k1", key=old_key), self.rec("k2", key=new_key)])
        self.assertEqual((d["accepted"], d["bad_mac"]), (1, 1))

    def test_decompression_bomb_is_refused(self):
        bomb = zlib.compress(b" " * (3 * 1024 * 1024), 9)   # 3 MB من المسافات يصبح بضعة كيلوبايت
        status, _ = self.raw_sync(bomb, HTTP_CONTENT_ENCODING="deflate")
        self.assertEqual(status, 413)


class TM351FixTests(SyncTestBase):
    """إصلاحات وجدها تحليل البيانات (TM351)."""

    def test_resent_sync_does_not_duplicate_sessions(self):
        s = [{"started_at": timezone.now().isoformat(), "seconds": 60}]
        self.sync([], sessions=s)
        self.sync([], sessions=s)                 # إعادة إرسال بعد انقطاع
        self.assertEqual(PlaySession.objects.count(), 1)

    def test_old_app_task_case_is_accepted(self):
        _, d = self.sync([self.rec("o1", task="Round")])
        self.assertEqual(d["accepted"], 1)


class TM351AnalyticsTests(ApiTestCase):
    """لوحة «تحليلاتي» وتصدير CSV."""

    def setUp(self):
        self.token = self.register()
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.get(username="salem")
        coins = GamePlatform.objects.get(key="coins", owner__isnull=True)
        rnd = GameTask.objects.get(platform=coins, key="round")
        now = timezone.now()
        for i, cid in enumerate([None, None, "off-1"]):
            EarningRecord.objects.create(user=self.user, platform=coins, task=rnd, cents=100, client_id=cid,
                                         created_at=now - timedelta(days=i))
        PlaySession.objects.create(user=self.user, started_at=now - timedelta(minutes=5), seconds=90)

    def test_analytics_aggregates(self):
        _, d = self.call("get", "/api/analytics/", token=self.token)
        self.assertEqual(d["total_cents"], 300)
        self.assertEqual(d["channel"], {"online": 200, "offline": 100, "manual": 0})
        self.assertEqual(d["by_game"][0]["records"], 3)
        self.assertEqual(len(d["daily"]), 14)
        self.assertEqual((d["sessions"]["count"], d["sessions"]["avg_seconds"]), (1, 90.0))
        self.assertEqual(sum(d["by_hour"]), 1)

    def test_earnings_view_uses_one_query_for_seven_days(self):
        with self.assertNumQueries(8):        # كانت 14 عندما كان كل يوم استعلاماً منفصلاً
            self.call("get", "/api/earnings/", token=self.token)

    def test_csv_export(self):
        r = self.client.get("/api/me/export.csv", HTTP_AUTHORIZATION=f"Bearer {self.token}")
        lines = r.content.decode("utf-8-sig").strip().splitlines()
        self.assertEqual(lines[0], "date_time,platform,task,dollars,source,offline")
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[1].endswith(",1.00,bot,1"))     # الأقدم أولاً: سجل بدون اتصال


class M269AdvisorTests(TestCase):
    """M269: خطة المستشار (برمجة ديناميكية) تساوي أفضل حل بالبحث الشامل في كل الحالات."""

    def test_dp_plan_is_optimal_against_brute_force(self):
        import itertools
        import random
        rng = random.Random(269)
        for _ in range(150):
            opts = [TaskOption(i, "p", f"t{i}", rng.randint(10, 400), rng.randint(1, 5), rng.randint(1, 3))
                    for i in range(rng.randint(1, 5))]
            budget = rng.randint(1, 15)
            got, plan = best_plan(opts, budget)
            best = 0
            for counts in itertools.product(*[range(o.remaining_today + 1) for o in opts]):
                if sum(c * o.minutes for c, o in zip(counts, opts)) <= budget:
                    best = max(best, sum(c * o.reward_cents for c, o in zip(counts, opts)))
            self.assertEqual(got, best)
            self.assertLessEqual(sum(s["total_minutes"] for s in plan), budget)
