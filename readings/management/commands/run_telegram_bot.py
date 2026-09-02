import asyncio
import logging
import re
import secrets
import tempfile
import unicodedata
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from functools import wraps
from pathlib import Path

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Forbidden, TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from readings.models import Node, Reading, ReadingSchedule
from readings.services.notifications import active_cycle_due
from readings.services.registration import get_registration_plan
from readings.services.ocr import read_meter
from readings.services.reminders import prepare_reminder_jobs, send_reminder_jobs

logger = logging.getLogger(__name__)
STATE = "state"
MAIN_MENU = "MAIN_MENU"
SELECT_NODE = "SELECT_NODE"
CONFIRM_NODE = "CONFIRM_NODE"
WAIT_PHOTO = "WAIT_PHOTO"
WAIT_MANUAL_VALUE = "WAIT_MANUAL_VALUE"
CONFIRM_MANUAL_VALUE = "CONFIRM_MANUAL_VALUE"
WAIT_CORRECTION = "WAIT_CORRECTION"
WAIT_DATE = "WAIT_DATE"
CHOOSE_DATE = "CHOOSE_DATE"
OCR_FAILED = "OCR_FAILED"
CONFIRM_READING = "CONFIRM_READING"
MODE = "mode"
ENTER = "ENTER"
ACTIVE_CHAT_ID = "active_chat_id"
ACTIVE_UNTIL = "active_until"
ACTIVE_USER_ID = "active_user_id"
CONVERSATION_TIMEOUT = timedelta(minutes=8)
ACTIVE_STATES = {
    SELECT_NODE, CONFIRM_NODE, WAIT_PHOTO, WAIT_MANUAL_VALUE,
    CONFIRM_MANUAL_VALUE, WAIT_CORRECTION, WAIT_DATE, CHOOSE_DATE,
    OCR_FAILED, CONFIRM_READING,
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
    return best if score >= 0.65 else None


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
    if not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,3})?", normalized):
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def mark_conversation_active(context, chat_id, now=None):
    now = now or timezone.now()
    context.user_data[ACTIVE_CHAT_ID] = chat_id
    context.user_data[ACTIVE_UNTIL] = now + CONVERSATION_TIMEOUT


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
        [InlineKeyboardButton("📷 Ingresar lectura", callback_data="menu:enter")],
    ])


def cancel_registration_markup(rows=None):
    rows = list(rows or [])
    rows.append([InlineKeyboardButton("❌ Cancelar registro", callback_data="reading:cancel")])
    return InlineKeyboardMarkup(rows)


def welcome_text():
    return (
        "👋 Hola. Aquí podrás ingresar las lecturas de los nodos de WI-NET.\n\n"
        "Pulsa el botón para continuar:"
    )


@sync_to_async
def authorized_nodes(chat_id):
    return list(Node.objects.filter(active=True, telegram_chat_id=chat_id).order_by("location", "name")
                .values_list("id", "name", "code"))


@sync_to_async
def get_authorized_node(node_id, chat_id):
    return Node.objects.filter(id=node_id, active=True, telegram_chat_id=chat_id).first()


def validated_ocr_values(node, ocr):
    previous_value = previous_confirmed_value(node)
    if ocr.value is not None and previous_value is not None and ocr.value <= previous_value:
        return None, f"{ocr.raw_text} | RECHAZADA: no supera la lectura anterior {previous_value}", None
    return ocr.value, ocr.raw_text, ocr.confidence


def previous_confirmed_value(node):
    return (
        Reading.objects.filter(
            schedule__node=node,
            status=Reading.Status.CONFIRMED,
            confirmed_value__isnull=False,
        )
        .order_by("-reading_date", "-id")
        .values_list("confirmed_value", flat=True)
        .first()
    )


def validate_node_schedule(node):
    if node.reading_day is None or not 1 <= node.reading_day <= 31:
        raise ValidationError(
            "Este nodo no tiene configurado un día de lectura válido. "
            "Pide al administrador que configure un día entre 1 y 31."
        )


def prepare_pending_schedule(node, reading_date=None):
    plan = get_registration_plan(node, reading_date)
    due_date, kind = plan.due_date, plan.kind
    schedule, _ = ReadingSchedule.objects.get_or_create(
        node=node, due_date=due_date,
        defaults={"status": ReadingSchedule.Status.PENDING,
                  "notes": "Lectura mensual" if kind == "MONTHLY" else "Seguimiento de 10 días"},
    )
    schedule.node = node
    return schedule


