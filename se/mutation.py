"""
TM354 (الوحدة 10): اختبار الطفرات (mutation testing) — هل اختباراتنا قوية فعلاً؟

نغيّر الكود الأصلي تغييراً صغيراً واحداً في كل مرة («طفرة»)، مثل < بدل <=، أو + بدل −، أو or بدل and،
ثم نشغّل الاختبارات. إذا فشل اختبار واحد على الأقل فالطفرة «قُتلت». إذا نجحت كل الاختبارات فالطفرة «نجت»:
خطأ بهذا الشكل لن تكشفه اختباراتنا. نسبة الطفرات المقتولة = قوة الاختبارات (mutation score).

  python se/mutation.py advisor|rules|bot [--old]      --old = بالاختبارات التي كانت قبل TM354 فقط

الملف الأصلي يُستعاد دائماً (حتى عند الخطأ أو الإيقاف).
"""
from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DJ = [sys.executable, "manage.py", "test", "--failfast", "-v", "0"]
PY = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"]

TARGETS = {
    "advisor": dict(file="backend/core/advisor.py", cwd="backend",
                    old=DJ + ["core.tests.AdvisorTests", "core.tests.M269AdvisorTests"],
                    new=DJ + ["core.tests.AdvisorTests", "core.tests.M269AdvisorTests", "core.tests_tm354.AdvisorContractTests", "core.tests_tm354.AdvisorMutationTests"]),
    "rules": dict(file="backend/core/sync_rules.py", cwd="backend",
                  old=DJ + ["core.tests.OfflineSyncTests", "core.tests.TM355SyncTests", "core.tests.TM351FixTests"],
                  new=DJ + ["core.tests.OfflineSyncTests", "core.tests.TM355SyncTests", "core.tests.TM351FixTests",
                            "core.tests_tm354.SyncRuleTests", "core.tests_tm354.SyncBoundaryTests"]),
    "bot": dict(file="realtime/realtime/bot.py", cwd="realtime",
                old=PY + ["tests/test_bot.py"],
                new=PY + ["tests/test_bot.py", "tests/test_tm354.py"]),
}

SWAP_CMP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
            ast.Is: ast.IsNot, ast.IsNot: ast.Is, ast.In: ast.NotIn, ast.NotIn: ast.In}
SWAP_BIN = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.FloorDiv, ast.FloorDiv: ast.Mult, ast.Div: ast.Mult}


def mutants(tree: ast.AST):
    """يولّد (وصف، شجرة معدّلة) لكل طفرة ممكنة. نتخطى نصوص التوثيق والسلاسل النصية."""
    nodes = list(ast.walk(tree))
    for i, n in enumerate(nodes):
        kinds = []
        if isinstance(n, ast.Compare):
            kinds += [("cmp", j) for j, op in enumerate(n.ops) if type(op) in SWAP_CMP]
        elif isinstance(n, ast.BinOp) and type(n.op) in SWAP_BIN:
            kinds.append(("bin", 0))
        elif isinstance(n, ast.BoolOp):
            kinds.append(("bool", 0))
        elif isinstance(n, ast.Constant) and type(n.value) is int and not isinstance(n.value, bool):
            kinds.append(("int", 0))
        elif isinstance(n, ast.Constant) and isinstance(n.value, bool):
            kinds.append(("boolconst", 0))
        elif isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            kinds.append(("not", 0))
        for kind, j in kinds:
            t2 = copy.deepcopy(tree)
            m = list(ast.walk(t2))[i]
            if kind == "cmp":
                old = type(m.ops[j]).__name__
                m.ops[j] = SWAP_CMP[type(m.ops[j])]()
                desc = f"{old} → {type(m.ops[j]).__name__}"
            elif kind == "bin":
                old = type(m.op).__name__
                m.op = SWAP_BIN[type(m.op)]()
                desc = f"{old} → {type(m.op).__name__}"
            elif kind == "bool":
                m.op = ast.Or() if isinstance(m.op, ast.And) else ast.And()
                desc = f"{'and → or' if isinstance(m.op, ast.Or) else 'or → and'}"
            elif kind == "int":
                desc = f"{m.value} → {m.value + 1}"
                m.value += 1
            elif kind == "boolconst":
                desc = f"{m.value} → {not m.value}"
                m.value = not m.value
            else:
                desc = "حذف not"
                parent = next(p for p in ast.walk(t2) for c in ast.iter_child_nodes(p) if c is m)
                for field, val in ast.iter_fields(parent):
                    if val is m:
                        setattr(parent, field, m.operand)
                    elif isinstance(val, list):
                        setattr(parent, field, [m.operand if x is m else x for x in val])
            yield f"سطر {n.lineno}: {desc}", t2


def _in_docstring_or_fstring(tree):
    """أسطر لا معنى لتغيير أرقامها: داخل f-strings (نصوص الرسائل)."""
    lines = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.JoinedStr):
            lines.update(range(n.lineno, n.end_lineno + 1))
    return lines


def run(target: str, old: bool = False) -> dict:
    cfg = TARGETS[target]
    path = ROOT / cfg["file"]
    original = path.read_text()
    tree = ast.parse(original)
    skip = _in_docstring_or_fstring(tree)
    cmd = cfg["old" if old else "new"]
    results = []
    t0 = time.time()
    try:
        base = subprocess.run(cmd, cwd=ROOT / cfg["cwd"], capture_output=True, text=True)
        assert base.returncode == 0, "الاختبارات تفشل على الكود الأصلي:\n" + base.stdout[-500:] + base.stderr[-1500:]
        for desc, t2 in mutants(tree):
            line = int(desc.split()[1].rstrip(":"))
            if line in skip:
                continue
            try:
                src = ast.unparse(t2)
            except Exception:
                continue
            path.write_text(src)
            r = subprocess.run(cmd, cwd=ROOT / cfg["cwd"], capture_output=True, text=True, timeout=300)
            results.append({"mutant": desc, "killed": r.returncode != 0})
            print(("قُتلت " if r.returncode else "نجت   ") + desc, flush=True)
    finally:
        path.write_text(original)
    killed = sum(r["killed"] for r in results)
    return {"target": target, "tests": "old" if old else "new", "mutants": len(results), "killed": killed,
            "score": round(100 * killed / len(results), 1) if results else 0.0,
            "survivors": [r["mutant"] for r in results if not r["killed"]], "seconds": round(time.time() - t0)}


if __name__ == "__main__":
    tgt = sys.argv[1]
    old = "--old" in sys.argv
    res = run(tgt, old)
    out = ROOT / "se" / "out"
    out.mkdir(exist_ok=True)
    (out / f"mutation_{tgt}_{res['tests']}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"{tgt} ({res['tests']}): {res['killed']}/{res['mutants']} = {res['score']}% في {res['seconds']} ث")
