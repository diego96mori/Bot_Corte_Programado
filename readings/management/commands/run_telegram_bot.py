import asyncio
import logging
import re
import tempfile
import unicodedata
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from readings.models import Node, Reading, ReadingSchedule
from readings.services.notifications import get_node_obligation
from readings.services.ocr import read_meter
from readings.services.reminders import prepare_reminder_jobs, record_reminder_results, send_reminder_jobs

logger = logging.getLogger(__name__)
STATE = "state"
SELECT_NODE = "SELECT_NODE"
CONFIRM_NODE = "CONFIRM_NODE"
WAIT_PHOTO = "WAIT_PHOTO"
WAIT_MANUAL_VALUE = "WAIT_MANUAL_VALUE"
CONFIRM_MANUAL_VALUE = "CONFIRM_MANUAL_VALUE"
WAIT_CORRECTION = "WAIT_CORRECTION"
WAIT_DATE = "WAIT_DATE"
MODE = "mode"
ENTER = "ENTER"
CONSULT = "CONSULT"
ACTIVE_CHAT_ID = "active_chat_id"
ACTIVE_UNTIL = "active_until"
ACTIVE_STATES = {
    SELECT_NODE, CONFIRM_NODE, WAIT_PHOTO, WAIT_MANUAL_VALUE,
    CONFIRM_MANUAL_VALUE, WAIT_CORRECTION, WAIT_DATE,
}


def normalize_node_name(value):
    value = unicodedata.normalize("NFKD", value or "")
    return " ".join("".join(ch for ch in value if not unicodedata.combining(ch)).lower().split())


def find_best_node_name(query, choices):
    wanted = normalize_node_name(query)
    if not wanted:
        return None
    exact = next((item for item in choices if wanted in {normalize_node_name(item[1]), normalize_node_name(item[2])}), None)
    if exact:
        return exact
    scored = [
        (max(SequenceMatcher(None, wanted, normalize_node_name(item[1])).ratio(),
             SequenceMatcher(None, wanted, normalize_node_name(item[2])).ratio()), item)
        for item in choices
    ]
    score, best = max(scored, default=(0, None), key=lambda pair: pair[0])
    return best if score >= 0.42 else None


def format_reading_value(value):
    if value is None:
        return "No detectada"
    formatted = format(value, "f")
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted


def parse_reading_date(value, today=None):
    today = today or timezone.localdate()
    if normalize_node_name(value) == "hoy":
        return today
    try:
        return datetime.strptime((value or "").strip(), "%d/%m/%Y").date()
    except (TypeError, ValueError):
        return None


def parse_reading_value(value):
    normalized = (value or "").strip().replace(",", ".")
    if not re.fullmatch(r"\d{1,12}(?:\.\d{1,3})?", normalized):
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def mark_conversation_active(context, chat_id, now=None):
    now = now or timezone.now()
    context.user_data[ACTIVE_CHAT_ID] = chat_id
    context.user_data[ACTIVE_UNTIL] = now + timedelta(hours=1)


def is_conversation_active(data, now=None):
    now = now or timezone.now()
    return (
        data.get(STATE) in ACTIVE_STATES
        and data.get(ACTIVE_CHAT_ID) is not None
        and data.get(ACTIVE_UNTIL) is not None
        and data[ACTIVE_UNTIL] > now
    )


def active_chat_ids(application, now=None):
    now = now or timezone.now()
    return {
        data[ACTIVE_CHAT_ID]
        for data in application.user_data.values()
        if is_conversation_active(data, now)
    }


def main_menu_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📷 1. Ingresar lectura", callback_data="menu:enter")],
        [InlineKeyboardButton("🔎 2. Consultar lectura", callback_data="menu:consult")],
    ])


def cancel_registration_markup(rows=None):
    rows = list(rows or [])
    rows.append([InlineKeyboardButton("❌ Cancelar registro", callback_data="reading:cancel")])
    return InlineKeyboardMarkup(rows)


