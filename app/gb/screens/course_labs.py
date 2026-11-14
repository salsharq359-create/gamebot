"""
TM354: شاشات المقررات (الشبكة، تحليلاتي، مختبر M269، مختبر TM355) نُقلت من الصنف GameBotApp إلى هذه الوحدة.
كان GameBotApp صنفاً واحداً بـ 1,287 سطراً و 58 دالة؛ هذه الشاشات الأربع وحدها ~394 سطراً ولا تستخدم
إلا واجهة صغيرة من التطبيق (set_screen، api، guard، toast ...). كل دالة هنا تأخذ التطبيق وسيطاً (app).
"""
from __future__ import annotations

import asyncio
import os
import random
from datetime import datetime

import flet as ft

from ..algorithms import graphs as AG, sorting as AS
from ..client import ApiError, money
from ..engine.games import CoinCollector
from ..tm355 import lab
from ..ui import GAME_COLORS, GOLD, LIME, NAVY, C, S, T, Theme, card, label_style, note, outline, primary, stat, title




def show_network(app):
    st, q = app.api.stats, app.queue
    rtt = app.socket.rtts[-1] if app.socket.rtts else None

    async def measure(_):
        app.api_latency = await asyncio.to_thread(app.api.health)
        await app.socket.ping()
        app.show_network()

    async def flight(e):
        off = bool(e.control.value)
        app.api.force_offline = app.socket.force_offline = off
        if off:
            await app.socket.disconnect()
            app.api_latency = None
            app.toast("وضع عدم الاتصال: التطبيق يتصرف كأن الشبكة مقطوعة")
        else:
            await app.socket.connect(app.api.token)
            app.api_latency = await asyncio.to_thread(app.api.health)
            app.toast("عاد الاتصال. ستُرسل السجلات المحفوظة تلقائياً")
        app.show_network()

    def status_row(name, ok, value):
        color = C("OK") if ok else C("ERROR")
        return ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE if ok else ft.Icons.CANCEL, color=color, size=S(20)),
                       T(name, 14, ft.FontWeight.W_900, expand=True), T(value, 13, ft.FontWeight.BOLD, color)])

    lat = list(st.latencies)[-15:]
    peak = max(lat + [1])
    chart = ft.Row([ft.Container(width=12, height=max(3, 70 * v / peak), bgcolor=C("INK"), border_radius=3,
                                 tooltip=f"{v:.0f} ms") for v in lat],
                   spacing=4, vertical_alignment=ft.CrossAxisAlignment.END, height=74, rtl=False)
    last = q.last_sync if q else None
    per_record = (last["bytes"] / last["records"]) if last and last.get("records") else None
    api_ok = app.api_latency is not None and not app.api.force_offline
    app.set_screen("network", "الشبكة والمزامنة", [
        card(ft.Column([
            status_row("خادم Django (REST)", api_ok, f"{app.api_latency:.0f} ms" if api_ok else "غير متصل"),
            status_row("خادم الروبوت (Socket.io)", app.socket.connected,
                       f"RTT {rtt:.0f} ms" if app.socket.connected and rtt is not None
                       else "متصل" if app.socket.connected else "غير متصل"),
        ], spacing=8)),
        primary("قياس الاتصال الآن", measure, ft.Icons.NETWORK_CHECK),
        title("بانتظار المزامنة"),
        ft.Row([stat("مهام الروبوت", str(len(q.records)) if q else "0"),
                stat("أرباح يدوية", str(len(q.manual)) if q else "0")], spacing=10),
        outline("مزامنة الآن", lambda _: app.page.run_task(app.sync_once, False), ft.Icons.SYNC),
        *([note(f"آخر مزامنة {last['at']:%H:%M}: أُرسل {last['records']} سجل في {last['bytes']} بايت "
                f"(≈ {per_record:.0f} بايت للسجل الواحد، أي ≈ {per_record * 100 / 1024:.1f} KB لكل 100 لعبة). "
                f"البيانات {last['plain_bytes']} بايت قبل الضغط، وبعد الضغط {last['packed_bytes']} بايت، "
                f"وتحقق CRC-32 ({last['crc']}) من {last['tries']} محاولة.")]
          if per_record and last.get("packed_bytes") else []),
        title("قياسات هذه الجلسة"),
        ft.Row([stat("الطلبات", str(st.requests)), stat("أخطاء الاتصال", str(st.errors))], spacing=10),
        ft.Row([stat("بيانات مرسلة", f"{st.bytes_up / 1024:.1f} KB"),
                stat("بيانات مستقبلة", f"{st.bytes_down / 1024:.1f} KB")], spacing=10),
        card(ft.Column([T(f"زمن الاستجابة لآخر {len(lat)} طلبات • المتوسط "
                          f"{st.avg_latency if st.avg_latency is not None else '-'} ms", 13, ft.FontWeight.BOLD),
                        chart], spacing=8)),
        *([T(f"آخر خطأ: {st.last_error}", 12, color=C("MUTED"))] if st.last_error else []),
        title("تجربة انقطاع الشبكة"),
        card(ft.Switch(label="وضع عدم الاتصال (للتجربة)", value=app.api.force_offline, on_change=flight,
                       active_track_color=LIME, active_color=NAVY, label_text_style=label_style())),
        note("التطبيق يعمل بدون إنترنت أولاً: إذا انقطع الاتصال يلعب الروبوت على جهازك، وتُحفظ النتائج والأرباح "
             "اليدوية في ملف على الجهاز، ثم تُرسل دفعة واحدة عند عودة الاتصال. الخادم يحدد المبالغ بنفسه، ويرفض "
             "المكرر والقديم وما يتجاوز الحد اليومي."),
    ], back=app.back_to_account)


