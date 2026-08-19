from django.db import migrations


def backfill_reading_date(apps, schema_editor):
    Reading = apps.get_model("readings", "Reading")
    for reading in Reading.objects.filter(reading_date__isnull=True).select_related("schedule"):
        reading.reading_date = reading.schedule.due_date
        reading.save(update_fields=["reading_date"])


class Migration(migrations.Migration):
    dependencies = [("readings", "0003_node_billing_day_node_due_day_node_provider_and_more")]
    operations = [migrations.RunPython(backfill_reading_date, migrations.RunPython.noop)]