def welcome_text():
    return (
        "👋 Hola. Aquí podrás ingresar y consultar las lecturas de los nodos de WI-NET.\n\n"
        "Elige una opción para continuar:"
    )


@sync_to_async
def authorized_nodes(chat_id):
    return list(Node.objects.filter(active=True, telegram_chat_id=chat_id).order_by("location", "name")
                .values_list("id", "name", "code"))


@sync_to_async
def get_authorized_node(node_id, chat_id):
    return Node.objects.filter(id=node_id, active=True, telegram_chat_id=chat_id).first()


def validated_ocr_values(node, ocr):
    previous_value = (
        Reading.objects.filter(
            schedule__node=node,
            status=Reading.Status.CONFIRMED,
            confirmed_value__isnull=False,
        )
        .order_by("-reading_date", "-id")
        .values_list("confirmed_value", flat=True)
        .first()
    )
    if ocr.value is not None and previous_value is not None and ocr.value < previous_value:
        return None, f"{ocr.raw_text} | RECHAZADA: menor que lectura anterior {previous_value}", None
    return ocr.value, ocr.raw_text, ocr.confidence


def prepare_pending_schedule(node):
    due_date, kind = get_node_obligation(node)
    schedule, _ = ReadingSchedule.objects.get_or_create(
        node=node, due_date=due_date,
        defaults={"status": ReadingSchedule.Status.PENDING,
                  "notes": "Lectura mensual" if kind == "MONTHLY" else "Seguimiento de 10 días"},
    )
    schedule.node = node
    if schedule.status != ReadingSchedule.Status.PENDING:
        schedule.status = ReadingSchedule.Status.PENDING
        schedule.save(update_fields=["status"])
    return schedule


@sync_to_async
def create_reading(node_id, image_bytes, filename, telegram_user, chat_id):
    node = Node.objects.filter(id=node_id, active=True, telegram_chat_id=chat_id).first()
    if not node:
        return None, "Este chat no está autorizado para registrar lecturas de ese nodo."
    schedule = prepare_pending_schedule(node)
    Reading.objects.filter(
        schedule=schedule, telegram_chat_id=chat_id, telegram_user_id=telegram_user.id,
        status=Reading.Status.REVIEW,
    ).update(status=Reading.Status.CANCELLED)
    suffix = Path(filename).suffix or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
        temp.write(image_bytes)
        temp_path = Path(temp.name)
    try:
        ocr = read_meter(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)
    detected_value, ocr_text, ocr_confidence = validated_ocr_values(node, ocr)
    reading = Reading(
        schedule=schedule, detected_value=detected_value, ocr_text=ocr_text,
        ocr_confidence=ocr_confidence, telegram_chat_id=chat_id,
        telegram_user_id=telegram_user.id,
        telegram_username=telegram_user.username or telegram_user.full_name,
    )
    reading.photo.save(filename, ContentFile(image_bytes), save=False)
    reading.save()
    return reading, None


@sync_to_async
def create_manual_reading(node_id, value, telegram_user, chat_id):
    node = Node.objects.filter(id=node_id, active=True, telegram_chat_id=chat_id).first()
    if not node:
        return None, "Este chat no está autorizado para registrar lecturas de ese nodo."
    schedule = prepare_pending_schedule(node)
    Reading.objects.filter(
        schedule=schedule, telegram_chat_id=chat_id, telegram_user_id=telegram_user.id,
        status=Reading.Status.REVIEW,
    ).update(status=Reading.Status.CANCELLED)
    reading = Reading.objects.create(
        schedule=schedule,
        detected_value=value,
        source=Reading.Source.MANUAL,
        ocr_text="INGRESO MANUAL SIN FOTOGRAFÍA",
        telegram_chat_id=chat_id,
        telegram_user_id=telegram_user.id,
        telegram_username=telegram_user.username or telegram_user.full_name,
    )
    return reading, None