@sync_to_async
def create_reading(node_id, image_bytes, filename, telegram_user, chat_id):
    node = Node.objects.filter(id=node_id, active=True, telegram_chat_id=chat_id).first()
    if not node:
        return None, "Este chat no está autorizado para registrar lecturas de ese nodo."
    try:
        schedule = prepare_pending_schedule(node)
    except ValidationError as error:
        return None, " ".join(error.messages)
    Reading.objects.filter(
        schedule=schedule, telegram_chat_id=chat_id, telegram_user_id=telegram_user.id,
        status=Reading.Status.REVIEW,
    ).update(status=Reading.Status.CANCELLED)
    suffix = Path(filename).suffix or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
        temp.write(image_bytes)
        temp_path = Path(temp.name)
    try:
        ocr = read_meter(temp_path, previous_value=previous_confirmed_value(node))
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
    try:
        schedule = prepare_pending_schedule(node)
    except ValidationError as error:
        return None, " ".join(error.messages)
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
        ocr = read_meter(
            reading.photo.path,
            previous_value=previous_confirmed_value(reading.schedule.node),
        )
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
@transaction.atomic
def confirm_reading(reading_id, telegram_user_id, reading_date, corrected_value=None):
    reading = Reading.objects.select_for_update().select_related("schedule__node").filter(pk=reading_id).first()
    if not reading or reading.telegram_user_id != telegram_user_id or reading.status != Reading.Status.REVIEW:
        return None
    value = corrected_value if corrected_value is not None else reading.detected_value
    if value is None:
        return None
    node = Node.objects.select_for_update().get(pk=reading.schedule.node_id)
    if not node.active or node.telegram_chat_id != reading.telegram_chat_id:
        raise ValidationError("Este chat ya no está autorizado para registrar lecturas de ese nodo.")
    today = timezone.localdate()
    if reading_date > today:
        raise ValidationError(
            f"No puedes registrar una lectura con fecha futura. Hoy es {today:%d/%m/%Y}. "
            "Corrige la fecha o cancela el registro.",
            code="future_date",
        )
    # Recheck capacity at save time, including drafts started before another
    # operator completed the cycle. Dates from an older cycle are historical:
    # they remain visible, but the bot must not reopen their grey/closed task.
    validate_node_schedule(node)
    current_cycle_due = active_cycle_due(node, today)
    dated_cycle_due = active_cycle_due(node, reading_date)
    if dated_cycle_due != current_cycle_due:
        raise ValidationError(
            f"La fecha {reading_date:%d/%m/%Y} pertenece al ciclo "
            f"{dated_cycle_due:%m/%Y}, que ya está cerrado. "
            "Los ciclos anteriores se conservan como historial en gris y no pueden recibir nuevas lecturas. "
            f"Ingresa una fecha correspondiente al ciclo activo {current_cycle_due:%m/%Y}.",
            code="closed_cycle",
        )
    get_registration_plan(node, today)
    # The draft was created before the operator supplied the actual reading date.
    reading.schedule = prepare_pending_schedule(reading.schedule.node, reading_date)
    reading.confirmed_value = value
    reading.status = Reading.Status.CONFIRMED
    reading.reading_date = reading_date
    reading.confirmed_at = timezone.now()
    reading.save(update_fields=["schedule", "confirmed_value", "status", "reading_date", "confirmed_at"])
    if reading.schedule.status != ReadingSchedule.Status.COMPLETED:
        reading.schedule.status = ReadingSchedule.Status.COMPLETED
        reading.schedule.save(update_fields=["status"])
    return reading


def node_selection_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Ver opciones de nodos", callback_data="nodes:list")],
        [InlineKeyboardButton("↩️ Volver al inicio", callback_data="menu:home")],
    ])


