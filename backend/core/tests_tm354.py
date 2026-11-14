"""
اختبارات TM354: العقود (Design by Contract)، والتزامن، وقيم الحدود، وقواعد التحقق في المزامنة.
"""
import json
import threading
import time
from unittest import mock, skipUnless

from django.db import connection, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings

from . import views
from .advisor import TaskOption, best_plan
from .contracts import ContractError
from .models import EarningRecord, GamePlatform
from .tests import INTERNAL, ApiTestCase, SyncTestBase


# ------------------------------------------------- 1) العقد: الرصيد لا يصبح سالباً
@override_settings(INTERNAL_API_KEY=INTERNAL)
@skipUnless(connection.vendor == "postgresql", "سباق حقيقي يحتاج قاعدة تسمح بكتابات متزامنة (PostgreSQL)")
class WithdrawalRaceTests(TransactionTestCase):
    """
    خمسة طلبات سحب متزامنة لكامل الرصيد. قبل الإصلاح كان كل طلب يقرأ الرصيد (5$) قبل أن يكتب أي طلب آخر،
    فتنجح الطلبات كلها ويصبح الرصيد −20$. الآن يُقفل صف المستخدم (SELECT … FOR UPDATE) فينجح طلب واحد فقط.
    """

    def test_concurrent_withdrawals_never_overdraw(self):
        c = Client()
        r = c.post("/api/auth/register/", json.dumps({"username": "racer", "password": "correct horse battery"}),
                   content_type="application/json").json()
        token = r["token"]
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.get(username="racer")
        EarningRecord.objects.create(user=user, platform=GamePlatform.objects.get(key="coins", owner=None),
                                     cents=500, note="seed")
        real = views.balance_cents

        def slow_balance(u):                      # نوسّع نافذة السباق: زمن الشبكة بين القراءة والكتابة
            v = real(u)
            time.sleep(0.15)
            return v
        codes, barrier = [], threading.Barrier(5)

        def withdraw():
            barrier.wait()
            resp = Client().post("/api/withdrawals/", json.dumps({"method": "محفظة إلكترونية", "amount": 5}),
                                 content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")
            codes.append(resp.status_code)
            connections.close_all()
        with mock.patch.object(views, "balance_cents", slow_balance):
            threads = [threading.Thread(target=withdraw) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(sorted(codes), [200, 400, 400, 400, 400])
        self.assertEqual(real(user), 0)


# ------------------------------------------------- 2) العقود في المستشار
class AdvisorContractTests(TestCase):
    def opts(self):
        return [TaskOption(1, "coins", "جولة", 100, 1, 10), TaskOption(2, "coins", "بطولة", 200, 3, 1)]

    def test_boundary_values_of_budget(self):
        # تقسيم التكافؤ وقيم الحدود: 0 (أدنى)، 1 (أصغر قيمة مفيدة)، 240 (أعلى قيمة يسمح بها التطبيق)
        self.assertEqual(best_plan(self.opts(), 0), (0, []))
        self.assertEqual(best_plan(self.opts(), 1)[0], 100)
        self.assertEqual(best_plan(self.opts(), 240)[0], 10 * 100 + 200)

    def test_precondition_rejects_negative_budget(self):
        with self.assertRaises(ContractError):
            best_plan(self.opts(), -5)

    def test_postcondition_holds_on_random_inputs(self):
        import random
        rng = random.Random(354)
        for _ in range(300):        # العقد يُفحص داخل الدالة: أي خرق يرفع ContractError
            opts = [TaskOption(i, "p", "t", rng.randint(1, 500), rng.randint(1, 8), rng.randint(0, 4))
                    for i in range(rng.randint(0, 6))]
            best_plan(opts, rng.randint(0, 60))


# ------------------------------------------------- 3) قيم الحدود في واجهات الخادم
class BoundaryTests(ApiTestCase):
    def setUp(self):
        self.token = self.register()

    def test_strategy_minutes_boundaries(self):
        # المواصفة (R-ADV-2): الميزانية تُقصّ إلى [0، 240] ومحدودة بحد اللعب اليومي (60 افتراضياً)، والقيمة غير الرقمية = 30
        self.call("patch", "/api/me/prefs/", {"daily_limit_min": 0}, token=self.token)
        for minutes, budget in ((-1, 0), (0, 0), (1, 1), (240, 240), (241, 240), ("abc", 30)):
            status, data = self.call("get", "/api/bot/strategy/", {"minutes": minutes}, token=self.token)
            self.assertEqual((status, data["minutes_budget"]), (200, budget), minutes)

    def test_prefs_reject_bad_numbers_instead_of_crashing(self):
        for bad in ({"text_scale": "big"}, {"daily_limit_min": "abc"}, {"daily_limit_min": None}):
            status, _ = self.call("patch", "/api/me/prefs/", bad, token=self.token)
            self.assertEqual(status, 400, bad)
        status, _ = self.call("patch", "/api/me/prefs/", {"daily_limit_min": 999}, token=self.token)
        self.assertEqual(status, 200)          # خارج المدى لكنه رقم: يُقصّ إلى 240

    @override_settings(INTERNAL_API_KEY=INTERNAL)
    def test_internal_session_rejects_bad_numbers_instead_of_crashing(self):
        from django.contrib.auth import get_user_model
        uid = get_user_model().objects.get(username="salem").id
        for bad in ({"seconds": "abc"}, {"seconds": 10, "session_cents": "x"}, {"seconds": None}):
            status, _ = self.call("post", "/api/internal/sessions/", {"user_id": uid, **bad}, internal=True)
            self.assertEqual(status, 400, bad)

    def test_withdrawal_amount_boundaries(self):
        status, _ = self.call("post", "/api/withdrawals/", {"method": "محفظة إلكترونية", "amount": 0}, token=self.token)
        self.assertEqual(status, 400)
        status, _ = self.call("post", "/api/withdrawals/", {"method": "محفظة إلكترونية", "amount": 0.01},
                              token=self.token)
        self.assertEqual(status, 400)          # الرصيد صفر: أصغر مبلغ موجب يُرفض أيضاً


# ------------------------------------------------- 4) أسباب رفض المزامنة (سلسلة قواعد)
class SyncRuleTests(SyncTestBase):
    def test_each_rejection_has_a_reason(self):
        from datetime import timedelta
        good = self.rec("ok-1")
        tampered = {**self.rec("bad-mac"), "task": "tournament"}
        old = self.rec("old-1", ago=timedelta(days=8))
        unknown = self.rec("unk-1", task="nope")
        status, res = self.sync([good, tampered, old, unknown, {"x": 1}, good])
        self.assertEqual(status, 200)
        self.assertEqual(res["accepted"], 1)
        self.assertEqual(res["duplicates"], 1)
        self.assertEqual(res["reasons"], {"bad_mac": 1, "too_old": 1, "unknown_task": 1, "malformed": 1})
        self.assertEqual(res["rejected"], 4)


# ------------------------------------------------- 5) اختبارات كتبناها بعد تحليل الطفرات الناجية
class AdvisorMutationTests(TestCase):
    """كل اختبار هنا يقتل طفرة نجت من الاختبارات السابقة (انظر se/out/mutation_advisor_*.json)."""

    def test_zero_minute_or_zero_reward_tasks_are_ignored_but_one_cent_counts(self):
        opts = [TaskOption(1, "p", "صفر دقائق", 500, 0, 3), TaskOption(2, "p", "بلا مكافأة", 0, 1, 3),
                TaskOption(3, "p", "سنت واحد", 1, 1, 2)]
        total, plan = best_plan(opts, 5)          # بدون التجاهل: قسمة على صفر
        self.assertEqual((total, [p["task_id"] for p in plan]), (2, [3]))

    def test_plan_fields_are_exact_and_sorted_by_rate(self):
        opts = [TaskOption(1, "p", "بطيئة", 270, 3, 1), TaskOption(2, "p", "سريعة", 100, 1, 2)]
        total, plan = best_plan(opts, 5)
        self.assertEqual(total, 470)
        self.assertEqual([(p["task_id"], p["times"], p["cents_per_minute"], p["total_minutes"], p["total_cents"])
                          for p in plan], [(2, 2, 100.0, 2, 200), (1, 1, 90.0, 3, 270)])

    def test_rate_is_rounded_to_one_decimal(self):
        plan = best_plan([TaskOption(1, "p", "t", 100, 3, 1)], 3)[1]
        self.assertEqual(plan[0]["cents_per_minute"], 33.3)

    def test_precondition_rejects_non_integer_budget(self):
        with self.assertRaises(ContractError):
            best_plan([TaskOption(1, "p", "t", 100, 1, 1)], 2.5)

    def test_task_options_are_immutable(self):
        from dataclasses import FrozenInstanceError
        with self.assertRaises(FrozenInstanceError):
            TaskOption(1, "p", "t", 100, 1, 1).reward_cents = 10 ** 6


# ------------------------------------------------- 6) قيم الحدود في قواعد المزامنة (بعد تحليل الطفرات)
class SyncBoundaryTests(SyncTestBase):
    """كل حد في sync_rules.py يُختبر من جهتيه: 7 أيام، و5 دقائق في المستقبل، وبداية اليوم ونهايته، وطول client_id."""

    def test_age_limit_is_seven_days(self):
        from datetime import timedelta
        _, d = self.sync([self.rec("in", ago=timedelta(days=6, hours=23)),
                          self.rec("out", ago=timedelta(days=7, hours=1))])
        self.assertEqual((d["accepted"], d["reasons"]), (1, {"too_old": 1}))

    def test_exactly_seven_days_is_still_accepted(self):
        from datetime import timedelta
        from django.utils import timezone
        fixed = timezone.now()
        with mock.patch("django.utils.timezone.now", return_value=fixed):
            _, d = self.sync([self.rec("edge", ago=timedelta(days=7))])
        self.assertEqual(d["accepted"], 1)

    def test_future_tolerance_is_five_minutes(self):
        from datetime import timedelta
        _, d = self.sync([self.rec("skew", ago=-timedelta(minutes=4)), self.rec("fut", ago=-timedelta(minutes=5, seconds=30)),
                          self.rec("recent", ago=timedelta(minutes=1))])
        self.assertEqual((d["accepted"], d["reasons"]), (2, {"future": 1}))

    def test_day_window_starts_exactly_at_local_midnight_and_lasts_one_day(self):
        from datetime import timedelta
        from django.utils import timezone
        now = timezone.localtime()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        # مكافأة يومية (مرة واحدة في اليوم): منتصف ليل الأمس بالضبط، ثم ظهر الأمس = نفس اليوم، فالثانية مرفوضة
        with mock.patch("django.utils.timezone.now", return_value=now):      # الوقت ثابت: منتصف الليل بالميكروثانية
            _, d = self.sync([self.rec("m0", task="daily", ago=now - midnight),
                              self.rec("m12", task="daily", ago=now - midnight - timedelta(hours=12))])
        self.assertEqual((d["accepted"], d["reasons"]), (1, {"daily_limit": 1}))

    def test_exactly_five_minutes_ahead_is_still_accepted(self):
        from datetime import timedelta
        from django.utils import timezone
        with mock.patch("django.utils.timezone.now", return_value=timezone.now()):
            _, d = self.sync([self.rec("edge", ago=-timedelta(minutes=5))])
        self.assertEqual(d["accepted"], 1)

    def test_today_does_not_count_against_yesterday(self):
        from datetime import timedelta
        _, d = self.sync([self.rec("t", task="daily"), self.rec("y", task="daily", ago=timedelta(days=1))])
        self.assertEqual(d["accepted"], 2)

    def test_client_id_is_truncated_to_64_characters(self):
        _, d = self.sync([self.rec("x" * 70)])
        self.assertEqual(d["processed_ids"], ["x" * 64])