@sync_to_async
def get_pending_node_reading(node_id, chat_id, telegram_user_id):
    reading = (
        Reading.objects.select_related("schedule__node")
        .filter(
            schedule__node_id=node_id,
            telegram_chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            status=Reading.Status.REVIEW,
        )
        .order_by("-created_at")
        .first()
    )
    if reading and reading.photo:
        ocr = read_meter(reading.photo.path)
        reading.detected_value, reading.ocr_text, reading.ocr_confidence = validated_ocr_values(
            reading.schedule.node, ocr
        )
        reading.save(update_fields=["detected_value", "ocr_text", "ocr_confidence"])
    return reading


@sync_to_async
def cancel_pending_reading(reading_id, telegram_user_id):
    if not reading_id:
        return False
    updated = Reading.objects.filter(
        pk=reading_id,
        telegram_user_id=telegram_user_id,
        status=Reading.Status.REVIEW,
    ).update(status=Reading.Status.CANCELLED)
    return bool(updated)


@sync_to_async
def confirm_reading(reading_id, telegram_user_id, reading_date, corrected_value=None):
    reading = Reading.objects.select_related("schedule__node").filter(pk=reading_id).first()
    if not reading or reading.telegram_user_id != telegram_user_id or reading.status != Reading.Status.REVIEW:
        return None
    value = corrected_value if corrected_value is not None else reading.detected_value
    if value is None:
        return None
    reading.confirmed_value = value
    reading.status = Reading.Status.CONFIRMED
    reading.reading_date = reading_date
    reading.confirmed_at = timezone.now()
    reading.save(update_fields=["confirmed_value", "status", "reading_date", "confirmed_at"])
    if reading.schedule.status != ReadingSchedule.Status.COMPLETED:
        reading.schedule.status = ReadingSchedule.Status.COMPLETED
        reading.schedule.save(update_fields=["status"])
    ReadingSchedule.objects.filter(
        node=reading.schedule.node, status=ReadingSchedule.Status.PENDING,
        due_date__lte=reading.reading_date,
    ).update(status=ReadingSchedule.Status.COMPLETED)
    return reading


@sync_to_async
def reading_history(node_id, chat_id, current_month=False):
    node = Node.objects.filter(id=node_id, active=True, telegram_chat_id=chat_id).first()
    if not node:
        return None, []
    readings = Reading.objects.filter(
        schedule__node=node, status=Reading.Status.CONFIRMED, confirmed_value__isnull=False,
        reading_date__isnull=False,
    ).order_by("-reading_date", "-id")
    if current_month:
        today = timezone.localdate()
        readings = readings.filter(reading_date__year=today.year, reading_date__month=today.month)
    return node, list(readings.values_list("reading_date", "confirmed_value")[:15])


async def show_main_menu(message, context):
    context.user_data.clear()
    await message.reply_text(welcome_text(), reply_markup=main_menu_markup())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update.message, context)


async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"El identificador de este chat es: {update.effective_chat.id}")


async def begin_node_selection(message, context, mode):
    context.user_data.clear()
    context.user_data[MODE] = mode
    context.user_data[STATE] = SELECT_NODE
    mark_conversation_active(context, message.chat.id)
    label = "registrar" if mode == ENTER else "consultar"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Ver opciones de nodos", callback_data="nodes:list")],
        [InlineKeyboardButton("↩️ Volver al inicio", callback_data="menu:home")],
    ])
    await message.reply_text(
        f"Escribe el nombre del nodo que deseas {label}, aunque no lo recuerdes exactamente.\n"
        "También puedes ver la lista completa:", reply_markup=keyboard
    )


