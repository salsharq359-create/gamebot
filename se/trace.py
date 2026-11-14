"""
TM354: مصفوفة التتبع من المتطلبات إلى الاختبارات.

  python se/trace.py          يتحقق من المراجع فقط (سريع، بدون تشغيل)
  python se/trace.py --run    يشغّل كل مجموعات الاختبار، ويكتب se/out/trace.json و se/out/trace.md

لتشغيل اختبار السباق الحقيقي في المحفظة اضبط DATABASE_HOST (PostgreSQL) قبل --run، وإلا يُتخطى على SQLite.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from se.requirements import REQUIREMENTS  # noqa: E402

TEST_FILES = ["backend/core/tests.py", "backend/core/tests_tm354.py", "realtime/tests/test_bot.py",
              "realtime/tests/test_tm354.py", "realtime/tests/test_e2e.py", "app/tests/test_offline.py",
              "app/tests/test_tm354.py", "app/tests/test_tm355.py", "algorithms/tests/test_algorithms.py",
              "analytics/tests/test_analytics.py", "se/tests/test_quality.py"]


def collect_tests() -> set[str]:
    """كل اختبار موجود: ملف::دالة أو ملف::صنف::دالة."""
    ids = set()
    for f in TEST_FILES:
        tree = ast.parse((ROOT / f).read_text())
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                ids.add(f"{f}::{node.name}")
            elif isinstance(node, ast.ClassDef):
                for m in node.body:
                    if isinstance(m, ast.FunctionDef) and m.name.startswith("test_"):
                        ids.add(f"{f}::{node.name}::{m.name}")
    return ids


def check() -> dict:
    existing = collect_tests()
    referenced = {t for r in REQUIREMENTS for t in r["tests"]}
    return {
        "requirements": len(REQUIREMENTS),
        "by_moscow": dict(Counter(r["moscow"] for r in REQUIREMENTS)),
        "by_kind": dict(Counter(r["kind"].split(":")[0] for r in REQUIREMENTS)),
        "broken_refs": sorted(referenced - existing),
        "untraced": [r["id"] for r in REQUIREMENTS if r["moscow"] in ("Must", "Should") and not r["tests"]],
        "tests_total": len(existing),
        "tests_traced": len(referenced & existing),
        "orphan_tests": sorted(existing - referenced),
    }


# ---------------------------------------------------------------- التشغيل
def _pytest(cwd: str, target: str, prefix: str) -> dict[str, str]:
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rA", "-p", "no:cacheprovider", target],
                         cwd=ROOT / cwd, capture_output=True, text=True).stdout
    res = {}
    for m in re.finditer(r"^(PASSED|FAILED|ERROR|SKIPPED) (\S+?\.py)::(\S+)", out, re.M):
        name = m.group(3).split("[")[0]
        key = f"{prefix}{m.group(2)}::{name}"
        status = m.group(1).lower()
        if res.get(key) != "failed":                     # الاختبار ذو المعاملات: يفشل إذا فشلت أي حالة
            res[key] = status
    return res


def _django() -> dict[str, str]:
    p = subprocess.run([sys.executable, "manage.py", "test", "core", "-v", "2"], cwd=ROOT / "backend",
                       capture_output=True, text=True)
    res = {}
    for m in re.finditer(r"^(test_\w+) \(core\.(\w+)\.(\w+)\.\w+\)\s*\.\.\.\s*(ok|FAIL|ERROR|skipped)", p.stderr, re.M):
        status = {"ok": "passed", "FAIL": "failed", "ERROR": "failed", "skipped": "skipped"}[m.group(4)]
        res[f"backend/core/{m.group(2)}.py::{m.group(3)}::{m.group(1)}"] = status
    return res


def run_all() -> dict[str, str]:
    res = _django()
    res |= _pytest("realtime", "tests", "realtime/")
    res |= _pytest("app", "tests", "app/")
    res |= _pytest(".", "algorithms/tests", "")
    res |= _pytest(".", "analytics/tests", "")
    res |= _pytest(".", "se/tests", "")
    return res


def matrix(results: dict[str, str]) -> list[dict]:
    rows = []
    for r in REQUIREMENTS:
        st = [results.get(t, "not_run") for t in r["tests"]]
        verdict = ("—" if not st else "failed" if "failed" in st else "passed" if all(s == "passed" for s in st)
                   else "partial")
        rows.append({"id": r["id"], "moscow": r["moscow"], "kind": r["kind"], "tests": len(st),
                     "passed": st.count("passed"), "skipped": st.count("skipped"), "verdict": verdict})
    return rows


def main() -> int:
    info = check()
    print(f"{info['requirements']} متطلباً، {info['tests_traced']} من {info['tests_total']} اختباراً مرتبطة بمتطلب")
    for b in info["broken_refs"]:
        print("مرجع مكسور:", b)
    for u in info["untraced"]:
        print("متطلب بلا اختبار:", u)
    ok = not info["broken_refs"] and not info["untraced"]
    if "--run" in sys.argv:
        results = run_all()
        rows = matrix(results)
        out = ROOT / "se" / "out"
        out.mkdir(exist_ok=True)
        total = Counter(results.values())
        (out / "trace.json").write_text(json.dumps({"check": info, "results": results, "matrix": rows,
                                                    "totals": total}, ensure_ascii=False, indent=1))
        lines = ["| المتطلب | MoSCoW | النوع | الاختبارات | نجح | النتيجة |", "|---|---|---|---|---|---|"]
        lines += [f"| {r['id']} | {r['moscow']} | {r['kind']} | {r['tests']} | {r['passed']} | {r['verdict']} |"
                  for r in rows]
        (out / "trace.md").write_text("\n".join(lines) + "\n")
        print("نتائج الاختبارات:", dict(total))
        for r in rows:
            print(f"  {r['id']:<11} {r['moscow']:<7} {r['passed']}/{r['tests']}  {r['verdict']}")
        ok = ok and total.get("failed", 0) == 0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
