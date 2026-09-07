from django.db import migrations, models


def exclude_existing_photos(apps, schema_editor):
    Reading = apps.get_model("readings", "Reading")
    Reading.objects.using(schema_editor.connection.alias).exclude(photo="").update(
        ocr_learning_excluded=True, ocr_learning_verified=False,
    )


class Migration(migrations.Migration):
    dependencies = [("readings", "0007_reading_ocr_learning_verified")]
    operations = [
        migrations.AddField(
            model_name="reading", name="ocr_learning_excluded",
            field=models.BooleanField(default=False, verbose_name="excluida del aprendizaje por ser histórica"),
        ),
        migrations.RunPython(exclude_existing_photos, migrations.RunPython.noop),
    ]