async def show_node_list(message, context, edit=False):
    nodes = await authorized_nodes(message.chat.id)
    if not nodes:
        await message.reply_text("Este chat todavía no tiene nodos autorizados.")
        return
    keyboard = [[InlineKeyboardButton(name, callback_data=f"node:select:{node_id}")]
                for node_id, name, _code in nodes]
    keyboard.append([InlineKeyboardButton("↩️ Volver al inicio", callback_data="menu:home")])
    text = "📋 Selecciona uno de los nodos WI-NET:"
    if edit:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def select_node(message, context, node_id, telegram_user_id):
    node = await get_authorized_node(node_id, message.chat.id)
    if not node:
        await message.reply_text("Ese nodo no está disponible para este chat.")
        return
    context.user_data["node_id"] = node.id
    if context.user_data.get(MODE) == CONSULT:
        context.user_data[STATE] = None
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 Lecturas del mes actual", callback_data=f"query:current:{node.id}")],
            [InlineKeyboardButton("🗂 Últimas lecturas registradas", callback_data=f"query:recent:{node.id}")],
            [InlineKeyboardButton("↩️ Volver al inicio", callback_data="menu:home")],
        ])
        await message.reply_text(f"🔎 Consulta de lecturas\n🏢 Nodo: {node.name}\n\n¿Qué deseas ver?", reply_markup=keyboard)
    else:
        mark_conversation_active(context, message.chat.id)
        pending = await get_pending_node_reading(node.id, message.chat.id, telegram_user_id)
        if pending:
            context.user_data["reading_id"] = pending.id
            pending_description = (
                "una lectura manual pendiente" if pending.source == Reading.Source.MANUAL
                else "una fotografía ya procesada"
            )
            correction_callback = (
                f"reading:manual:correct:{pending.id}" if pending.source == Reading.Source.MANUAL
                else f"reading:correct:{pending.id}"
            )
            await message.reply_text(
                f"🔄 Encontré {pending_description} para este nodo.\n\n"
                f"🏢 Nodo: {node.name}\n"
                f"⚡ Lectura detectada: {format_reading_value(pending.detected_value)}\n\n"
                "¿Confirmas esta lectura?",
                reply_markup=cancel_registration_markup([
                    [InlineKeyboardButton("✅ Confirmar", callback_data=f"reading:confirm:{pending.id}")],
                    [InlineKeyboardButton("✏️ Corregir", callback_data=correction_callback)],
                ]),
            )
            return
        context.user_data[STATE] = WAIT_PHOTO
        await message.reply_text(
            f"📷 Registro de lectura\n🏢 Nodo: {node.name}\n\n"
            "Ahora envía una fotografía clara del medidor. Analizaré el número localmente.\n\n"
            "Si no tienes una fotografía, puedes escribir el número de la lectura.",
            reply_markup=cancel_registration_markup([[
                InlineKeyboardButton("⌨️ Escribir lectura manualmente", callback_data="reading:manual:start")
            ]]),
        )


async def ask_reading_date(message, context):
    context.user_data[STATE] = WAIT_DATE
    mark_conversation_active(context, message.chat.id)
    await message.reply_text(
        "📅 ¿Qué fecha corresponde a esta lectura?\n\n"
        "Pulsa «Hoy» para usar la fecha actual o escribe la fecha con el formato:\n"
        "DÍA/MES/AÑO — ejemplo: 17/08/2026",
        reply_markup=cancel_registration_markup([
            [InlineKeyboardButton("📅 Hoy", callback_data="date:today")],
            [InlineKeyboardButton("✍️ Escribir otra fecha", callback_data="date:manual")],
        ]),
    )


async def finish_reading(message, context, telegram_user_id, reading_date, edit=False):
    reading = await confirm_reading(
        context.user_data.get("reading_id"), telegram_user_id, reading_date,
        context.user_data.get("corrected_value"),
    )
    if reading:
        context.user_data.clear()
        text = (
            f"✅ LECTURA REGISTRADA\n\n🏢 Nodo: {reading.schedule.node.name}\n"
            f"⚡ Lectura: {format_reading_value(reading.confirmed_value)}\n"
            f"📅 Fecha: {reading.reading_date:%d/%m/%Y}\n\n"
            "La información ya aparece en LECTURAS WI-NET."
        )
    else:
        context.user_data.clear()
        text = "No se pudo registrar. La lectura ya fue procesada o no tiene un valor válido."
    if edit:
        await message.edit_text(text, reply_markup=None if reading else main_menu_markup())
    else:
        await message.reply_text(text, reply_markup=None if reading else main_menu_markup())
    if reading:
        await message.reply_text(welcome_text(), reply_markup=main_menu_markup())


