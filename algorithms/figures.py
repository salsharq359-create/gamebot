"""رسوم M269 بالعربية أو الإنجليزية (lang = "ar" | "en")."""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

FONT = Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts" / "Cairo.ttf"
if FONT.exists():
    font_manager.fontManager.addfont(str(FONT))
C1, C2, C3, C4, GRAY, INK, MUTED, GRID, SURF = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#9b9a94", "#0b0b0b",
                                                "#52514e", "#ecebe6", "#fcfcfb")
TX = {
    "sort_title": {"ar": "زمن الترتيب مع زيادة عدد اللاعبين (محورا لوغاريتم)", "en": "Sorting time as the number of players grows (log–log)"},
    "players": {"ar": "عدد اللاعبين n", "en": "Players n"},
    "ms": {"ar": "ملي ثانية", "en": "milliseconds"},
    "sorts": {"ar": {"insertion": "الإدراج", "merge": "الدمج", "quick": "السريع", "heap": "الكومة"},
              "en": {"insertion": "insertion", "merge": "merge", "quick": "quick", "heap": "heap"}},
    "slope": {"ar": "ميل المقارنات", "en": "comparison slope"},
    "tsp_title": {"ar": "عدد الحالات لإيجاد أفضل ترتيب لجمع k عملة", "en": "Work needed to find the best order for k coins"},
    "k": {"ar": "عدد العملات k", "en": "Coins k"},
    "count": {"ar": "حالات / ترتيبات (لوغاريتم)", "en": "States / orders (log scale)"},
    "bf": {"ar": "بحث شامل (k!)", "en": "brute force: k!"},
    "hk": {"ar": "Held-Karp (k·2^(k−1))", "en": "Held-Karp: k·(2^(k−1)−1)"},
    "game": {"ar": "اللعبة: 6 عملات", "en": "the game: 6 coins"},
    "gap_title": {"ar": "كم خطوة زائدة يمشيها «الأقرب أولاً» مقارنة بالمسار الأمثل (3,000 خريطة)",
                  "en": "Extra steps taken by nearest-first compared with the optimal route (3,000 maps)"},
    "extra": {"ar": "خطوات زائدة", "en": "Extra steps"}, "maps": {"ar": "خرائط", "en": "maps"},
    "search_title": {"ar": "متوسط العقد التي يفحصها كل بحث (500 خريطة بتضاريس)",
                     "en": "Average nodes expanded per search (500 terrain maps)"},
}


def _ax(size):
    plt.rcParams["font.family"] = ["Cairo", "DejaVu Sans"]
    plt.rcParams["font.size"] = 10
    fig, ax = plt.subplots(figsize=size, dpi=200)
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c9c8c2")
    ax.tick_params(colors=MUTED)
    return fig, ax


def _title(ax, text, lang):
    ax.set_title(text, color=INK, fontsize=11.5, loc="right" if lang == "ar" else "left")


def _save(fig, path):
    fig.tight_layout()
    if path:
        fig.savefig(path)
    return fig


def sorting_loglog(res, lang="ar", path=None):
    fig, ax = _ax((7.2, 3.3))
    for (name, r), color in zip(res.items(), (C2, C1, C3, C4)):
        ax.loglog(r["n"], r["ms"], "-o", color=color, lw=2, ms=5, markeredgecolor=SURF,
                  label=f"{TX['sorts'][lang][name]} ({TX['slope'][lang]} {r['slope_comparisons']})")
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    ax.set_xlim(200, 5000)
    ax.set_xlabel(TX["players"][lang])
    ax.set_ylabel(TX["ms"][lang])
    ax.grid(True, which="major", color=GRID)
    _title(ax, TX["sort_title"][lang], lang)
    return _save(fig, path)


def tsp_growth(res, lang="ar", path=None):
    fig, ax = _ax((7.2, 3.2))
    ks = list(range(2, 17))
    ax.semilogy(ks, [math.factorial(k) for k in ks], "-", color=C2, lw=2)
    ax.semilogy(ks, [k * (2 ** (k - 1) - 1) for k in ks], "-", color=C1, lw=2)
    ax.axvline(6, color=MUTED, lw=1, ls=(0, (4, 3)))
    ax.text(6.2, 3e10, TX["game"][lang], color=MUTED, fontsize=9)
    ax.text(14.2, math.factorial(14) * 3, TX["bf"][lang], color=INK, fontsize=9, ha="right")
    ax.text(16, 16 * (2 ** 15 - 1) / 12, TX["hk"][lang], color=INK, fontsize=9, ha="right")
    ax.set_xlabel(TX["k"][lang])
    ax.set_ylabel(TX["count"][lang])
    ax.grid(True, color=GRID)
    _title(ax, TX["tsp_title"][lang], lang)
    return _save(fig, path)


def gap_hist(res, lang="ar", path=None):
    fig, ax = _ax((7.2, 2.8))
    ks = [int(k) for k in res["hist"]]
    vs = [res["hist"][k] for k in res["hist"]]
    ax.bar(ks, vs, color=[GRAY if k == 0 else C2 for k in ks], width=0.7)
    for k, v in zip(ks, vs):
        ax.text(k, v + 25, f"{v:,}", ha="center", fontsize=8.5, color=INK)
    ax.set_xticks(ks)
    ax.set_xlabel(TX["extra"][lang])
    ax.set_ylabel(TX["maps"][lang])
    ax.grid(True, axis="y", color=GRID)
    ax.set_axisbelow(True)
    _title(ax, TX["gap_title"][lang], lang)
    return _save(fig, path)


def search_nodes(res, lang="ar", path=None):
    fig, ax = _ax((7.2, 2.3))
    names = ["BFS", "Dijkstra", "A*"]
    vals = [res["expanded_bfs"], res["expanded_dijkstra"], res["expanded_astar"]]
    y = [2, 1, 0]
    ax.barh(y, vals, color=[GRAY, C1, C3], height=0.55)
    for yi, v in zip(y, vals):
        ax.text(v + 1, yi, f"{v:.1f}", va="center", fontsize=9.5, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.set_xlim(0, max(vals) * 1.2)
    ax.grid(True, axis="x", color=GRID)
    ax.set_axisbelow(True)
    _title(ax, TX["search_title"][lang], lang)
    return _save(fig, path)
