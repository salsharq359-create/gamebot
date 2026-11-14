"""
TM354: شاشات «الحساب» الفرعية (الحسابات المرتبطة، التنبيهات، الأمان، الخصوصية، المظهر، اللعب الصحي، المتصدرين،
المساعدة، السياسة) نُقلت من GameBotApp. كل دالة تأخذ التطبيق وسيطاً (app) وتستخدم واجهته العامة فقط.
"""
from __future__ import annotations

import json

import flet as ft

from ..client import money
from ..ui import (LIME, NAVY, C, S, T, Theme, card, label_style, note, outline, primary, stat, strength, textfield,
                 title)


def show_accounts(app):
    d = app.guard(lambda: app.api.get("/api/user/accounts/")) or {"accounts": []}

    def toggle(pid):
        def h(e):
            res = app.guard(lambda: app.api.post("/api/user/accounts/",
                                                   {"platform_id": pid, "linked": e.control.value}))
            if res is not None:
                app._remember_linked(res)
                app.toast("تم الحفظ")
        return h
    rows = [card(ft.Row([
        ft.Column([T(a["platform"]["name"], 16, ft.FontWeight.W_900),
                   T("منصة تتبعها يدوياً" if a["platform"]["custom"]
                     else f"خوارزمية الروبوت: {a['platform']['algorithm']}", 12, color=C("MUTED"))],
                  spacing=0, expand=True),
        ft.Switch(value=a["platform"]["linked"], active_color=NAVY, active_track_color=LIME,
                  on_change=toggle(a["platform"]["id"]), tooltip=f"ربط {a['platform']['name']}")]))
        for a in d["accounts"]]
    app.set_screen("accounts", "ربط الألعاب", rows + [
        note("الروبوت يلعب فقط الألعاب التجريبية الموجودة داخل التطبيق، ولا يتصل بألعاب حقيقية أو بحسابات خارجية.")],
        back=app.back_to_account)


def show_notifications(app):
    d = app.guard(lambda: app.api.post("/api/notifications/")) or {"notifications": []}
    app.guard(app.refresh_me)
    items = [card(ft.Column([T(n["title"], 14, ft.FontWeight.W_900), *([T(n["body"], 13)] if n["body"] else []),
                             T(n["at"].replace("T", " ")[:16], 11, color=C("MUTED"))], spacing=2))
             for n in d["notifications"]]
    app.set_screen("notifications", "التنبيهات", items or [note("لا توجد تنبيهات.")], back=app.back_to_account)


def show_security(app):
    old = textfield("كلمة المرور الحالية", ft.Icons.LOCK_OUTLINE, password=True)
    new = textfield("كلمة المرور الجديدة", ft.Icons.KEY, password=True)
    hint = T("قوة كلمة المرور: -", 12, ft.FontWeight.BOLD, C("MUTED"))

    def on_new(_):
        hint.value = f"قوة كلمة المرور: {strength(new.value or '')[1]}"
        app.page.update()
    new.on_change = on_new

    def change(_):
        d = app.guard(lambda: app.api.post("/api/me/password/", {"old": old.value or "", "new": new.value or ""}))
        if d:
            app.api.token = d["token"]   # الرموز القديمة تبطل تلقائياً
            app.sync_key = d.get("sync_key")
            if app.queue and app.sync_key:
                app.queue.rekey(new.value or "", app.sync_key)   # TM355: مفتاح تشفير وتوقيع جديدان
            app.page.run_task(app.socket.connect, app.api.token)
            app.toast("تم تغيير كلمة المرور")
            app.show_security()

    events = app.guard(lambda: app.api.get("/api/security/events/")) or {"events": []}
    policies = [
        ("كلمات المرور مشفّرة", "PBKDF2-SHA256 في Django، ولا تُحفظ كلمة المرور نفسها أبداً"),
        ("حظر كلمات المرور الشائعة", "قائمة Django بعشرين ألف كلمة شائعة، حسب إرشادات NIST الحديثة"),
        ("قفل الحساب", "بعد 5 محاولات خاطئة يُقفل الحساب 5 دقائق"),
        ("خروج تلقائي", "بعد 10 دقائق بدون نشاط"),
        ("رموز دخول موقّعة", "تنتهي بعد 24 ساعة، وتبطل تلقائياً عند تغيير كلمة المرور"),
        ("الخادم لا يثق بالتطبيق", "Django يحدد مبلغ كل مهمة ويرفض التكرار والمبالغ المزوّرة"),
    ]
    app.set_screen("security", "الأمان", [
        card(ft.Column([ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, color=C("OK"), size=S(20)),
                                ft.Column([T(a, 14, ft.FontWeight.W_900), T(b, 12, color=C("MUTED"))],
                                          spacing=0, expand=True)]) for a, b in policies], spacing=10)),
        title("تغيير كلمة المرور"), old, new, hint, primary("تغيير كلمة المرور", change, ft.Icons.KEY),
        title("السجل الأمني (آخر 10 أحداث)"),
        *[card(ft.Row([T(e["event"], 13, ft.FontWeight.BOLD, expand=True),
                       T(e["at"].replace("T", " ")[5:16], 11, color=C("MUTED"))]), padding=10)
          for e in events["events"]],
    ], back=app.back_to_account)