async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    state = context.user_data.get(STATE)
    if state in ACTIVE_STATES:
        mark_conversation_active(context, update.effective_chat.id)
    if state == SELECT_NODE:
        if normalize_node_name(text) in {"opciones", "ver opciones", "lista"}:
            await show_node_list(update.message, context)
            return
        nodes = await authorized_nodes(update.effective_chat.id)
        best = find_best_node_name(text, nodes)
        if not best:
            await update.message.reply_text("No encontré un nodo parecido. Escribe otro nombre o pulsa «Ver opciones de nodos».")
            return
        context.user_data["candidate_id"] = best[0]
        context.user_data[STATE] = CONFIRM_NODE
        await update.message.reply_text(
            f"Encontré este nodo:\n🏢 {best[1]}\n\n¿Es el nodo correcto?",
            reply_markup=cancel_registration_markup([
                [InlineKeyboardButton("✅ Sí", callback_data="node:yes"),
                 InlineKeyboardButton("❌ No", callback_data="node:no")]
            ]),
        )
        return
    if state == WAIT_CORRECTION:
        value = parse_reading_value(text)
        if value is None:
            await update.message.reply_text("Escribe solo un número positivo. Ejemplo: 170269.6")
            return
        context.user_data["corrected_value"] = value
        await ask_reading_date(update.message, context)
        return
    if state == WAIT_MANUAL_VALUE:
        value = parse_reading_value(text)
        if value is None:
            await update.message.reply_text(
                "El valor no es válido. Escribe únicamente la lectura.\nEjemplo: 170269.6"
            )
            return
        reading_id = context.user_data.get("reading_id")
        if reading_id:
            context.user_data["corrected_value"] = value
        else:
            reading, error = await create_manual_reading(
                context.user_data.get("node_id"), value, update.effective_user,
                update.effective_chat.id,
            )
            if error:
                await update.message.reply_text(error)
                return
            reading_id = reading.id
            context.user_data["reading_id"] = reading_id
            context.user_data.pop("corrected_value", None)
        context.user_data[STATE] = CONFIRM_MANUAL_VALUE
        await update.message.reply_text(
            f"⌨️ LECTURA INGRESADA MANUALMENTE\n\n"
            f"⚡ Lectura: {format_reading_value(value)}\n\n"
            "¿El número es correcto?",
            reply_markup=cancel_registration_markup([
                [InlineKeyboardButton("✅ Sí, continuar", callback_data=f"reading:manual:confirm:{reading_id}")],
                [InlineKeyboardButton("✏️ Corregir número", callback_data=f"reading:manual:correct:{reading_id}")],
            ]),
        )
        return
    if state == CONFIRM_MANUAL_VALUE:
        await update.message.reply_text("Usa «Sí, continuar» o «Corregir número» para continuar.")
        return
    if state == WAIT_DATE:
        reading_date = parse_reading_date(text)
        if reading_date is None:
            await update.message.reply_text(
                "La fecha no es válida. Escribe «Hoy» o una fecha con el formato DÍA/MES/AÑO.\n"
                "Ejemplo: 17/08/2026"
            )
            return
        await finish_reading(update.message, context, update.effective_user.id, reading_date)
        return
    normalized = normalize_node_name(text)
    if normalized in {"1", "ingresar", "ingresar lectura"}:
        await begin_node_selection(update.message, context, ENTER)
    elif normalized in {"2", "consultar", "consultar lectura"}:
        await begin_node_selection(update.message, context, CONSULT)
    else:
        await update.message.reply_text(welcome_text(), reply_markup=main_menu_markup())


