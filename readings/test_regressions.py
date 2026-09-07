from readings.test_access_helpers import create_interface_user
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from telegram.error import Forbidden

from readings.management.commands import run_telegram_bot as bot
from readings.models import Node, Reading, ReadingSchedule, ReminderLog
from readings.services.calendar import get_calendar_events
from readings.services.notifications import (
    ReadingNotification, get_cycle_state, get_node_obligation, get_reading_notifications,
)
from readings.services.reminders import prepare_reminder_jobs, send_reminder_jobs


class ReadingCycleRegressionTests(TestCase):
    def setUp(self):
        self.node = Node.objects.create(
            code="CYCLE", name="200 Millas", reading_day=11, telegram_chat_id=1,
        )
        self.user = SimpleNamespace(id=1, username="operador", full_name="Operador")

    def draft(self, entered_on, value="100"):
        self.entered_on = entered_on
        with patch.object(bot.timezone, "localdate", return_value=entered_on):
            reading, error = async_to_sync(bot.create_manual_reading)(
                self.node.id, Decimal(value), self.user, 1,
            )
        self.assertIsNone(error)
        return reading

    def confirm(self, reading, reading_date):
        with patch.object(bot.timezone, "localdate", return_value=max(self.entered_on, reading_date)):
            return async_to_sync(bot.confirm_reading)(reading.id, self.user.id, reading_date)

    def test_late_august_reading_keeps_august_cycle_and_ten_day_follow_up(self):
        reading = self.confirm(self.draft(date(2026, 8, 31)), date(2026, 8, 31))
        self.assertEqual(reading.schedule.due_date, date(2026, 8, 11))
        state = get_cycle_state(self.node, date(2026, 8, 11))
        self.assertEqual(state["follow_up_due"], date(2026, 9, 10))
        self.assertEqual(state["cutoff"], date(2026, 9, 9))
        for day in (7, 8):
            self.assertEqual(
                get_node_obligation(self.node, date(2026, 9, day)),
                (date(2026, 9, 10), "FOLLOW_UP"),
            )
        self.assertEqual(
            get_node_obligation(self.node, date(2026, 9, 9)),
            (date(2026, 9, 11), "MONTHLY"),
        )

    def test_september_eighth_registers_a_single_follow_up(self):
        self.confirm(self.draft(date(2026, 8, 29)), date(2026, 8, 29))
        follow_up = self.confirm(self.draft(date(2026, 9, 8), "110"), date(2026, 9, 8))
        self.assertTrue(follow_up.schedule.is_follow_up)
        self.assertEqual(follow_up.schedule.due_date, date(2026, 9, 8))
        self.assertTrue(get_cycle_state(self.node, date(2026, 8, 11))["follow_up_completed"])
        self.assertEqual(
            get_node_obligation(self.node, date(2026, 9, 9)),
            (date(2026, 9, 11), "MONTHLY"),
        )

    def test_draft_started_on_eighth_becomes_monthly_when_dated_ninth(self):
        self.confirm(self.draft(date(2026, 8, 29)), date(2026, 8, 29))
        draft = self.draft(date(2026, 9, 8), "110")
        old_follow_up = draft.schedule
        monthly = self.confirm(draft, date(2026, 9, 9))
        self.assertFalse(monthly.schedule.is_follow_up)
        self.assertEqual(monthly.schedule.due_date, date(2026, 9, 11))
        self.assertIsNotNone(get_cycle_state(self.node, date(2026, 9, 11))["monthly_reading"])
        old_follow_up.refresh_from_db()
        self.assertNotEqual(old_follow_up.status, ReadingSchedule.Status.COMPLETED)
        events = get_calendar_events(2026, 9, date(2026, 9, 9))
        old_task = next(event for event in events if event["date"] == "2026-09-08")
        self.assertEqual(old_task["state"], "closed")

    def test_backdated_reading_cannot_reopen_a_closed_cycle(self):
        older = ReadingSchedule.objects.create(node=self.node, due_date=date(2026, 6, 11))
        draft = self.draft(date(2026, 8, 31))
        august = draft.schedule
        with self.assertRaisesMessage(ValidationError, "ya está cerrado"):
            self.confirm(draft, date(2026, 7, 11))
        draft.refresh_from_db()
        self.assertEqual(draft.status, Reading.Status.REVIEW)
        for schedule in (older, august):
            schedule.refresh_from_db()
            self.assertEqual(schedule.status, ReadingSchedule.Status.PENDING)
        prepare_reminder_jobs(timezone.make_aware(datetime(2026, 8, 31, 12)))
        august.refresh_from_db()
        self.assertEqual(august.status, ReadingSchedule.Status.PENDING)

    def test_backdating_cannot_create_another_monthly_before_existing_reading(self):
        self.confirm(self.draft(date(2026, 8, 31)), date(2026, 8, 31))
        draft = self.draft(date(2026, 9, 15), "90")
        with self.assertRaisesMessage(ValidationError, "historial en gris"):
            self.confirm(draft, date(2026, 8, 11))
        draft.refresh_from_db()
        self.assertEqual(draft.status, Reading.Status.REVIEW)

    def test_backdating_cannot_insert_a_third_reading_in_completed_cycle(self):
        self.confirm(self.draft(date(2026, 8, 29)), date(2026, 8, 29))
        self.confirm(self.draft(date(2026, 9, 8), "110"), date(2026, 9, 8))
        draft = self.draft(date(2026, 9, 15), "105")
        with self.assertRaisesMessage(ValidationError, "historial en gris"):
            self.confirm(draft, date(2026, 9, 7))
        draft.refresh_from_db()
        self.assertEqual(draft.status, Reading.Status.REVIEW)

    def test_completion_is_atomic_when_schedule_save_fails(self):
        draft = self.draft(date(2026, 8, 31))
        with patch.object(ReadingSchedule, "save", side_effect=RuntimeError("database failure")):
            with self.assertRaises(RuntimeError):
                self.confirm(draft, date(2026, 8, 31))
        draft.refresh_from_db()
        self.assertEqual(draft.status, Reading.Status.REVIEW)
        self.assertIsNone(draft.confirmed_value)

    def test_missing_august_reading_keeps_alert_until_september_ninth(self):
        for today in (date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 8)):
            with self.subTest(today=today):
                alerts = get_reading_notifications(today)
                self.assertEqual(len(alerts), 1)
                self.assertEqual(alerts[0].due_date, date(2026, 8, 11))
                self.assertTrue(alerts[0].is_overdue)
        alerts = get_reading_notifications(date(2026, 9, 9))
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].due_date, date(2026, 9, 11))
        self.assertFalse(alerts[0].is_overdue)

    def test_overdue_alert_survives_year_change(self):
        alerts = get_reading_notifications(date(2027, 1, 1))
        self.assertEqual(alerts[0].due_date, date(2026, 12, 11))


