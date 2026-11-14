"""
TM354 (الوحدة 10): تغطية الاختبارات (الأسطر والفروع) لكل مكوّن.

  python se/coverage_report.py [جذر_المشروع] [--json ملف]

يحتاج coverage و pytest-cov. يشغّل كل مجموعة اختبار تحت coverage ويجمع النسب.
اختبار PostgreSQL للسباق يعمل فقط إذا ضُبط DATABASE_HOST.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _report(data_file: str, cwd: Path, include: str) -> dict:
    out = subprocess.run([sys.executable, "-m", "coverage", "json", "-o", "-", "--data-file", data_file,
                          "--include", include], cwd=cwd, capture_output=True, text=True).stdout
    tot = json.loads(out)["totals"]
    return {"lines": tot["num_statements"], "covered": tot["covered_lines"],
            "line_pct": round(100 * tot["covered_lines"] / max(1, tot["num_statements"]), 1),
            "branches": tot.get("num_branches", 0), "branch_pct":
            round(100 * tot.get("covered_branches", 0) / max(1, tot.get("num_branches", 0)), 1)}


def run(root: Path) -> dict:
    tmp = tempfile.mkdtemp()
    suites = {
        "Django (backend/core)": dict(cwd=root / "backend", include="core/*",
                                       cmd=["manage.py", "test", "core"], omit="core/migrations/*,core/tests*,core/management/*"),
        "Bot server (realtime)": dict(cwd=root / "realtime", include="realtime/*", cmd=["-m", "pytest", "-q", "tests"]),
        "App (app/gb)": dict(cwd=root / "app", include="gb/*", cmd=["-m", "pytest", "-q", "tests"],
                             omit="gb/algorithms/*,gb/app.py,gb/screens/*,gb/ui.py"),
    }
    res = {}
    for name, s in suites.items():
        data = os.path.join(tmp, name.split()[0] + ".cov")
        omit = ["--omit", s["omit"]] if s.get("omit") else []
        subprocess.run([sys.executable, "-m", "coverage", "run", "--branch", "--data-file", data,
                        "--source", ".", *omit, *s["cmd"]], cwd=s["cwd"], capture_output=True, text=True)
        res[name] = _report(data, s["cwd"], s["include"])
    return res


if __name__ == "__main__":
    argv = sys.argv[1:]
    out = argv.pop(argv.index("--json") + 1) if "--json" in argv else None
    args = [a for a in argv if not a.startswith("--")]
    root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[1]
    r = run(root)
    for k, v in r.items():
        print(f"{k:<24} أسطر {v['line_pct']:>5}%  فروع {v['branch_pct']:>5}%  ({v['covered']}/{v['lines']})")
    if out:
        Path(out).write_text(json.dumps(r, ensure_ascii=False, indent=1))