async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get(STATE) != WAIT_PHOTO or not context.user_data.get("node_id"):
        await update.message.reply_text("Primero elige «Ingresar lectura» y selecciona el nodo.", reply_markup=main_menu_markup())
        return
    mark_conversation_active(context, update.effective_chat.id)
    status = await update.message.reply_text("⏳ Procesando la imagen localmente…")
    photo = update.message.photo[-1]
    telegram_file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await telegram_file.download_as_bytearray())
    reading, error = await create_reading(
        context.user_data["node_id"], image_bytes, f"telegram_{photo.file_unique_id}.jpg",
        update.effective_user, update.effective_chat.id,
    )
    if error:
        await status.edit_text(error)
        return
    context.user_data["reading_id"] = reading.id
    detected = format_reading_value(reading.detected_value)
    confidence = f"{reading.ocr_confidence:.0%}" if reading.ocr_confidence is not None else "no disponible"
    await status.edit_text(
        f"🔍 ANÁLISIS COMPLETADO\n\n🏢 Nodo: {reading.schedule.node.name}\n"
        f"⚡ Lectura detectada: {detected}\n🎯 Confianza OCR: {confidence}\n\n¿Confirmas esta lectura?",
        reply_markup=cancel_registration_markup([
            [InlineKeyboardButton("✅ Confirmar", callback_data=f"reading:confirm:{reading.id}")],
            [InlineKeyboardButton("✏️ Corregir", callback_data=f"reading:correct:{reading.id}")],
        ]),
    )


