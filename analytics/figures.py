"""
رسوم TM351 (matplotlib). نفس الرسم بالعربية أو الإنجليزية: lang = "ar" | "en".
ألوان ثابتة لكل فئة (لا تتغير مع الترتيب)، وتسميات مباشرة بدل الاعتماد على اللون وحده.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

FONT = Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts" / "Cairo.ttf"
if FONT.exists():
    font_manager.fontManager.addfont(str(FONT))
BLUE, ORANGE, AQUA, GRAY, INK, MUTED, GRID, SURF = ("#2a78d6", "#eb6834", "#1baf7a", "#9b9a94", "#0b0b0b",
                                                    "#52514e", "#ecebe6", "#fcfcfb")
GAME = {"coins": BLUE, "guess": ORANGE, "xo": AQUA}

T = {
    "game_title": {"ar": "الأرباح حسب اللعبة ونوع المهمة (دولار، 30 يوماً، 300 مستخدم)",
                   "en": "Earnings by game and task type (dollars, 30 days, 300 users)"},
    "games": {"ar": {"coins": "جمع العملات", "guess": "تخمين الرقم", "xo": "إكس أو"},
              "en": {"coins": "Coin Collector", "guess": "Number Guessing", "xo": "Tic-Tac-Toe"}},
    "tasks": {"ar": {"round": "جولات", "tournament": "بطولة", "streak": "تحدي", "daily": "يومية"},
              "en": {"round": "rounds", "tournament": "tournament", "streak": "streak", "daily": "daily"}},
    "heat_title": {"ar": "الجلسات حسب اليوم والساعة (توقيت الكويت)", "en": "Sessions by weekday and hour (Kuwait time)"},
    "hour": {"ar": "الساعة", "en": "Hour"},
    "days": {"ar": ["السبت", "الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة"],
             "en": ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri"]},
    "guess_title": {"ar": "محاولات «تخمين الرقم»: المرصود مقابل نظرية البحث الثنائي",
                    "en": "Number Guessing attempts: observed vs binary-search theory"},
    "attempts": {"ar": "عدد المحاولات", "en": "Attempts"}, "pct": {"ar": "% من الجولات", "en": "% of rounds"},
    "observed": {"ar": "مرصود", "en": "observed"}, "theory": {"ar": "نظري", "en": "theory"},
    "sync_title": {"ar": "مصير 20,417 سجلاً وصلت في طلبات المزامنة", "en": "Outcome of 20,417 records received in sync requests"},
    "reasons": {"ar": {"accepted": "مقبول", "daily_cap": "تجاوز حد المهمة اليومي", "duplicate": "مكرر (إعادة إرسال)",
                       "bad_task": "اسم مهمة خاطئ (نسخة قديمة)", "stale": "أقدم من 7 أيام", "future": "تاريخ مستقبلي"},
                "en": {"accepted": "accepted", "daily_cap": "task daily cap", "duplicate": "duplicate (resend)",
                       "bad_task": "bad task name (old app)", "stale": "older than 7 days", "future": "future date"}},
    "records": {"ar": "سجلات", "en": "records"},
    "min_title": {"ar": "دقائق لعب الروبوت لكل مستخدم في اليوم", "en": "Robot play minutes per user per day"},
    "minutes": {"ar": "دقائق في اليوم", "en": "Minutes per day"}, "userdays": {"ar": "أيام-مستخدم", "en": "user-days"},
    "lowest_limit": {"ar": "أصغر حد يومي متاح: 30 دقيقة", "en": "Smallest daily limit offered: 30 min"},
    "idx_title": {"ar": "أثر الفهرس على زمن الاستعلام (PostgreSQL، وسيط 15 تشغيلاً)",
                  "en": "Effect of an index on query time (PostgreSQL, median of 15 runs)"},
    "without": {"ar": "بدون الفهرس", "en": "without index"}, "with": {"ar": "مع الفهرس", "en": "with index"},
}


def _ax(figsize):
    fig, ax = plt.subplots(figsize=figsize, dpi=200)
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color("#c9c8c2")
    ax.spines["bottom"].set_color("#c9c8c2")
    ax.tick_params(colors=MUTED)
    return fig, ax


def _setup(lang):
    plt.rcParams["font.family"] = ["Cairo", "DejaVu Sans"]
    plt.rcParams["font.size"] = 10


def _title(ax, text, lang):
    ax.set_title(text, color=INK, fontsize=11.5, loc="right" if lang == "ar" else "left")


def _save(fig, path):
    fig.tight_layout()
    if path:
        fig.savefig(path)
    return fig


def earnings_by_game(table, lang="ar", path=None):
    _setup(lang)
    fig, ax = _ax((7.2, 2.8))
    games = [g for g in ("coins", "guess", "xo") if g in table.index]
    order = ["round", "tournament", "streak", "daily"]
    names = T["tasks"][lang]
    y = list(range(len(games)))[::-1]
    left = [0.0] * len(games)
    shades = {"round": 1.0, "tournament": 0.75, "streak": 0.55, "daily": 0.35}
    for task in order:
        vals = [float(table.loc[g, task]) if task in table.columns else 0 for g in games]
        ax.barh(y, vals, left=left, height=0.55, color=[GAME[g] for g in games], alpha=shades[task],
                edgecolor=SURF, linewidth=1.5)
        for yi, l, v in zip(y, left, vals):
            if v > 2500:
                ax.text(l + v / 2, yi, names[task], ha="center", va="center", fontsize=8, color="white")
        left = [a + b for a, b in zip(left, vals)]
    for yi, total in zip(y, left):
        ax.text(total + 400, yi, f"{total:,.0f}", va="center", fontsize=9.5, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels([T["games"][lang][g] for g in games])
    ax.set_xlim(0, max(left) * 1.15)
    ax.grid(True, axis="x", color=GRID)
    ax.set_axisbelow(True)
    _title(ax, T["game_title"][lang], lang)
    return _save(fig, path)


def heatmap(table, lang="ar", path=None):
    _setup(lang)
    fig, ax = _ax((7.2, 2.9))
    im = ax.imshow(table.values, aspect="auto", cmap="Blues")
    ax.set_yticks(range(7))
    ax.set_yticklabels(T["days"][lang])
    ax.set_xticks(range(0, len(table.columns), 2))
    ax.set_xticklabels([str(h) for h in table.columns[::2]])
    ax.set_xlabel(T["hour"][lang])
    for s in ax.spines.values():
        s.set_visible(False)
    fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    _title(ax, T["heat_title"][lang], lang)
    return _save(fig, path)


def guess_vs_theory(df, lang="ar", path=None):
    _setup(lang)
    fig, ax = _ax((7.2, 3.0))
    ax.bar(df["attempts"], df["observed_pct"], color=BLUE, width=0.6, label=T["observed"][lang])
    ax.plot(df["attempts"], df["theory_pct"], "o", color=ORANGE, ms=7, markeredgecolor=SURF, label=T["theory"][lang])
    for a, v in zip(df["attempts"], df["observed_pct"]):
        if v > 5:
            ax.text(a, v + 1.2, f"{v:.1f}%", ha="center", fontsize=8.5, color=INK)
    ax.set_xticks(df["attempts"])
    ax.set_xlabel(T["attempts"][lang])
    ax.set_ylabel(T["pct"][lang])
    ax.legend(frameon=False, loc="upper left")
    ax.grid(True, axis="y", color=GRID)
    ax.set_axisbelow(True)
    ax.text(0.99 if lang == "ar" else 0.01, 0.45, f"χ² = {df.attrs['chi2']}   df = {df.attrs['dof']}   n = {df.attrs['n']:,}",
            transform=ax.transAxes, ha="right" if lang == "ar" else "left", fontsize=9, color=MUTED)
    _title(ax, T["guess_title"][lang], lang)
    return _save(fig, path)


def sync_reasons(reasons, lang="ar", path=None):
    _setup(lang)
    fig, ax = _ax((7.2, 2.8))
    r = reasons.iloc[::-1]
    colors = [BLUE if k == "accepted" else (GRAY if k == "duplicate" else ORANGE) for k in r.index]
    ax.barh(range(len(r)), r["records"], color=colors, height=0.6)
    for i, (n, p) in enumerate(zip(r["records"], r["pct"])):
        ax.text(n + 150, i, f"{n:,}  ({p}%)", va="center", fontsize=9, color=INK)
    ax.set_yticks(range(len(r)))
    ax.set_yticklabels([T["reasons"][lang][k] for k in r.index])
    ax.set_xlim(0, r["records"].max() * 1.25)
    ax.grid(True, axis="x", color=GRID)
    ax.set_axisbelow(True)
    _title(ax, T["sync_title"][lang], lang)
    return _save(fig, path)


def minutes_hist(per_day, lang="ar", path=None):
    _setup(lang)
    fig, ax = _ax((7.2, 2.8))
    ax.hist(per_day["minutes"], bins=[x / 4 for x in range(0, 21)], color=BLUE, edgecolor=SURF, linewidth=1.5)
    ax.set_xlim(0, 32)
    ax.axvline(30, color=ORANGE, linewidth=2)
    ax.text(29.5, ax.get_ylim()[1] * 0.85, T["lowest_limit"][lang], ha="right", color=INK, fontsize=9)
    ax.set_xlabel(T["minutes"][lang])
    ax.set_ylabel(T["userdays"][lang])
    ax.grid(True, axis="y", color=GRID)
    ax.set_axisbelow(True)
    _title(ax, T["min_title"][lang], lang)
    return _save(fig, path)


def index_bench(rows, lang="ar", path=None):
    _setup(lang)
    fig, ax = _ax((7.2, 2.4))
    labels = {"ar": {"user_week": "أرباح مستخدم في 7 أيام\n(user_id, created_at)",
                     "all_day": "أرباح كل المستخدمين في يوم\n(created_at)"},
              "en": {"user_week": "One user's last 7 days\n(user_id, created_at)",
                     "all_day": "All users, one day\n(created_at)"}}[lang]
    y = list(range(len(rows)))
    h = 0.35
    ax.barh([i + h / 2 for i in y], [r["ms_without"] for r in rows], height=h, color=GRAY, label=T["without"][lang])
    ax.barh([i - h / 2 for i in y], [r["ms_with"] for r in rows], height=h, color=BLUE, label=T["with"][lang])
    for i, r in enumerate(rows):
        ax.text(r["ms_without"] + 0.02, i + h / 2, f"{r['ms_without']:.3f} ms", va="center", fontsize=8.5)
        ax.text(r["ms_with"] + 0.02, i - h / 2, f"{r['ms_with']:.3f} ms  (×{r['speedup']})", va="center", fontsize=8.5)
    ax.set_yticks(y)
    ax.set_yticklabels([labels[r["query"]] for r in rows], fontsize=8.5)
    ax.set_xlim(0, max(r["ms_without"] for r in rows) * 1.45)
    ax.legend(frameon=False, loc="lower right", fontsize=8.5)
    _title(ax, T["idx_title"][lang], lang)
    return _save(fig, path)
