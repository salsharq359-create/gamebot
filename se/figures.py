"""رسوم تقرير TM354 من نتائج se/out/*.json (lang = ar | en)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from algorithms.figures import C1, C2, C3, GRAY, GRID, INK, _ax, _save, _title  # noqa: E402

OUT = ROOT / "se" / "out"
J = lambda n: json.loads((OUT / n).read_text())  # noqa: E731
TX = {
    "cc_title": {"ar": "أعلى الدوال تعقيداً قبل TM354 وبعده (التعقيد الدوري لـ McCabe)",
                 "en": "Most complex functions before and after TM354 (McCabe cyclomatic complexity)"},
    "before": {"ar": "قبل", "en": "before"}, "after": {"ar": "بعد", "en": "after"},
    "limit": {"ar": "حد بوابة الجودة = 20", "en": "quality-gate limit = 20"},
    "mut_title": {"ar": "نسبة الطفرات التي تقتلها الاختبارات (قوة الاختبارات)",
                  "en": "Mutation score: share of injected faults the tests catch"},
    "old": {"ar": "اختبارات ما قبل TM354", "en": "tests before TM354"},
    "new": {"ar": "مع اختبارات TM354", "en": "with TM354 tests"},
    "cov_title": {"ar": "تغطية الأسطر والفروع قبل TM354 وبعده", "en": "Line and branch coverage before and after TM354"},
    "lines": {"ar": "أسطر", "en": "lines"}, "branches": {"ar": "فروع", "en": "branches"},
    "targets": {"ar": {"advisor": "المستشار\nadvisor.py", "rules": "قواعد المزامنة\nsync_rules.py",
                       "bot": "جلسة الروبوت\nbot.py"},
                "en": {"advisor": "advisor\nadvisor.py", "rules": "sync rules\nsync_rules.py", "bot": "bot session\nbot.py"}},
    "comp": {"ar": {"Django (backend/core)": "Django", "Bot server (realtime)": "خادم الروبوت", "App (app/gb)": "التطبيق"},
             "en": {"Django (backend/core)": "Django", "Bot server (realtime)": "bot server", "App (app/gb)": "app"}},
}
CC_ROWS = [("offline_sync", "backend/core/views.py", "offline_sync"),
           ("run_session", "realtime/realtime/bot.py", "run_session"),
           ("show_lab", None, "show_lab"), ("sync_once", "app/gb/app.py", "GameBotApp.sync_once")]


def _cc(metrics, name):
    hits = [f["cc"] for f in metrics["worst"] if f["name"].split(".")[-1] == name.split(".")[-1]]
    return max(hits) if hits else None


def cc_hotspots(lang="ar", path=None):
    from se import metrics as M
    before = {f["name"].split(".")[-1]: f["cc"] for f in M.functions(Path("/tmp/oldgb/gamebot-py"))} \
        if Path("/tmp/oldgb/gamebot-py").exists() else {}
    after = {}
    for f in M.functions(ROOT):
        k = f["name"].split(".")[-1]
        after[k] = max(after.get(k, 0), f["cc"])
    names = ["offline_sync", "run_session", "show_lab", "sync_once", "show_analytics", "best_plan"]
    b = [before.get(n, 0) for n in names]
    a = [after.get(n, 0) for n in names]
    fig, ax = _ax((7.2, 3.0))
    x = range(len(names))
    ax.bar([i - 0.2 for i in x], b, width=0.38, color=GRAY, label=TX["before"][lang])
    ax.bar([i + 0.2 for i in x], a, width=0.38, color=C1, label=TX["after"][lang])
    for i, (vb, va) in enumerate(zip(b, a)):
        ax.text(i - 0.2, vb + 0.4, str(vb), ha="center", fontsize=8.5, color=INK)
        ax.text(i + 0.2, va + 0.4, str(va), ha="center", fontsize=8.5, color=INK)
    ax.axhline(20, color=C2, lw=1.2, ls=(0, (4, 3)))
    ax.text(4.5, 20.6, TX["limit"][lang], color=C2, fontsize=8.5, ha="center")
    ax.set_xticks(list(x))
    ax.set_xticklabels(names, fontsize=8.5)
    ax.set_ylim(0, 30)
    ax.grid(True, axis="y", color=GRID)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper right", fontsize=9, ncol=2)
    _title(ax, TX["cc_title"][lang], lang)
    return _save(fig, path), dict(zip(names, zip(b, a)))


def mutation(lang="ar", path=None):
    fig, ax = _ax((7.2, 2.8))
    keys = ["advisor", "rules", "bot"]
    old = [J(f"mutation_{k}_old.json") for k in keys]
    new = [J(f"mutation_{k}_new.json") for k in keys]
    x = range(len(keys))
    ax.bar([i - 0.2 for i in x], [o["score"] for o in old], width=0.38, color=GRAY, label=TX["old"][lang])
    ax.bar([i + 0.2 for i in x], [n["score"] for n in new], width=0.38, color=C3, label=TX["new"][lang])
    for i, (o, n) in enumerate(zip(old, new)):
        ax.text(i - 0.2, o["score"] + 2, f"{o['score']:g}%", ha="center", fontsize=8, color=INK)
        ax.text(i + 0.2, n["score"] + 2, f"{n['score']:g}%", ha="center", fontsize=8, color=INK)
    ax.set_xticks(list(x))
    ax.set_xticklabels([TX["targets"][lang][k] for k in keys], fontsize=8.5)
    ax.set_ylim(0, 120)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.grid(True, axis="y", color=GRID)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper left", fontsize=8.5, ncol=2)
    _title(ax, TX["mut_title"][lang], lang)
    return _save(fig, path)


def coverage(lang="ar", path=None):
    b, a = J("coverage_before.json"), J("coverage_after.json")
    comps = list(a)
    fig, ax = _ax((7.2, 2.7))
    labels, vals, cols = [], [], []
    for c in comps:
        for kind, key in (("lines", "line_pct"), ("branches", "branch_pct")):
            labels.append(f"{TX['comp'][lang][c]}\n{TX[kind][lang]}")
            vals.append((b[c][key], a[c][key]))
    x = range(len(labels))
    ax.bar([i - 0.2 for i in x], [v[0] for v in vals], width=0.38, color=GRAY, label=TX["before"][lang])
    ax.bar([i + 0.2 for i in x], [v[1] for v in vals], width=0.38, color=C1, label=TX["after"][lang])
    for i, (vb, va) in enumerate(vals):
        ax.text(i - 0.2, vb + 1.5, f"{vb:g}", ha="center", fontsize=7.5, color=INK)
        ax.text(i + 0.2, va + 1.5, f"{va:g}", ha="center", fontsize=7.5, color=INK)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0, 112)
    ax.grid(True, axis="y", color=GRID)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper right", fontsize=8.5, ncol=2)
    _title(ax, TX["cov_title"][lang], lang)
    return _save(fig, path)


if __name__ == "__main__":
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    for lang in ("ar", "en"):
        _, rows = cc_hotspots(lang, dest / f"cc_{lang}.png")
        mutation(lang, dest / f"mutation_{lang}.png")
        coverage(lang, dest / f"coverage_{lang}.png")
    print(rows)
