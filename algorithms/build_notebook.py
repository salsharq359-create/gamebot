"""يبني دفتر Jupyter الخاص بمقرر M269 ثم يشغّله:  python algorithms/build_notebook.py"""
from pathlib import Path

import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "algorithms" / "GameBot-M269.ipynb"
cells = []
md = lambda s: cells.append(nbf.v4.new_markdown_cell(s.strip()))
code = lambda s: cells.append(nbf.v4.new_code_cell(s.strip()))

md("""<div dir="rtl">

# جيم بوت — تطبيق مقرر M269 (الخوارزميات وهياكل البيانات والحوسبة)

الدفتر يقيس كل خوارزمية في جيم بوت ويقارنها بالنظرية، ويبيّن كيف غيّر هذا التحليل الروبوت نفسه:

1. **التعقيد**: هل الزمن المقاس يطابق رتبة النمو النظرية؟
2. **هياكل البيانات**: الطابور، والكومة، وجدول التجزئة، من الصفر
3. **الجشع مقابل البرمجة الديناميكية**: ترتيب جمع العملات، وخطة المستشار
4. **الرسوم البيانية**: BFS و Dijkstra و A* على خريطة بتضاريس
5. **الاستدعاء الذاتي والذاكرة**: Minimax في «إكس أو»
6. **حدود الحوسبة**: NP-hard، والزمن شبه كثير الحدود، ومسألة التوقف

كل التجارب بذور ثابتة، فتعطي نفس الأرقام عند إعادة التشغيل (عدا الأزمنة بالملي ثانية).
</div>""")
code("""
import sys, json, math
from pathlib import Path
ROOT = Path.cwd() if (Path.cwd() / "algorithms").exists() else Path.cwd().parent
sys.path.insert(0, str(ROOT))
import pandas as pd
from algorithms import experiments as E, figures as F, structures as S, sorting, graphs as G, tsp, knapsack
FIG = ROOT / "algorithms" / "figures"; FIG.mkdir(exist_ok=True)
R = {}
""")

md("""<div dir="rtl">

## 1. التعقيد: النظرية مقابل القياس

إذا كان الزمن ≈ c·nᵏ فإن log(الزمن) = k·log(n) + ثابت، أي أن **ميل** الخط على محورين لوغاريتميين يقدّر k.
ميل ≈ 1 يعني خطياً (أو n log n)، وميل ≈ 2 يعني تربيعياً.

### 1.1 ترتيب لوحة المتصدرين
</div>""")
code("""
R["sorting"] = E.sorting_growth()
F.sorting_loglog(R["sorting"], "ar", FIG / "sorting_ar.png")
pd.DataFrame({k: {"ميل الزمن": v["slope"], "ميل المقارنات": v["slope_comparisons"],
                  "مقارنات عند n=2000": v["comparisons"][v["n"].index(2000)]} for k, v in R["sorting"].items()}).T
""")
md("""<div dir="rtl">

**ميل المقارنات** هو المقياس الثابت: الإدراج 2.0 (تربيعي)، والبقية نحو 1.15 (n log n يبدو أكبر قليلاً من 1 على
هذه الأحجام). ميل **الزمن** يتغير قليلاً بين تشغيل وآخر لأنه يتأثر بالذاكرة المؤقتة وبمفسّر بايثون.
عند 2,000 لاعب يحتاج الإدراج نحو مليون مقارنة، والدمج نحو 19 ألفاً فقط.

### 1.2 البحث: خطي مقابل ثنائي (أسوأ حالة)
</div>""")
code("""R["search"] = E.search_growth(); pd.DataFrame(R["search"])""")
md("""<div dir="rtl">

### 1.3 BFS على خرائط أكبر
</div>""")
code("""R["bfs"] = E.bfs_growth(); print("ميل الزمن مقابل عدد الخلايا V:", R["bfs"]["slope"]); pd.DataFrame(R["bfs"]).drop(columns="slope")""")

md("""<div dir="rtl">

## 2. هياكل البيانات

### 2.1 الكومة: heapify مقابل n عمليات push
</div>""")
code("""R["heap"] = E.heap_build(); pd.DataFrame(R["heap"])""")
md("""<div dir="rtl">

البناء من الأسفل للأعلى يحتاج نحو 1.9n مقارنة مهما كبر n (أي O(n))، والإدخال واحداً واحداً أكثر.
وفي ترتيب الكومة نحتاج بعد ذلك n عمليات pop، كل واحدة O(log n).

### 2.2 جدول التجزئة
</div>""")
code("""R["hashmap"] = E.hashmap_probes(); pd.Series(R["hashmap"])""")
md("""<div dir="rtl">

متوسط 1.2 مقارنة لكل بحث بين 50 ألف مفتاح: هذا معنى O(1) في المتوسط، لأن التكبير يُبقي الحمل تحت 0.75.
</div>""")

