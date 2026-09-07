"""Manual web registration using the bot's active-cycle rules."""
from uuid import uuid4

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from readings.models import Node, Reading, ReadingSchedule
from readings.services.registration import get_registration_plan, available_plan


def plan_identity(node, plan, today):
    return [node.pk, today.isoformat(), plan.cycle_due.isoformat(), plan.due_date.isoformat(), plan.kind]


def pending_option(node, today):
    plan = available_plan(node, today)
    label = "Pendiente de lectura mensual" if plan.kind == "MONTHLY" else "Pendiente de seguimiento"
    return {
        "token": signing.dumps(plan_identity(node, plan, today), salt="web-reading"),
        "label": f"{label} · programada {plan.due_date:%d/%m/%Y} · ciclo {plan.cycle_due:%m/%Y}",
        "explanation": plan.explanation,
        "min_date": plan.opens_on.isoformat(),
    }


def register_reading(user, data):
    photo_name = None
    storage = Reading._meta.get_field("photo").storage
    try:
        with transaction.atomic():
            node = Node.objects.select_for_update().filter(pk=data["node"], active=True).first()
            if not node:
                raise ValidationError("El nodo no está disponible.")
            today = timezone.localdate()
            plan = available_plan(node, today)
            try:
                identity = signing.loads(data["obligation"], salt="web-reading", max_age=3600)
            except signing.BadSignature:
                raise ValidationError("El pendiente ha caducado. Vuelve a elegir el nodo.")
            if identity != plan_identity(node, plan, today):
                raise ValidationError("El pendiente cambió. Vuelve a elegir el nodo antes de guardar.")
            reading_date = data["reading_date"]
            if reading_date > today:
                raise ValidationError("La fecha de toma no puede ser futura.")
            dated_plan = get_registration_plan(node, reading_date)
            if (dated_plan.cycle_due, dated_plan.due_date, dated_plan.kind) != (plan.cycle_due, plan.due_date, plan.kind):
                raise ValidationError("La fecha indicada pertenece a otro ciclo. Solo puedes registrar el pendiente del ciclo activo.")
            schedule, _ = ReadingSchedule.objects.get_or_create(
                node=node, due_date=plan.due_date,
                defaults={"notes": "Lectura mensual" if plan.kind == "MONTHLY" else "Seguimiento de 10 días"},
            )
            reading = Reading(
                schedule=schedule, confirmed_value=data["value"], reading_date=reading_date,
                status=Reading.Status.CONFIRMED, source=Reading.Source.MANUAL,
                confirmed_by=user, confirmed_at=timezone.now(),
                ocr_text="INGRESO MANUAL WEB",
            )
            photo = data.get("photo")
            if photo:
                extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[photo.image.format]
                reading.photo.save(f"web-{uuid4().hex}.{extension}", photo, save=False)
                photo_name = reading.photo.name
                # A manual attachment is evidence, not an automatically verified OCR label.
            reading.save()
            schedule.status = ReadingSchedule.Status.COMPLETED
            schedule.save(update_fields=["status"])
            return reading
    except Exception:
        if photo_name:
            storage.delete(photo_name)
        raise
