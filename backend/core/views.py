"""
واجهة REST (JSON) لتطبيق جيم بوت — نفس مسارات خطة Copilot:
  /api/platforms/        عرض الألعاب والمنصات
  /api/user/accounts/    حسابات المستخدم في الألعاب
  /api/tasks/            المهام المتاحة في كل لعبة
  /api/bot/strategy/     اقتراحات الروبوت (المستشار)
  /api/earnings/         أرباح المستخدم
بالإضافة إلى المصادقة والخصوصية والسحب والتنبيهات، ومسارات داخلية لخادم الروبوت.
"""
from __future__ import annotations

import json
import zlib
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import ExtractHour, TruncDate
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .advisor import TaskOption, best_plan
from .contracts import check_invariant
from .sync_rules import OFFLINE_MAX_AGE, Candidate, SyncContext, first_failure, parse_time
from .auth import (AuthError, log, login_with_lockout, make_token, profile_of, require_internal,
                   require_user, sync_key)
from .models import (BotStrategy, EarningRecord, GamePlatform, GameTask, Notification, PlaySession,
                     SecurityEvent, UserGameAccount, Withdrawal)

MAX_MANUAL_CENTS = 100_00   # أعلى مبلغ لسجل يدوي واحد: 100$


# ------------------------------------------------------------------ أدوات
def body(request) -> dict:
    try:
        data = json.loads(request.body or b"{}")
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def err(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def dollars(cents: int) -> float:
    return round((cents or 0) / 100, 2)


def today_start():
    return timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)


def visible_platforms(user):
    return GamePlatform.objects.filter(Q(owner__isnull=True) | Q(owner=user))


def platform_json(p: GamePlatform, linked: bool | None = None) -> dict:
    return {"id": p.id, "key": p.key, "name": p.name, "category": p.category, "algorithm": p.algorithm,
            "description": p.description, "is_demo": p.is_demo, "custom": p.owner_id is not None,
            "linked": linked}


def task_json(t: GameTask) -> dict:
    return {"id": t.id, "platform_id": t.platform_id, "platform": t.platform.name, "key": t.key,
            "title": t.title, "kind": t.kind, "reward_cents": t.reward_cents,
            "reward": dollars(t.reward_cents), "minutes": t.minutes, "max_per_day": t.max_per_day}


def balance_cents(user) -> int:
    earned = EarningRecord.objects.filter(user=user).aggregate(s=Sum("cents"))["s"] or 0
    spent = Withdrawal.objects.filter(user=user).aggregate(s=Sum("cents"))["s"] or 0
    return earned - spent


def lock_user(user):
    """
    TM354: يقفل صف المستخدم حتى نهاية المعاملة (SELECT … FOR UPDATE). كل عملية تقرأ الرصيد أو الحد اليومي
    ثم تكتب بناءً عليه يجب أن تبدأ بهذا القفل، وإلا قرأ طلبان متزامنان نفس القيمة (سباق: فحص ثم تنفيذ).
    """
    return get_user_model().objects.select_for_update().get(pk=user.pk)


def minutes_today(user) -> float:
    secs = PlaySession.objects.filter(user=user, started_at__gte=today_start()).aggregate(
        s=Sum("seconds"))["s"] or 0
    return round(secs / 60, 1)


def notify(user, title: str, body_text: str = "") -> None:
    Notification.objects.create(user=user, title=title, body=body_text)


