"""
TM351: إزالة الجلسات المكررة (من إعادة إرسال المزامنة) ثم إضافة قيد التفرد على (المستخدم، وقت البداية).
"""
from django.db import migrations, models


def remove_duplicates(apps, schema_editor):
    PlaySession = apps.get_model("core", "PlaySession")
    seen = set()
    extra = []
    for pk, uid, started in PlaySession.objects.order_by("pk").values_list("pk", "user_id", "started_at"):
        if (uid, started) in seen:
            extra.append(pk)
        else:
            seen.add((uid, started))
    PlaySession.objects.filter(pk__in=extra).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0002_seed_demo_games")]
    operations = [
        migrations.RunPython(remove_duplicates, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="playsession",
            constraint=models.UniqueConstraint(fields=("user", "started_at"), name="uniq_session_start"),
        ),
    ]
