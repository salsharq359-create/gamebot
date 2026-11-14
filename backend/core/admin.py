from django.contrib import admin

from .models import (BotStrategy, EarningRecord, GamePlatform, GameTask, Notification, PlaySession, Profile,
                     SecurityEvent, UserGameAccount, Withdrawal)


@admin.register(GamePlatform)
class GamePlatformAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "category", "is_demo", "owner")


@admin.register(GameTask)
class GameTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "platform", "kind", "reward_cents", "minutes", "max_per_day")
    list_filter = ("platform", "kind")


@admin.register(EarningRecord)
class EarningRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "platform", "task", "cents", "source", "created_at")
    list_filter = ("source", "platform")


for model in (Profile, UserGameAccount, BotStrategy, Notification, Withdrawal, SecurityEvent, PlaySession):
    admin.site.register(model)
