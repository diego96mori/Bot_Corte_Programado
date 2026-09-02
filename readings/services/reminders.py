import logging
from datetime import timedelta

from asgiref.sync import sync_to_async
from django.utils import timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from readings.models import Reading, ReadingSchedule, ReminderLog
from readings.services.notifications import get_reading_notifications


REMINDER_INTERVAL = timedelta(hours=5)
logger = logging.getLogger(__name__)


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
        if schedule.status == ReadingSchedule.Status.CANCELLED:
            continue
        if schedule.readings.filter(
            status=Reading.Status.CONFIRMED, confirmed_value__isnull=False,
        ).exists():
            # A reminder must never reopen a schedule with a confirmed reading.
            if schedule.status != ReadingSchedule.Status.COMPLETED:
                schedule.status = ReadingSchedule.Status.COMPLETED
                schedule.save(update_fields=["status"])
            continue
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
    availability = ""
    if item.kind == "FOLLOW_UP" and item.cutoff and item.due_date >= item.cutoff:
        availability = (
            f"🛑 Último día para registrarlo: "
            f"{item.cutoff - timedelta(days=1):%d/%m/%Y}\n"
        )
    return (
        "🔔 WI-NET | RECORDATORIO DE LECTURA\n\n"
        f"⚠️ {state}\n\n"
        f"🏢 Nodo: {item.node.name}\n"
        f"📌 Tipo: {kind_label}\n"
        f"🧾 Suministro: {item.node.supply_number or 'No registrado'}\n"
        f"💡 Concesionaria: {item.node.provider or 'No registrada'}\n"
        f"📅 Fecha programada: {item.due_date:%d/%m/%Y}\n"
        f"{availability}"
        f"⏰ Estado: {item.status_label}\n\n"
        "Registra la fotografía del medidor desde el botón inferior."
    )


async def send_reminder_jobs(bot, jobs):
    """Persist each successful delivery before attempting the next recipient."""
    results = []
    for job in jobs:
        item = job["item"]
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📷 Registrar lectura", callback_data=f"reminder_register:{item.node.id}")]]
        )
        try:
            message = await bot.send_message(
                chat_id=job["chat_id"], text=reminder_text(item), reply_markup=keyboard
            )
        except TelegramError:
            logger.exception("No se pudo enviar el recordatorio de la programación %s", job["schedule"].pk)
            continue
        result = (job, message.message_id)
        await sync_to_async(record_reminder_results)([result])
        results.append(result)
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