# ------------------------------------------------------------ المصادقة
@csrf_exempt
@require_http_methods(["POST"])
def register(request):
    data = body(request)
    username, password = str(data.get("username", "")).strip(), str(data.get("password", ""))
    if not (3 <= len(username) <= 40):
        return err("اسم المستخدم يجب أن يكون بين 3 و 40 حرفاً")
    User = get_user_model()
    if User.objects.filter(username=username).exists():
        return err("اسم المستخدم مستخدم من قبل", 409)
    candidate = User(username=username)
    try:
        validate_password(password, candidate)
    except ValidationError as e:
        return err(" ".join(e.messages))
    with transaction.atomic():
        user = User.objects.create_user(username=username, password=password)
        profile_of(user)
        for p in GamePlatform.objects.filter(is_demo=True, owner__isnull=True):
            UserGameAccount.objects.create(user=user, platform=p, linked=p.key != "xo")
    log(user, "إنشاء الحساب")
    notify(user, "مرحباً بك في جيم بوت", "اربط ألعابك ثم اطلب من الروبوت خطة اليوم.")
    return JsonResponse({"token": make_token(user), "username": user.username, "sync_key": sync_key(user)},
                        status=201)


@csrf_exempt
@require_http_methods(["POST"])
def login(request):
    data = body(request)
    try:
        user = login_with_lockout(str(data.get("username", "")), str(data.get("password", "")))
    except AuthError as e:
        return err(str(e), e.status)
    return JsonResponse({"token": make_token(user), "username": user.username, "sync_key": sync_key(user)})


@csrf_exempt
@require_http_methods(["GET", "DELETE"])
@require_user
def me(request):
    user = request.user
    if request.method == "DELETE":
        # الحق في الحذف: حذف الحساب وكل بياناته نهائياً بعد تأكيد كلمة المرور
        if not user.check_password(str(body(request).get("password", ""))):
            return err("كلمة المرور غير صحيحة", 403)
        user.delete()
        return JsonResponse({"deleted": True})
    prof = profile_of(user)
    return JsonResponse({
        "id": user.id, "username": user.username, "joined": user.date_joined.isoformat(),
        "balance_cents": balance_cents(user), "balance": dollars(balance_cents(user)),
        "minutes_today": minutes_today(user),
        "unread_notifications": Notification.objects.filter(user=user, read=False).count(),
        "prefs": {"dark": prof.dark, "text_scale": prof.text_scale,
                  "daily_limit_min": prof.daily_limit_min, "leaderboard": prof.leaderboard},
    })


@csrf_exempt
@require_http_methods(["PATCH", "POST"])
@require_user
def prefs(request):
    data, prof = body(request), profile_of(request.user)
    if "dark" in data:
        prof.dark = bool(data["dark"])
    try:
        if "text_scale" in data:
            prof.text_scale = min(1.4, max(0.9, float(data["text_scale"])))
        if "daily_limit_min" in data:
            prof.daily_limit_min = min(240, max(0, int(data["daily_limit_min"])))
    except (TypeError, ValueError):       # TM354 (قيم الحدود): كان خطأ 500، والصحيح 400
        return err("قيمة رقمية غير صحيحة")
    if "leaderboard" in data:
        prof.leaderboard = bool(data["leaderboard"])
    prof.save()
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
@require_user
def change_password(request):
    data, user = body(request), request.user
    if not user.check_password(str(data.get("old", ""))):
        log(user, "فشل تغيير كلمة المرور")
        return err("كلمة المرور الحالية غير صحيحة", 403)
    try:
        validate_password(str(data.get("new", "")), user)
    except ValidationError as e:
        return err(" ".join(e.messages))
    user.set_password(str(data["new"]))
    user.save()
    log(user, "تغيير كلمة المرور")
    # الرموز القديمة ومفتاح المزامنة القديم يبطلان تلقائياً
    return JsonResponse({"token": make_token(user), "sync_key": sync_key(user)})


