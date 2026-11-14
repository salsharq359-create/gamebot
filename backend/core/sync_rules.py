"""
TM354: قواعد قبول سجلات المزامنة بدون اتصال، بنمط «سلسلة المسؤولية» (Chain of Responsibility).

كانت الدالة offline_sync تفحص كل الشروط في حلقة واحدة (تعقيد دوري 26) وتجمع كل أنواع الرفض في رقم واحد
«rejected»، فلا يعرف التطبيق ولا المطوّر لماذا رُفض السجل. الآن كل قاعدة صنف صغير له مسؤولية واحدة:
يرجع None إذا قَبِل، أو سبب الرفض. السلسلة تتوقف عند أول رفض.

إضافة قاعدة جديدة = إضافة صنف إلى RULES فقط، دون تعديل offline_sync (مبدأ مفتوح للتوسعة مغلق للتعديل).
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.utils import timezone

from .models import EarningRecord, GameTask

SIGNED_FIELDS = ("client_id", "platform", "task", "played_at")
OFFLINE_MAX_AGE = timedelta(days=7)
FUTURE_TOLERANCE = timedelta(minutes=5)


def parse_time(value):
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return timezone.make_aware(t) if timezone.is_naive(t) else t


@dataclass
class SyncContext:
    """ما تحتاجه القواعد: المستخدم، ومفتاح التوقيع، والألعاب المرتبطة، والوقت. يُحسب مرة واحدة لكل طلب."""
    user: object
    key: str
    linked: set
    now: datetime = field(default_factory=lambda: timezone.now())   # lambda: حتى يمكن تثبيت الوقت في الاختبار


@dataclass
class Candidate:
    """سجل قيد الفحص. القواعد تملأ الحقول المشتقة (played، task) فتستخدمها القواعد التالية."""
    raw: dict
    client_id: str = ""
    played: datetime | None = None
    task: GameTask | None = None


class Rule:
    reason = ""

    def check(self, c: Candidate, ctx: SyncContext) -> str | None:   # None = مقبول
        raise NotImplementedError


class WellFormed(Rule):
    reason = "malformed"

    def check(self, c, ctx):
        if not isinstance(c.raw, dict) or not c.raw.get("client_id"):
            return self.reason
        c.client_id = str(c.raw["client_id"])[:64]
        return None


class ValidSignature(Rule):
    """TM355: كل سجل موقّع بـ HMAC-SHA256 بمفتاح المزامنة الخاص بالمستخدم."""
    reason = "bad_mac"

    def check(self, c, ctx):
        msg = "|".join(str(c.raw.get(f, "")) for f in SIGNED_FIELDS).encode()
        good = hmac.new(bytes.fromhex(ctx.key), msg, hashlib.sha256).hexdigest()
        mac = c.raw.get("mac")
        return None if isinstance(mac, str) and hmac.compare_digest(mac, good) else self.reason


class PlayedRecently(Rule):
    reason = "too_old"

    def check(self, c, ctx):
        c.played = parse_time(c.raw.get("played_at"))
        if not c.played:
            return "bad_time"
        if c.played > ctx.now + FUTURE_TOLERANCE:
            return "future"
        return self.reason if ctx.now - c.played > OFFLINE_MAX_AGE else None


class KnownDemoTask(Rule):
    reason = "unknown_task"

    def check(self, c, ctx):
        # TM351: نسخة قديمة من التطبيق ترسل "Round" بدل "round"، فنوحّد الاسم قبل البحث
        key = str(c.raw.get("task", "")).strip().lower()
        c.task = GameTask.objects.filter(platform__key=c.raw.get("platform"), platform__owner__isnull=True,
                                         platform__is_demo=True, key=key).select_related("platform").first()
        return None if c.task else self.reason


class GameLinked(Rule):
    reason = "not_linked"

    def check(self, c, ctx):
        return None if c.task.platform_id in ctx.linked else self.reason


class NotDuplicate(Rule):
    """إعادة الإرسال لا تضاعف الأرباح. ليس رفضاً: السجل موجود أصلاً."""
    reason = "duplicate"

    def check(self, c, ctx):
        return self.reason if EarningRecord.objects.filter(user=ctx.user, client_id=c.client_id).exists() else None


class WithinDailyLimit(Rule):
    """الحد اليومي يُحسب حسب يوم اللعب الفعلي، لا يوم المزامنة."""
    reason = "daily_limit"

    def check(self, c, ctx):
        day0 = timezone.localtime(c.played).replace(hour=0, minute=0, second=0, microsecond=0)
        n = EarningRecord.objects.filter(user=ctx.user, task=c.task, created_at__gte=day0,
                                         created_at__lt=day0 + timedelta(days=1)).count()
        return self.reason if n >= c.task.max_per_day else None


# الترتيب مهم: الفحوص الرخيصة التي لا تحتاج قاعدة البيانات أولاً، ثم التي تعتمد على ما ملأته السابقة
RULES: tuple[Rule, ...] = (WellFormed(), ValidSignature(), PlayedRecently(), KnownDemoTask(), GameLinked(),
                           NotDuplicate(), WithinDailyLimit())


def first_failure(c: Candidate, ctx: SyncContext, rules=RULES) -> str | None:
    for rule in rules:
        reason = rule.check(c, ctx)
        if reason:
            return reason
    return None
