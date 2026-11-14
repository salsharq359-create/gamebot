"""
TM354 (الوحدة 11): مقاييس جودة المنتج لكود جيم بوت.

  python se/metrics.py [جذر_المشروع] [--json ملف]

  * التعقيد الدوري لـ McCabe لكل دالة (radon): عدد المسارات المستقلة = عدد القرارات + 1
  * مؤشر قابلية الصيانة MI لكل ملف (0–100، أعلى أفضل)
  * مقاييس الأصناف (Chidamber & Kemerer): WMC = مجموع تعقيد الدوال، DIT = عمق الوراثة،
    CBO = عدد أصناف المشروع الأخرى التي يستخدمها الصنف، و NOM = عدد الدوال
  * الاقتران بين الوحدات: Ce (يعتمد على) و Ca (يُعتمد عليه) والثبات I = Ce / (Ca + Ce)
"""
from __future__ import annotations

import ast
import json
import sys
from collections import defaultdict
from pathlib import Path

from radon.complexity import cc_rank, cc_visit
from radon.metrics import mi_visit
from radon.raw import analyze

SCOPES = ["app/gb", "backend/core", "realtime/realtime"]
SKIP = ("/migrations/", "/tests", "/algorithms/", "/management/", "__init__.py")


def files(root: Path) -> list[Path]:
    out = []
    for s in SCOPES:
        out += [p for p in sorted((root / s).rglob("*.py")) if not any(k in str(p) for k in SKIP)
                and not p.name.startswith("tests")]
    return out


def _module(root: Path, p: Path) -> str:
    return ".".join(p.relative_to(root).with_suffix("").parts)


def functions(root: Path) -> list[dict]:
    rows = []
    for p in files(root):
        for b in cc_visit(p.read_text()):
            if b.letter == "C" and not hasattr(b, "classname"):     # الصنف نفسه، لا دالة
                continue
            name = f"{b.classname}.{b.name}" if getattr(b, "classname", None) else b.name
            rows.append({"file": str(p.relative_to(root)), "name": name, "cc": b.complexity,
                         "rank": cc_rank(b.complexity), "lines": b.endline - b.lineno + 1})
    return rows


def classes(root: Path) -> list[dict]:
    trees = {p: ast.parse(p.read_text()) for p in files(root)}
    defs = {n.name: (p, n) for p, t in trees.items() for n in t.body if isinstance(n, ast.ClassDef)}
    cc = {(r["file"], r["name"]): r["cc"] for r in functions(root)}

    def dit(name, seen=()):
        _, node = defs[name]
        depth = 1
        for b in node.bases:
            bn = b.id if isinstance(b, ast.Name) else b.attr if isinstance(b, ast.Attribute) else None
            if bn in defs and bn not in seen:
                depth = max(depth, 1 + dit(bn, seen + (name,)))
            elif bn and bn not in ("object",):
                depth = max(depth, 2)                 # يرث من صنف مكتبة (Exception، Enum، Model ...)
        return depth
    rows = []
    for name, (p, node) in defs.items():
        f = str(p.relative_to(root))
        methods = [m for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
        used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | \
               {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
        rows.append({"file": f, "class": name, "nom": len(methods),
                     "wmc": sum(cc.get((f, f"{name}.{m.name}"), 1) for m in methods),
                     "dit": dit(name), "cbo": len((used & set(defs)) - {name}),
                     "lines": node.end_lineno - node.lineno + 1})
    return sorted(rows, key=lambda r: -r["wmc"])


def coupling(root: Path) -> list[dict]:
    mods = {_module(root, p): p for p in files(root)}
    ce, ca = defaultdict(set), defaultdict(set)
    for m, p in mods.items():
        pkg = m.rsplit(".", 1)[0]
        for n in ast.walk(ast.parse(p.read_text())):
            if isinstance(n, ast.ImportFrom) and n.level:
                base = pkg.rsplit(".", n.level - 1)[0] if n.level > 1 else pkg
                targets = [f"{base}.{n.module}"] if n.module else [f"{base}.{a.name}" for a in n.names]
                targets += [f"{base}.{n.module}.{a.name}" for a in n.names] if n.module else []
                for t in targets:
                    if t in mods and t != m:
                        ce[m].add(t)
                        ca[t].add(m)
    rows = [{"module": m, "ce": len(ce[m]), "ca": len(ca[m]),
             "instability": round(len(ce[m]) / (len(ce[m]) + len(ca[m])), 2) if ce[m] or ca[m] else 0}
            for m in mods]
    return sorted(rows, key=lambda r: (-r["ce"] - r["ca"]))


def summary(root: Path) -> dict:
    fs = functions(root)
    ranks = defaultdict(int)
    for r in fs:
        ranks[r["rank"]] += 1
    per_file = []
    for p in files(root):
        src = p.read_text()
        per_file.append({"file": str(p.relative_to(root)), "sloc": analyze(src).sloc,
                         "mi": round(mi_visit(src, multi=True), 1)})
    cls = classes(root)
    return {
        "files": len(per_file), "sloc": sum(f["sloc"] for f in per_file), "functions": len(fs),
        "avg_cc": round(sum(r["cc"] for r in fs) / len(fs), 2), "max_cc": max(r["cc"] for r in fs),
        "ranks": dict(sorted(ranks.items())), "over_10": sum(r["cc"] > 10 for r in fs),
        "over_20": sum(r["cc"] > 20 for r in fs),
        "worst": sorted(fs, key=lambda r: -r["cc"])[:10], "per_file": sorted(per_file, key=lambda f: f["mi"]),
        "classes": cls[:10], "max_wmc": cls[0]["wmc"], "max_dit": max(c["dit"] for c in cls),
        "coupling": coupling(root)[:10],
    }


if __name__ == "__main__":
    argv = sys.argv[1:]
    out_json = argv.pop(argv.index("--json") + 1) if "--json" in argv else None
    args = [a for a in argv if not a.startswith("--")]
    root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[1]
    s = summary(root)
    if out_json:
        Path(out_json).write_text(json.dumps(s, ensure_ascii=False, indent=1))
    print(f"{s['files']} ملفاً، {s['sloc']} سطراً فعلياً، {s['functions']} دالة")
    print(f"التعقيد: متوسط {s['avg_cc']}، أعلى {s['max_cc']}، فوق 10: {s['over_10']}، فوق 20: {s['over_20']}  {s['ranks']}")
    print(f"أكبر WMC: {s['max_wmc']} ({s['classes'][0]['class']})، أعمق وراثة DIT: {s['max_dit']}")
    for r in s["worst"][:6]:
        print(f"  CC {r['cc']:>3}  {r['file']}  {r['name']}")
