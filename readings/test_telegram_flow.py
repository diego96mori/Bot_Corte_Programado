import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.test import TestCase
from django.utils import timezone
from telegram.error import Forbidden

from readings.management.commands import run_telegram_bot as bot
from readings.models import Node, Reading


class TelegramFlowTests(TestCase):
    def setUp(self):
        self.now = timezone.make_aware(datetime(2026, 8, 31, 10))
        clock = patch.object(bot.timezone, "now", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.node = Node.objects.create(code="PIM", name="Pimentel", reading_day=20, telegram_chat_id=1)
        self.user = SimpleNamespace(id=123, username="operador", full_name="Operador")
        self.status_message = SimpleNamespace(edit_text=AsyncMock())
        self.message = SimpleNamespace(
            chat=SimpleNamespace(id=1), text="", photo=[],
            reply_text=AsyncMock(return_value=self.status_message),
        )
        self.context = SimpleNamespace(user_data={}, bot=SimpleNamespace(
            get_file=AsyncMock(return_value=SimpleNamespace(download_as_bytearray=AsyncMock(return_value=b"photo"))),
        ))
        self.update = SimpleNamespace(
            message=self.message, effective_message=self.message,
            effective_chat=self.message.chat, effective_user=self.user, callback_query=None,
        )
        self.application = SimpleNamespace(user_data={self.user.id: self.context.user_data}, bot=SimpleNamespace(send_message=AsyncMock()))
        async_to_sync(bot.start)(self.update, self.context)

    def text(self, value):
        self.update.callback_query = None
        self.message.text = value
        async_to_sync(bot.receive_text)(self.update, self.context)

    def click(self, action, token=None):
        token = token if token is not None else self.context.user_data["prompt_token"]
        self.update.callback_query = SimpleNamespace(
            message=self.message, answer=AsyncMock(), data=f"{action}|{token}",
        )
        async_to_sync(bot.callback)(self.update, self.context)

    def state(self, expected):
        self.assertEqual(self.context.user_data[bot.STATE], expected)

    def last_text(self):
        return self.message.reply_text.call_args.args[0]

    def last_actions(self):
        return [button.callback_data.split("|")[0]
                for row in self.message.reply_text.call_args.kwargs["reply_markup"].inline_keyboard for button in row]

    def select_node(self):
        self.click("menu:enter")
        self.text("pimentel")
        self.click("node:yes")
        self.state(bot.WAIT_PHOTO)

    def manual_draft(self):
        self.select_node()
        self.click("reading:manual:start")
        self.text("170269,6")
        self.state(bot.CONFIRM_MANUAL_VALUE)
        return Reading.objects.get(pk=self.context.user_data["reading_id"])

    def choose_date(self):
        reading = self.manual_draft()
        self.click(f"reading:manual:confirm:{reading.id}")
        self.state(bot.CHOOSE_DATE)
        return reading

    def photo(self):
        self.update.callback_query = None
        self.message.photo = [SimpleNamespace(file_id="photo", file_unique_id="unique")]
        async_to_sync(bot.receive_photo)(self.update, self.context)

    def test_main_menu_repeats_for_text_numbers_and_media(self):
        for value in ("hola", "123", "ingresar lectura", "1"):
            self.text(value)
            self.state(bot.MAIN_MENU)
            self.assertEqual(self.last_text(), bot.welcome_text())
            self.assertEqual(self.last_actions(), ["menu:enter", "menu:consult"])
        self.photo()
        self.context.bot.get_file.assert_not_called()
        self.assertEqual(self.last_text(), bot.welcome_text())
        async_to_sync(bot.receive_unexpected)(self.update, self.context)
        self.assertEqual(self.last_text(), bot.welcome_text())
        self.assertFalse(Reading.objects.exists())

    def test_unknown_node_shows_list_and_home_then_accepts_typo(self):
        self.click("menu:enter")
        self.text("quiero comprar una camisa")
        self.state(bot.SELECT_NODE)
        self.assertIn("No se reconoce ese nombre", self.last_text())
        self.assertEqual(self.last_actions(), ["nodes:list", "menu:home"])
        self.click("nodes:list")
        self.assertIn(f"node:select:{self.node.id}", self.last_actions())
        self.text("pimntel")
        self.state(bot.CONFIRM_NODE)
        self.assertIn("Pimentel", self.last_text())

    def test_node_confirmation_repeats_until_button_selected(self):
        self.click("menu:enter")
        self.text("Pimentel")
        question = self.last_text()
        for value in ("sí", "no", "123", "cualquier cosa"):
            self.text(value)
            self.state(bot.CONFIRM_NODE)
            self.assertEqual(self.last_text(), question)
            self.assertEqual(self.last_actions(), ["node:yes", "node:no", "reading:cancel"])
        self.photo()
        self.assertEqual(self.last_text(), question)
        self.click("node:no")
        self.state(bot.SELECT_NODE)
        self.assertIn("menu:home", self.last_actions())

    def test_photo_step_rejects_direct_number_and_word_without_creating_draft(self):
        self.select_node()
        question = self.last_text()
        for value in ("170269.6", "hola", "no tengo foto"):
            self.text(value)
            self.state(bot.WAIT_PHOTO)
            self.assertEqual(self.last_text(), question)
            self.assertIn("reading:manual:start", self.last_actions())
        self.assertFalse(Reading.objects.exists())

    def test_invalid_manual_input_retries_with_examples_and_cancel(self):
        self.select_node()
        self.click("reading:manual:start")
        for value in ("abc", "123 kWh", "1.2.3", "-12", "12.1234", "", "1234567890123"):
            self.text(value)
            self.state(bot.WAIT_MANUAL_VALUE)
            self.assertIn("Solo se acepta un número", self.last_text())
            self.assertIn("Ejemplos:", self.last_text())
            self.assertEqual(self.last_actions(), ["reading:cancel"])
        self.assertFalse(Reading.objects.exists())
        self.text("170269")
        self.state(bot.CONFIRM_MANUAL_VALUE)
        self.assertEqual(Reading.objects.get().detected_value, Decimal("170269"))

    def test_manual_confirmation_and_correction_require_buttons(self):
        reading = self.manual_draft()
        self.text("sí")
        self.state(bot.CONFIRM_MANUAL_VALUE)
        self.assertIn("170269.6", self.last_text())
        self.click(f"reading:manual:correct:{reading.id}")
        self.text("170300.25")
        self.click(f"reading:manual:confirm:{reading.id}")
        self.click("date:today")
        reading.refresh_from_db()
        self.assertEqual(reading.confirmed_value, Decimal("170300.25"))
        self.assertEqual(reading.reading_date, date(2026, 8, 31))
        self.state(bot.MAIN_MENU)
        self.assertEqual(self.last_text(), bot.welcome_text())

    def test_date_choice_does_not_accept_text_even_valid_dates(self):
        reading = self.choose_date()
        for value in ("hoy", "31/08/2026", "31-08-2026", "cancelar"):
            self.text(value)
            self.state(bot.CHOOSE_DATE)
            self.assertEqual(self.last_actions(), ["date:today", "date:manual", "reading:cancel"])
        reading.refresh_from_db()
        self.assertEqual(reading.status, Reading.Status.REVIEW)

    def test_manual_date_requires_exact_format_and_real_day_then_returns_menu(self):
        reading = self.choose_date()
        self.click("date:manual")
        for value in ("hoy", "ayer", "31/02/2026", "31/13/2026", "2026-08-31", "1/8/2026", "31/08/26", "29/02/2026"):
            self.text(value)
            self.state(bot.WAIT_DATE)
            self.assertIn("La fecha no es válida", self.last_text())
            self.assertIn("DD/MM/AAAA", self.last_text())
            self.assertIn("31/08/2026", self.last_text())
            self.assertEqual(self.last_actions(), ["reading:cancel"])
        self.text("31/08/2026")
        reading.refresh_from_db()
        self.assertEqual(reading.status, Reading.Status.CONFIRMED)
        self.assertEqual(reading.reading_date, date(2026, 8, 31))
        self.assertIn("LECTURA REGISTRADA", self.message.reply_text.call_args_list[-2].args[0])
        self.assertEqual(self.last_text(), bot.welcome_text())

    def test_ocr_failure_requires_manual_button_before_value(self):
        self.select_node()
        reading, _ = async_to_sync(bot.create_manual_reading)(self.node.id, Decimal("100"), self.user, 1)
        reading.detected_value = None
        reading.source = Reading.Source.TELEGRAM
        reading.save()
        with patch.object(bot, "create_reading", new=AsyncMock(return_value=(reading, None))):
            self.photo()
        self.state(bot.OCR_FAILED)
        for value in ("100", "hola"):
            self.text(value)
            self.state(bot.OCR_FAILED)
            self.assertEqual(self.last_actions(), [f"reading:correct:{reading.id}", "reading:cancel"])
        self.click(f"reading:correct:{reading.id}")
        self.text("100.5")
        self.click(f"reading:manual:confirm:{reading.id}")
        self.click("date:today")
        reading.refresh_from_db()
        self.assertEqual(reading.confirmed_value, Decimal("100.5"))
        self.assertEqual(Reading.objects.count(), 1)

    def test_successful_ocr_confirmation_repeats_and_cannot_receive_another_photo(self):
        self.select_node()
        reading, _ = async_to_sync(bot.create_manual_reading)(self.node.id, Decimal("100.25"), self.user, 1)
        with patch.object(bot, "create_reading", new=AsyncMock(return_value=(reading, None))) as create:
            self.photo()
            self.state(bot.CONFIRM_READING)
            self.photo()
            create.assert_awaited_once()
        self.text("sí")
        self.state(bot.CONFIRM_READING)
        self.assertIn("100.25", self.last_text())
        self.click(f"reading:confirm:{reading.id}")
        self.click("date:today")
        reading.refresh_from_db()
        self.assertEqual(reading.status, Reading.Status.CONFIRMED)

    def test_cancel_discards_draft_and_old_buttons_cannot_confirm_it(self):
        reading = self.choose_date()
        old_token = self.context.user_data["prompt_token"]
        self.click("reading:cancel")
        self.state(bot.MAIN_MENU)
        self.click("date:today", token=old_token)
        self.state(bot.MAIN_MENU)
        reading.refresh_from_db()
        self.assertEqual(reading.status, Reading.Status.CANCELLED)
        self.assertIsNone(reading.confirmed_value)

    def test_wrong_reading_id_and_previous_question_cannot_skip_current_step(self):
        reading = self.manual_draft()
        old_token = self.context.user_data["prompt_token"]
        self.click(f"reading:manual:confirm:{reading.id + 999}")
        self.state(bot.CONFIRM_MANUAL_VALUE)
        self.click(f"reading:manual:correct:{reading.id}")
        self.click(f"reading:manual:confirm:{reading.id}", token=old_token)
        self.state(bot.WAIT_MANUAL_VALUE)
        self.click("date:today")
        self.state(bot.WAIT_MANUAL_VALUE)

    def test_consultation_invalid_input_repeats_and_history_returns_to_menu(self):
        self.click("menu:consult")
        self.click("nodes:list")
        self.click(f"node:select:{self.node.id}")
        self.state(bot.SELECT_PERIOD)
        self.text("hola")
        self.state(bot.SELECT_PERIOD)
        self.assertIn("¿Qué deseas ver?", self.last_text())
        self.click(f"query:current:{self.node.id}")
        self.assertIn("No hay lecturas", self.message.reply_text.call_args_list[-2].args[0])
        self.state(bot.MAIN_MENU)

    def test_eight_minutes_cancel_draft_and_repeat_menu_every_eight_minutes(self):
        reading = self.choose_date()
        deadline = self.context.user_data[bot.ACTIVE_UNTIL]
        self.assertEqual(deadline, self.now + timedelta(minutes=8))
        async_to_sync(bot.expire_conversations)(self.application, deadline - timedelta(seconds=1))
        self.application.bot.send_message.assert_not_called()
        self.state(bot.CHOOSE_DATE)
        async_to_sync(bot.expire_conversations)(self.application, deadline)
        self.state(bot.MAIN_MENU)
        reading.refresh_from_db()
        self.assertEqual(reading.status, Reading.Status.CANCELLED)
        self.assertEqual(self.application.bot.send_message.call_count, 1)
        self.assertEqual(self.application.bot.send_message.call_args.kwargs["text"], bot.welcome_text())
        async_to_sync(bot.expire_conversations)(self.application, deadline + timedelta(seconds=1))
        self.assertEqual(self.application.bot.send_message.call_count, 1)
        async_to_sync(bot.expire_conversations)(self.application, deadline + timedelta(minutes=8))
        self.assertEqual(self.application.bot.send_message.call_count, 2)
        self.assertEqual(bot.active_chat_ids(self.application, deadline), set())

    def test_invalid_input_renews_inactivity_deadline(self):
        self.select_node()
        self.now += timedelta(minutes=7)
        self.text("hola")
        self.assertEqual(self.context.user_data[bot.ACTIVE_UNTIL], self.now + timedelta(minutes=8))
        async_to_sync(bot.expire_conversations)(self.application, self.now + timedelta(minutes=1))
        self.application.bot.send_message.assert_not_called()
        self.state(bot.WAIT_PHOTO)

    def test_expired_button_is_rejected_even_before_timeout_loop_runs(self):
        reading = self.choose_date()
        self.now += timedelta(minutes=8)
        self.click("date:today")
        self.state(bot.MAIN_MENU)
        reading.refresh_from_db()
        self.assertEqual(reading.status, Reading.Status.CANCELLED)
        self.assertIsNone(reading.confirmed_value)

    def test_timeout_waits_for_in_progress_handler(self):
        self.select_node()

        async def check():
            async with bot.conversation_lock(self.context.user_data):
                await bot.expire_conversations(self.application, self.now + timedelta(minutes=9))
        async_to_sync(check)()
        self.application.bot.send_message.assert_not_called()
        self.state(bot.WAIT_PHOTO)

    def test_blocked_chat_does_not_repeat_timeout_delivery(self):
        self.application.bot.send_message.side_effect = Forbidden("blocked")
        async_to_sync(bot.expire_conversations)(self.application, self.now + timedelta(minutes=8))
        async_to_sync(bot.expire_conversations)(self.application, self.now + timedelta(minutes=16))
        self.application.bot.send_message.assert_awaited_once()

    def test_restart_cancels_pending_draft_and_keeps_confirmed_readings(self):
        reading = self.manual_draft()
        self.update.callback_query = None
        async_to_sync(bot.start)(self.update, self.context)
        reading.refresh_from_db()
        self.assertEqual(reading.status, Reading.Status.CANCELLED)
        self.state(bot.MAIN_MENU)

    def test_background_tasks_are_stopped_cleanly(self):
        async def run():
            app = SimpleNamespace(bot_data={})
            with patch.object(bot, "reminder_loop", side_effect=lambda application: asyncio.sleep(60)), patch.object(
                bot, "conversation_timeout_loop", side_effect=lambda application: asyncio.sleep(60),
            ):
                await bot.post_init(app)
                tasks = list(app.bot_data["background_tasks"])
                await bot.post_stop(app)
                self.assertTrue(all(task.done() for task in tasks))
        async_to_sync(run)()
