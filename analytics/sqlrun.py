"""
تشغيل استعلامات TM351 على PostgreSQL، وتجربة أثر الفهارس بـ EXPLAIN ANALYZE.

  python -m analytics.sqlrun                 # كل الاستعلامات
  python -m analytics.sqlrun --bench         # تجربة الفهارس

الاتصال من متغيرات البيئة نفسها التي يستخدمها Django: DATABASE_HOST/PORT/NAME/USER/PASSWORD.
"""
from __future__ import annotations

import json
import os
import re
import statistics
import sys
from pathlib import Path

import pandas as pd
import psycopg

SQL_FILE = Path(__file__).with_name("sql") / "queries.sql"


def connect():
    return psycopg.connect(host=os.environ.get("DATABASE_HOST", "127.0.0.1"),
                           port=os.environ.get("DATABASE_PORT", "5432"),
                           dbname=os.environ.get("DATABASE_NAME", "gamebot"),
                           user=os.environ.get("DATABASE_USER", "gamebot"),
                           password=os.environ.get("DATABASE_PASSWORD", ""), autocommit=True)


def load_queries(path: Path = SQL_FILE) -> dict[str, str]:
    """يقرأ الملف ويقسمه حسب سطور «-- name: ...»."""
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^-- name: (\w+)\s*$", text, flags=re.M)
    return {parts[i]: parts[i + 1].strip().rstrip(";") for i in range(1, len(parts), 2)}


def run(conn, sql: str, params=None) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def explain_ms(conn, sql: str, params=None, repeat: int = 15) -> tuple[float, str]:
    """وسيط زمن التنفيذ (ms) من EXPLAIN ANALYZE، ونوع المسح في الخطة."""
    times, plan = [], None
    with conn.cursor() as cur:
        for _ in range(repeat):
            cur.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql, params)
            out = cur.fetchone()[0][0]
            times.append(out["Execution Time"])
            plan = out["Plan"]
    return round(statistics.median(times), 3), _scan_types(plan)


def _scan_types(plan: dict) -> str:
    found = []

    def walk(n):
        if "Scan" in n["Node Type"]:
            found.append(n["Node Type"] + (f" ({n['Index Name']})" if n.get("Index Name") else ""))
        for c in n.get("Plans", []):
            walk(c)
    walk(plan)
    return "; ".join(dict.fromkeys(found))


BENCH = {
    # (الوصف، الاستعلام، فهرس للتجربة: يُحذف ثم يُعاد)
    "user_week": ("أرباح مستخدم واحد في آخر 7 أيام",
                  "SELECT SUM(cents) FROM core_earningrecord WHERE user_id = %(uid)s "
                  "AND created_at >= %(since)s",
                  "core_earnin_user_id_5c1350_idx", "core_earningrecord (user_id, created_at)"),
    "all_day": ("أرباح كل المستخدمين في يوم واحد",
                "SELECT SUM(cents) FROM core_earningrecord WHERE created_at >= %(day)s "
                "AND created_at < %(day)s + interval '1 day'",
                "tm351_earning_created_idx", "core_earningrecord (created_at)"),
}


def bench(conn) -> list[dict]:
    uid = run(conn, "SELECT user_id FROM core_earningrecord GROUP BY user_id ORDER BY COUNT(*) DESC LIMIT 1").iloc[0, 0]
    last = run(conn, "SELECT MAX(created_at) FROM core_earningrecord").iloc[0, 0]
    params = {"uid": int(uid), "since": last - pd.Timedelta(days=7), "day": last.normalize()}
    rows = []
    for key, (label, sql, idx, cols) in BENCH.items():
        exists = not run(conn, "SELECT 1 FROM pg_indexes WHERE indexname = %s", (idx,)).empty
        with conn.cursor() as cur:
            if exists:
                definition = run(conn, "SELECT indexdef FROM pg_indexes WHERE indexname = %s", (idx,)).iloc[0, 0]
                cur.execute(f"DROP INDEX {idx}")
            cur.execute("ANALYZE core_earningrecord")
        t_without, plan_without = explain_ms(conn, sql, params)
        with conn.cursor() as cur:
            cur.execute(definition if exists else f"CREATE INDEX {idx} ON {cols}")
            cur.execute("ANALYZE core_earningrecord")
        t_with, plan_with = explain_ms(conn, sql, params)
        if not exists:
            with conn.cursor() as cur:
                cur.execute(f"DROP INDEX {idx}")        # تجربة فقط: لا نترك فهرساً لا يحتاجه التطبيق
        rows.append({"query": key, "label": label, "index": cols, "ms_without": t_without, "plan_without": plan_without,
                     "ms_with": t_with, "plan_with": plan_with, "speedup": round(t_without / t_with, 1)})
    return rows


def main():
    conn = connect()
    if "--bench" in sys.argv:
        print(json.dumps(bench(conn), ensure_ascii=False, indent=1, default=str))
        return
    for name, sql in load_queries().items():
        df = run(conn, sql)
        print(f"\n== {name} ({len(df)} rows)\n{df.head(12).to_string(index=False)}")


if __name__ == "__main__":
    main()