@require_http_methods(["GET"])
@require_user
def export_data(request):
    """حق الوصول ونقل البيانات: كل بيانات المستخدم بدون كلمة المرور."""
    u = request.user
    prof = profile_of(u)
    return JsonResponse({
        "exported_at": timezone.now().isoformat(),
        "user": {"username": u.username, "joined": u.date_joined.isoformat()},
        "prefs": {"dark": prof.dark, "text_scale": prof.text_scale,
                  "daily_limit_min": prof.daily_limit_min, "leaderboard": prof.leaderboard},
        "accounts": [{"platform": a.platform.name, "linked": a.linked}
                     for a in UserGameAccount.objects.filter(user=u).select_related("platform")],
        "earnings": [{"platform": e.platform.name if e.platform else None, "cents": e.cents, "note": e.note,
                      "source": e.source, "at": timezone.localtime(e.created_at).isoformat()}
                     for e in EarningRecord.objects.filter(user=u).select_related("platform")],
        "withdrawals": list(Withdrawal.objects.filter(user=u).values("method", "cents", "created_at")),
        "play_sessions": list(PlaySession.objects.filter(user=u).values("started_at", "seconds")),
        "security_events": list(SecurityEvent.objects.filter(user=u).values("event", "created_at")),
    }, json_dumps_params={"ensure_ascii": False, "default": str})


@require_http_methods(["GET"])
@require_user
def security_events(request):
    rows = SecurityEvent.objects.filter(user=request.user).order_by("-id")[:10]
    return JsonResponse({"events": [{"event": r.event, "at": timezone.localtime(r.created_at).isoformat()} for r in rows]})


# ------------------------------------------------------- المنصات والحسابات
@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_user
def platforms(request):
    user = request.user
    if request.method == "POST":
        # منصة يضيفها المستخدم لتتبع أرباحه منها يدوياً (لا يلعبها الروبوت)
        data = body(request)
        name = str(data.get("name", "")).strip()[:80]
        if len(name) < 2:
            return err("اكتب اسم المنصة")
        key = f"u{user.id}-{GamePlatform.objects.filter(owner=user).count() + 1}"
        p = GamePlatform.objects.create(key=key, name=name, category=str(data.get("category", ""))[:40],
                                        description="منصة يتتبعها المستخدم يدوياً", owner=user)
        UserGameAccount.objects.create(user=user, platform=p, linked=True)
        return JsonResponse(platform_json(p, True), status=201)
    linked = dict(UserGameAccount.objects.filter(user=user).values_list("platform_id", "linked"))
    return JsonResponse({"platforms": [platform_json(p, linked.get(p.id, False))
                                       for p in visible_platforms(user).order_by("owner_id", "id")]})


@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_user
def accounts(request):
    user = request.user
    if request.method == "POST":
        data = body(request)
        p = visible_platforms(user).filter(id=data.get("platform_id")).first()
        if not p:
            return err("المنصة غير موجودة", 404)
        acc, _ = UserGameAccount.objects.get_or_create(user=user, platform=p)
        acc.linked = bool(data.get("linked", True))
        acc.nickname = str(data.get("nickname", acc.nickname))[:60]
        acc.save()
    rows = UserGameAccount.objects.filter(user=user).select_related("platform")
    return JsonResponse({"accounts": [{"platform": platform_json(a.platform, a.linked), "nickname": a.nickname}
                                      for a in rows]})


@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_user
def tasks(request):
    user = request.user
    if request.method == "POST":
        data = body(request)
        p = GamePlatform.objects.filter(id=data.get("platform_id"), owner=user).first()
        if not p:
            return err("يمكنك إضافة مهام لمنصاتك أنت فقط", 403)
        try:
            reward = int(round(float(data.get("reward", 0)) * 100))
            minutes = int(data.get("minutes", 0))
        except (TypeError, ValueError):
            return err("قيم غير صحيحة")
        if not (0 < reward <= MAX_MANUAL_CENTS and 0 < minutes <= 240):
            return err("المكافأة يجب أن تكون بين 0.01$ و 100$ والمدة بين 1 و 240 دقيقة")
        t = GameTask.objects.create(platform=p, key=f"t{GameTask.objects.filter(platform=p).count() + 1}",
                                    title=str(data.get("title", "مهمة"))[:120], kind="custom",
                                    reward_cents=reward, minutes=minutes,
                                    max_per_day=max(1, min(20, int(data.get("max_per_day", 1)))))
        return JsonResponse(task_json(t), status=201)
    qs = GameTask.objects.filter(platform__in=visible_platforms(user)).select_related("platform")
    if request.GET.get("platform"):
        qs = qs.filter(platform_id=request.GET["platform"])
    return JsonResponse({"tasks": [task_json(t) for t in qs.order_by("platform_id", "id")]})