class TelegramInputRegressionTests(TestCase):
    def setUp(self):
        self.node = Node.objects.create(code="INPUT", name="Nodo", reading_day=11, telegram_chat_id=1)
        self.user = SimpleNamespace(id=1, username="operador", full_name="Operador")
        self.message = SimpleNamespace(chat=SimpleNamespace(id=1), text="1234.5", reply_text=AsyncMock())
        self.context = SimpleNamespace(user_data={bot.STATE: bot.WAIT_PHOTO, "node_id": self.node.id})
        self.update = SimpleNamespace(
            message=self.message, effective_chat=self.message.chat, effective_user=self.user,
        )

    def test_manual_entry_after_choosing_it_can_be_confirmed_and_saved(self):
        self.context.user_data[bot.STATE] = bot.WAIT_MANUAL_VALUE
        async_to_sync(bot.receive_text)(self.update, self.context)
        self.assertEqual(self.context.user_data[bot.STATE], bot.CONFIRM_MANUAL_VALUE)
        reading = Reading.objects.get(pk=self.context.user_data["reading_id"])
        self.assertEqual(reading.detected_value, Decimal("1234.5"))
        self.assertEqual(reading.source, Reading.Source.MANUAL)
        self.assertEqual(reading.status, Reading.Status.REVIEW)
        async_to_sync(bot.ask_reading_date)(self.message, self.context)
        self.assertEqual(self.context.user_data[bot.STATE], bot.CHOOSE_DATE)
        query = SimpleNamespace(
            message=self.message, answer=AsyncMock(),
            data=f"date:manual|{self.context.user_data['prompt_token']}",
        )
        self.update.callback_query = query
        async_to_sync(bot.callback)(self.update, self.context)
        self.message.text = "31/08/2026"
        async_to_sync(bot.receive_text)(self.update, self.context)
        reading.refresh_from_db()
        self.assertEqual(reading.status, Reading.Status.CONFIRMED)
        self.assertEqual(reading.confirmed_value, Decimal("1234.5"))
        self.assertEqual(reading.schedule.due_date, date(2026, 8, 11))

    def test_invalid_text_keeps_photo_option_without_creating_a_reading(self):
        self.message.text = "no tengo foto"
        async_to_sync(bot.receive_text)(self.update, self.context)
        self.assertEqual(self.context.user_data[bot.STATE], bot.WAIT_PHOTO)
        self.assertFalse(Reading.objects.exists())

    def test_missing_day_blocks_manual_and_photo_before_processing(self):
        self.node.reading_day = None
        self.node.save()
        manual, error = async_to_sync(bot.create_manual_reading)(self.node.id, Decimal("100"), self.user, 1)
        self.assertIsNone(manual)
        self.assertIn("día de lectura", error)
        with patch.object(bot, "read_meter") as ocr:
            photo, error = async_to_sync(bot.create_reading)(self.node.id, b"", "test.jpg", self.user, 1)
            ocr.assert_not_called()
        self.assertIsNone(photo)
        self.assertIn("día de lectura", error)
        self.assertFalse(Reading.objects.exists())
        self.assertFalse(ReadingSchedule.objects.exists())

    def test_selecting_unconfigured_node_explains_the_missing_day(self):
        self.node.reading_day = None
        self.node.save()
        async_to_sync(bot.select_node)(self.message, self.context, self.node.id, 1)
        self.assertTrue(any("día de lectura" in call.args[0] for call in self.message.reply_text.call_args_list))
        self.assertEqual(self.context.user_data[bot.STATE], bot.MAIN_MENU)

    def test_day_removed_before_confirmation_keeps_draft_and_explains_problem(self):
        self.context.user_data[bot.STATE] = bot.WAIT_MANUAL_VALUE
        async_to_sync(bot.receive_text)(self.update, self.context)
        reading_id = self.context.user_data["reading_id"]
        self.node.reading_day = None
        self.node.save()
        async_to_sync(bot.finish_reading)(self.message, self.context, 1, date(2026, 8, 31))
        self.assertIn("día de lectura", self.message.reply_text.call_args.args[0])
        self.assertEqual(Reading.objects.get(pk=reading_id).status, Reading.Status.REVIEW)
        self.assertEqual(self.context.user_data["reading_id"], reading_id)


