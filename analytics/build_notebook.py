"""يبني دفتر Jupyter الخاص بمقرر TM351 ثم يشغّله:  python analytics/build_notebook.py"""
from pathlib import Path

import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "analytics" / "GameBot-TM351.ipynb"
cells = []
md = lambda s: cells.append(nbf.v4.new_markdown_cell(s.strip()))
code = lambda s: cells.append(nbf.v4.new_code_cell(s.strip()))

md("""
<div dir="rtl">

# جيم بوت — تطبيق مقرر TM351 (إدارة البيانات وتحليلها)

هذا الدفتر يمر بدورة حياة البيانات كاملة على بيانات جيم بوت:

1. **جمع البيانات** من قاعدة PostgreSQL ومن السجلات الخام (JSONL)
2. **الأخلاقيات والخصوصية**: الأسماء المستعارة، وفحص k-anonymity
3. **التنظيف والتجهيز** بمكتبة pandas، مع التحقق من النتيجة مقابل قرارات الخادم
4. **التحليل** والرسوم
5. **قاعدة البيانات العلائقية**: استعلامات SQL، وأثر الفهارس
6. **قاعدة بيانات المستندات**: جلسات الروبوت في MongoDB
7. **ما وجدناه وما أصلحناه في التطبيق**

**مصدر البيانات (بصراحة):** البيانات أنتجها محاكي (`simulate_players`) لـ 300 مستخدم خلال 30 يوماً.
الروبوت يلعب فعلاً بمحرك الألعاب نفسه، والمكافآت والحدود من جدول المهام، والجلسات بدون اتصال أُرسلت عبر
مسار المزامنة الحقيقي، فالخادم هو من قبلها أو رفضها. أما **سلوك المستخدمين** (متى يلعبون، وكم مرة، ونسبة اللعب بدون
اتصال، وأخطاء أجهزتهم) فهو افتراضات المحاكي، ولا تُستنتج منه حقائق عن مستخدمين حقيقيين.

</div>
""")
code("""
import os, sys, json, warnings
from pathlib import Path
ROOT = Path.cwd() if (Path.cwd() / "analytics").exists() else Path.cwd().parent
sys.path.insert(0, str(ROOT))
import pandas as pd
from scipy import stats
from analytics import clean, analysis as A, mongo, sqlrun, figures as F
pd.set_option("display.width", 160); pd.set_option("display.max_columns", 20)
warnings.filterwarnings("ignore")
EXPORT = ROOT / "data" / "export"
FIG = ROOT / "analytics" / "figures"; FIG.mkdir(exist_ok=True)
""")

md("""<div dir="rtl">

## 1. جمع البيانات

البيانات صُدّرت من قاعدة PostgreSQL بأمر Django:

```bash
python manage.py simulate_players --users 300 --days 30 --seed 351
python manage.py export_dataset
```

خمسة جداول CSV (من القاعدة العلائقية) وملفان JSONL (بيانات خام متداخلة):
</div>""")
code("""
t = clean.load_tables(EXPORT)
pd.DataFrame({name: {"rows": len(df), "columns": len(df.columns)} for name, df in t.items()}).T
""")
code("""t["earnings"].head()""")
code("""t["earnings"].dtypes""")

md("""<div dir="rtl">

## 2. الأخلاقيات والخصوصية قبل التحليل

* لا يوجد اسم مستخدم في البيانات المصدّرة: كل مستخدم له **اسم مستعار** = HMAC(المفتاح السري، المعرّف).
* الملاحظات النصية الحرة وتواقيع HMAC حُذفت، وتاريخ التسجيل قُرّب إلى اليوم (**تقليل البيانات**).
* لكن الاسم المستعار وحده لا يكفي: قد يُعرف الشخص من **تركيبة** صفات (معرّفات شبه شخصية).
  نقيس ذلك بـ **k-anonymity**: أصغر مجموعة من المستخدمين يتشاركون نفس القيم.
</div>""")
code("""
quasi = ["joined_date", "daily_limit_min", "text_scale", "dark_mode", "leaderboard", "demo_games_linked"]
before = A.k_anonymity(t["users"], quasi)
gen = A.generalise_users(t["users"])
after = A.k_anonymity(gen, ["joined_week", "daily_limit_min"])
pd.DataFrame([before, after], index=["قبل التعميم", "بعد التعميم"])
""")
md("""<div dir="rtl">

قبل التعميم كان نحو نصف المستخدمين **متفردين** (k = 1)، أي يمكن تمييزهم لو عرف أحد تاريخ تسجيلهم وإعداداتهم.
بعد استبدال اليوم بالأسبوع وحذف إعدادات المظهر صار k = 3. لذلك أي نشر للبيانات خارج فريق التطوير يجب أن
يستخدم الجدول المعمّم.
</div>""")