def current_prompt(data):
    """One source for the initial question and every retry of that question."""
    state = data.get(STATE, MAIN_MENU)
    node_name = data.get("node_name", "")
    reading_id = data.get("reading_id")
    if state == SELECT_NODE:
        return (
            "Escribe el nombre del nodo que deseas registrar, aunque no lo recuerdes exactamente.\n"
            "También puedes ver la lista completa:", node_selection_markup(),
        )
    if state == CONFIRM_NODE:
        return (
            f"Encontré este nodo:\n🏢 {data['candidate_name']}\n\n¿Es el nodo correcto?",
            cancel_registration_markup([[
                InlineKeyboardButton("✅ Sí", callback_data="node:yes"),
                InlineKeyboardButton("❌ No", callback_data="node:no"),
            ]]),
        )
    if state == WAIT_PHOTO:
        return (
            f"📷 Registro de lectura\n🏢 Nodo: {node_name}\n\n"
            f"{data.get('registration_explanation', '')}\n\n"
            "Ahora envía una fotografía clara del medidor. Analizaré el número localmente.\n\n"
            "Si no tienes una fotografía, pulsa «Escribir lectura manualmente» para ingresar el número.",
            cancel_registration_markup([[
                InlineKeyboardButton("⌨️ Escribir lectura manualmente", callback_data="reading:manual:start"),
            ]]),
        )
    if state == OCR_FAILED:
        return (
            f"⚠️ NO SE PUDO RECONOCER LA LECTURA\n\n🏢 Nodo: {node_name}\n\n"
            "No se obtuvo un resultado suficientemente seguro. "
            "Elige «Ingresar lectura manual» o «Cancelar registro».",
            cancel_registration_markup([[
                InlineKeyboardButton("⌨️ Ingresar lectura manual", callback_data=f"reading:correct:{reading_id}"),
            ]]),
        )
    if state in {WAIT_MANUAL_VALUE, WAIT_CORRECTION}:
        return (
            "⌨️ Escribe el valor correcto de la lectura.\n\n"
            "Solo se aceptan números enteros o decimales, sin letras ni unidades.\n"
            "Ejemplos: 170269, 170269.6 o 170269,6.\n"
            "Máximo 12 dígitos enteros y 3 decimales; no se aceptan números negativos.",
            cancel_registration_markup(),
        )
    if state == CONFIRM_MANUAL_VALUE:
        return (
            "⌨️ LECTURA INGRESADA MANUALMENTE\n\n"
            f"⚡ Lectura: {format_reading_value(data['display_value'])}\n\n¿El número es correcto?",
            cancel_registration_markup([
                [InlineKeyboardButton("✅ Sí, continuar", callback_data=f"reading:manual:confirm:{reading_id}")],
                [InlineKeyboardButton("✏️ Corregir número", callback_data=f"reading:manual:correct:{reading_id}")],
            ]),
        )
    if state == CONFIRM_READING:
        return (
            f"🔍 LECTURA POR CONFIRMAR\n\n🏢 Nodo: {node_name}\n"
            f"⚡ Lectura detectada: {format_reading_value(data['display_value'])}\n"
            f"{data.get('ocr_details', '')}\n¿Confirmas esta lectura?",
            cancel_registration_markup([
                [InlineKeyboardButton("✅ Confirmar", callback_data=f"reading:confirm:{reading_id}")],
                [InlineKeyboardButton("✏️ Corregir", callback_data=f"reading:correct:{reading_id}")],
            ]),
        )
    if state == CHOOSE_DATE:
        return (
            "📅 ¿Qué fecha corresponde a esta lectura?\n\n"
            "Elige «Hoy» para usar la fecha actual o «Escribir fecha» para indicar otra fecha.",
            cancel_registration_markup([
                [InlineKeyboardButton("📅 Hoy", callback_data="date:today")],
                [InlineKeyboardButton("✍️ Escribir fecha", callback_data="date:manual")],
            ]),
        )
    if state == WAIT_DATE:
        return (
            "📅 Escribe la fecha con el formato DÍA/MES/AÑO (DD/MM/AAAA).\n"
            "Ejemplo: 31/08/2026. Usa dos dígitos para el día y el mes, y cuatro para el año.",
            cancel_registration_markup(),
        )
    return welcome_text(), main_menu_markup()


def prompt_payload(data, text, markup):
    # Buttons from previous questions must never confirm a new node or draft.
    token = secrets.token_hex(4)
    data["prompt_token"] = token
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(button.text, callback_data=f"{button.callback_data}|{token}") for button in row]
        for row in markup.inline_keyboard
    ])
    return text, keyboard


async def repeat_prompt(message, context, prefix=None):
    text, markup = current_prompt(context.user_data)
    if prefix:
        text = f"{prefix}\n\n{text}"
    text, markup = prompt_payload(context.user_data, text, markup)
    await message.reply_text(text, reply_markup=markup)


def conversation_lock(data):
    return data.setdefault("conversation_lock", asyncio.Lock())


async def reset_conversation(data, chat_id, now=None):
    lock = conversation_lock(data)
    user_id = data.get(ACTIVE_USER_ID)
    await cancel_pending_reading(data.get("reading_id"), user_id)
    data.clear()
    data.update({
        "conversation_lock": lock, STATE: MAIN_MENU, ACTIVE_USER_ID: user_id,
        ACTIVE_CHAT_ID: chat_id, ACTIVE_UNTIL: (now or timezone.now()) + CONVERSATION_TIMEOUT,
    })


