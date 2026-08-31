"""One-time reconciliation of the user-approved August 2026 starting point."""

from collections import defaultdict
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from readings.models import Reading, ReadingSchedule
from readings.services.notifications import monthly_due_date


BASELINE_MONTH = date(2026, 8, 1)
BASELINE_END = date(2026, 9, 1)
BASELINE_NOTE = "Base operativa agosto 2026"


def baseline_plan():
    """Only confirmed August records of active nodes participate; July is untouched."""
    grouped = defaultdict(list)
    readings = Reading.objects.select_related("schedule__node").filter(
        schedule__node__active=True,
        status=Reading.Status.CONFIRMED,
        confirmed_value__isnull=False,
        reading_date__gte=BASELINE_MONTH,
        reading_date__lt=BASELINE_END,
    ).order_by("schedule__node__name", "reading_date", "id")
    for reading in readings:
        grouped[reading.schedule.node_id].append(reading)

    plan = []
    for node_readings in grouped.values():
        node = node_readings[0].schedule.node
        if not node.reading_day or not 1 <= node.reading_day <= 31:
            raise ValidationError(f"{node.name}: falta configurar el día de lectura.")
        if len(node_readings) > 2:
            raise ValidationError(f"{node.name}: hay más de dos lecturas; se requiere revisar antes de clasificar.")
        monthly_due = monthly_due_date(node, BASELINE_MONTH)
        follow_up_due = node_readings[0].reading_date + timedelta(days=10)
        if len(node_readings) == 2 and monthly_due == follow_up_due:
            raise ValidationError(f"{node.name}: mensual y seguimiento coinciden en fecha; se requiere revisar.")
        ids = [reading.pk for reading in node_readings]
        for index, reading in enumerate(node_readings):
            due_date = monthly_due if index == 0 else follow_up_due
            target = ReadingSchedule.objects.filter(node=node, due_date=due_date).first()
            if target and target.readings.exclude(pk__in=ids).exists():
                raise ValidationError(f"{node.name}: la programación destino contiene otros registros.")
            plan.append({
                "node_id": node.pk,
                "node_name": node.name,
                "reading_id": reading.pk,
                "reading_date": reading.reading_date.isoformat(),
                "value": str(reading.confirmed_value),
                "kind": "MONTHLY" if index == 0 else "FOLLOW_UP",
                "due_date": due_date.isoformat(),
                "previous_schedule_id": reading.schedule_id,
                "previous_due_date": reading.schedule.due_date.isoformat(),
                "previous_notes": reading.schedule.notes,
                "previous_status": reading.schedule.status,
            })
    return plan


def _notes(previous, kind):
    label = "Lectura mensual" if kind == "MONTHLY" else "Seguimiento de 10 días"
    if previous.startswith(label) and BASELINE_NOTE in previous:
        return previous
    result = f"{label} | {BASELINE_NOTE}"
    if previous and previous != label:
        result += f" | Observación anterior: {previous}"
    return result


@transaction.atomic
def apply_baseline(expected_plan):
    """Apply a reviewed plan atomically; refuse changes if data has moved meanwhile."""
    plan = baseline_plan()
    if plan != expected_plan:
        raise ValidationError("Las lecturas cambiaron desde la revisión. Genera nuevamente el plan.")
    selected_ids = [item["reading_id"] for item in plan]
    used_ids = set()
    original_ids = {item["previous_schedule_id"] for item in plan}
    changes = []
    for item in plan:
        reading = Reading.objects.select_related("schedule").get(pk=item["reading_id"])
        source = reading.schedule
        due_date = date.fromisoformat(item["due_date"])
        target = ReadingSchedule.objects.filter(node_id=item["node_id"], due_date=due_date).first()
        previous = None
        if target is None:
            # Reuse an unshared source row to avoid creating empty duplicate rows.
            reusable = source.pk not in used_ids and not source.readings.exclude(pk__in=selected_ids).exists()
            if reusable:
                target = source
                previous = {"id": target.pk, "due_date": str(target.due_date), "status": target.status, "notes": target.notes}
                target.due_date = due_date
            else:
                target = ReadingSchedule(node_id=item["node_id"], due_date=due_date)
        elif target.pk:
            previous = {"id": target.pk, "due_date": str(target.due_date), "status": target.status, "notes": target.notes}
        target.status = ReadingSchedule.Status.COMPLETED
        target.notes = _notes(target.notes, item["kind"])
        target.save()
        if reading.schedule_id != target.pk:
            reading.schedule = target
            reading.save(update_fields=["schedule"])
        used_ids.add(target.pk)
        changes.append({**item, "schedule_id": target.pk, "schedule_before": previous, "notes": target.notes})

    # Keep historical rows for audit, but do not leave empty obsolete tasks pending.
    cancelled = []
    for schedule in ReadingSchedule.objects.filter(pk__in=original_ids - used_ids):
        if not schedule.readings.exists() and schedule.status != ReadingSchedule.Status.CANCELLED:
            schedule.status = ReadingSchedule.Status.CANCELLED
            schedule.save(update_fields=["status"])
            cancelled.append(schedule.pk)
    for item in plan:
        if item["kind"] != "MONTHLY":
            continue
        follow_up_due = date.fromisoformat(item["reading_date"]) + timedelta(days=10)
        obsolete = ReadingSchedule.objects.filter(
            node_id=item["node_id"], notes__istartswith="Seguimiento",
            due_date__gte=BASELINE_MONTH, due_date__lt=BASELINE_END,
            status=ReadingSchedule.Status.PENDING, readings__isnull=True,
        ).exclude(due_date=follow_up_due)
        cancelled.extend(obsolete.values_list("pk", flat=True))
        obsolete.update(status=ReadingSchedule.Status.CANCELLED)
    return {"readings": changes, "cancelled_empty_schedules": cancelled}
