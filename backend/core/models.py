"""
نماذج البيانات (الجداول) — نفس جداول خطة Copilot مع جداول TM255:

User              المستخدم (من Django)
Profile           قفل الحساب + تفضيلات المظهر واللعب الصحي والخصوصية
GamePlatform      منصة / لعبة (ألعاب تجريبية مدمجة، أو منصة يضيفها المستخدم لتتبع أرباحه يدوياً)
UserGameAccount   حساب المستخدم في اللعبة (مرتبط أو لا)
GameTask          مهمة / فرصة ربح داخل اللعبة (المكافأة والمدة)
BotStrategy       خطة الروبوت المقترحة (ناتج المستشار)
EarningRecord     سجل أرباح المستخدم (بالسنت: 100 = 1 دولار، أرباح محاكاة)
Notification      تنبيهات الروبوت
Withdrawal        عمليات السحب (محاكاة)
SecurityEvent     السجل الأمني
PlaySession       مدة جلسات اللعب (لحد اللعب اليومي)
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    failed_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    dark = models.BooleanField(default=False)
    text_scale = models.FloatField(default=1.0)
    daily_limit_min = models.PositiveIntegerField(default=60)   # 0 = بدون حد
    leaderboard = models.BooleanField(default=False)            # الظهور في لوحة المتصدرين (اختياري)

    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())


class GamePlatform(models.Model):
    key = models.SlugField(max_length=40)
    name = models.CharField(max_length=80)
    category = models.CharField(max_length=40, blank=True)
    algorithm = models.CharField(max_length=60, blank=True)
    description = models.CharField(max_length=300, blank=True)
    # منصة تجريبية مدمجة: الروبوت يلعبها فعلاً. غير ذلك: منصة يتتبعها المستخدم يدوياً.
    is_demo = models.BooleanField(default=False)
    owner = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE,
                              related_name="own_platforms")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "key"], name="uniq_platform_key_per_owner")]

    def __str__(self):
        return self.name


class UserGameAccount(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="game_accounts")
    platform = models.ForeignKey(GamePlatform, on_delete=models.CASCADE, related_name="accounts")
    linked = models.BooleanField(default=True)
    nickname = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "platform"], name="uniq_account")]


class GameTask(models.Model):
    KINDS = [("round", "جولة لعب"), ("daily", "مكافأة يومية"), ("challenge", "تحدٍّ"),
             ("tournament", "بطولة"), ("custom", "مهمة يضيفها المستخدم")]
    platform = models.ForeignKey(GamePlatform, on_delete=models.CASCADE, related_name="tasks")
    key = models.SlugField(max_length=40)
    title = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=KINDS)
    reward_cents = models.PositiveIntegerField()
    minutes = models.PositiveIntegerField(default=1)
    max_per_day = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["platform", "key"], name="uniq_task_key")]

    def __str__(self):
        return f"{self.platform.name}: {self.title}"


class BotStrategy(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="strategies")
    created_at = models.DateTimeField(auto_now_add=True)
    minutes_budget = models.PositiveIntegerField()
    expected_cents = models.PositiveIntegerField()
    plan = models.JSONField(default=list)


class EarningRecord(models.Model):
    SOURCES = [("bot", "الروبوت"), ("manual", "يدوي")]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="earnings")
    platform = models.ForeignKey(GamePlatform, null=True, on_delete=models.SET_NULL)
    task = models.ForeignKey(GameTask, null=True, on_delete=models.SET_NULL)
    cents = models.PositiveIntegerField()
    note = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=10, choices=SOURCES, default="bot")
    # معرّف فريد من خادم الروبوت: إعادة الإرسال لا تضاعف الأرباح
    client_id = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "client_id"], name="uniq_earning_client_id")]
        indexes = [models.Index(fields=["user", "created_at"])]


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=300, blank=True)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class Withdrawal(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="withdrawals")
    method = models.CharField(max_length=40)
    cents = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class SecurityEvent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="security_events")
    event = models.CharField(max_length=160)
    created_at = models.DateTimeField(auto_now_add=True)


class PlaySession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="play_sessions")
    started_at = models.DateTimeField()
    seconds = models.PositiveIntegerField()

    class Meta:
        # TM351: تحليل البيانات كشف جلسات مكررة عند إعادة إرسال المزامنة. المستخدم لا يبدأ جلستين في نفس اللحظة،
        # فـ (المستخدم، وقت البداية) مفتاح طبيعي، والقيد يمنع التكرار ويعمل أيضاً كفهرس لحساب «دقائق اليوم».
        constraints = [models.UniqueConstraint(fields=["user", "started_at"], name="uniq_session_start")]
