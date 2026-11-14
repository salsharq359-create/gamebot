"""
تطبيق جيم بوت بلغة بايثون (Flet) — يتصل بخادم Django (REST) وخادم الروبوت (python-socketio).
الشاشات: تسجيل الدخول، الرئيسية، المستشار، الروبوت المباشر، الأرباح والسحب، والحساب بشاشاته الفرعية.
"""
from __future__ import annotations

import asyncio
import os
import random
from datetime import date, datetime, timedelta

import flet as ft

from .client import Api, ApiError, BotSocket, money
from .engine.bot import BotSession, State, run_session
from .offline import OfflineQueue, QueueLocked
from .tm355.framecodec import Decoder
from .screens import account_screens, course_labs
from .ui import (GAME_COLORS, GOLD, LIME, NAVY, C, S, T, Theme, balance_card, card, label_style, menu_item, note, outline,
                 primary, robot_logo, stat, strength, textfield, title)

IDLE_MINUTES = 10
TABS = ["الرئيسية", "المستشار", "الروبوت", "الأرباح", "الحساب"]
DAY_NAMES = ["اثنين", "ثلاثاء", "أربعاء", "خميس", "جمعة", "سبت", "أحد"]
DEFAULT_REWARDS = {"round": 100, "daily": 50, "streak": 100, "tournament": 200}   # بالسنت، تُحدَّث من الخادم


REJECT_REASONS = {"daily_limit": "تجاوزت الحد اليومي", "too_old": "أقدم من 7 أيام", "future": "بتاريخ مستقبلي",
                  "bad_time": "وقت غير صالح", "unknown_task": "مهمة غير معروفة", "not_linked": "لعبة غير مرتبطة",
                  "bad_mac": "توقيع غير صحيح", "malformed": "سجل تالف"}


def sync_message(res: dict) -> str:
    """
    TM354 (R-SYNC-3): كانت الرسالة تخمّن «تجاوزت الحد اليومي أو قديمة» لكل رفض. الخادم صار يرسل سبب كل رفض
    (سلسلة القواعد في sync_rules.py)، فتعرض الرسالة الأسباب الفعلية.
    """
    msg = f"تمت المزامنة: قُبلت {res['accepted']} مهام (+{money(res['accepted_cents'])})"
    if res["rejected"]:
        why = "، ".join(f"{REJECT_REASONS.get(k, k)}: {n}" for k, n in sorted(res.get("reasons", {}).items()))
        msg += f"، ورُفضت {res['rejected']}" + (f" ({why})" if why else "")
    if res["manual"]:
        msg += f"، و{res['manual']} أرباح يدوية"
    return msg


class GameBotApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.api = Api()
        self.socket = BotSocket()
        self.me: dict | None = None
        self.current = ""
        self.last_active = datetime.now()
        self.minutes = 30
        self.plan: dict | None = None
        # حالة جلسة الروبوت (تصل عبر Socket.io)
        # TM354: آلة حالات صريحة بدل ثلاثة متغيرات منطقية (bot_running و local_running و local_stop)
        self.session = BotSession()
        self.bot_status = ""
        self.bot_progress = 0.0
        self.session_cents = 0
        self.board: list[str] | None = None
        self.bot_log: list[str] = []
        self.rounds = 3
        self.tasks = {"daily": True, "challenges": True, "tournament": False}
        # العمل بدون اتصال (TM255 - الوحدة 1)
        self.queue: OfflineQueue | None = None
        self.rewards = dict(DEFAULT_REWARDS)
        self.linked_games: list[str] = []
        self.api_latency: float | None = None
        self.loop_started = False
        # TM355: فك إطارات الفروق، وإحصاءات آخر جلسة
        self.frame_decoder = Decoder()
        self.last_frames: dict | None = None
        self.lab_mod, self.lab_ebn0, self.lab_p = "QPSK", 8.0, 0.01
        self.sync_key: str | None = None

        page.title = "جيم بوت"
        page.rtl = True
        page.padding = 0
        page.fonts = {"Cairo": "fonts/Cairo.ttf"}
        page.theme = ft.Theme(font_family="Cairo", color_scheme_seed=NAVY)
        page.dark_theme = ft.Theme(font_family="Cairo", color_scheme_seed=NAVY)
        try:
            page.window.width, page.window.height = 420, 860
        except Exception:
            pass
        for event, handler in [("bot_started", self.on_bot_started), ("bot_event", self.on_bot_event),
                               ("earning", self.on_earning), ("bot_done", self.on_bot_done),
                               ("bot_error", self.on_bot_error)]:
            self.socket.on(event, handler)
        self.socket.on_status = self.on_socket_status
        self.apply_theme()
        self.show_login()

    # ================================================================ أدوات
    @property
    def prefs(self) -> dict:
        return (self.me or {}).get("prefs", {})

    def apply_theme(self):
        Theme.apply(self.prefs.get("dark", False), self.prefs.get("text_scale", 1.0))
        self.page.theme_mode = ft.ThemeMode.DARK if Theme.dark else ft.ThemeMode.LIGHT
        self.page.bgcolor = C("BG")
        self.nav = ft.NavigationBar(
            selected_index=getattr(self, "nav", None).selected_index if hasattr(self, "nav") else 0,
            on_change=lambda e: self.go(e.control.selected_index), bgcolor=C("SURFACE"), indicator_color=LIME,
            destinations=[
                ft.NavigationBarDestination(icon=ft.Icons.HOME_OUTLINED, label=TABS[0]),
                ft.NavigationBarDestination(icon=ft.Icons.LIGHTBULB_OUTLINE, label=TABS[1]),
                ft.NavigationBarDestination(icon=ft.Icons.SMART_TOY_OUTLINED, label=TABS[2]),
                ft.NavigationBarDestination(icon=ft.Icons.BAR_CHART, label=TABS[3]),
                ft.NavigationBarDestination(icon=ft.Icons.PERSON_OUTLINE, label=TABS[4]),
            ])

    def refresh_me(self):
        self.me = self.api.get("/api/me/")
        old = (Theme.dark, Theme.scale)
        if old != (bool(self.prefs.get("dark")), float(self.prefs.get("text_scale", 1.0))):
            self.apply_theme()

    def set_screen(self, name: str, header: str | None, body: list[ft.Control], with_nav=True, back=None):
        # خروج تلقائي بعد مدة عدم نشاط (TM255 - الوحدة 2)
        if self.me and not self.bot_running and datetime.now() - self.last_active > timedelta(minutes=IDLE_MINUTES):
            self.logout(message="تم تسجيل خروجك تلقائياً بعد 10 دقائق من عدم النشاط.")
            return
        self.last_active = datetime.now()
        self.current = name
        controls: list[ft.Control] = []
        if header:
            row = [title(header, 22)]
            if back:
                row = [ft.IconButton(ft.Icons.ARROW_BACK, icon_color=C("INK"), tooltip="رجوع",
                                     on_click=lambda _: back()), title(header, 22), ft.Container(width=40)]
            if with_nav and not back:
                row = [title(header, 22), ft.Container(expand=True), self.net_chip()]
            controls.append(ft.Row(row, alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
        controls.extend(body)
        self.page.controls.clear()
        self.page.navigation_bar = self.nav if with_nav else None
        self.page.add(ft.SafeArea(expand=True, minimum_padding=ft.Padding(18, 12, 18, 12), content=ft.Column(
            controls, spacing=12, expand=True, scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH)))
        self.page.update()

    def toast(self, text: str):
        self.page.show_dialog(ft.SnackBar(content=ft.Text(text, size=S(15), color=ft.Colors.WHITE), bgcolor=NAVY,
                                          rtl=True))

    def confirm(self, heading: str, message: str, on_yes, yes="تأكيد", no="إلغاء", danger=False,
                extra: ft.Control | None = None):
        """نافذة تأكيد قبل الإجراءات المهمة (TM255 - الوحدة 3: منع الأخطاء)."""
        def yes_click(_):
            self.page.pop_dialog()
            on_yes()
        content = [T(message, 15)] + ([extra] if extra else [])
        self.page.show_dialog(ft.AlertDialog(
            modal=True, rtl=True, bgcolor=C("SURFACE"), title=T(heading, 19, ft.FontWeight.W_900),
            content=ft.Column(content, tight=True, spacing=12, width=320),
            actions=[ft.TextButton(content=no, on_click=lambda _: self.page.pop_dialog(),
                                   style=ft.ButtonStyle(color=C("INK"))),
                     ft.FilledButton(content=yes, on_click=yes_click, style=ft.ButtonStyle(
                         bgcolor=C("ERROR") if danger else C("BTN_BG"),
                         color=ft.Colors.WHITE if danger else C("BTN_FG")))]))

    def guard(self, fn):
        """ينفّذ طلباً للخادم ويعرض رسالة الخطأ بدل أن يتوقف التطبيق."""
        try:
            return fn()
        except ApiError as e:
            self.toast(str(e))
            return None

    def go(self, index: int):
        self.nav.selected_index = index
        [self.show_home, self.show_advisor, self.show_bot, self.show_earnings, self.show_account][index]()

    def net_chip(self) -> ft.Container:
        on = self.socket.connected
        pending = self.queue.size if self.queue else 0
        color = C("OK") if on else C("ERROR")
        text = "متصل" if on else "بدون اتصال"
        if pending:
            text += f" • {pending} بانتظار المزامنة"
        return ft.Container(
            ft.Row([ft.Icon(ft.Icons.CLOUD_DONE_OUTLINED if on else ft.Icons.CLOUD_OFF, color=color, size=S(18)),
                    T(text, 12, ft.FontWeight.BOLD, color)], spacing=4, tight=True),
            padding=ft.Padding(10, 4, 10, 4), border_radius=999, border=ft.Border.all(1, color),
            tooltip="الشبكة والمزامنة", on_click=lambda _: self.show_network())

    # ======================================================= تسجيل الدخول
    def show_login(self, register: bool = False, message: str = ""):
        user = textfield("اسم المستخدم", ft.Icons.PERSON_OUTLINE)
        pwd = textfield("كلمة المرور", ft.Icons.LOCK_OUTLINE, password=True)
        error = T(message, 14, ft.FontWeight.BOLD, C("MUTED") if message else C("ERROR"))
        bar = ft.ProgressBar(value=0, color=C("ERROR"), bgcolor=C("TRACK"), height=8, border_radius=4,
                             visible=register)
        hint = T("قوة كلمة المرور: -", 12, ft.FontWeight.BOLD, C("MUTED"), visible=register)

        def on_change(_):
            if register:
                score, name = strength(pwd.value or "")
                bar.value = max(score, 0.3) / 4 if pwd.value else 0
                bar.color = [C("ERROR"), C("ERROR"), GOLD, C("OK"), C("OK")][score]
                hint.value = f"قوة كلمة المرور: {name} — الأطول أفضل، جرّب عبارة من عدة كلمات"
                self.page.update()

        def submit(_):
            path = "/api/auth/register/" if register else "/api/auth/login/"
            try:
                data = self.api.post(path, {"username": (user.value or "").strip(), "password": pwd.value or ""})
                self.api.token = data["token"]
                self.sync_key = data.get("sync_key")
                self.refresh_me()
            except ApiError as e:
                error.value, error.color = str(e), C("ERROR")
                self.page.update()
                return
            self.last_active = datetime.now()
            self.apply_theme()
            self.open_queue(pwd.value or "")
            self.cache_offline_data()
            self.api_latency = self.api.health()
            self.page.run_task(self.socket.connect, self.api.token)
            if not self.loop_started:
                self.loop_started = True
                self.page.run_task(self.sync_loop)
            self.go(0)

        pwd.on_change, pwd.on_submit = on_change, submit
        self.set_screen("login", None, [
            ft.Container(height=24),
            ft.Row([robot_logo(110)], alignment=ft.MainAxisAlignment.CENTER),
            T("جيم بوت", 40, ft.FontWeight.W_900, text_align=ft.TextAlign.CENTER),
            T("روبوت يلعب ويقترح عليك أفضل خطة", 16, ft.FontWeight.BOLD, C("MUTED"), text_align=ft.TextAlign.CENTER),
            ft.Container(height=10),
            title("إنشاء حساب جديد" if register else "تسجيل الدخول", 20),
            user, pwd, bar, hint, error,
            primary("إنشاء الحساب" if register else "تسجيل الدخول", submit),
            outline("لدي حساب، تسجيل الدخول" if register else "إنشاء حساب", lambda _: self.show_login(not register)),
            T("لحمايتك: يُقفل الحساب 5 دقائق بعد 5 محاولات خاطئة.", 12, color=C("MUTED"),
              text_align=ft.TextAlign.CENTER),
        ], with_nav=False)

    def open_queue(self, password: str) -> None:
        """طابور الجهاز مشفّر بمفتاح من كلمة المرور (TM355). إذا تعذّر فكه نحتفظ بنسخة ونبدأ طابوراً جديداً."""
        try:
            self.queue = OfflineQueue(self.me["username"], password=password, sync_key=self.sync_key)
        except QueueLocked:
            old = OfflineQueue.path_for(self.me["username"])
            os.replace(old, old + f".locked-{datetime.now():%Y%m%d%H%M%S}")
            self.queue = OfflineQueue(self.me["username"], password=password, sync_key=self.sync_key)
            self.toast("تعذّر فك تشفير الطابور القديم (كلمة مرور مختلفة أو ملف معدّل)، فحُفظ جانباً.")

    def logout(self, message: str = ""):
        self.page.run_task(self.socket.disconnect)
        if self.session.can("stop"):
            self.session.fire("stop")          # جلسة على الجهاز تتوقف عند الحركة التالية
        self.api.token, self.me, self.bot_log, self.queue = None, None, [], None
        self.apply_theme()
        self.show_login(message=message)

    # =========================================================== الرئيسية
    def show_home(self):
        acc = self.guard(lambda: self.api.get("/api/user/accounts/"))
        if acc is not None:
            self._remember_linked(acc)
            self.guard(self.refresh_me)
        acc = acc or {"accounts": []}
        used, limit = self.me.get("minutes_today", 0), self.prefs.get("daily_limit_min", 0)
        tiles = []
        for a in acc["accounts"]:
            pl = a["platform"]
            tiles.append(card(ft.Row([
                ft.Container(ft.Icon(ft.Icons.EDIT_NOTE if pl["custom"] else ft.Icons.SPORTS_ESPORTS, color=NAVY),
                             width=40, height=40, border_radius=12, bgcolor=GAME_COLORS.get(pl["key"], LIME),
                             alignment=ft.Alignment.CENTER),
                ft.Column([T(pl["name"], 16, ft.FontWeight.W_900),
                           T("منصة تتبعها يدوياً" if pl["custom"] else f"الروبوت يلعبها • {pl['algorithm']}", 12,
                             color=C("MUTED"))], spacing=0, expand=True),
                T("مرتبطة" if pl["linked"] else "غير مرتبطة", 12, ft.FontWeight.BOLD,
                  C("INK") if pl["linked"] else C("MUTED")),
            ], spacing=12), on_click=lambda _: self.show_accounts()))
        usage = []
        if limit:
            usage = [card(ft.Column([
                T(f"وقت اللعب اليوم: {used:g} من {limit} دقيقة", 13, ft.FontWeight.BOLD),
                ft.ProgressBar(value=min(used / limit, 1), color=C("ERROR") if used >= limit else C("OK"),
                               bgcolor=C("TRACK"), height=8, border_radius=4)], spacing=6), padding=12)]
        unread = self.me.get("unread_notifications", 0)
        pending = []
        if self.queue and self.queue.size:
            pending = [note(f"لديك {self.queue.size} سجلات لُعبت أو سُجّلت بدون اتصال، وستُرسل للخادم تلقائياً "
                            "عند عودة الاتصال.")]
        self.set_screen("home", TABS[0], [
            *pending,
            T(f"أهلاً {self.me['username']}" + (f" • لديك {unread} تنبيهات جديدة" if unread else ""), 14,
              ft.FontWeight.BOLD, C("MUTED")),
            balance_card("رصيد الأرباح", self.me["balance_cents"],
                         "الروبوت يعمل الآن" if self.bot_running else "الروبوت جاهز للعمل"),
            *usage, title("ألعابي"), *tiles,
            primary("اطلب خطة اليوم من المستشار", lambda _: self.go(1), ft.Icons.LIGHTBULB_OUTLINE),
            outline("تشغيل الروبوت", lambda _: self.go(2), ft.Icons.PLAY_ARROW),
        ])

    # ============================================================ المستشار
    def show_advisor(self):
        minutes_text = T(f"الوقت المتاح: {self.minutes} دقيقة", 15, ft.FontWeight.W_900)

        def slide(e):
            self.minutes = int(e.control.value)
            minutes_text.value = f"الوقت المتاح: {self.minutes} دقيقة"
            self.page.update()

        def ask(_):
            plan = self.guard(lambda: self.api.get("/api/bot/strategy/", {"minutes": self.minutes}))
            if plan is not None:
                self.plan = plan
                self.show_advisor()

        body = [
            T("أخبر المستشار كم دقيقة لديك اليوم، وسيختار أفضل مجموعة مهام من ألعابك ومنصاتك.", 14, color=C("MUTED")),
            card(ft.Column([minutes_text, ft.Slider(min=5, max=120, divisions=23, value=self.minutes, label="{value}",
                                                    active_color=C("INK"), thumb_color=C("INK"), on_change=slide)],
                           spacing=0)),
            primary("اقترح خطة اليوم", ask, ft.Icons.AUTO_AWESOME),
        ]
        if self.plan:
            p = self.plan
            body += [ft.Row([stat("الربح المتوقع", money(p["expected_cents"])),
                             stat("الوقت المستخدم", f"{p['minutes_budget']} دقيقة")], spacing=10)]
            if p.get("note"):
                body.append(note(p["note"]))
            if not p["plan"]:
                body.append(note("لا توجد مهام متاحة الآن. اربط لعبة، أو أضف منصة ومهامها، أو جرّب غداً."))
            for i, s in enumerate(p["plan"], 1):
                body.append(card(ft.Row([
                    ft.Container(T(i, 14, ft.FontWeight.W_900, LIME), width=32, height=32, border_radius=16,
                                 bgcolor=NAVY, alignment=ft.Alignment.CENTER),
                    ft.Column([T(f"{s['platform']}: {s['title']} × {s['times']}", 14, ft.FontWeight.W_900),
                               T(f"{s['total_minutes']} دقيقة • {s['reason']}", 12, color=C("MUTED"))],
                              spacing=0, expand=True),
                    T(money(s["total_cents"]), 14, ft.FontWeight.W_900)], spacing=12)))
            if p["plan"]:
                body.append(outline("دع الروبوت ينفّذ مهام الألعاب التجريبية", lambda _: self.go(2),
                                    ft.Icons.SMART_TOY_OUTLINED))
            body.append(note("الروبوت ينفّذ فقط الألعاب التجريبية داخل التطبيق. مهام منصاتك الأخرى تنفذها أنت ثم "
                             "تسجّل أرباحها يدوياً. المستشار لا يدخل حساباتك ولا يلعب عنك في أي منصة خارجية."))
        body += [title("منصاتي الخاصة"), *self.custom_platforms()]
        self.set_screen("advisor", TABS[1], body)

    def custom_platforms(self) -> list[ft.Control]:
        platforms = self.guard(lambda: self.api.get("/api/platforms/")) or {"platforms": []}
        tasks = self.guard(lambda: self.api.get("/api/tasks/")) or {"tasks": []}
        mine = [p for p in platforms["platforms"] if p["custom"]]
        out: list[ft.Control] = []
        if not mine:
            out.append(T("أضف منصة تلعب فيها بنفسك، ثم أضف مهامها (المكافأة والمدة)، وسيضمّها المستشار إلى خطتك.", 13,
                         color=C("MUTED")))
        for pl in mine:
            lines = [T(f"• {t['title']}: {money(t['reward_cents'])} / {t['minutes']} دقيقة "
                       f"(حتى {t['max_per_day']} مرات يومياً)", 13)
                     for t in tasks["tasks"] if t["platform_id"] == pl["id"]]
            out.append(card(ft.Column([
                T(pl["name"], 16, ft.FontWeight.W_900), *lines,
                ft.Row([ft.TextButton(content="+ إضافة مهمة", on_click=lambda _, pid=pl["id"]: self.add_task(pid),
                                      style=ft.ButtonStyle(color=C("INK"))),
                        ft.TextButton(content="$ تسجيل ربح", on_click=lambda _, pid=pl["id"]: self.add_earning(pid),
                                      style=ft.ButtonStyle(color=C("INK")))], wrap=True)], spacing=4)))
        out.append(outline("إضافة منصة", lambda _: self.add_platform(), ft.Icons.ADD))
        return out

    def _post_then(self, path: str, body: dict, done: str, after):
        if self.guard(lambda: self.api.post(path, body)) is not None:
            self.toast(done)
            after()

    def add_platform(self):
        name = textfield("اسم المنصة", ft.Icons.VIDEOGAME_ASSET_OUTLINED)
        self.confirm("منصة جديدة", "اسم المنصة أو اللعبة التي تتبع أرباحك منها.",
                     lambda: self._post_then("/api/platforms/", {"name": (name.value or "").strip()},
                                             "تمت إضافة المنصة", self.show_advisor), "إضافة", extra=name)

    def add_task(self, platform_id: int):
        t, r, m = textfield("اسم المهمة", ft.Icons.TASK_ALT), textfield("المكافأة بالدولار", ft.Icons.ATTACH_MONEY), \
            textfield("المدة بالدقائق", ft.Icons.TIMER_OUTLINED)
        n = textfield("أقصى عدد مرات في اليوم", ft.Icons.REPEAT, value="1")

        def go():
            try:
                body = {"platform_id": platform_id, "title": (t.value or "").strip(), "reward": float(r.value or 0),
                        "minutes": int(m.value or 0), "max_per_day": int(n.value or 1)}
            except ValueError:
                self.toast("أدخل أرقاماً صحيحة")
                return
            self._post_then("/api/tasks/", body, "تمت إضافة المهمة", self.show_advisor)
        self.confirm("مهمة جديدة", "أدخل المكافأة كما تعرفها من المنصة، والمدة التي تستغرقها.", go, "إضافة",
                     extra=ft.Column([t, r, m, n], tight=True, spacing=8))

    def add_earning(self, platform_id: int):
        a = textfield("المبلغ بالدولار", ft.Icons.ATTACH_MONEY)

        def go():
            try:
                amount = float(a.value or 0)
            except ValueError:
                self.toast("أدخل مبلغاً صحيحاً")
                return
            try:
                self.api.post("/api/earnings/", {"platform_id": platform_id, "amount": amount})
                self.toast("تم تسجيل الربح")
            except ApiError as e:
                if e.status == 0 and self.queue:
                    self.queue.add_manual(platform_id, amount)   # يُرسل لاحقاً
                    self.toast("لا يوجد اتصال: حُفظ الربح على جهازك وسيُرسل عند عودة الاتصال")
                else:
                    self.toast(str(e))
        self.confirm("تسجيل ربح", "سجّل مبلغاً ربحته بنفسك من هذه المنصة.", go, "تسجيل", extra=a)

    # ====================================================== الروبوت المباشر
    def show_bot(self):
        if self.bot_running or self.bot_log:
            return self.show_bot_live()
        labels = {"daily": "جمع المكافأة اليومية لكل لعبة", "challenges": "إكمال التحديات (3 انتصارات متتالية)",
                  "tournament": "المشاركة في البطولة (2$ للجولة)"}

        def toggle(key):
            def h(e):
                self.tasks[key] = bool(e.control.value)
            return h
        rounds_text = T(f"{self.rounds} جولات لكل لعبة مرتبطة • كل لعبة = 1$", 13, ft.FontWeight.BOLD, C("MUTED"))

        def slide(e):
            self.rounds = int(e.control.value)
            rounds_text.value = f"{self.rounds} جولات لكل لعبة مرتبطة • كل لعبة = 1$"
            self.page.update()

        self.set_screen("bot", TABS[2], [
            title("مهام الروبوت"),
            card(ft.Column([ft.Checkbox(label=v, value=self.tasks[k], on_change=toggle(k), active_color=C("INK"),
                                        check_color=C("BG"), label_style=label_style()) for k, v in labels.items()],
                           spacing=2)),
            title("مدة العمل"),
            card(ft.Column([ft.Slider(min=1, max=10, divisions=9, value=self.rounds, label="{value}",
                                      active_color=C("INK"), thumb_color=C("INK"), on_change=slide), rounds_text],
                           spacing=0)),
            primary("تشغيل الروبوت", self.start_bot, ft.Icons.PLAY_ARROW),
            note("الروبوت يلعب الألعاب التجريبية داخل التطبيق فقط، لأن البوتات في الألعاب الحقيقية مخالفة لشروطها. "
                 "والأرباح محاكاة تعليمية."),
        ])

    async def start_bot(self, _=None):
        used, limit = self.me.get("minutes_today", 0), self.prefs.get("daily_limit_min", 0)
        if limit and used >= limit:
            self.confirm("وقت للاستراحة", f"لعبت اليوم {used:g} دقيقة وتجاوزت حدّك اليومي ({limit} دقيقة). "
                         "ننصحك بأخذ استراحة.", lambda: self.page.run_task(self._start_now), "متابعة على أي حال",
                         no="استراحة")
            return
        await self._start_now()

    async def _start_now(self):
        if not self.socket.connected:
            # العمل بدون اتصال: الروبوت يلعب على الجهاز، والنتائج تُحفظ في الطابور
            if not self.linked_games:
                self.toast("لا توجد ألعاب مرتبطة محفوظة على الجهاز. اتصل بالإنترنت مرة واحدة أولاً.")
                return
            self.confirm("لا يوجد اتصال", "خادم الروبوت غير متاح الآن. هل تريد أن يلعب الروبوت على جهازك؟ "
                         "ستُحفظ النتائج وتُرسل للخادم عند عودة الاتصال، والخادم يتحقق منها.",
                         lambda: self.page.run_task(self.run_local), "العب على جهازي")
            return
        try:
            res = await self.socket.call("start_bot", {"rounds": self.rounds, "tasks": self.tasks, "delta": True})
        except Exception as e:
            self.toast(str(e))
            return
        if not res.get("ok"):
            self.toast(res.get("error", "تعذّر تشغيل الروبوت"))

    def show_bot_live(self):
        self.ui_status = T(self.bot_status, 17, ft.FontWeight.W_900, text_align=ft.TextAlign.CENTER)
        self.ui_progress = ft.ProgressBar(value=self.bot_progress, color=LIME, bgcolor=C("TRACK"), height=12,
                                          border_radius=6)
        self.ui_progress_text = T(f"إنجاز المهام {round(self.bot_progress * 100)}٪", 13, ft.FontWeight.BOLD,
                                  C("MUTED"))
        self.ui_session = T(f"أرباح الجلسة: {money(self.session_cents)}", 13, ft.FontWeight.BOLD)
        self.ui_board = ft.Container(padding=8, bgcolor=C("CARD"), border_radius=14, visible=False)
        self.ui_log = ft.Column([T("• " + x, 13, ft.FontWeight.W_600) for x in self.bot_log], spacing=4, height=200,
                                scroll=ft.ScrollMode.AUTO)
        self.draw_board()
        action = outline("إيقاف الروبوت", lambda _: self.stop_bot(), ft.Icons.PAUSE) if self.bot_running else \
            primary("جلسة جديدة", lambda _: (self.bot_log.clear(), self.show_bot()), ft.Icons.REPLAY)
        heading = ("الروبوت يعمل على جهازك" if self.local_running else "الروبوت يعمل") if self.bot_running \
            else "انتهت الجلسة"
        self.set_screen("bot", heading, [
            ft.Row([ft.Container(width=110, height=110, border_radius=55, bgcolor=NAVY, border=ft.Border.all(6, LIME),
                                 alignment=ft.Alignment.CENTER,
                                 content=ft.Icon(ft.Icons.SMART_TOY_OUTLINED, color=LIME, size=60))],
                   alignment=ft.MainAxisAlignment.CENTER),
            self.ui_status, self.ui_progress,
            ft.Row([self.ui_progress_text, self.ui_session], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([self.ui_board], alignment=ft.MainAxisAlignment.CENTER),
            title("سجل الروبوت", 16), card(self.ui_log, padding=10), action,
        ])

    @property
    def bot_running(self) -> bool:
        return self.session.active

    @property
    def local_running(self) -> bool:
        return self.session.active and self.session.local

    def stop_bot(self):
        if self.local_running:
            self.session.fire("stop")
        else:
            self.page.run_task(self.socket.emit, "stop_bot", {})

    async def run_local(self):
        """جلسة روبوت على الجهاز بدون اتصال: نفس المحرك، والمهام تُحفظ في الطابور."""
        self.session.start(local=True)
        started = datetime.now().astimezone()
        await self.on_bot_started({})
        pending = 0
        for ev in run_session(self.linked_games, self.rounds, self.tasks, random.Random(),
                              stopped=lambda: self.session.stop_requested):
            if ev["type"] == "task":
                self.queue.add_record(ev["platform"], ev["task"], ev["note"])
                cents = self.rewards.get(ev["task"], 100)
                pending += cents
                await self.on_earning({"pending": True, "note": ev["note"], "cents": cents, "session_cents": pending})
                await asyncio.sleep(0.35)
            else:
                await self.on_bot_event(ev)
                await asyncio.sleep(0.12 if ev["type"] == "move" else 0 if ev["type"] == "progress" else 0.35)
        seconds = round((datetime.now().astimezone() - started).total_seconds())
        if self.queue:
            self.queue.add_session(started, seconds)
        await self.on_bot_done({"session_cents": pending, "seconds": seconds, "offline": True})

    def draw_board(self):
        if not self.board:
            self.ui_board.visible = False
            return
        colors = {".": ft.Colors.WHITE, "#": "#7A84A8", "$": GOLD, "R": LIME}
        self.ui_board.visible = True
        self.ui_board.content = ft.Column([ft.Row([
            ft.Container(width=26, height=26, border_radius=6, bgcolor=colors.get(ch, ft.Colors.WHITE),
                         border=ft.Border.all(1, "#DDE4F5"), alignment=ft.Alignment.CENTER,
                         content=ft.Icon(ft.Icons.SMART_TOY, size=18, color=NAVY) if ch == "R" else None)
            for ch in row], spacing=3, tight=True, rtl=False) for row in self.board], spacing=3, tight=True)

    def _log(self, text: str):
        self.bot_log.insert(0, text)
        del self.bot_log[60:]
        if self.current == "bot" and hasattr(self, "ui_log"):
            self.ui_log.controls.insert(0, T("• " + text, 13, ft.FontWeight.W_600))
            del self.ui_log.controls[60:]

    # ------------------------------------------------------ أحداث Socket.io
    async def on_socket_status(self, connected: bool):
        if not connected and self.session.active and not self.session.local:
            # TM354: الخادم يوقف الروبوت عند انقطاع آخر اتصال، ورسالة «انتهت الجلسة» لن تصل.
            # قبل آلة الحالات كانت الشاشة تبقى على «الروبوت يعمل» إلى الأبد، ويتعطل الخروج التلقائي.
            self.session.fire("connection_lost")
            self.bot_status = "انقطع الاتصال فتوقف الروبوت"
            self._log("انقطع الاتصال: أوقف الخادم الروبوت، والأرباح التي ظهرت محفوظة")
            if self.current == "bot":
                self.show_bot_live()
        if self.me and self.current in ("home", "advisor", "earnings", "account"):
            self.go(TABS.index({"home": "الرئيسية", "advisor": "المستشار", "earnings": "الأرباح",
                                "account": "الحساب"}[self.current]))

    async def on_bot_started(self, data):
        if not self.session.active:
            self.session.start()
        self.bot_progress, self.session_cents, self.board = 0.0, 0, None
        self.bot_status, self.bot_log = "يبدأ الروبوت ...", []
        self.nav.selected_index = 2
        self.show_bot_live()

    async def on_bot_event(self, e):
        kind = e.get("type")
        if kind == "game":
            self.bot_status, self.board = e["text"], None
            self.frame_decoder.board = None
            self._log(e["text"])
        elif kind == "move":
            if "frame" in e:                       # TM355: إطار مفتاحي أو إطار فروق
                board = self.frame_decoder.decode(e["frame"])
                if board is not None:
                    self.board = board
            else:
                self.board = e["board"]
        elif kind == "log":
            self._log(e["text"])
        elif kind == "progress":
            self.bot_progress = float(e["value"])
        if self.current == "bot" and hasattr(self, "ui_status"):
            self.ui_status.value = self.bot_status
            self.ui_progress.value = self.bot_progress
            self.ui_progress_text.value = f"إنجاز المهام {round(self.bot_progress * 100)}٪"
            self.draw_board()
            self.page.update()

    async def on_earning(self, e):
        self.session_cents = e.get("session_cents", self.session_cents)
        if e.get("pending"):
            self._log(f"{e['note']} (+{money(e['cents'])} بانتظار المزامنة)")
        elif e.get("accepted"):
            self._log(f"{e['note']} (+{money(e['cents'])})")
            if self.me and e.get("balance_cents") is not None:
                self.me["balance_cents"] = e["balance_cents"]
        else:
            reason = "وصلت للحد اليومي لهذه المهمة" if e.get("reason") == "daily_limit" else "لم تُحتسب"
            self._log(f"{e['note']} — {reason}")
        if self.current == "bot" and hasattr(self, "ui_session"):
            self.ui_session.value = f"أرباح الجلسة: {money(self.session_cents)}"
            self.page.update()

    async def on_bot_done(self, e):
        if not self.session.active:          # وصلت متأخرة بعد انقطاع الاتصال: الحالة النهائية سُجلت
            return
        if e.get("stopped") and self.session.can("stop"):
            self.session.fire("stop")
        self.session.fire("done")
        if e.get("frames"):
            self.last_frames = e["frames"]
        self.bot_status = "أوقفت الروبوت" if self.session.state is State.STOPPED else "انتهت الجلسة"
        self._log(f"انتهت الجلسة: {money(e['session_cents'])} في {e['seconds'] / 60:.1f} دقيقة")
        if e.get("offline"):
            self._log("الأرباح محفوظة على جهازك وستُرسل للخادم عند عودة الاتصال")
        self.last_active = datetime.now()
        try:
            self.refresh_me()
        except ApiError:
            pass
        if self.current == "bot":
            self.show_bot_live()

    async def on_bot_error(self, e):
        if self.session.can("error"):
            self.session.fire("error")
        self._log(f"خطأ: {e.get('error')}")
        if self.current == "bot":
            self.show_bot_live()

    # ============================================================ الأرباح
    def show_earnings(self):
        d = self.guard(lambda: self.api.get("/api/earnings/"))
        if d is None:
            return self.set_screen("earnings", TABS[3], [note("تعذّر تحميل الأرباح."), primary(
                "إعادة المحاولة", lambda _: self.show_earnings())])
        days = d["last_7_days"]
        peak = max([x["cents"] for x in days] + [1])
        bars = [ft.Column([
            T(f"{x['cents'] / 100:g}$", 10, color=C("MUTED")),
            ft.Container(width=26, height=4 + 120 * x["cents"] / peak, border_radius=6,
                         bgcolor=LIME if i == len(days) - 1 else C("INK"), tooltip=f"{x['date']}: {money(x['cents'])}"),
            T(DAY_NAMES[date.fromisoformat(x["date"]).weekday()], 10, ft.FontWeight.BOLD),
        ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.END)
            for i, x in enumerate(days)]
        self.set_screen("earnings", TABS[3], [
            balance_card("الرصيد المتاح", d["balance_cents"]),
            ft.Row([stat("اليوم", money(d["today_cents"])), stat("آخر 7 أيام", money(d["week_cents"]))], spacing=10),
            title("أرباح الأسبوع (دولار)"),
            card(ft.Row(bars, alignment=ft.MainAxisAlignment.SPACE_AROUND,
                        vertical_alignment=ft.CrossAxisAlignment.END, height=190)),
            title("حسب المنصة"),
            *([card(ft.Row([T(r["platform"], 15, ft.FontWeight.BOLD, expand=True),
                            T(money(r["cents"]), 15, ft.FontWeight.W_900)]), padding=12) for r in d["by_platform"]]
              or [T("لا توجد أرباح بعد. شغّل الروبوت!", 14, color=C("MUTED"))]),
            primary("سحب الأرباح", lambda _: self.show_withdraw(), ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED),
            outline("تحليلاتي", lambda _: self.show_analytics(), ft.Icons.INSIGHTS),
            title("آخر العمليات"),
            *[card(ft.Row([ft.Icon(ft.Icons.EDIT_NOTE if r["source"] == "manual" else ft.Icons.SMART_TOY_OUTLINED,
                                   size=S(20), color=C("MUTED")),
                           T(r["note"] or r["platform"], 13, expand=True),
                           T(f"+{money(r['cents'])}", 13, ft.FontWeight.W_900)], spacing=8), padding=10)
              for r in d["recent"]],
        ])

    def show_withdraw(self):
        d = self.guard(lambda: self.api.get("/api/withdrawals/")) or {"balance_cents": 0, "withdrawals": []}
        methods = ft.RadioGroup(value="محفظة إلكترونية", content=ft.Column([
            ft.Radio(value=m, label=m, active_color=C("INK"), label_style=label_style())
            for m in ("محفظة إلكترونية", "تحويل بنكي", "بطاقات هدايا")], spacing=0))
        amount = textfield("المبلغ بالدولار", ft.Icons.ATTACH_MONEY, keyboard_type=ft.KeyboardType.NUMBER)

        def submit(_):
            try:
                value = float(amount.value or 0)
            except ValueError:
                self.toast("أدخل مبلغاً صحيحاً")
                return

            def do():
                if self.guard(lambda: self.api.post("/api/withdrawals/", {"method": methods.value, "amount": value})):
                    self.toast("تم تسجيل طلب السحب (محاكاة)")
                    self.show_withdraw()
            self.confirm("تأكيد السحب", f"سحب {value:.2f}$ عبر {methods.value}؟", do, "سحب")

        self.set_screen("withdraw", "سحب الأرباح", [
            balance_card("الرصيد المتاح", d["balance_cents"]), title("طريقة السحب"), card(methods), amount,
            primary("سحب الأرباح", submit, ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED),
            T("هذا مشروع تعليمي: السحب يُسجَّل في قاعدة البيانات فقط ولا يرسل أموالاً حقيقية.", 12, color=C("MUTED")),
            *[card(ft.Row([T(w["method"], 14, ft.FontWeight.BOLD, expand=True), T(w["at"][:10], 12, color=C("MUTED")),
                           T(money(w["cents"]), 14, ft.FontWeight.W_900)]), padding=10) for w in d["withdrawals"]],
        ], back=self.show_earnings)

    # ============================================================= الحساب
    def show_account(self):
        unread = (self.me or {}).get("unread_notifications", 0)
        self.set_screen("account", TABS[4], [
            menu_item(ft.Icons.WIFI, "الشبكة والمزامنة", "قياسات الاتصال والعمل بدون إنترنت",
                      lambda _: self.show_network()),
            menu_item(ft.Icons.INSIGHTS, "تحليلاتي", "أرباحك وأوقات لعبك بالأرقام، وتصدير CSV",
                      lambda _: self.show_analytics()),
            menu_item(ft.Icons.ACCOUNT_TREE_OUTLINED, "مختبر M269", "المسار الأمثل، Dijkstra و A*، الترتيب",
                      lambda _: self.show_m269()),
            menu_item(ft.Icons.SCIENCE_OUTLINED, "مختبر TM355", "الضغط، تصحيح الأخطاء، القناة، الشبكات، التشفير",
                      lambda _: self.show_lab()),
            menu_item(ft.Icons.LINK, "ربط الألعاب", "اختر الألعاب التي يلعبها الروبوت", lambda _: self.show_accounts()),
            menu_item(ft.Icons.NOTIFICATIONS_NONE, "التنبيهات",
                      f"{unread} تنبيهات جديدة" if unread else "تنبيهات الروبوت", lambda _: self.show_notifications()),
            menu_item(ft.Icons.SHIELD_OUTLINED, "الأمان", "كلمة المرور، قفل الحساب، السجل الأمني",
                      lambda _: self.show_security()),
            menu_item(ft.Icons.PRIVACY_TIP_OUTLINED, "الخصوصية وبياناتي", "تصدير بياناتك أو حذف حسابك",
                      lambda _: self.show_privacy()),
            menu_item(ft.Icons.PALETTE_OUTLINED, "المظهر وسهولة الاستخدام", "الوضع الداكن وحجم الخط",
                      lambda _: self.show_appearance()),
            menu_item(ft.Icons.FAVORITE_OUTLINE, "اللعب الصحي", "حد اللعب اليومي والاستخدام المسؤول",
                      lambda _: self.show_wellbeing()),
            menu_item(ft.Icons.EMOJI_EVENTS_OUTLINED, "لوحة المتصدرين", "اختياري ومغلق افتراضياً",
                      lambda _: self.show_leaderboard()),
            menu_item(ft.Icons.HELP_OUTLINE, "المساعدة", "أسئلة شائعة وكيف يعمل الروبوت", lambda _: self.show_help()),
            menu_item(ft.Icons.DESCRIPTION_OUTLINED, "سياسة الخصوصية", "ما البيانات التي نجمعها ولماذا",
                      lambda _: self.show_policy()),
            outline("تسجيل الخروج", lambda _: self.confirm("تسجيل الخروج", "هل تريد تسجيل الخروج من حسابك؟",
                                                            self.logout, "خروج"), ft.Icons.LOGOUT, C("ERROR")),
        ])

    def back_to_account(self):
        self.nav.selected_index = 4
        self.show_account()

    def show_accounts(self):
        return account_screens.show_accounts(self)

    # ------------------------------------------- الشبكة والمزامنة (الوحدة 1)
    def _remember_linked(self, acc: dict) -> None:
        self.linked_games = [a["platform"]["key"] for a in acc.get("accounts", [])
                             if a["platform"]["linked"] and a["platform"]["is_demo"] and not a["platform"]["custom"]]

    def cache_offline_data(self) -> None:
        """يحفظ ما يحتاجه الروبوت للعمل بدون اتصال: الألعاب المرتبطة ومكافأة كل مهمة."""
        try:
            self._remember_linked(self.api.get("/api/user/accounts/"))
            platforms = {p["id"]: p for p in self.api.get("/api/platforms/")["platforms"]}
            for t in self.api.get("/api/tasks/")["tasks"]:
                if platforms.get(t["platform_id"], {}).get("is_demo"):
                    self.rewards[t["key"]] = t["reward_cents"]
        except ApiError:
            pass

    async def sync_loop(self):
        """كل 15 ثانية: يعيد الاتصال إذا انقطع، ويرسل ما في طابور العمل بدون اتصال."""
        while True:
            await asyncio.sleep(15)
            try:
                await self.sync_once(silent=True)
            except Exception:
                pass

    async def sync_once(self, silent: bool = False):
        if not self.me or not self.queue or self.local_running:
            return
        if not self.socket.connected and not self.socket.force_offline and self.api.token:
            self.api_latency = await asyncio.to_thread(self.api.health)
            if self.api_latency is not None:
                await self.socket.connect(self.api.token)
        if not self.queue.size or self.api.force_offline:
            if not silent:
                self.toast("لا يوجد ما يُرسل" if not self.queue.size else "وضع عدم الاتصال مفعّل")
            return
        try:
            res = await asyncio.to_thread(self.queue.flush, self.api)
        except ApiError as e:
            if not silent:
                self.toast(str(e))
            return
        if res is None:
            if not silent:
                self.toast("ما زال لا يوجد اتصال. سنحاول تلقائياً.")
            return
        self.toast(sync_message(res))
        try:
            await asyncio.to_thread(self.refresh_me)
        except ApiError:
            pass
        if self.current in ("home", "network", "earnings"):
            {"home": lambda: self.go(0), "network": self.show_network, "earnings": lambda: self.go(3)}[self.current]()

    def show_network(self):
        return course_labs.show_network(self)

    # ------------------------------------------------------------ تحليلاتي (TM351)
    def show_analytics(self, days: int | None = None):
        return course_labs.show_analytics(self, days)

    # ------------------------------------------------------------ مختبر M269
    def show_m269(self, seed: int | None = None):
        return course_labs.show_m269(self, seed)

    # ------------------------------------------------------------ مختبر TM355
    def show_lab(self):
        return course_labs.show_lab(self)

    def show_notifications(self):
        return account_screens.show_notifications(self)

    def show_security(self):
        return account_screens.show_security(self)

    def show_privacy(self):
        return account_screens.show_privacy(self)

    def _set_pref(self, key, value, then):
        if self.guard(lambda: self.api.patch("/api/me/prefs/", {key: value})) is not None:
            self.guard(self.refresh_me)
            self.apply_theme()
            then()

    def show_appearance(self):
        return account_screens.show_appearance(self)

    def show_wellbeing(self):
        return account_screens.show_wellbeing(self)

    def show_leaderboard(self):
        return account_screens.show_leaderboard(self)

    def show_help(self):
        return account_screens.show_help(self)

    def show_policy(self):
        return account_screens.show_policy(self)