md("""<div dir="rtl">

## 3. التنظيف والتجهيز

### 3.1 جدول الأرباح المرتب (tidy)
ربط الأرباح بالمنصات والمهام (merge)، وتحويل الوقت من UTC إلى توقيت الكويت، واشتقاق التاريخ والساعة واليوم والقناة.
</div>""")
code("""
e = clean.tidy_earnings(t)
e[["user", "platform_key", "task_key", "dollars", "channel", "created_at", "hour", "weekday"]].head()
""")
md("""<div dir="rtl">

### 3.2 الجلسات المكررة
</div>""")
code("""
sessions, dup_sessions = clean.dedupe_sessions(t["sessions"])
print("جلسات مكررة حُذفت:", dup_sessions, "| بقي:", len(sessions))
""")
md("""<div dir="rtl">

السبب: عند إعادة إرسال طلب المزامنة (انقطاع في المنتصف) يسجل الخادم مدة الجلسة مرتين، لأن الجلسات لم يكن
لها مفتاح فريد مثل الأرباح. **أُصلح في الخادم** (القسم 7).

### 3.3 طلبات المزامنة الخام: من JSON متداخل إلى جدول
</div>""")
code("""
raw = clean.load_sync_requests(EXPORT / "raw_sync_requests.jsonl")
print(raw.shape)
raw["ts_format"].value_counts()
""")
md("""<div dir="rtl">

ثلاث صيغ مختلفة للوقت من التطبيقات (`Z` و `+00:00` و `+03:00`)، و `pd.to_datetime(utc=True, format="ISO8601")` يوحّدها كلها.

### 3.4 إعادة اشتقاق قرار الخادم لكل سجل، والتحقق منه
</div>""")
code("""
classified = clean.classify_sync(raw, t["earnings"])
check = clean.check_against_server(classified, EXPORT / "raw_sync_requests.jsonl")
print(f"طلبات مطابقة لرد الخادم: {check['match'].sum()} من {len(check)} ({100 * check['match'].mean():.1f}%)")
reasons, by_version = A.sync_quality(classified)
reasons
""")
code("""by_version""")
md("""<div dir="rtl">

**كل** ردود الخادم (1,482 طلباً) طابقت تصنيفنا، فالتنظيف صحيح. واكتشاف مهم: **كل** سجلات النسخة القديمة 1.0
رُفضت، لأنها ترسل `Round` بحرف كبير. مستخدموها يخسرون كل أرباحهم بدون اتصال. **أُصلح في الخادم.**

### 3.5 توحيد أسماء المنصات التي يكتبها المستخدمون
</div>""")
code("""
names = A.platform_names(t["platforms"], clean.normalise_platform_name)
print("أسماء مختلفة قبل التوحيد:", t["platforms"].query("is_demo == 0")["name"].nunique(), "| بعده:", len(names))
names
""")

md("""<div dir="rtl">

## 4. التحليل
</div>""")
code("""pd.Series(A.headline(e, t["users"], sessions))""")
code("""
by_game = A.earnings_by_game_task(e)
F.earnings_by_game(by_game, "ar", FIG / "earnings_by_game_ar.png")
by_game
""")
code("""A.channel_share(e)""")
md("""<div dir="rtl">

### 4.1 متى يلعب المستخدمون؟
(هذا الرسم يعكس افتراضات المحاكي عن الشخصيات، وفائدته هنا إظهار طريقة التحليل: pivot_table ثم خريطة حرارية.)
</div>""")
code("""
hw = A.hour_weekday(sessions)
F.heatmap(hw, "ar", FIG / "heatmap_ar.png");
""")
md("""<div dir="rtl">

### 4.2 هل يحتاج الروبوت حداً يومياً؟
</div>""")
code("""
per_day, mins = A.minutes_per_day(sessions, t["users"])
F.minutes_hist(per_day, "ar", FIG / "minutes_ar.png")
pd.Series(mins)
""")
md("""<div dir="rtl">

هذه نتيجة حقيقية لأنها تأتي من تأخيرات الخادم نفسها: الجلسة تستغرق نحو 37 ثانية، وأعلى يوم لم يتجاوز 5 دقائق،
فلم يصل أي مستخدم لحده اليومي (أصغر حد 30 دقيقة). **الحد اليومي في التطبيق يقيس وقت الروبوت فقط**،
أما الوقت الذي يقضيه المستخدم في الألعاب نفسها فلا يقيسه، وهذا قيد يجب ذكره بوضوح في شاشة «اللعب الصحي».
</div>""")

md("""<div dir="rtl">

## 5. قاعدة البيانات العلائقية (PostgreSQL)

الاستعلامات في `analytics/sql/queries.sql`، وتشغيلها مباشرة على القاعدة:
</div>""")
code("""
conn = sqlrun.connect()
Q = sqlrun.load_queries()
list(Q)
""")
code("""sqlrun.run(conn, Q["q1_daily_earnings_by_game"]).tail(6)""")
code("""sqlrun.run(conn, Q["q2_top_earners_window"])""")
code("""sqlrun.run(conn, Q["q3_minutes_vs_limit"]).head(5)""")
code("""
dups_now = sqlrun.run(conn, Q["q4_duplicate_sessions"])
print("جلسات مكررة في القاعدة الآن:", len(dups_now), "(كانت 81 قبل ترحيل الإصلاح 0003)")
""")
code("""sqlrun.run(conn, Q["q5_offline_share_by_hour"]).head(8)""")
md("""<div dir="rtl">

### 5.1 أثر الفهارس
نحذف الفهرس، ونقيس زمن التنفيذ بـ `EXPLAIN ANALYZE` (وسيط 15 مرة)، ثم نعيده ونقيس مرة أخرى.
</div>""")
code("""
bench = sqlrun.bench(conn)
F.index_bench(bench, "ar", FIG / "index_ar.png")
pd.DataFrame(bench)[["label", "index", "ms_without", "ms_with", "speedup", "plan_without", "plan_with"]]
""")

