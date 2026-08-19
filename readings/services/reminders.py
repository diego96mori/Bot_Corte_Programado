from datetime import timedelta

from django.utils import timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from readings.models import ReadingSchedule, ReminderLog
from readings.services.notifications import get_reading_notifications


REMINDER_INTERVAL = timedelta(hours=5)


def prepare_reminder_jobs(now=None, force=False):
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    jobs = []
    for item in get_reading_notifications(today):
        chat_id = item.node.telegram_chat_id
        if chat_id is None:
            continue
        schedule, _ = ReadingSchedule.objects.get_or_create(
            node=item.node,
            due_date=item.due_date,
            defaults={"status": ReadingSchedule.Status.PENDING, "notes": item.kind_label},
        )
        if schedule.status != ReadingSchedule.Status.PENDING:
            schedule.status = ReadingSchedule.Status.PENDING
            schedule.notes = item.kind_label
            schedule.save(update_fields=["status", "notes"])
        latest = ReminderLog.objects.filter(schedule=schedule, chat_id=chat_id).order_by("-sent_at").first()
        if not force and latest and latest.sent_at > now - REMINDER_INTERVAL:
            continue
        jobs.append({"item": item, "schedule": schedule, "chat_id": chat_id})
    return jobs


def reminder_text(item):
    if item.kind == "FOLLOW_UP":
        kind_label = "Seguimiento de lectura (10 días)"
        state = "SEGUIMIENTO DE 10 DÍAS ATRASADO" if item.is_overdue else "SEGUIMIENTO DE 10 DÍAS PRÓXIMO"
    else:
        kind_label = "Día de lectura mensual"
        state = "LECTURA MENSUAL ATRASADA" if item.is_overdue else "LECTURA MENSUAL PRÓXIMA"
    return (
        "🔔 WI-NET | RECORDATORIO DE LECTURA\n\n"
        f"⚠️ {state}\n\n"
        f"🏢 Nodo: {item.node.name}\n"
        f"📌 Tipo: {kind_label}\n"
        f"🧾 Suministro: {item.node.supply_number or 'No registrado'}\n"
        f"💡 Concesionaria: {item.node.provider or 'No registrada'}\n"
        f"📅 Fecha programada: {item.due_date:%d/%m/%Y}\n"
        f"⏰ Estado: {item.status_label}\n\n"
        "Registra la fotografía del medidor desde el botón inferior."
    )


async def send_reminder_jobs(bot, jobs):
    results = []
    for job in jobs:
        item = job["item"]
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📷 Registrar lectura", callback_data=f"reminder_register:{item.node.id}")]]
        )
        message = await bot.send_message(
            chat_id=job["chat_id"], text=reminder_text(item), reply_markup=keyboard
        )
        results.append((job, message.message_id))
    return results


def record_reminder_results(results, now=None):
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    return ReminderLog.objects.bulk_create(
        [
            ReminderLog(
                schedule=job["schedule"],
                sent_on=today,
                chat_id=job["chat_id"],
                telegram_message_id=message_id,
            )
            for job, message_id in results
        ]
    )