# --------------------------------------------------------- المستشار
@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_user
def strategy(request):
    """يقترح أفضل خطة لليوم ضمن الوقت المتاح وحد اللعب اليومي."""
    user = request.user
    prof = profile_of(user)
    try:
        wanted = int(request.GET.get("minutes") or body(request).get("minutes") or 30)
    except (TypeError, ValueError):
        wanted = 30
    left_today = None
    if prof.daily_limit_min:
        left_today = max(0, int(prof.daily_limit_min - minutes_today(user)))
    budget = max(0, min(wanted, 240, left_today if left_today is not None else 240))

    linked_ids = set(UserGameAccount.objects.filter(user=user, linked=True).values_list("platform_id", flat=True))
    done_today = dict(EarningRecord.objects.filter(user=user, created_at__gte=today_start(), task__isnull=False)
                      .values_list("task_id").annotate(n=Count("id")))
    options = [TaskOption(t.id, t.platform.name, t.title, t.reward_cents, t.minutes,
                          max(0, t.max_per_day - done_today.get(t.id, 0)))
               for t in GameTask.objects.filter(platform_id__in=linked_ids).select_related("platform")]
    expected, plan = best_plan(options, budget)
    s = BotStrategy.objects.create(user=user, minutes_budget=budget, expected_cents=expected, plan=plan)
    note = None
    if left_today is not None and left_today < wanted:
        note = f"الخطة محدودة بـ {left_today} دقيقة لأنك قريب من حد اللعب اليومي ({prof.daily_limit_min} دقيقة)."
    return JsonResponse({"id": s.id, "minutes_budget": budget, "expected_cents": expected,
                         "expected": dollars(expected), "plan": plan, "note": note})


# ------------------------------------------------------------ الأرباح
@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_user
def earnings(request):
    user = request.user
    if request.method == "POST":
        # تسجيل ربح يدوي من منصة يتتبعها المستخدم بنفسه
        data = body(request)
        p = GamePlatform.objects.filter(id=data.get("platform_id"), owner=user).first()
        if not p:
            return err("التسجيل اليدوي متاح لمنصاتك المضافة فقط", 403)
        try:
            cents = int(round(float(data.get("amount", 0)) * 100))
        except (TypeError, ValueError):
            return err("مبلغ غير صحيح")
        if not 0 < cents <= MAX_MANUAL_CENTS:
            return err("المبلغ يجب أن يكون بين 0.01$ و 100$")
        task = GameTask.objects.filter(id=data.get("task_id"), platform=p).first()
        # client_id اختياري: إذا أُرسل نفس السجل مرتين (مثلاً من طابور بدون اتصال) لا يتكرر الربح
        try:
            with transaction.atomic():
                EarningRecord.objects.create(user=user, platform=p, task=task, cents=cents, source="manual",
                                             note=str(data.get("note", ""))[:200],
                                             client_id=str(data.get("client_id", ""))[:64] or None)
        except IntegrityError:
            pass
    now = timezone.localtime()
    start = today_start()
    qs = EarningRecord.objects.filter(user=user)
    days = _daily_cents(qs, start, 7)     # TM351: استعلام واحد (GROUP BY) بدل 7 استعلامات
    by_platform = [{"platform": r["platform__name"] or "أخرى", "cents": r["s"]}
                   for r in qs.values("platform__name").annotate(s=Sum("cents")).order_by("-s")]
    recent = [{"platform": e.platform.name if e.platform else "", "cents": e.cents, "note": e.note,
               "source": e.source, "at": timezone.localtime(e.created_at).isoformat()}
              for e in qs.select_related("platform").order_by("-id")[:15]]
    return JsonResponse({
        "balance_cents": balance_cents(user),
        "today_cents": qs.filter(created_at__gte=start).aggregate(s=Sum("cents"))["s"] or 0,
        "week_cents": qs.filter(created_at__gte=start - timedelta(days=6)).aggregate(s=Sum("cents"))["s"] or 0,
        "last_7_days": days, "by_platform": by_platform, "recent": recent, "as_of": now.isoformat(),
    })