class PartialReminderDeliveryTests(TestCase):
    def setUp(self):
        for number in (1, 2, 3):
            Node.objects.create(
                code=f"SEND-{number}", name=f"Nodo {number}", reading_day=19, telegram_chat_id=number,
            )
        self.now = timezone.make_aware(datetime(2026, 8, 17, 12))

    def test_failure_does_not_block_later_recipients_or_repeat_successful_sends(self):
        jobs = prepare_reminder_jobs(self.now)

        async def send_message(**kwargs):
            chat_id = kwargs["chat_id"]
            if chat_id == 2:
                # The first delivery must already be durable before the second starts.
                self.assertTrue(await sync_to_async(ReminderLog.objects.filter(chat_id=1).exists)())
                raise Forbidden("Bot blocked")
            return SimpleNamespace(message_id=chat_id * 10)

        fake_bot = SimpleNamespace(send_message=AsyncMock(side_effect=send_message))
        with patch("django.utils.timezone.now", return_value=self.now):
            with self.assertLogs("readings.services.reminders", level="ERROR"):
                results = async_to_sync(send_reminder_jobs)(fake_bot, jobs)
        self.assertEqual(fake_bot.send_message.await_count, 3)
        self.assertEqual(len(results), 2)
        self.assertEqual(set(ReminderLog.objects.values_list("chat_id", flat=True)), {1, 3})
        self.assertEqual([job["chat_id"] for job in prepare_reminder_jobs(self.now)], [2])

    def test_successful_delivery_remains_recorded_after_unexpected_later_failure(self):
        jobs = prepare_reminder_jobs(self.now)
        fake_bot = SimpleNamespace(send_message=AsyncMock(side_effect=[
            SimpleNamespace(message_id=10), RuntimeError("unexpected failure"),
        ]))
        with self.assertRaises(RuntimeError):
            async_to_sync(send_reminder_jobs)(fake_bot, jobs)
        self.assertEqual(ReminderLog.objects.count(), 1)
        self.assertEqual(ReminderLog.objects.get().chat_id, 1)