def show_analytics(app, days: int | None = None):
    """لوحة تحليلات المستخدم: كل رقم استعلام تجميعي واحد في الخادم (/api/analytics/)."""
    app.analytics_days = days or getattr(app, "analytics_days", 14)
    d = app.guard(lambda: app.api.get("/api/analytics/", {"days": app.analytics_days}))
    back = app.back_to_account if app.nav.selected_index == 4 else (lambda: app.go(3))
    if d is None:
        return app.set_screen("analytics", "تحليلاتي", [note("تعذّر تحميل التحليلات. تحقق من الاتصال.")], back=back)

    def bars(values, labels, color, height=110, width=None, fmt=lambda v: str(v)):
        peak = max(values + [1])
        w = width or max(6, int(300 / max(1, len(values))) - 4)
        return ft.Row([ft.Column([
            ft.Container(width=w, height=3 + height * v / peak, border_radius=4, bgcolor=color,
                         tooltip=f"{lab}: {fmt(v)}"),
            *([T(lab, 9, color=C("MUTED"))] if lab and len(values) <= 14 else []),
        ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.END)
            for v, lab in zip(values, labels)], spacing=4, alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.END, height=height + 22, rtl=False)

    def pick(n):
        return lambda _: app.show_analytics(n)

    ranges = ft.Row([ft.Container(T(f"{n} يوماً", 13, ft.FontWeight.W_900, NAVY if n == app.analytics_days else C("INK")),
                                  padding=ft.Padding(14, 6, 14, 6), border_radius=999, on_click=pick(n),
                                  bgcolor=LIME if n == app.analytics_days else C("CARD"))
                     for n in (7, 14, 30)], spacing=8)
    daily = d["daily"]
    ch = d["channel"]
    total_ch = max(1, sum(ch.values()))
    channel_rows = [ft.Column([
        ft.Row([T(name, 13, ft.FontWeight.BOLD, expand=True), T(f"{money(v)} • {100 * v / total_ch:.0f}٪", 13, ft.FontWeight.W_900)]),
        ft.Container(height=8, border_radius=4, bgcolor=C("TRACK"), content=ft.Row([
            ft.Container(width=max(3, 300 * v / total_ch), height=8, border_radius=4, bgcolor=color)], rtl=True)),
    ], spacing=2) for name, v, color in (("الروبوت متصل", ch["online"], NAVY if not Theme.dark else LIME),
                                         ("بدون اتصال (مزامنة)", ch["offline"], GOLD),
                                         ("يدوي", ch["manual"], "#9DB4FF"))]
    games = d["by_game"]
    top = max([g["cents"] for g in games] + [1])
    game_rows = [ft.Column([
        ft.Row([T(g["game"], 13, ft.FontWeight.BOLD, expand=True), T(f"{money(g['cents'])} • {g['records']} سجل", 12)]),
        ft.Container(height=8, border_radius=4, bgcolor=C("TRACK"), content=ft.Row([
            ft.Container(width=max(3, 300 * g["cents"] / top), height=8, border_radius=4,
                         bgcolor=GAME_COLORS.get({"جمع العملات": "coins", "تخمين الرقم": "guess",
                                                  "إكس أو": "xo"}.get(g["game"], ""), C("MUTED")))], rtl=True)),
    ], spacing=2) for g in games]
    s = d["sessions"]
    best = d["best_day"]
    limit = d["daily_limit_min"]

    async def export(_):
        try:
            text = await asyncio.to_thread(app.api.get_text, "/api/me/export.csv")
        except ApiError as e:
            app.toast(str(e))
            return
        folder = os.path.join(os.path.expanduser("~"), ".gamebot", "exports")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"gamebot-earnings-{datetime.now():%Y%m%d-%H%M}.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(text)
        app.toast(f"تم حفظ {text.count(chr(10)) - 1} سجل في {path}")

    app.set_screen("analytics", "تحليلاتي", [
        ranges,
        ft.Row([stat("الأرباح", money(d["total_cents"])), stat("أيام نشطة", f"{d['active_days']} من {d['days']}")], spacing=10),
        ft.Row([stat("الجلسات", str(s["count"])), stat("متوسط الجلسة", f"{s['avg_seconds']:.0f} ث")], spacing=10),
        title("الأرباح اليومية", 16),
        card(ft.Column([bars([x["cents"] / 100 for x in daily],
                             [x["date"][8:] for x in daily], LIME if Theme.dark else NAVY, fmt=lambda v: f"{v:g}$"),
                        T(f"أفضل يوم: {best['date']} ({money(best['cents'])})" if best else "لا توجد أرباح في هذه الفترة",
                          12, color=C("MUTED"))], spacing=6)),
        title("من أين جاءت الأرباح", 16),
        card(ft.Column(channel_rows, spacing=10)),
        title("حسب اللعبة", 16),
        card(ft.Column(game_rows or [T("لا توجد أرباح بعد.", 13, color=C("MUTED"))], spacing=10)),
        title("متى تلعب؟ (الجلسات حسب الساعة)", 16),
        card(ft.Column([bars(d["by_hour"], [str(h) for h in range(24)], GOLD, height=80, width=9),
                        ft.Row([T("0", 10, color=C("MUTED")), T("12", 10, color=C("MUTED")), T("23", 10, color=C("MUTED"))],
                               alignment=ft.MainAxisAlignment.SPACE_BETWEEN, rtl=False)], spacing=4)),
        card(ft.Row([ft.Icon(ft.Icons.FAVORITE_OUTLINE, color=C("OK")),
                     T(f"مجموع وقت الروبوت {s['total_minutes']:g} دقيقة. "
                       + (f"تجاوزت حدّك اليومي ({limit} دقيقة) في {d['days_over_limit']} يوم." if limit
                          else "لم تضع حداً يومياً."), 13, expand=True)], spacing=10)),
        outline("تصدير أرباحي (CSV)", export, ft.Icons.DOWNLOAD),
        note("التحليلات محسوبة في الخادم من بياناتك فقط، ولا تُشارك مع أحد. ملف CSV يُفتح في Excel أو pandas."),
    ], back=back)


def show_m269(app, seed: int | None = None):
    """مقارنات حية بين الخوارزميات على خرائط اللعبة نفسها."""
    import time
    app.m269_seed = seed if seed is not None else getattr(app, "m269_seed", 1)
    rng = random.Random(app.m269_seed)

    def cell(color, icon=None, text=""):
        return ft.Container(width=24, height=24, border_radius=5, bgcolor=color, border=ft.Border.all(1, "#DDE4F5"),
                            alignment=ft.Alignment.CENTER,
                            content=ft.Icon(icon, size=16, color=NAVY) if icon else
                            (ft.Text(text, size=10, weight=ft.FontWeight.BOLD, color=NAVY) if text else None))

    def grid_view(size, paint):
        return ft.Column([ft.Row([paint((r, c)) for c in range(size)], spacing=2, tight=True, rtl=False)
                          for r in range(size)], spacing=2, tight=True)

    # 1) المسار الأمثل لجمع العملات على خريطة حقيقية من اللعبة
    cc = CoinCollector(rng=rng)
    start, walls, coins = cc.bot, set(cc.walls), set(cc.coins)
    order, best, greedy = cc.plan()
    rank = {c: i + 1 for i, c in enumerate(order)}

    def paint_route(rc):
        if rc == start:
            return cell(LIME, ft.Icons.SMART_TOY)
        if rc in walls:
            return cell("#7A84A8")
        if rc in coins:
            return cell(GOLD, text=str(rank[rc]))
        return cell(ft.Colors.WHITE)

    t0 = time.perf_counter()
    sample_rng = random.Random(app.m269_seed * 7919)
    worse, saved, n_maps = 0, 0, 200
    for _ in range(n_maps):
        o, b, g = CoinCollector(rng=sample_rng).plan()
        worse += g > b
        saved += g - b
    sample_ms = (time.perf_counter() - t0) * 1000

    # 2) BFS و Dijkstra و A* على خريطة فيها طين (تكلفة 3)
    tg = AG.random_grid(10, 14, mud=30, rng=rng)
    free = [(r, c) for r in range(10) for c in range(10) if (r, c) not in tg.walls]
    while True:
        a, b = rng.sample(free, 2)
        if AG.manhattan(a, b) >= 9 and b in AG.reachable(tg, a):
            break
    pb, eb = AG.bfs(tg, a, b)
    pd, cd, ed = AG.dijkstra(tg, a, b)
    pa, ca, ea = AG.astar(tg, a, b)
    on_path = set(pd)

    def paint_terrain(rc):
        if rc in (a, b):
            return cell(LIME, ft.Icons.SMART_TOY if rc == a else ft.Icons.FLAG)
        if rc in tg.walls:
            return cell("#7A84A8")
        mud = tg.step_cost(rc) > 1
        if rc in on_path:
            return cell("#9DB4FF" if not mud else "#C8A2FF", text="•")
        return cell("#D9B38C" if mud else ft.Colors.WHITE)

    # 3) ترتيب لوحة متصدرين من 2,000 لاعب
    scores = [rng.randrange(100_000) for _ in range(2000)]
    sort_rows = []
    for name, fn in AS.ALGORITHMS.items():
        data = scores if name != "insertion" else scores[:500]
        t = time.perf_counter()
        _, comps = fn(data, reverse=True)
        sort_rows.append((name, len(data), comps, (time.perf_counter() - t) * 1000))
    t = time.perf_counter()
    _, topk_comps = AS.top_k(scores, 10)
    topk_ms = (time.perf_counter() - t) * 1000

    def row(k, v):
        return ft.Row([T(k, 13, expand=True), T(v, 13, ft.FontWeight.W_900)])

    names = {"insertion": "الإدراج O(n²)", "merge": "الدمج O(n log n)", "quick": "السريع O(n log n)",
             "heap": "الكومة O(n log n)"}
    app.set_screen("m269", "مختبر M269", [
        ft.Row([outline("خريطة أخرى", lambda _: app.show_m269(app.m269_seed + 1), ft.Icons.REFRESH)]),
        title("1. أفضل ترتيب لجمع العملات", 16),
        card(ft.Column([
            ft.Row([grid_view(8, paint_route)], alignment=ft.MainAxisAlignment.CENTER),
            row("المسار الأمثل (Held-Karp)", f"{best} خطوة"),
            row("الأقرب أولاً (جشع)", f"{greedy} خطوة" + (f" • أطول بـ {greedy - best}" if greedy > best else " • نفس النتيجة")),
            row(f"على {n_maps} خريطة عشوائية", f"الجشع أطول في {100 * worse / n_maps:.0f}٪ منها"),
            row("متوسط الخطوات الموفّرة", f"{saved / n_maps:.2f} خطوة لكل جولة"),
            row("زمن حساب 200 خطة", f"{sample_ms:.0f} ms"),
        ], spacing=6)),
        note("الأرقام على العملات = ترتيب الزيارة الأمثل. «الأقرب أولاً» يبدو منطقياً لكنه ليس الأقصر دائماً؛ "
             "البرمجة الديناميكية تحسب 186 حالة (مجموعة جزئية + آخر عملة) بدل تجربة كل الترتيبات (6! = 720)."),
        title("2. أقصر طريق مع التضاريس", 16),
        card(ft.Column([
            ft.Row([grid_view(10, paint_terrain)], alignment=ft.MainAxisAlignment.CENTER),
            T("البني = طين (تكلفة 3)، والنقاط = طريق Dijkstra", 11, color=C("MUTED")),
            row("BFS (يتجاهل الطين)", f"تكلفة {AG.path_cost(tg, pb)} • {eb} عقدة"),
            row("Dijkstra", f"تكلفة {cd} • {ed} عقدة"),
            row("A* (مانهاتن)", f"تكلفة {ca} • {ea} عقدة"),
        ], spacing=6)),
        title("3. ترتيب لوحة المتصدرين", 16),
        card(ft.Column([ft.Row([T("الخوارزمية", 12, ft.FontWeight.W_900, C("MUTED"), expand=True),
                                T("n", 12, ft.FontWeight.W_900, C("MUTED"), width=44),
                                T("مقارنات", 12, ft.FontWeight.W_900, C("MUTED"), width=70),
                                T("ms", 12, ft.FontWeight.W_900, C("MUTED"), width=44)])] + [
            ft.Row([T(names[nm], 12, ft.FontWeight.BOLD, expand=True), T(f"{n:,}", 12, width=44),
                    T(f"{c:,}", 12, width=70), T(f"{ms:.1f}", 12, width=44)]) for nm, n, c, ms in sort_rows] + [
            row("أعلى 10 بكومة حجمها 10", f"{topk_comps:,} مقارنة • {topk_ms:.1f} ms")], spacing=6)),
        note("ترتيب الإدراج جُرّب على 500 لاعب فقط لأنه تربيعي. ولعرض أعلى 10 فقط لا نحتاج ترتيب الكل: "
             "كومة صغيرة بحجم 10 تكفي، O(n log k)."),
        title("4. حدود الحوسبة", 16),
        note("ترتيب جمع العملات نسخة من «البائع المتجول»، وخطة المستشار «حقيبة ظهر»، وكلتاهما من نوع NP-hard، "
             "فلا نعرف حلاً سريعاً لكل الأحجام. نحلهما بدقة لأن الأحجام صغيرة: 6 عملات، و240 دقيقة على الأكثر. "
             "ولو سمحنا للمستخدم بكتابة سكربت خاص لروبوته، لما استطعنا أن نعرف مسبقاً هل سينتهي (مسألة التوقف)، "
             "لذلك يكفي التطبيق أن المهام بيانات وليست برامج، وأي تنفيذ له مهلة زمنية."),
    ], back=app.back_to_account)


def _lab_source(q) -> tuple[bytes, str]:
    """بيانات المختبر: آخر طلب مزامنة فعلي، أو الطابور الحالي، أو عينة بنفس الشكل."""
    if q and q.last_payload:
        return q.last_payload, "آخر طلب مزامنة فعلي"
    if q and q.records:
        return q.build_payload()[0], "الطابور الحالي"
    return lab.sample_payload(), "عينة بنفس شكل طلب المزامنة"


def _lab_row(k, v):
    return ft.Row([T(k, 13, expand=True), T(v, 13, ft.FontWeight.W_900)])


def _frames_block(f):
    if not f:
        return note("شغّل الروبوت مرة وهو متصل، ثم ارجع هنا لترى حجم إطارات الخريطة.")
    return card(ft.Column([
        _lab_row("الإطارات في آخر جلسة", f"{f['frames']} (منها {f['keyframes']} مفتاحية)"),
        _lab_row("لو أُرسلت الخريطة كاملة كل مرة", f"{f['full_bytes']:,} بايت"),
        _lab_row("ما أُرسل فعلاً (مفتاحية + فروق)", f"{f['sent_bytes']:,} بايت"),
        _lab_row("نسبة التوفير", f"{f['ratio']}×"),
    ], spacing=6))


def _security_rows(q):
    signed = sum(1 for r in (q.records if q else []) if r.get("mac"))
    return [
        _lab_row("تشفير طابور الجهاز", "AES-256-GCM" if q and q.encrypted else "لم يُحفظ بعد"),
        _lab_row("اشتقاق المفتاح", "PBKDF2-SHA256 • 200,000 تكرار"),
        _lab_row("حجم ملف الطابور", f"{q.file_bytes:,} بايت" if q else "-"),
        _lab_row("سجلات موقّعة HMAC-SHA256", f"{signed} من {len(q.records) if q else 0}"),
        _lab_row("سلامة الطلب", "CRC-32 + إعادة الإرسال"),
    ]


def show_lab(app):
    """تطبيق مقرر TM355 على بيانات جيم بوت الحقيقية."""
    q = app.queue
    payload, source = _lab_source(q)
    comp = lab.compression(payload)
    crc = lab.crc_demo(payload)
    ham = lab.hamming_demo(payload, app.lab_p)
    ch = lab.channel_demo(app.lab_mod, app.lab_ebn0, comp["deflate"])
    nets = lab.networks_demo(comp["original"], comp["deflate"])

    def bar(name, value, top, color, extra=""):
        return ft.Column([
            ft.Row([T(name, 13, ft.FontWeight.BOLD, expand=True), T(f"{value:,} بايت{extra}", 13, ft.FontWeight.W_900)]),
            ft.Container(height=10, border_radius=5, bgcolor=C("TRACK"), content=ft.Row([
                ft.Container(width=max(4, 300 * value / top), height=10, border_radius=5, bgcolor=color)],
                rtl=True)),
        ], spacing=2)

    row = _lab_row

    def pick_mod(m):
        def h(_):
            app.lab_mod = m
            app.show_lab()
        return h

    def on_ebn0(e):
        app.lab_ebn0 = round(float(e.control.value), 1)
        app.show_lab()

    def on_p(e):
        app.lab_p = round(float(e.control.value), 3)
        app.show_lab()

    top = comp["original"]
    frames_block = _frames_block(app.last_frames)

    mods = ft.Row([ft.Container(T(m, 13, ft.FontWeight.W_900, NAVY if m == app.lab_mod else C("INK")),
                                padding=ft.Padding(14, 6, 14, 6), border_radius=999,
                                bgcolor=LIME if m == app.lab_mod else C("CARD"), on_click=pick_mod(m))
                   for m in ("BPSK", "QPSK", "16-QAM")], spacing=8)
    tries = "∞" if ch["tries"] == float("inf") or ch["tries"] > 1e6 else f"{ch['tries']:.2f}"
    net_rows = [ft.Row([T(n["name"], 12, ft.FontWeight.BOLD, expand=True),
                        T(f"{n['capacity_mbps']:,.0f}", 12, width=52),
                        T(f"{n['plain_ms']:.0f}", 12, width=48),
                        T(f"{n['compressed_ms']:.0f}", 12, ft.FontWeight.W_900, width=52)])
                for n in nets]
    app.set_screen("lab", "مختبر TM355", [
        note(f"كل الحسابات هنا على بيانات جيم بوت نفسها. المصدر: {source} ({comp['original']:,} بايت)."),

        title("1. نظرية المعلومات والضغط بدون فقد", 16),
        card(ft.Column([
            row("الإنتروبيا", f"{comp['entropy_bits']} بت لكل بايت (من 8)"),
            row("أقل حجم نظري (بايت بايت)", f"{comp['entropy_min']:,} بايت"),
            row("متوسط طول رمز هوفمان", f"{comp['huffman_avg_bits']} بت ({comp['symbols']} رمزاً)"),
            bar("الأصل (JSON)", comp["original"], top, C("MUTED")),
            bar("هوفمان (مع الجدول)", comp["huffman"], top, "#9DB4FF"),
            bar("LZ77 (LZSS)", comp["lz77"], top, GOLD),
            bar("DEFLATE (zlib = LZ77 + هوفمان)", comp["deflate"], top, LIME, f" • {comp['ratio_deflate']}×"),
        ], spacing=8)),
        note("الضغط يحدث فعلاً عند كل مزامنة: التطبيق يرسل البيانات مضغوطة بـ DEFLATE، والخادم يفك الضغط."),

        title("2. ترميز إطارات الخريطة (فكرة ضغط الفيديو)", 16),
        frames_block,

        title("3. كشف الأخطاء وتصحيحها", 16),
        card(ft.Column([
            row("CRC-32 لهذه البيانات", crc["crc"]),
            row("خطأ في بت واحد", f"كُشف {crc['single']} من {crc['trials']}"),
            row("خطأ في بتين", f"كُشف {crc['double']} من {crc['trials']}"),
            row("أخطاء متتالية (24 بت)", f"كُشف {crc['burst']} من {crc['trials']}"),
        ], spacing=6)),
        card(ft.Column([
            T(f"كود هامنغ (7,4) على قناة تقلب كل بت باحتمال {app.lab_p * 100:.1f}٪", 13, ft.FontWeight.W_900),
            ft.Slider(min=0.001, max=0.05, divisions=49, value=app.lab_p, on_change_end=on_p,
                      active_color=NAVY, label="{value}"),
            row("بدون ترميز: أخطاء متبقية", f"{ham['raw_errors']} بت"),
            row("مع هامنغ: كلمات صُححت", f"{ham['corrected_words']}"),
            row("مع هامنغ: أخطاء متبقية", f"{ham['residual_errors_coded']} بت"),
            row("الثمن: حجم البيانات", f"من {ham['data_bits']:,} إلى {ham['coded_bits']:,} بت"),
        ], spacing=6)),

        title("4. القناة والتعديل الرقمي", 16),
        card(ft.Column([
            mods,
            T(f"Eb/N0 = {app.lab_ebn0:.1f} dB", 13, ft.FontWeight.W_900),
            ft.Slider(min=0, max=14, divisions=28, value=app.lab_ebn0, on_change_end=on_ebn0,
                      active_color=NAVY, label="{value} dB"),
            row("بتات لكل رمز", str(ch["bits_per_symbol"])),
            row("BER النظري", f"{ch['ber_theory']:.2e}"),
            row(f"BER بالمحاكاة ({ch['sim_bits']:,} بت)", f"{ch['ber_sim']:.2e}"),
            row(f"خطأ في طلب المزامنة ({ch['packet_bits']:,} بت)", f"{ch['per'] * 100:.1f}٪"),
            row("عدد مرات الإرسال المتوقع", tries),
        ], spacing=6)),
        note("بدون تصحيح أخطاء يحتاج طلب بهذا الحجم نسبة إشارة عالية، لذلك تستخدم شبكات الجوال وشبكات Wi-Fi "
             "أكواداً مثل LDPC مع إعادة الإرسال (HARQ). أما في جيم بوت فيكشف CRC-32 الطلب التالف ويُعاد إرساله."),

        title("5. الشبكات المتنقلة والثابتة (سعة شانون)", 16),
        card(ft.Column([ft.Row([T("الشبكة", 12, ft.FontWeight.W_900, C("MUTED"), expand=True),
                                T("Mb/s", 12, ft.FontWeight.W_900, C("MUTED"), width=52),
                                T("عادي ms", 12, ft.FontWeight.W_900, C("MUTED"), width=48),
                                T("مضغوط ms", 12, ft.FontWeight.W_900, C("MUTED"), width=52)])] + net_rows,
                       spacing=6)),
        note("القيم افتراضات تعليمية (عرض القناة ونسبة الإشارة)، والزمن = زمن الذهاب والإياب + الحجم ÷ ربع السعة "
             "تقريباً. الضغط يفيد أكثر في الشبكات البطيئة، أما في الشبكات الحديثة فزمن الذهاب والإياب هو الأهم."),

        title("6. الأمن والتشفير", 16),
        card(ft.Column(_security_rows(q), spacing=6)),
    ], back=app.back_to_account)