@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_user
def withdrawals(request):
    user = request.user
    if request.method == "POST":
        data = body(request)
        method = str(data.get("method", "")).strip()
        if method not in ("محفظة إلكترونية", "تحويل بنكي", "بطاقات هدايا"):
            return err("طريقة سحب غير معروفة")
        try:
            cents = int(round(float(data.get("amount", 0)) * 100))
        except (TypeError, ValueError):
            return err("مبلغ غير صحيح")
        if cents <= 0:
            return err("أدخل مبلغاً أكبر من صفر")
        with transaction.atomic():
            lock_user(user)       # TM354: بدون القفل نجحت 5 طلبات متزامنة لكامل الرصيد فصار سالباً
            if cents > balance_cents(user):
                return err("الرصيد غير كافٍ")
            Withdrawal.objects.create(user=user, method=method, cents=cents)
            check_invariant(balance_cents(user) >= 0, "الرصيد لا يصبح سالباً أبداً")
        log(user, f"طلب سحب {dollars(cents):.2f}$ عبر {method}")
        notify(user, "تم تسجيل طلب السحب", f"{dollars(cents):.2f}$ عبر {method} (محاكاة)")
    rows = Withdrawal.objects.filter(user=user).order_by("-id")[:10]
    return JsonResponse({"balance_cents": balance_cents(user),
                         "withdrawals": [{"method": w.method, "cents": w.cents, "at": timezone.localtime(w.created_at).isoformat()}
                                         for w in rows]})


@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_user
def notifications(request, pk: int | None = None):
    if request.method == "POST":
        Notification.objects.filter(user=request.user, **({"pk": pk} if pk else {})).update(read=True)
    rows = Notification.objects.filter(user=request.user).order_by("-id")[:30]
    return JsonResponse({"notifications": [{"id": n.id, "title": n.title, "body": n.body, "read": n.read,
                                            "at": timezone.localtime(n.created_at).isoformat()} for n in rows]})


@require_http_methods(["GET"])
def leaderboard(request):
    rows = (get_user_model().objects.filter(profile__leaderboard=True)
            .annotate(total=Sum("earnings__cents")).order_by("-total")[:10])
    return JsonResponse({"top": [{"username": u.username, "cents": u.total or 0} for u in rows]})


@require_http_methods(["GET"])
def health(request):
    return JsonResponse({"ok": True, "time": timezone.now().isoformat()})


# --------------------------------------- مزامنة ما لُعب بدون اتصال (TM255 - الوحدة 1)
_parse_time = parse_time


MAX_SYNC_BODY = 256 * 1024          # أكبر حجم مضغوط نقبله
MAX_SYNC_JSON = 2 * 1024 * 1024     # أكبر حجم بعد فك الضغط (حماية من «قنبلة الضغط»)


def _sync_payload(request):
    """
    TM355: التطبيق يرسل الطابور مضغوطاً بـ DEFLATE (zlib)، ومعه CRC-32 للبايتات كما أُرسلت.
    إذا لم يطابق الـ CRC نرفض الطلب بـ 400 ويعيد التطبيق الإرسال (ARQ).
    يرجع (البيانات، None) أو (None، رد الخطأ).
    """
    raw = request.body or b""
    if len(raw) > MAX_SYNC_BODY:
        return None, err("حجم المزامنة كبير جداً", 413)
    crc = request.headers.get("X-Payload-CRC32")
    if crc is not None:
        try:
            expected = int(crc, 16)
        except ValueError:
            expected = -1
        if zlib.crc32(raw) != expected:
            r = JsonResponse({"error": "فشل التحقق من سلامة البيانات (CRC-32)، أعد الإرسال", "crc_failed": True},
                             status=400)
            return None, r
    if request.headers.get("Content-Encoding", "").lower() == "deflate":
        try:
            d = zlib.decompressobj()
            raw = d.decompress(raw, MAX_SYNC_JSON)
            if d.unconsumed_tail:
                return None, err("حجم المزامنة كبير جداً", 413)
        except zlib.error:
            return None, err("بيانات مضغوطة غير صالحة")
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        return None, err("JSON غير صالح")
    return (data if isinstance(data, dict) else {}), None


