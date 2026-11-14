"""
يضيف الألعاب التجريبية الثلاث ومهامها. الروبوت (في خادم python-socketio) يلعبها فعلاً.
المبالغ بالسنت (100 = 1 دولار) وهي أرباح محاكاة. المدد تقديرية لأغراض خطة المستشار.
"""
from django.db import migrations

GAMES = [
    ("coins", "جمع العملات", "مغامرات", "BFS – أقصر طريق", "خريطة فيها جدران وعملات، والروبوت يجد أقصر طريق."),
    ("guess", "تخمين الرقم", "ألغاز", "البحث الثنائي", "رقم سري بين 1 و 1000، والروبوت يجده في 10 محاولات أو أقل."),
    ("xo", "إكس أو", "استراتيجية", "Minimax", "الروبوت يحسب كل الاحتمالات فلا يخسر أبداً."),
]
# (key, title, kind, reward_cents, minutes, max_per_day)
TASKS = [
    ("round", "جولة لعب", "round", 100, 1, 50),
    ("daily", "المكافأة اليومية", "daily", 50, 1, 1),
    ("streak", "تحدي 3 انتصارات متتالية", "challenge", 100, 3, 5),
    ("tournament", "جولة بطولة", "tournament", 200, 3, 3),
]


def seed(apps, schema_editor):
    GamePlatform = apps.get_model("core", "GamePlatform")
    GameTask = apps.get_model("core", "GameTask")
    for key, name, cat, algo, desc in GAMES:
        p, _ = GamePlatform.objects.get_or_create(key=key, owner=None, defaults=dict(
            name=name, category=cat, algorithm=algo, description=desc, is_demo=True))
        for tkey, title, kind, cents, minutes, per_day in TASKS:
            if key == "guess" and kind == "challenge":
                continue   # تخمين الرقم ليس فيه خسارة، فلا معنى لتحدي الانتصارات المتتالية
            GameTask.objects.get_or_create(platform=p, key=tkey, defaults=dict(
                title=title, kind=kind, reward_cents=cents, minutes=minutes, max_per_day=per_day))


def unseed(apps, schema_editor):
    apps.get_model("core", "GamePlatform").objects.filter(is_demo=True, owner=None).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
