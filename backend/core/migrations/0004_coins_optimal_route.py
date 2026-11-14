"""M269: لعبة «جمع العملات» صارت تستخدم المسار الأمثل (BFS + Held-Karp) بدل الأقرب أولاً."""
from django.db import migrations


def forwards(apps, schema_editor):
    apps.get_model("core", "GamePlatform").objects.filter(key="coins", is_demo=True, owner__isnull=True).update(
        algorithm="BFS + Held-Karp – المسار الأمثل",
        description="خريطة فيها جدران وعملات، والروبوت يحسب أفضل ترتيب لجمعها كلها بأقل عدد خطوات.")


def backwards(apps, schema_editor):
    apps.get_model("core", "GamePlatform").objects.filter(key="coins", is_demo=True, owner__isnull=True).update(
        algorithm="BFS – أقصر طريق", description="خريطة فيها جدران وعملات، والروبوت يجد أقصر طريق.")


class Migration(migrations.Migration):
    dependencies = [("core", "0003_unique_play_session")]
    operations = [migrations.RunPython(forwards, backwards)]