def _log_sessions(user, sessions: list, now) -> None:
    for s in sessions:
        started = _parse_time(s.get("started_at")) if isinstance(s, dict) else None
        try:
            seconds = max(0, min(6 * 3600, int(s.get("seconds", 0))))
        except (TypeError, ValueError, AttributeError):
            continue
        if started and now - started <= OFFLINE_MAX_AGE:      # إعادة الإرسال لا تكرر الجلسة (قيد التفرد)
            PlaySession.objects.get_or_create(user=user, started_at=started, defaults={"seconds": seconds})


def _accept(user, c: Candidate) -> str | None:
    """ينشئ سجل الربح. المبلغ من جدول المهام دائماً. يرجع "duplicate" إذا سبقه طلب آخر بنفس client_id."""
    try:
        with transaction.atomic():
            EarningRecord.objects.create(user=user, platform=c.task.platform, task=c.task, cents=c.task.reward_cents,
                                         note=(str(c.raw.get("note", ""))[:180] + " (بدون اتصال)").strip(),
                                         source="bot", client_id=c.client_id, created_at=c.played)
    except IntegrityError:
        return "duplicate"
    return None


@csrf_exempt
@require_http_methods(["POST"])
@require_user
def offline_sync(request):
    """
    التطبيق يلعب على الجهاز عند انقطاع الاتصال، ويحفظ نتائج المهام في طابور.
    عند عودة الاتصال يرسلها هنا دفعة واحدة. الخادم لا يثق بالتطبيق:
      - المبلغ من جدول المهام فقط، والألعاب يجب أن تكون مرتبطة
      - حد المرات اليومي لكل مهمة يُحسب حسب يوم اللعب الفعلي
      - السجلات الأقدم من 7 أيام أو بتاريخ مستقبلي تُرفض
      - client_id فريد: إعادة الإرسال لا تضاعف الأرباح
      - (TM355) الطلب مضغوط ومعه CRC-32، وكل سجل موقّع بـ HMAC-SHA256 بمفتاح المزامنة
    """
    user = request.user
    data, problem = _sync_payload(request)
    if problem:
        return problem
    records, sessions = data.get("records") or [], data.get("sessions") or []
    if not isinstance(records, list) or not isinstance(sessions, list) or len(records) > 500 or len(sessions) > 50:
        return err("حجم المزامنة كبير جداً")
    ctx = SyncContext(user=user, key=sync_key(user), linked=set(
        UserGameAccount.objects.filter(user=user, linked=True).values_list("platform_id", flat=True)))
    now = ctx.now
    result = {"accepted": 0, "duplicates": 0, "rejected": 0, "bad_mac": 0, "processed_ids": [], "accepted_cents": 0,
              "reasons": {}}
    with transaction.atomic():
        lock_user(user)          # TM354: طلبا مزامنة متزامنان لا يتجاوزان الحد اليومي معاً
        for r in records:
            c = Candidate(raw=r)
            reason = first_failure(c, ctx)
            if reason != "malformed":
                result["processed_ids"].append(c.client_id)
            if reason is None:
                reason = _accept(user, c)
            if reason == "duplicate":
                result["duplicates"] += 1
            elif reason:
                result["rejected"] += 1
                result["reasons"][reason] = result["reasons"].get(reason, 0) + 1
            else:
                result["accepted"] += 1
                result["accepted_cents"] += c.task.reward_cents
    result["bad_mac"] = result["reasons"].get("bad_mac", 0)
    _log_sessions(user, sessions, now)
    if result["accepted"]:
        notify(user, "تمت مزامنة الأرباح", f"{result['accepted']} مهام لُعبت بدون اتصال: "
                                           f"+{dollars(result['accepted_cents']):.2f}$ (محاكاة)")
    result["balance_cents"] = balance_cents(user)
    return JsonResponse(result)