md("""<div dir="rtl">

## 6. قاعدة بيانات المستندات (MongoDB)

كل جلسة روبوت مستند واحد فيه مصفوفة الألعاب. إذا ضُبط `MONGO_URL` يُستخدم MongoDB حقيقي، وإلا `mongomock`
(بنفس واجهة pymongo).
</div>""")
code("""
coll = mongo.collection()
print("مستندات:", mongo.load(coll, EXPORT / "raw_bot_sessions.jsonl"))
coll.find_one({}, {"_id": 0, "games": {"$slice": 2}})
""")
code("""pd.DataFrame(mongo.per_game_stats(coll)).set_index("_id")""")
md("""<div dir="rtl">

### 6.1 هل يتصرف البحث الثنائي كما تقول النظرية؟
لأي رقم سري بين 1 و 1000، عدد الأرقام التي يجدها البحث الثنائي في k محاولة معروف بالضبط (1، 2، 4 ... 256، ثم 489).
نقارن المرصود في آلاف الجولات بالنظرية باختبار مربع كاي:
</div>""")
code("""
observed = mongo.guess_attempts(coll)
g = A.compare_guess(observed)
p_value = stats.chi2.sf(g.attrs["chi2"], g.attrs["dof"])
F.guess_vs_theory(g, "ar", FIG / "guess_ar.png")
print(f"χ² = {g.attrs['chi2']}, درجات الحرية = {g.attrs['dof']}, p = {p_value:.2f}, n = {g.attrs['n']}")
g
""")
code("""
xo = mongo.xo_outcomes(coll)
print(xo, "| نسبة الخسارة:", 0 if "خسر الروبوت" not in xo else xo["خسر الروبوت"])
print("جلسات فيها بطولة ($elemMatch):", mongo.sessions_with_tournament(coll))
pd.DataFrame(mongo.top_sessions(coll, 5))
""")

md("""<div dir="rtl">

## 7. ما وجدناه وما أصلحناه في التطبيق

| ما وجده التحليل | الدليل | الإصلاح في الكود |
|---|---|---|
| جلسات مكررة عند إعادة إرسال المزامنة | 81 جلسة (pandas و SQL) | قيد تفرد (user, started_at) + ترحيل يحذف المكرر + `get_or_create` |
| كل سجلات النسخة القديمة تُرفض | 100% من سجلات v1.0 (`bad_task`) | الخادم يوحّد اسم المهمة إلى أحرف صغيرة |
| 15% من سجلات المزامنة تتجاوز حد المهمة اليومي | معظمها مكافأة يومية أُخذت والتطبيق متصل | توصية: التطبيق ينبه أن المكافأة اليومية قد لا تُحتسب |
| شاشة الأرباح تنفذ 7 استعلامات للأسبوع | عدّ الاستعلامات | استعلام GROUP BY واحد (من 14 إلى 8 استعلامات) |
| الحد اليومي لا يصل له أحد | أعلى يوم أقل من 5 دقائق | توصية: توضيح أن الحد يقيس وقت الروبوت فقط |

</div>""")
code("""
F.sync_reasons(reasons, "ar", FIG / "sync_ar.png")
# حفظ النتائج الرئيسية (للتقرير وللرسوم الإنجليزية)
results = {"headline": A.headline(e, t["users"], sessions), "dup_sessions": dup_sessions,
           "k_before": before, "k_after": after, "reasons": reasons["records"].to_dict(),
           "by_version": by_version.to_dict(), "match": int(check["match"].sum()), "requests": len(check),
           "records": len(raw), "ts_formats": raw["ts_format"].value_counts().to_dict(),
           "names_before": int(t["platforms"].query("is_demo == 0")["name"].nunique()), "names_after": len(names),
           "channel": A.channel_share(e).to_dict(), "minutes": mins, "bench": bench,
           "guess": g.to_dict(orient="list"), "guess_attrs": dict(g.attrs), "p_value": float(p_value), "xo": xo,
           "per_game": mongo.per_game_stats(coll), "tournament_sessions": mongo.sessions_with_tournament(coll),
           "by_game": by_game.to_dict()}
(FIG / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1, default=float))
print("الرسوم والنتائج محفوظة في", FIG)
""")

nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3"},
                                                "language_info": {"name": "python"}})
ExecutePreprocessor(timeout=900, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(ROOT)}})
nbf.write(nb, NB)
print("wrote", NB)