async def show_main_menu(message, context):
    await reset_conversation(context.user_data, message.chat.id)
    await repeat_prompt(message, context)


def conversation_handler(handler):
    @wraps(handler)
    async def wrapped(update, context):
        data = context.user_data
        async with conversation_lock(data):
            data[ACTIVE_USER_ID] = update.effective_user.id
            expires = data.get(ACTIVE_UNTIL)
            if expires is not None and expires <= timezone.now():
                query = getattr(update, "callback_query", None)
                if query:
                    await query.answer()
                message = query.message if query else update.message
                await show_main_menu(message, context)
                return
            mark_conversation_active(context, update.effective_chat.id)
            try:
                await handler(update, context)
            finally:
                # Processing time (including OCR) is not user inactivity.
                mark_conversation_active(context, update.effective_chat.id)
    return wrapped


@conversation_handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update.message, context)


@conversation_handler
async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"El identificador de este chat es: {update.effective_chat.id}")
    await repeat_prompt(update.message, context)


async def begin_node_selection(message, context):
    await reset_conversation(context.user_data, message.chat.id)
    context.user_data.update({MODE: ENTER, STATE: SELECT_NODE})
    await repeat_prompt(message, context)


async def show_node_list(message, context, edit=False):
    nodes = await authorized_nodes(message.chat.id)
    if not nodes:
        await repeat_prompt(message, context, "Este chat todavía no tiene nodos autorizados.")
        return
    keyboard = [[InlineKeyboardButton(name, callback_data=f"node:select:{node_id}")]
                for node_id, name, _code in nodes]
    keyboard.append([InlineKeyboardButton("↩️ Volver al inicio", callback_data="menu:home")])
    text, markup = prompt_payload(context.user_data, "📋 Selecciona uno de los nodos WI-NET:", InlineKeyboardMarkup(keyboard))
    await message.reply_text(text, reply_markup=markup)


async def select_node(message, context, node_id, telegram_user_id):
    node = await get_authorized_node(node_id, message.chat.id)
    if not node:
        await repeat_prompt(message, context, "Ese nodo no está disponible para este chat.")
        return
    context.user_data.update({"node_id": node.id, "node_name": node.name})
    try:
        plan = await sync_to_async(get_registration_plan)(node)
    except ValidationError as error:
        await message.reply_text(" ".join(error.messages))
        await show_main_menu(message, context)
        return
    context.user_data["registration_explanation"] = plan.explanation
    pending = await get_pending_node_reading(node.id, message.chat.id, telegram_user_id)
    if pending:
        context.user_data.update({"reading_id": pending.id, "display_value": pending.detected_value})
        context.user_data[STATE] = (
            OCR_FAILED if pending.detected_value is None else
            CONFIRM_MANUAL_VALUE if pending.source == Reading.Source.MANUAL else CONFIRM_READING
        )
    else:
        context.user_data[STATE] = WAIT_PHOTO
    mark_conversation_active(context, message.chat.id)
    await repeat_prompt(message, context)


async def ask_reading_date(message, context):
    context.user_data[STATE] = CHOOSE_DATE
    mark_conversation_active(context, message.chat.id)
    await repeat_prompt(message, context)


async def finish_reading(message, context, telegram_user_id, reading_date, edit=False):
    try:
        reading = await confirm_reading(
            context.user_data.get("reading_id"), telegram_user_id, reading_date,
            context.user_data.get("corrected_value"),
        )
    except ValidationError as error:
        await repeat_prompt(message, context, " ".join(error.messages))
        return
    if reading:
        text = (
            f"✅ LECTURA REGISTRADA\n\n🏢 Nodo: {reading.schedule.node.name}\n"
            f"📋 Tipo: {'Seguimiento' if reading.schedule.is_follow_up else 'Lectura mensual'}\n"
            f"⚡ Lectura: {format_reading_value(reading.confirmed_value)}\n"
            f"📅 Fecha: {reading.reading_date:%d/%m/%Y}\n\n"
            "La información ya aparece en LECTURAS WI-NET."
        )
    else:
        text = "No se pudo registrar. La lectura ya fue procesada o no tiene un valor válido."
    await message.reply_text(text)
    await show_main_menu(message, context)