# ------------------------------------------------------- التحليلات (TM351)
def _daily_cents(qs, start, n: int) -> list[dict]:
    """أرباح كل يوم من آخر n أيام بتوقيت المستخدم، باستعلام GROUP BY واحد، مع أيام بلا أرباح = 0."""
    first = start - timedelta(days=n - 1)
    tz = timezone.get_current_timezone()
    sums = {r["day"]: r["s"] for r in qs.filter(created_at__gte=first)
            .annotate(day=TruncDate("created_at", tzinfo=tz)).values("day").annotate(s=Sum("cents"))}
    return [{"date": (first + timedelta(days=i)).date().isoformat(),
             "cents": sums.get((first + timedelta(days=i)).date(), 0)} for i in range(n)]


@require_http_methods(["GET"])
@require_user
def analytics(request):
    """
    لوحة «تحليلاتي»: كل رقم هنا استعلام SQL تجميعي واحد (GROUP BY) تولّده Django ORM،
    ويستفيد من الفهرس (user_id, created_at) ومن قيد التفرد (user_id, started_at) على الجلسات.
    """
    user = request.user
    try:
        n = max(7, min(60, int(request.GET.get("days", 14))))
    except ValueError:
        n = 14
    start = today_start()
    first = start - timedelta(days=n - 1)
    tz = timezone.get_current_timezone()
    earn = EarningRecord.objects.filter(user=user, created_at__gte=first)
    daily = _daily_cents(EarningRecord.objects.filter(user=user), start, n)
    by_game = [{"game": r["platform__name"] or "أخرى", "cents": r["s"], "records": r["n"]}
               for r in earn.values("platform__name").annotate(s=Sum("cents"), n=Count("id")).order_by("-s")]
    channel = earn.aggregate(
        online=Sum("cents", filter=Q(source="bot") & ~Q(client_id__startswith="off-")),
        offline=Sum("cents", filter=Q(client_id__startswith="off-")),
        manual=Sum("cents", filter=Q(source="manual")))
    sess = PlaySession.objects.filter(user=user, started_at__gte=first)
    totals = sess.aggregate(n=Count("id"), avg=Avg("seconds"), total=Sum("seconds"))
    hours = {r["h"]: r["n"] for r in sess.annotate(h=ExtractHour("started_at", tzinfo=tz))
             .values("h").annotate(n=Count("id"))}
    per_day = {r["day"]: r["s"] for r in sess.annotate(day=TruncDate("started_at", tzinfo=tz))
               .values("day").annotate(s=Sum("seconds"))}
    limit = profile_of(user).daily_limit_min
    best = max(daily, key=lambda d: d["cents"])
    return JsonResponse({
        "days": n, "daily": daily, "by_game": by_game,
        "channel": {k: v or 0 for k, v in channel.items()},
        "sessions": {"count": totals["n"], "avg_seconds": round(totals["avg"] or 0, 1),
                     "total_minutes": round((totals["total"] or 0) / 60, 1)},
        "by_hour": [hours.get(h, 0) for h in range(24)],
        "active_days": len(per_day),
        "days_over_limit": sum(1 for s in per_day.values() if limit and s / 60 >= limit),
        "daily_limit_min": limit,
        "best_day": best if best["cents"] else None,
        "total_cents": sum(d["cents"] for d in daily),
    })


