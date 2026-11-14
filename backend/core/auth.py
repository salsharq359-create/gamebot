"""
المصادقة (TM255 - الوحدة 2):
- رمز دخول موقّع (HMAC عبر django.core.signing) ينتهي بعد 24 ساعة.
- الرمز يتضمن جزءاً من بصمة كلمة المرور، فيبطل تلقائياً عند تغييرها.
- قفل الحساب 5 دقائق بعد 5 محاولات خاطئة.
- مفتاح داخلي مشترك بين Django وخادم الروبوت لطلبات الروبوت.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.http import JsonResponse
from django.utils import timezone

from .models import Profile, SecurityEvent

TOKEN_MAX_AGE = 24 * 3600
MAX_FAILED = 5
LOCK_MINUTES = 5
SALT = "gamebot.auth.v1"


def log(user, event: str) -> None:
    SecurityEvent.objects.create(user=user, event=event)


def make_token(user) -> str:
    return signing.dumps({"uid": user.pk, "pv": user.password[-12:]}, salt=SALT)


def sync_key(user) -> str:
    """
    مفتاح توقيع سجلات العمل بدون اتصال (TM355 — سلامة البيانات، HMAC-SHA256).
    يُشتق من المفتاح السري للخادم ومعرّف المستخدم وجزء من بصمة كلمة المرور، فلا يُخزَّن في قاعدة البيانات،
    ويتغير تلقائياً عند تغيير كلمة المرور.
    """
    msg = f"gamebot.sync.v1:{user.pk}:{user.password[-12:]}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def user_from_token(token: str):
    try:
        data = signing.loads(token, salt=SALT, max_age=TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None
    user = get_user_model().objects.filter(pk=data.get("uid"), is_active=True).first()
    if not user or not hmac.compare_digest(user.password[-12:], str(data.get("pv"))):
        return None
    return user


def profile_of(user) -> Profile:
    return Profile.objects.get_or_create(user=user)[0]


class AuthError(Exception):
    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


def login_with_lockout(username: str, password: str):
    user = get_user_model().objects.filter(username=username.strip()).first()
    if not user:
        raise AuthError("اسم المستخدم أو كلمة المرور غير صحيحة")
    prof = profile_of(user)
    if prof.is_locked():
        left = int((prof.locked_until - timezone.now()).total_seconds() // 60) + 1
        log(user, "محاولة دخول أثناء قفل الحساب")
        raise AuthError(f"الحساب مقفل مؤقتاً. حاول بعد {left} دقيقة", 423)
    if not user.check_password(password):
        prof.failed_attempts += 1
        if prof.failed_attempts >= MAX_FAILED:
            prof.failed_attempts = 0
            prof.locked_until = timezone.now() + timedelta(minutes=LOCK_MINUTES)
            prof.save()
            log(user, f"قفل الحساب {LOCK_MINUTES} دقائق بعد {MAX_FAILED} محاولات خاطئة")
            raise AuthError(f"تم قفل الحساب {LOCK_MINUTES} دقائق بسبب كثرة المحاولات الخاطئة", 423)
        prof.save()
        log(user, "محاولة دخول بكلمة مرور خاطئة")
        remaining = MAX_FAILED - prof.failed_attempts
        msg = "اسم المستخدم أو كلمة المرور غير صحيحة"
        if remaining <= 2:
            msg += f" (متبقي {remaining} محاولات قبل قفل الحساب)"
        raise AuthError(msg)
    prof.failed_attempts, prof.locked_until = 0, None
    prof.save()
    log(user, "تسجيل دخول ناجح")
    return user


def require_user(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        header = request.headers.get("Authorization", "")
        user = user_from_token(header[7:]) if header.startswith("Bearer ") else None
        if not user:
            return JsonResponse({"error": "مطلوب تسجيل الدخول"}, status=401)
        request.user = user
        return view(request, *args, **kwargs)
    return wrapper


def require_internal(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        key = request.headers.get("X-Internal-Key", "")
        if not hmac.compare_digest(key, settings.INTERNAL_API_KEY):
            return JsonResponse({"error": "forbidden"}, status=403)
        return view(request, *args, **kwargs)
    return wrapper