md("""<div dir="rtl">

## 3. الجشع مقابل البرمجة الديناميكية

### 3.1 ترتيب جمع العملات
كان الروبوت يذهب دائماً لأقرب عملة. نقارن ذلك بالترتيب الأمثل (Held-Karp) على 3,000 خريطة من محرك اللعبة نفسه:
</div>""")
code("""
R["routes"] = E.coin_routes()
F.gap_hist(R["routes"], "ar", FIG / "gap_ar.png")
pd.Series({k: v for k, v in R["routes"].items() if k != "hist"})
""")
code("""R["route_steps"] = E.coin_route_steps(); pd.Series(R["route_steps"])""")
md("""<div dir="rtl">

«الأقرب أولاً» ليس الأقصر في نحو 45% من الخرائط، وقد يزيد حتى 10 خطوات. **لذلك صار الروبوت يستخدم Held-Karp**،
فقلّ متوسط الخطوات الفعلية من 21.4 إلى 20.1 (6.2%). والحساب سريع: 6 عملات = 186 حالة فقط.

### 3.2 لماذا لا نجرّب كل الترتيبات؟
</div>""")
code("""
R["tsp"] = E.tsp_growth()
F.tsp_growth(R["tsp"], "ar", FIG / "tsp_ar.png")
pd.DataFrame(R["tsp"]["held_karp"]).merge(pd.DataFrame(R["tsp"]["brute_force"]), on="k", how="left",
                                         suffixes=("_held_karp", "_brute"))
""")
md("""<div dir="rtl">

البحث الشامل ينمو مثل k! والبرمجة الديناميكية مثل 2ᵏ·k². الاثنان أُسّيان، لكن الفرق ضخم:
عند 14 عملة، 14! ≈ 87 مليار ترتيب، مقابل نحو 115 ألف حالة.

### 3.3 خطة المستشار (حقيبة الظهر 0/1)
</div>""")
code("""R["knapsack"] = E.knapsack_compare(); pd.Series(R["knapsack"])""")
code("""R["knapsack_T"] = E.knapsack_pseudo_poly(); print("ميل زمن DP مقابل T:", R["knapsack_T"]["slope"]); pd.DataFrame(R["knapsack_T"]).drop(columns=["slope","n"])""")
md("""<div dir="rtl">

الجشع يخطئ في 7% من الحالات المشابهة لمهام جيم بوت، لذلك يستخدم المستشار البرمجة الديناميكية، واختبار تلقائي
يقارنه بالبحث الشامل على 150 حالة. وزمن DP يتضاعف تقريباً عندما تتضاعف الدقائق T: هذا «شبه كثير حدود».
</div>""")

md("""<div dir="rtl">

## 4. الرسوم البيانية مع التضاريس

خرائط 12×12 فيها جدران وطين (تكلفة 3). BFS يجد أقل **عدد** خطوات، لا أقل **تكلفة**:
</div>""")
code("""
R["terrain"] = E.terrain_search()
F.search_nodes(R["terrain"], "ar", FIG / "search_ar.png")
pd.Series(R["terrain"])
""")
md("""<div dir="rtl">

مسار BFS أغلى في أكثر من نصف الخرائط. و A* يجد نفس تكلفة Dijkstra (لأن مسافة مانهاتن لا تبالغ أبداً)
لكنه يفحص عقداً أقل بنحو 60%.
</div>""")

md("""<div dir="rtl">

## 5. الاستدعاء الذاتي والذاكرة: Minimax
</div>""")
code("""R["minimax"] = E.minimax_nodes(); pd.Series(R["minimax"])""")
md("""<div dir="rtl">

Minimax بالاستدعاء الذاتي يزور 549,946 عقدة من لوحة فارغة، لكن عدد الوضعيات المختلفة 5,478 فقط.
الذاكرة (memoisation بجدول تجزئة، `lru_cache` في المحرك) تقلل العمل نحو 100 مرة. والقيمة 0 تعني أن اللعب المثالي
من الطرفين ينتهي بالتعادل، ولهذا لا يخسر الروبوت أبداً.
</div>""")

md("""<div dir="rtl">

## 6. حدود الحوسبة

* **ترتيب جمع العملات** نسخة من مسألة البائع المتجول (TSP)، وهي NP-hard: لا نعرف خوارزمية زمنها كثير حدود في k.
  نحلها بدقة لأن k = 6 صغير، ولو كبرت الخريطة لاحتجنا تقريباً (مثل الأقرب أولاً مع تحسين 2-opt).
* **خطة المستشار** حقيبة ظهر 0/1، ونسختها القرارية NP-complete. الحل O(n·T) ليس كثير حدود في **حجم** المدخلات،
  لأن T يُكتب بـ log T بت. لكنه سريع عملياً لأن T ≤ 240 دقيقة.
* **مسألة التوقف**: لو سمح التطبيق للمستخدم بكتابة برنامج لروبوته، لا يمكن لأي برنامج أن يقرر مسبقاً لكل البرامج
  هل ستنتهي (تورنغ 1936). لذلك المهام في جيم بوت **بيانات** (مكافأة ومدة)، وأي تنفيذ يجب أن تكون له مهلة.
</div>""")
code("""
(FIG / "results.json").write_text(json.dumps(R, ensure_ascii=False, indent=1, default=float))
print("محفوظ:", sorted(p.name for p in FIG.glob("*")))
""")

nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3"},
                                                "language_info": {"name": "python"}})
ExecutePreprocessor(timeout=900, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(ROOT)}})
nbf.write(nb, NB)
print("wrote", NB)