@require_http_methods(["GET"])
@require_user
def export_csv(request):
    """حق نقل البيانات: أرباحي كملف CSV يُفتح في Excel أو pandas (TM351 — جمع البيانات)."""
    import csv
    from django.http import HttpResponse
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="gamebot-earnings.csv"'
    resp.write("\ufeff")                     # حتى يقرأ Excel العربية بشكل صحيح
    w = csv.writer(resp)
    w.writerow(["date_time", "platform", "task", "dollars", "source", "offline"])
    for at, pname, tkey, cents, src, cid in EarningRecord.objects.filter(user=request.user).order_by("created_at") \
            .values_list("created_at", "platform__name", "task__key", "cents", "source", "client_id").iterator():
        w.writerow([timezone.localtime(at).isoformat(timespec="seconds"), pname or "", tkey or "", f"{cents / 100:.2f}",
                    src, int(bool(cid and cid.startswith("off-")))])
    return resp


# --------------------------------------------- مسارات داخلية لخادم الروبوت
@csrf_exempt
@require_http_methods(["POST"])
@require_internal
def internal_earning(request):
    """
    خادم الروبوت يبلّغ عن مهمة أنجزها الروبوت. Django هو من يحدد المبلغ من جدول المهام،
    فلا يستطيع أي طرف آخر أن يرسل مبلغاً من عنده. وكل سجل له client_id فريد يمنع التكرار.
    """
    data = body(request)
    user = get_user_model().objects.filter(pk=data.get("user_id")).first()
    if not user:
        return err("user not found", 404)
    task = GameTask.objects.filter(platform__key=data.get("platform"), platform__owner__isnull=True,
                                   platform__is_demo=True, key=data.get("task")).select_related("platform").first()
    if not task:
        return err("unknown task", 404)
    if not UserGameAccount.objects.filter(user=user, platform=task.platform, linked=True).exists():
        return err("game not linked", 403)
    client_id = str(data.get("client_id", ""))[:64] or None
    try:
        with transaction.atomic():
            lock_user(user)
            done = EarningRecord.objects.filter(user=user, task=task, created_at__gte=today_start()).count()
            if done >= task.max_per_day:
                return JsonResponse({"accepted": False, "reason": "daily_limit", "task": task.title}, status=409)
            EarningRecord.objects.create(user=user, platform=task.platform, task=task, cents=task.reward_cents,
                                         note=str(data.get("note", ""))[:200], source="bot", client_id=client_id)
    except IntegrityError:
        return JsonResponse({"accepted": False, "reason": "duplicate"})
    return JsonResponse({"accepted": True, "cents": task.reward_cents, "balance_cents": balance_cents(user)})


@csrf_exempt
@require_http_methods(["POST"])
@require_internal
def internal_session(request):
    data = body(request)
    user = get_user_model().objects.filter(pk=data.get("user_id")).first()
    if not user:
        return err("user not found", 404)
    try:
        seconds = max(0, min(6 * 3600, int(data.get("seconds", 0))))
        cents = int(data.get("session_cents", 0))
    except (TypeError, ValueError):
        return err("seconds و session_cents يجب أن تكون أرقاماً")
    started = timezone.now() - timedelta(seconds=seconds)
    if data.get("started_at"):
        try:
            started = datetime.fromisoformat(str(data["started_at"]).replace("Z", "+00:00"))
        except ValueError:
            pass
    PlaySession.objects.get_or_create(user=user, started_at=started, defaults={"seconds": seconds})
    notify(user, "انتهت جلسة الروبوت", f"أرباح الجلسة {dollars(cents):.2f}$ في {seconds / 60:.1f} دقيقة (محاكاة)")
    prof = profile_of(user)
    if prof.daily_limit_min and minutes_today(user) >= prof.daily_limit_min:
        notify(user, "وقت للاستراحة", f"وصلت إلى حد اللعب اليومي ({prof.daily_limit_min} دقيقة).")
    return JsonResponse({"ok": True, "minutes_today": minutes_today(user)})