class ConfirmedScheduleRegressionTests(TestCase):
    def setUp(self):
        self.now = timezone.make_aware(datetime(2026, 8, 31, 12))
        self.schedules = []
        for name, day, value in (("Chimbote Manco Capac", 15, "88746.84"), ("Pelitres", 5, "155841")):
            node = Node.objects.create(code=name, name=name, reading_day=23, telegram_chat_id=1)
            schedule = ReadingSchedule.objects.create(
                node=node, due_date=date(2026, 8, 23), notes="Lectura mensual",
                status=ReadingSchedule.Status.COMPLETED,
            )
            Reading.objects.create(
                schedule=schedule, reading_date=date(2026, 8, day),
                detected_value=Decimal(value), confirmed_value=Decimal(value),
                status=Reading.Status.CONFIRMED,
            )
            self.schedules.append(schedule)
        pelitres_follow_up = ReadingSchedule.objects.create(
            node=self.schedules[1].node, due_date=date(2026, 8, 15), notes="Seguimiento de 10 días",
            status=ReadingSchedule.Status.COMPLETED,
        )
        Reading.objects.create(
            schedule=pelitres_follow_up, reading_date=date(2026, 8, 19),
            detected_value=156440, confirmed_value=156440, status=Reading.Status.CONFIRMED,
        )

    def test_explicit_monthly_assignment_recognizes_early_capture_dates(self):
        chimbote, pelitres = self.schedules
        state = get_cycle_state(chimbote.node, date(2026, 8, 23))
        self.assertEqual(state["monthly_reading"].reading_date, date(2026, 8, 15))
        self.assertEqual(state["follow_up_due"], date(2026, 8, 25))
        self.assertEqual(
            get_node_obligation(pelitres.node, date(2026, 8, 31)),
            (date(2026, 9, 23), "MONTHLY"),
        )

    def test_reminders_do_not_reopen_completed_monthly_rows(self):
        for _ in range(2):
            jobs = prepare_reminder_jobs(self.now)
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["item"].kind, "FOLLOW_UP")
            self.assertEqual(jobs[0]["item"].due_date, date(2026, 8, 25))
            for schedule in self.schedules:
                schedule.refresh_from_db()
                self.assertEqual(schedule.status, ReadingSchedule.Status.COMPLETED)
                self.assertEqual(schedule.notes, "Lectura mensual")

    def test_stale_notification_cannot_reopen_a_confirmed_schedule(self):
        schedule = self.schedules[0]
        item = ReadingNotification(schedule.node, schedule.due_date, "MONTHLY", -8)
        for status in (ReadingSchedule.Status.COMPLETED, ReadingSchedule.Status.PENDING):
            schedule.status = status
            schedule.save(update_fields=["status"])
            with patch("readings.services.reminders.get_reading_notifications", return_value=[item]):
                self.assertEqual(prepare_reminder_jobs(self.now), [])
            schedule.refresh_from_db()
            self.assertEqual(schedule.status, ReadingSchedule.Status.COMPLETED)
            self.assertEqual(schedule.readings.get().confirmed_value, Decimal("88746.84"))

    def test_reminders_respect_explicit_cancellation(self):
        schedule = self.schedules[0]
        schedule.status = ReadingSchedule.Status.CANCELLED
        schedule.save(update_fields=["status"])
        item = ReadingNotification(schedule.node, schedule.due_date, "MONTHLY", -8)
        with patch("readings.services.reminders.get_reading_notifications", return_value=[item]):
            self.assertEqual(prepare_reminder_jobs(self.now), [])
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, ReadingSchedule.Status.CANCELLED)

    def test_completed_filter_keeps_confirmed_rows_after_reminder_check(self):
        prepare_reminder_jobs(self.now)
        user = create_interface_user(username="schedule_viewer")
        self.client.force_login(user)
        with patch("readings.views.timezone.localdate", return_value=date(2026, 8, 31)):
            response = self.client.get(reverse("readings:grid"), {"status": "COMPLETED"})
        ids = {schedule.pk for schedule in response.context["schedules"]}
        self.assertTrue({schedule.pk for schedule in self.schedules}.issubset(ids))
        self.assertNotContains(response, "Lectura atrasada 8 días")
        self.assertContains(response, '<td class="COMPLETED">Completada</td>', count=3)
