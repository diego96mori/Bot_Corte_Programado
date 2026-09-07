from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.core.exceptions import ValidationError
from django.test import TestCase

from readings.management.commands import run_telegram_bot as bot
from readings.models import Node, Reading, ReadingSchedule
from readings.services.registration import get_registration_plan


class RegistrationRulesTests(TestCase):
    def setUp(self):
        self.today = date(2026, 8, 31)
        clock = patch.object(bot.timezone, "localdate", side_effect=lambda: self.today)
        clock.start()
        self.addCleanup(clock.stop)
        self.user = SimpleNamespace(id=1, username="operador", full_name="Operador")
        self.huacho = Node.objects.create(code="HUA", name="Huacho", reading_day=3, telegram_chat_id=1)
        self.guardia = Node.objects.create(code="GUA", name="Guardia Peruana", reading_day=2, telegram_chat_id=1)
        self.monthly(self.huacho, date(2026, 8, 3), date(2026, 8, 2))
        self.follow_up(self.huacho, date(2026, 8, 12), date(2026, 8, 11))
        self.monthly(self.guardia, date(2026, 8, 2), date(2026, 8, 7))
        self.context = SimpleNamespace(user_data={bot.MODE: bot.ENTER})
        self.message = SimpleNamespace(chat=SimpleNamespace(id=1), reply_text=AsyncMock())

    def confirmed(self, node, due, actual, notes):
        schedule, _ = ReadingSchedule.objects.get_or_create(node=node, due_date=due, defaults={"notes": notes})
        schedule.status = ReadingSchedule.Status.COMPLETED
        schedule.save()
        return Reading.objects.create(
            schedule=schedule, reading_date=actual, confirmed_value=Decimal("100"),
            status=Reading.Status.CONFIRMED, telegram_user_id=self.user.id, telegram_chat_id=1,
        )

    def monthly(self, node, due, actual):
        return self.confirmed(node, due, actual, "Lectura mensual | Base operativa agosto 2026")

    def follow_up(self, node, due, actual):
        return self.confirmed(node, due, actual, "Seguimiento de 10 días")

    def select(self, node):
        async_to_sync(bot.select_node)(self.message, self.context, node.pk, self.user.id)

    def draft(self, node, user=None):
        reading, error = async_to_sync(bot.create_manual_reading)(node.pk, Decimal("200"), user or self.user, 1)
        self.assertIsNone(error)
        return reading

    def test_huacho_is_blocked_before_photo_with_exact_next_opening(self):
        before = (Reading.objects.count(), ReadingSchedule.objects.count())
        with patch.object(bot, "get_pending_node_reading", new=AsyncMock()) as pending:
            self.select(self.huacho)
            pending.assert_not_awaited()
        messages = "\n".join(call.args[0] for call in self.message.reply_text.call_args_list)
        self.assertIn("ya tiene su lectura mensual y su seguimiento", messages)
        self.assertIn("desde el 01/09/2026", messages)
        self.assertIn("03/09/2026", messages)
        self.assertNotIn("Ahora envía una fotografía", messages)
        self.assertEqual(self.context.user_data[bot.STATE], bot.MAIN_MENU)
        self.assertEqual((Reading.objects.count(), ReadingSchedule.objects.count()), before)

    def test_huacho_can_register_on_september_first(self):
        self.today = date(2026, 9, 1)
        self.select(self.huacho)
        self.assertEqual(self.context.user_data[bot.STATE], bot.WAIT_PHOTO)
        self.assertIn("lectura mensual del ciclo 09/2026", self.message.reply_text.call_args.args[0])
        draft = self.draft(self.huacho)
        reading = async_to_sync(bot.confirm_reading)(draft.pk, self.user.id, self.today)
        self.assertEqual(reading.schedule.due_date, date(2026, 9, 3))
        self.assertFalse(reading.schedule.is_follow_up)

    def test_completed_cycle_blocks_direct_manual_and_photo_creation(self):
        with patch.object(bot, "read_meter") as ocr:
            photo, error = async_to_sync(bot.create_reading)(self.huacho.pk, b"", "test.jpg", self.user, 1)
            ocr.assert_not_called()
        self.assertIsNone(photo)
        self.assertIn("01/09/2026", error)
        manual, error = async_to_sync(bot.create_manual_reading)(self.huacho.pk, Decimal("200"), self.user, 1)
        self.assertIsNone(manual)
        self.assertIn("01/09/2026", error)
        self.assertEqual(self.huacho.schedules.count(), 2)

    def test_guardia_switches_from_old_follow_up_to_new_monthly_on_august_31(self):
        self.today = date(2026, 8, 30)
        previous = get_registration_plan(self.guardia)
        self.assertEqual(previous.kind, "FOLLOW_UP")
        self.assertEqual(previous.due_date, date(2026, 8, 17))
        self.today = date(2026, 8, 31)
        self.select(self.guardia)
        message = self.message.reply_text.call_args.args[0]
        self.assertIn("lectura mensual del ciclo 09/2026", message)
        self.assertIn("02/09/2026", message)
        self.assertIn("ciclo anterior ya están cerrados", message)
        draft = self.draft(self.guardia)
        reading = async_to_sync(bot.confirm_reading)(draft.pk, self.user.id, self.today)
        self.assertEqual(reading.schedule.due_date, date(2026, 9, 2))
        self.assertFalse(reading.schedule.is_follow_up)
        with self.assertRaisesMessage(ValidationError, "09/09/2026"):
            get_registration_plan(self.guardia)
        self.today = date(2026, 9, 9)
        next_plan = get_registration_plan(self.guardia)
        self.assertEqual(next_plan.kind, "FOLLOW_UP")
        self.assertEqual(next_plan.due_date, date(2026, 9, 10))

    def test_single_monthly_reading_is_explained_as_follow_up_with_cutoff(self):
        node = Node.objects.create(code="200", name="200 Millas", reading_day=11, telegram_chat_id=1)
        self.monthly(node, date(2026, 8, 11), date(2026, 8, 31))
        self.select(node)
        message = "\n".join(call.args[0] for call in self.message.reply_text.call_args_list)
        self.assertIn("no tiene una ventana disponible", message)
        self.assertIn("09/09/2026", message)
        self.today = date(2026, 9, 8)
        with self.assertRaisesMessage(ValidationError, "09/09/2026"):
            get_registration_plan(node)
        self.today = date(2026, 9, 9)
        self.assertEqual(get_registration_plan(node).kind, "MONTHLY")

    def test_another_operator_completing_follow_up_blocks_old_draft_at_confirmation(self):
        self.today = date(2026, 8, 30)
        first = self.draft(self.guardia)
        other = SimpleNamespace(id=2, username="otro", full_name="Otro")
        second = self.draft(self.guardia, other)
        async_to_sync(bot.confirm_reading)(first.pk, self.user.id, self.today)
        with self.assertRaisesMessage(ValidationError, "ya tiene su lectura mensual y su seguimiento"):
            async_to_sync(bot.confirm_reading)(second.pk, other.id, self.today)
        second.refresh_from_db()
        self.assertEqual(second.status, Reading.Status.REVIEW)
        self.assertEqual(Reading.objects.filter(schedule__node=self.guardia, status=Reading.Status.CONFIRMED).count(), 2)

    def test_future_date_cannot_open_next_cycle_early(self):
        draft = self.draft(self.guardia)
        with self.assertRaisesMessage(ValidationError, "Hoy es 31/08/2026"):
            async_to_sync(bot.confirm_reading)(draft.pk, self.user.id, date(2026, 9, 30))
        draft.refresh_from_db()
        self.assertEqual(draft.status, Reading.Status.REVIEW)
        self.assertIsNone(draft.confirmed_value)

    def test_old_follow_up_draft_reclassifies_when_new_window_opens(self):
        self.today = date(2026, 8, 30)
        draft = self.draft(self.guardia)
        self.assertTrue(draft.schedule.is_follow_up)
        previous_schedule = draft.schedule
        self.today = date(2026, 8, 31)
        reading = async_to_sync(bot.confirm_reading)(draft.pk, self.user.id, self.today)
        self.assertEqual(reading.schedule.due_date, date(2026, 9, 2))
        self.assertFalse(reading.schedule.is_follow_up)
        previous_schedule.refresh_from_db()
        self.assertEqual(previous_schedule.status, ReadingSchedule.Status.PENDING)

    def test_incomplete_monthly_record_does_not_count_as_completed_reading(self):
        node = Node.objects.create(code="NONE", name="Sin lectura", reading_day=23, telegram_chat_id=1)
        schedule = ReadingSchedule.objects.create(node=node, due_date=date(2026, 8, 23), notes="Lectura mensual")
        Reading.objects.create(schedule=schedule, status=Reading.Status.REVIEW, detected_value=100)
        plan = get_registration_plan(node)
        self.assertEqual(plan.kind, "MONTHLY")
        self.assertEqual(plan.due_date, date(2026, 8, 23))

    def test_guardia_rejects_early_photo_date_cancels_draft_and_returns_home(self):
        self.monthly(self.guardia, date(2026, 9, 2), date(2026, 9, 2))
        self.today = date(2026, 9, 7)
        with self.assertRaisesMessage(ValidationError, "11/09/2026"):
            get_registration_plan(self.guardia)
        self.today = date(2026, 9, 11)
        draft = self.draft(self.guardia)
        draft.photo = 'meter_photos/test-window.jpg'
        draft.save()
        self.context.user_data.update({
            bot.STATE: bot.WAIT_DATE, 'reading_id': draft.pk,
            bot.ACTIVE_USER_ID: self.user.id,
        })
        async_to_sync(bot.finish_reading)(self.message, self.context, self.user.id, date(2026, 9, 7))
        draft.refresh_from_db()
        self.assertEqual(draft.status, Reading.Status.CANCELLED)
        self.assertIsNone(draft.confirmed_value)
        self.assertFalse(draft.ocr_learning_verified)
        self.assertEqual(self.context.user_data[bot.STATE], bot.MAIN_MENU)
        messages = '\n'.join(call.args[0] for call in self.message.reply_text.call_args_list)
        self.assertIn('11/09/2026', messages)
        self.assertIn('La lectura no fue registrada', messages)
        valid = self.draft(self.guardia)
        reading = async_to_sync(bot.confirm_reading)(valid.pk, self.user.id, date(2026, 9, 11))
        self.assertEqual(reading.status, Reading.Status.CONFIRMED)

    def test_200_millas_complete_august_cannot_open_september_until_ninth(self):
        node = Node.objects.create(code='200-W', name='200 Millas', reading_day=11, telegram_chat_id=1)
        self.monthly(node, date(2026, 8, 11), date(2026, 8, 11))
        self.follow_up(node, date(2026, 8, 21), date(2026, 8, 21))
        for day in (7, 8):
            self.today = date(2026, 9, day)
            with self.assertRaisesMessage(ValidationError, '09/09/2026'):
                get_registration_plan(node)
        self.today = date(2026, 9, 9)
        plan = get_registration_plan(node)
        self.assertEqual(plan.kind, 'MONTHLY')
        self.assertEqual(plan.due_date, date(2026, 9, 11))
        self.assertEqual(plan.opens_on, self.today)