async def show_history(message, node_id, chat_id, current_month):
    node, rows = await reading_history(node_id, chat_id, current_month)
    if not node:
        await message.reply_text("Ese nodo no está disponible para este chat.")
        return
    title = "LECTURAS DEL MES ACTUAL" if current_month else "ÚLTIMAS LECTURAS REGISTRADAS"
    lines = [f"📊 {title}", "", f"🏢 Nodo: {node.name}", ""]
    if rows:
        lines.extend(f"• {day:%d/%m/%Y}: {format_reading_value(value)}" for day, value in rows)
    else:
        lines.append("No hay lecturas registradas en este periodo.")
    await message.reply_text("\n".join(lines), reply_markup=main_menu_markup())


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "menu:home":
        context.user_data.clear()
        await query.edit_message_text(welcome_text(), reply_markup=main_menu_markup())
    elif data == "reading:cancel":
        await cancel_pending_reading(context.user_data.get("reading_id"), update.effective_user.id)
        context.user_data.clear()
        await query.edit_message_text(
            "❌ REGISTRO CANCELADO\n\n"
            "La lectura no fue registrada.\n\n"
            f"{welcome_text()}",
            reply_markup=main_menu_markup(),
        )
    elif data == "menu:enter":
        await begin_node_selection(query.message, context, ENTER)
    elif data == "menu:consult":
        await begin_node_selection(query.message, context, CONSULT)
    elif data == "nodes:list":
        await show_node_list(query.message, context, edit=True)
    elif data == "node:no":
        context.user_data[STATE] = SELECT_NODE
        mark_conversation_active(context, update.effective_chat.id)
        await query.edit_message_text("De acuerdo. Escribe nuevamente el nombre o selecciona la lista completa.",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 Ver opciones", callback_data="nodes:list")]]))
    elif data == "node:yes":
        await select_node(query.message, context, context.user_data.get("candidate_id"), update.effective_user.id)
    elif data.startswith("node:select:"):
        await select_node(query.message, context, int(data.rsplit(":", 1)[1]), update.effective_user.id)
    elif data.startswith("reminder_register:"):
        context.user_data.clear()
        context.user_data[MODE] = ENTER
        await select_node(query.message, context, int(data.rsplit(":", 1)[1]), update.effective_user.id)
    elif data.startswith("query:"):
        _, period, raw_id = data.split(":")
        await show_history(query.message, int(raw_id), update.effective_chat.id, period == "current")
    elif data == "reading:manual:start":
        if not context.user_data.get("node_id"):
            await query.message.reply_text("Primero selecciona el nodo.", reply_markup=main_menu_markup())
            return
        context.user_data[STATE] = WAIT_MANUAL_VALUE
        context.user_data.pop("reading_id", None)
        context.user_data.pop("corrected_value", None)
        mark_conversation_active(context, update.effective_chat.id)
        await query.message.reply_text(
            "⌨️ Escribe el número que aparece en el medidor.\n\nEjemplo: 170269.6",
            reply_markup=cancel_registration_markup(),
        )
    elif data.startswith("reading:manual:confirm:"):
        context.user_data["reading_id"] = int(data.rsplit(":", 1)[1])
        await ask_reading_date(query.message, context)
    elif data.startswith("reading:manual:correct:"):
        context.user_data["reading_id"] = int(data.rsplit(":", 1)[1])
        context.user_data[STATE] = WAIT_MANUAL_VALUE
        mark_conversation_active(context, update.effective_chat.id)
        await query.message.reply_text(
            "✏️ Escribe nuevamente el número correcto. Ejemplo: 170269.6",
            reply_markup=cancel_registration_markup(),
        )
    elif data.startswith("reading:confirm:"):
        context.user_data["reading_id"] = int(data.rsplit(":", 1)[1])
        context.user_data.pop("corrected_value", None)
        await ask_reading_date(query.message, context)
    elif data.startswith("reading:correct:"):
        context.user_data[STATE] = WAIT_CORRECTION
        context.user_data["reading_id"] = int(data.rsplit(":", 1)[1])
        mark_conversation_active(context, update.effective_chat.id)
        await query.message.reply_text(
            "✏️ Escribe el valor correcto. Ejemplo: 170269.6",
            reply_markup=cancel_registration_markup(),
        )
    elif data == "date:today":
        await finish_reading(query.message, context, update.effective_user.id, timezone.localdate(), edit=True)
    elif data == "date:manual":
        mark_conversation_active(context, update.effective_chat.id)
        await query.message.reply_text(
            "Escribe la fecha con el formato DÍA/MES/AÑO.\nEjemplo: 17/08/2026",
            reply_markup=cancel_registration_markup(),
        )


async def reminder_loop(application):
    while True:
        try:
            jobs = await sync_to_async(prepare_reminder_jobs)()
            paused_chats = active_chat_ids(application)
            jobs = [job for job in jobs if job["chat_id"] not in paused_chats]
            results = await send_reminder_jobs(application.bot, jobs)
            await sync_to_async(record_reminder_results)(results)
        except Exception:
            logger.exception("No se pudieron enviar los recordatorios de Telegram")
        # Se revisa cada minuto para reanudar pronto tras finalizar una conversación.
        # El servicio de recordatorios conserva el intervalo mínimo de cinco horas.
        await asyncio.sleep(60)


async def post_init(application):
    application.create_task(reminder_loop(application), name="wi-net-reminders")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Error al procesar una actualización de Telegram", exc_info=context.error)
    message = getattr(update, "effective_message", None)
    if message:
        await message.reply_text("Ocurrió un error. Inténtalo nuevamente o avisa al administrador.", reply_markup=main_menu_markup())


class Command(BaseCommand):
    help = "Ejecuta el bot de Telegram y su ciclo de recordatorios cada cinco horas"

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError("Configura TELEGRAM_BOT_TOKEN en el archivo .env")
        app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).post_init(post_init).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("id", chat_id))
        app.add_handler(CallbackQueryHandler(callback))
        app.add_handler(MessageHandler(filters.PHOTO, receive_photo))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text))
        app.add_error_handler(error_handler)
        self.stdout.write(self.style.SUCCESS("Bot WI-NET iniciado. Presiona Ctrl+C para detenerlo."))
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