@conversation_handler
async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    state = context.user_data.get(STATE, MAIN_MENU)
    if state == SELECT_NODE:
        if normalize_node_name(text) in {"opciones", "ver opciones", "lista"}:
            await show_node_list(update.message, context)
            return
        nodes = await authorized_nodes(update.effective_chat.id)
        best = find_best_node_name(text, nodes)
        if not best:
            await repeat_prompt(update.message, context, "No se reconoce ese nombre. Verifica la lista de nodos o escribe otro nombre.")
            return
        context.user_data.update({"candidate_id": best[0], "candidate_name": best[1], STATE: CONFIRM_NODE})
        await repeat_prompt(update.message, context)
        return
    if state in {WAIT_MANUAL_VALUE, WAIT_CORRECTION}:
        value = parse_reading_value(text)
        if value is None:
            await repeat_prompt(update.message, context, "El valor no es válido. Solo se acepta un número; escribe el valor correcto.")
            return
        reading_id = context.user_data.get("reading_id")
        if reading_id:
            context.user_data["corrected_value"] = value
        else:
            reading, error = await create_manual_reading(
                context.user_data.get("node_id"), value, update.effective_user, update.effective_chat.id,
            )
            if error:
                await repeat_prompt(update.message, context, error)
                return
            context.user_data["reading_id"] = reading.id
            context.user_data.pop("corrected_value", None)
        context.user_data.update({STATE: CONFIRM_MANUAL_VALUE, "display_value": value})
        await repeat_prompt(update.message, context)
        return
    if state == WAIT_DATE:
        reading_date = parse_reading_date(text) if re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", text) else None
        if reading_date is None:
            await repeat_prompt(update.message, context, "La fecha no es válida. Corrígela usando el formato indicado y una fecha que exista.")
            return
        await finish_reading(update.message, context, update.effective_user.id, reading_date)
        return
    await repeat_prompt(update.message, context)


@conversation_handler
async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get(STATE) != WAIT_PHOTO or not context.user_data.get("node_id"):
        await repeat_prompt(update.message, context)
        return
    status = await update.message.reply_text(
        "⏳ Analizando primero con OCR local; si no hay una lectura segura se probará el respaldo…"
    )
    photo = update.message.photo[-1]
    telegram_file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await telegram_file.download_as_bytearray())
    reading, error = await create_reading(
        context.user_data["node_id"], image_bytes, f"telegram_{photo.file_unique_id}.jpg",
        update.effective_user, update.effective_chat.id,
    )
    if error:
        await status.edit_text(error)
        await repeat_prompt(update.message, context)
        return
    context.user_data.update({"reading_id": reading.id, "display_value": reading.detected_value})
    if reading.detected_value is None:
        context.user_data[STATE] = OCR_FAILED
    else:
        context.user_data[STATE] = CONFIRM_READING
        confidence = f"{reading.ocr_confidence:.0%}" if reading.ocr_confidence is not None else "no disponible"
        method = "Cloudflare" if reading.ocr_text.startswith("CLOUDFLARE:") else "OCR local"
        context.user_data["ocr_details"] = f"🎯 Confianza: {confidence}\n🧠 Método: {method}\n"
    text, markup = current_prompt(context.user_data)
    text, markup = prompt_payload(context.user_data, text, markup)
    await status.edit_text(text, reply_markup=markup)


@conversation_handler
async def receive_unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await repeat_prompt(update.message, context)


