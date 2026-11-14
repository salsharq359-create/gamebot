from django.contrib import admin
from django.urls import path

from core import views as v

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", v.health),
    # المصادقة والحساب
    path("api/auth/register/", v.register),
    path("api/auth/login/", v.login),
    path("api/me/", v.me),
    path("api/me/prefs/", v.prefs),
    path("api/me/password/", v.change_password),
    path("api/me/export/", v.export_data),
    path("api/security/events/", v.security_events),
    # مسارات خطة Copilot
    path("api/platforms/", v.platforms),
    path("api/user/accounts/", v.accounts),
    path("api/tasks/", v.tasks),
    path("api/bot/strategy/", v.strategy),
    path("api/bot/offline-sync/", v.offline_sync),
    path("api/earnings/", v.earnings),
    path("api/analytics/", v.analytics),
    path("api/me/export.csv", v.export_csv),
    # السحب والتنبيهات والمتصدرين
    path("api/withdrawals/", v.withdrawals),
    path("api/notifications/", v.notifications),
    path("api/notifications/<int:pk>/read/", v.notifications),
    path("api/leaderboard/", v.leaderboard),
    # مسارات داخلية لخادم الروبوت (python-socketio) (محمية بمفتاح مشترك)
    path("api/internal/earnings/", v.internal_earning),
    path("api/internal/sessions/", v.internal_session),
]