def show_privacy(app):
    result = T("", 12, color=C("MUTED"), selectable=True)

    def export(_):
        data = app.guard(lambda: app.api.get("/api/me/export/"))
        if data is None:
            return
        import os
        path = os.path.join(os.path.expanduser("~"), f"GameBot-data-{data['user']['username']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        result.value = f"تم حفظ بياناتك في:\n{path}"
        app.page.update()

    def delete(_):
        pwd = textfield("كلمة المرور للتأكيد", ft.Icons.LOCK, password=True)

        def go():
            if app.guard(lambda: app.api.delete("/api/me/", {"password": pwd.value or ""})) is not None:
                app.logout(message="تم حذف حسابك وكل بياناتك نهائياً.")
        app.confirm("حذف الحساب نهائياً", "سيتم حذف حسابك وكل أرباحك وسجلاتك من الخادم، ولا يمكن التراجع.",
                     go, "حذف نهائي", danger=True, extra=pwd)

    stored = ["اسم المستخدم (بدون بريد أو رقم هاتف)", "كلمة المرور مشفّرة فقط", "الأرباح وعمليات السحب (محاكاة)",
              "مدة جلسات اللعب لحساب الحد اليومي", "الأحداث الأمنية مثل تسجيل الدخول", "إعداداتك وتفضيلاتك"]
    app.set_screen("privacy", "الخصوصية وبياناتي", [
        title("ما البيانات المحفوظة؟"), card(ft.Column([T("• " + s, 14) for s in stored], spacing=4)),
        note("لا نجمع موقعك ولا جهات اتصالك ولا نعرض إعلانات. الظهور في لوحة المتصدرين اختياري."),
        primary("تصدير بياناتي (JSON)", export, ft.Icons.DOWNLOAD), result,
        outline("حذف حسابي وكل بياناتي", delete, ft.Icons.DELETE_FOREVER, C("ERROR")),
    ], back=app.back_to_account)


def show_appearance(app):
    app.set_screen("appearance", "المظهر وسهولة الاستخدام", [
        card(ft.Switch(label="الوضع الداكن", value=Theme.dark, active_track_color=LIME, active_color=NAVY,
                       label_text_style=label_style(),
                       on_change=lambda e: app._set_pref("dark", bool(e.control.value), app.show_appearance))),
        title("حجم الخط"),
        card(ft.Column([
            ft.Slider(min=0.9, max=1.4, divisions=5, value=Theme.scale, label="{value}", active_color=C("INK"),
                      thumb_color=C("INK"), on_change_end=lambda e: app._set_pref(
                          "text_scale", round(float(e.control.value), 1), app.show_appearance)),
            T(f"الحجم الحالي: {round(Theme.scale * 100)}٪", 13, ft.FontWeight.BOLD, C("MUTED")),
            T("هذا نص تجريبي لمعاينة حجم الخط.", 16)], spacing=4)),
        note("مبادئ التصميم: ألوان بتباين واضح، أزرار كبيرة سهلة اللمس، دعم العربية من اليمين لليسار، "
             "تلميحات للأيقونات، ونوافذ تأكيد قبل الإجراءات المهمة."),
    ], back=app.back_to_account)


def show_wellbeing(app):
    used, limit = app.me.get("minutes_today", 0), app.prefs.get("daily_limit_min", 60)

    def label(v):
        return "بدون حد" if not v else f"{int(v)} دقيقة يومياً"
    limit_text = T("الحد: " + label(limit), 13, ft.FontWeight.BOLD, C("MUTED"))

    def on_change(e):
        limit_text.value = "الحد: " + label(e.control.value)
        app.page.update()

    def on_end(e):
        app._set_pref("daily_limit_min", int(e.control.value), lambda: app.toast("تم حفظ حد اللعب اليومي"))

    app.set_screen("wellbeing", "اللعب الصحي", [
        ft.Row([stat("وقت اللعب اليوم", f"{used:g} دقيقة"), stat("الحد اليومي", label(limit))], spacing=10),
        title("حد اللعب اليومي"),
        card(ft.Column([ft.Slider(min=0, max=180, divisions=12, value=limit, label="{value}", active_color=C("INK"),
                                  thumb_color=C("INK"), on_change=on_change, on_change_end=on_end), limit_text],
                       spacing=0)),
        title("لماذا هذا مهم؟"),
        card(ft.Column([T(s, 13) for s in [
            "• التطبيقات التي تعد بالأرباح قد تدفع للاستخدام المفرط، لذلك نذكّرك عند تجاوز حدك.",
            "• منظمة الصحة العالمية تصنّف «اضطراب الألعاب» في ICD-11.",
            "• الروبوت لا يلعب في الألعاب الحقيقية لأن ذلك مخالف لشروطها، ولا يشاهد إعلانات بدلاً عنك.",
            "• كل الأرباح هنا محاكاة تعليمية وليست دخلاً حقيقياً."]], spacing=6)),
    ], back=app.back_to_account)


def show_leaderboard(app):
    d = app.guard(lambda: app.api.get("/api/leaderboard/")) or {"top": []}
    rows = [card(ft.Row([T(f"{i}. {r['username']}", 14, ft.FontWeight.BOLD, expand=True),
                         T(money(r["cents"]), 14, ft.FontWeight.W_900)]), padding=12)
            for i, r in enumerate(d["top"], 1)]
    app.set_screen("leaderboard", "لوحة المتصدرين", [
        card(ft.Switch(label="أظهر اسمي ومجموع أرباحي (اختياري)", value=bool(app.prefs.get("leaderboard")),
                       active_track_color=LIME, active_color=NAVY, label_text_style=label_style(),
                       on_change=lambda e: app._set_pref("leaderboard", bool(e.control.value),
                                                          app.show_leaderboard))),
        *(rows or [note("لا يوجد مشاركون بعد.")]),
    ], back=app.back_to_account)


def show_help(app):
    faqs = [
        ("كيف يربح الروبوت؟", "كل لعبة يلعبها الروبوت تعطيك 1$ (محاكاة)، مع مكافأة يومية وتحديات وبطولة."),
        ("ما الفرق بين المستشار والروبوت؟", "المستشار يقترح أفضل خطة لوقتك من كل ألعابك ومنصاتك. الروبوت ينفّذ "
                                           "الألعاب التجريبية داخل التطبيق فقط."),
        ("كيف يلعب الروبوت؟", "جمع العملات: أقصر طريق (BFS). تخمين الرقم: البحث الثنائي. إكس أو: Minimax."),
        ("كيف يختار المستشار الخطة؟", "يحل مسألة «حقيبة الظهر» بالبرمجة الديناميكية: أعلى ربح ضمن الوقت المتاح "
                                      "وحد اللعب اليومي."),
        ("لماذا قُفل حسابي؟", "بعد 5 محاولات دخول خاطئة يُقفل الحساب 5 دقائق لحمايته."),
        ("هل السحب حقيقي؟", "لا، هذا مشروع تعليمي والسحب يُسجَّل فقط."),
    ]
    app.set_screen("help", "المساعدة", [
        ft.ExpansionTile(title=T(q, 15, ft.FontWeight.W_900), bgcolor=C("CARD"), collapsed_bgcolor=C("CARD"),
                         icon_color=C("INK"), collapsed_icon_color=C("INK"),
                         shape=ft.RoundedRectangleBorder(radius=16),
                         collapsed_shape=ft.RoundedRectangleBorder(radius=16),
                         controls=[ft.Container(T(a, 13, color=C("MUTED")), padding=ft.Padding(16, 0, 16, 14))])
        for q, a in faqs], back=app.back_to_account)


def show_policy(app):
    sections = [
        ("1. البيانات التي نجمعها", "اسم المستخدم، كلمة المرور مشفّرة، الأرباح المحاكاة، مدة اللعب، والأحداث الأمنية."),
        ("2. لماذا نجمعها", "لتشغيل حسابك وحساب أرباحك وحمايته من الاختراق ومساعدتك على اللعب بشكل صحي."),
        ("3. أين تُحفظ", "على خادم التطبيق (Django). جهازك لا يحفظ كلمة المرور."),
        ("4. المشاركة", "لا نبيع بياناتك ولا نشاركها. لوحة المتصدرين تعرض اسمك وأرباحك فقط إذا فعّلتها."),
        ("5. حقوقك", "تصدير كل بياناتك أو حذف حسابك نهائياً في أي وقت من «الخصوصية وبياناتي»."),
        ("6. الأمان", "تشفير كلمات المرور، قفل الحساب، خروج تلقائي، رموز موقّعة، واتصال HTTPS عند النشر."),
        ("7. الأرباح", "كل الأرباح والسحوبات محاكاة تعليمية ولا تمثل أموالاً حقيقية."),
    ]
    app.set_screen("policy", "سياسة الخصوصية", [card(ft.Column([
        ft.Column([T(a, 15, ft.FontWeight.W_900), T(b, 13, color=C("MUTED"))], spacing=2) for a, b in sections],
        spacing=14))], back=app.back_to_account)