@conversation_handler
async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, separator, token = (query.data or "").partition("|")
    state = context.user_data.get(STATE, MAIN_MENU)
    # Reminder buttons are entry points, but cannot interrupt an ongoing registration.
    if action.startswith("reminder_register:") and state == MAIN_MENU:
        raw_id = action.rsplit(":", 1)[1]
        if raw_id.isascii() and raw_id.isdigit():
            context.user_data[MODE] = ENTER
            await select_node(query.message, context, int(raw_id), update.effective_user.id)
            return
    if not separator or token != context.user_data.get("prompt_token"):
        await repeat_prompt(query.message, context)
        return
    allowed = {button.callback_data for row in current_prompt(context.user_data)[1].inline_keyboard for button in row}
    # The node list has a variable keyboard; authorization is checked by select_node.
    list_selection = state == SELECT_NODE and re.fullmatch(r"node:select:[0-9]+", action)
    if action not in allowed and not list_selection:
        await repeat_prompt(query.message, context)
        return
    if action in {"menu:home", "reading:cancel"}:
        if action == "reading:cancel":
            await query.message.reply_text("❌ REGISTRO CANCELADO\n\nLa lectura no fue registrada.")
        await show_main_menu(query.message, context)
    elif action == "menu:enter":
        await begin_node_selection(query.message, context)
    elif action == "nodes:list":
        await show_node_list(query.message, context)
    elif action == "node:no":
        context.user_data[STATE] = SELECT_NODE
        await repeat_prompt(query.message, context)
    elif action == "node:yes":
        await select_node(query.message, context, context.user_data.get("candidate_id"), update.effective_user.id)
    elif list_selection:
        await select_node(query.message, context, int(action.rsplit(":", 1)[1]), update.effective_user.id)
    elif action == "reading:manual:start":
        context.user_data[STATE] = WAIT_MANUAL_VALUE
        await repeat_prompt(query.message, context)
    elif action.startswith(("reading:manual:confirm:", "reading:confirm:")):
        await ask_reading_date(query.message, context)
    elif action.startswith(("reading:manual:correct:", "reading:correct:")):
        context.user_data[STATE] = WAIT_MANUAL_VALUE
        await repeat_prompt(query.message, context)
    elif action == "date:today":
        await finish_reading(query.message, context, update.effective_user.id, timezone.localdate())
    elif action == "date:manual":
        context.user_data[STATE] = WAIT_DATE
        await repeat_prompt(query.message, context)


async def expire_conversations(application, now=None):
    now = now or timezone.now()
    for user_id, data in list(application.user_data.items()):
        lock = conversation_lock(data)
        if lock.locked():
            continue
        async with lock:
            # El menú principal ya fue mostrado por /start, al terminar un
            # registro o al vencer un flujo. No debe programar otro menú.
            if data.get(STATE, MAIN_MENU) == MAIN_MENU:
                data.pop(ACTIVE_UNTIL, None)
                continue
            deadline = data.get(ACTIVE_UNTIL)
            chat_id = data.get(ACTIVE_CHAT_ID)
            if deadline is None or deadline > now or chat_id is None:
                continue
            data[ACTIVE_USER_ID] = user_id
            await reset_conversation(data, chat_id, now)
            text, markup = prompt_payload(data, welcome_text(), main_menu_markup())
            try:
                await application.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
            except Forbidden:
                # A blocked bot must not keep trying to contact the user.
                data.pop(ACTIVE_UNTIL, None)
            except TelegramError:
                logger.exception("No se pudo enviar el menú tras la inactividad")


async def conversation_timeout_loop(application):
    while True:
        try:
            await expire_conversations(application)
        except Exception:
            logger.exception("No se pudieron reiniciar las conversaciones inactivas")
        await asyncio.sleep(1)


async def reminder_loop(application):
    while True:
        try:
            jobs = await sync_to_async(prepare_reminder_jobs)()
            paused_chats = active_chat_ids(application)
            jobs = [job for job in jobs if job["chat_id"] not in paused_chats]
            await send_reminder_jobs(application.bot, jobs)
        except Exception:
            logger.exception("No se pudieron enviar los recordatorios de Telegram")
        # Se revisa cada minuto para reanudar pronto tras finalizar una conversación.
        # El servicio de recordatorios conserva el intervalo mínimo de cinco horas.
        await asyncio.sleep(60)


async def post_init(application):
    application.bot_data["background_tasks"] = [
        asyncio.create_task(reminder_loop(application), name="wi-net-reminders"),
        asyncio.create_task(conversation_timeout_loop(application), name="wi-net-conversation-timeouts"),
    ]


async def post_stop(application):
    tasks = application.bot_data.pop("background_tasks", [])
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Error al procesar una actualización de Telegram", exc_info=context.error)
    message = getattr(update, "effective_message", None)
    if message:
        await repeat_prompt(message, context, "Ocurrió un error. Inténtalo nuevamente o avisa al administrador.")


class Command(BaseCommand):
    help = "Ejecuta el bot de Telegram y su ciclo de recordatorios cada cinco horas"

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError("Configura TELEGRAM_BOT_TOKEN en el archivo .env")
        app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).post_init(post_init).post_stop(post_stop).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("id", chat_id))
        app.add_handler(CallbackQueryHandler(callback))
        app.add_handler(MessageHandler(filters.PHOTO, receive_photo))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text))
        app.add_handler(MessageHandler(filters.ALL, receive_unexpected))
        app.add_error_handler(error_handler)
        self.stdout.write(self.style.SUCCESS("Bot WI-NET iniciado. Presiona Ctrl+C para detenerlo."))
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
