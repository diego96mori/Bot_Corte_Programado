from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from readings.management.commands import run_telegram_bot as bot
from readings.models import Node, Reading, ReadingSchedule
from readings.services.calendar import get_calendar_events
from readings.services.notifications import active_cycle_due, get_node_obligation, get_reading_notifications
from readings.services.reminders import prepare_reminder_jobs
from readings.services.reminders import reminder_text


class CycleBoundaryTests(TestCase):
    def test_window_includes_previous_month_year_and_leap_day(self):
        cases = [
            (2, date(2026, 8, 31), date(2026, 9, 2)),
            (1, date(2026, 8, 30), date(2026, 9, 1)),
            (1, date(2026, 12, 30), date(2027, 1, 1)),
            (2, date(2026, 12, 31), date(2027, 1, 2)),
            (2, date(2027, 2, 28), date(2027, 3, 2)),
            (2, date(2028, 2, 29), date(2028, 3, 2)),
            (1, date(2028, 2, 28), date(2028, 3, 1)),
            (31, date(2027, 2, 26), date(2027, 2, 28)),
            (31, date(2028, 2, 27), date(2028, 2, 29)),
            (11, date(2026, 9, 9), date(2026, 9, 11)),
        ]
        for day, cutoff, due in cases:
            with self.subTest(day=day, cutoff=cutoff):
                node = Node(reading_day=day)
                self.assertEqual(active_cycle_due(node, cutoff), due)
                self.assertLess(active_cycle_due(node, cutoff - timedelta(days=1)), due)

    def test_late_monthly_reading_reminds_until_next_cycle_opens(self):
        node = Node.objects.create(
            code="LATE-15", name="Lectura tardía", reading_day=15,
            telegram_chat_id=1,
        )
        monthly = ReadingSchedule.objects.create(
            node=node, due_date=date(2026, 8, 15),
            notes="Lectura mensual", status=ReadingSchedule.Status.COMPLETED,
        )
        Reading.objects.create(
            schedule=monthly, reading_date=date(2026, 9, 11),
            confirmed_value=100, status=Reading.Status.CONFIRMED,
        )

        for today in (date(2026, 9, 11), date(2026, 9, 12)):
            with self.subTest(today=today):
                alerts = get_reading_notifications(today)
                self.assertEqual(len(alerts), 1)
                self.assertEqual(alerts[0].kind, "FOLLOW_UP")
                self.assertEqual(alerts[0].due_date, date(2026, 9, 21))
                self.assertEqual(alerts[0].cutoff, date(2026, 9, 13))
                self.assertIn("Disponible hasta el 12/09/2026", alerts[0].status_label)
                self.assertIn("Último día para registrarlo: 12/09/2026", reminder_text(alerts[0]))

        alerts = get_reading_notifications(date(2026, 9, 13))
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].kind, "MONTHLY")
        self.assertEqual(alerts[0].due_date, date(2026, 9, 15))


class UpcomingGridTests(TestCase):
    today = date(2026, 8, 31)

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="grid_boundaries")
        self.client.force_login(self.user)
        self.nodes = []
        for name, actual_day, provider in (("Benvenutto", 4, "PLUZ"), ("Guardia Peruana", 7, "LUZ DEL SUR")):
            node = Node.objects.create(code=name, name=name, reading_day=2, provider=provider)
            monthly = ReadingSchedule.objects.create(
                node=node, due_date=date(2026, 8, 2), notes="Lectura mensual | Base operativa agosto 2026",
                status=ReadingSchedule.Status.COMPLETED,
            )
            Reading.objects.create(
                schedule=monthly, reading_date=date(2026, 8, actual_day),
                confirmed_value=100, status=Reading.Status.CONFIRMED,
            )
            ReadingSchedule.objects.create(
                node=node, due_date=date(2026, 8, actual_day + 10), notes="Seguimiento de 10 días",
            )
            self.nodes.append(node)

    def grid(self, filters=None, today=None):
        with patch("readings.views.timezone.localdate", return_value=today or self.today):
            return self.client.get(reverse("readings:grid"), filters or {})

    def test_grid_shows_two_days_remaining_without_worker_or_database_writes(self):
        before = (ReadingSchedule.objects.count(), Reading.objects.count())
        response = self.grid()
        rows = response.context["schedules"]
        self.assertEqual([row.node.name for row in rows[:2]], ["Benvenutto", "Guardia Peruana"])
        self.assertTrue(all(row.due_date == date(2026, 9, 2) for row in rows[:2]))
        self.assertContains(response, "Lectura: faltan 2 días", count=2)
        self.assertContains(response, "Seguimiento no registrado · ciclo cerrado por nueva lectura mensual", count=2)
        self.assertContains(response, '<td class="CLOSED">', count=2)
        self.assertNotContains(response, "Seguimiento atrasado")
        self.assertEqual((ReadingSchedule.objects.count(), Reading.objects.count()), before)

    def test_grid_filters_include_projected_rows_but_not_in_completed(self):
        response = self.grid({"status": "PENDING_READING", "node": str(self.nodes[0].pk), "provider": "PLUZ"})
        rows = response.context["schedules"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].node, self.nodes[0])
        self.assertEqual(rows[0].due_date, date(2026, 9, 2))
        self.assertEqual(self.grid({"status": "PENDING_READING", "provider": "UNKNOWN"}).context["schedules"], [])
        completed = self.grid({"status": "COMPLETED"}).context["schedules"]
        self.assertEqual(len(completed), 2)
        self.assertTrue(all(row.status == ReadingSchedule.Status.COMPLETED for row in completed))

    def test_existing_schedule_appears_once_and_explicit_cancellation_is_preserved(self):
        existing = ReadingSchedule.objects.create(node=self.nodes[0], due_date=date(2026, 9, 2), notes="Lectura mensual")
        cancelled = ReadingSchedule.objects.create(
            node=self.nodes[1], due_date=date(2026, 9, 2), notes="Lectura mensual", status=ReadingSchedule.Status.CANCELLED,
        )
        rows = [row for row in self.grid().context["schedules"] if row.due_date == date(2026, 9, 2)]
        self.assertEqual({row.pk for row in rows}, {existing.pk, cancelled.pk})
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(self.grid({"status": "PENDING_READING"}).context["schedules"]), 1)

    def test_grid_calendar_obligation_and_jobs_switch_on_same_day(self):
        for node in self.nodes:
            node.telegram_chat_id = node.pk
            node.save(update_fields=["telegram_chat_id"])
            self.assertEqual(get_node_obligation(node, date(2026, 8, 30))[1], "FOLLOW_UP")
            self.assertEqual(get_node_obligation(node, self.today), (date(2026, 9, 2), "MONTHLY"))
        notifications = get_reading_notifications(self.today)
        self.assertEqual([(item.kind, item.due_date) for item in notifications], [("MONTHLY", date(2026, 9, 2))] * 2)
        events = get_calendar_events(2026, 9, self.today)
        self.assertEqual(len(events), 2)
        self.assertTrue(all(event["date"] == "2026-09-02" and event["state"] == "warning" for event in events))
        now = timezone.make_aware(datetime(2026, 8, 31, 12))
        jobs = prepare_reminder_jobs(now)
        self.assertEqual(len(jobs), 2)
        self.assertTrue(all(job["item"].kind == "MONTHLY" for job in jobs))
        self.assertEqual(len([row for row in self.grid().context["schedules"] if row.due_date == date(2026, 9, 2)]), 2)

    def test_countdown_advances_to_today_then_overdue(self):
        for today, label in (
            (date(2026, 9, 1), "Lectura: falta 1 día"),
            (date(2026, 9, 2), "Lectura para hoy"),
            (date(2026, 9, 3), "Lectura atrasada 1 día"),
        ):
            with self.subTest(today=today):
                self.assertContains(self.grid(today=today), label, count=2)

    def test_unregistered_old_monthly_row_is_closed_without_becoming_completed(self):
        node = Node.objects.create(code="Missing", name="Sin lectura", reading_day=2)
        old = ReadingSchedule.objects.create(node=node, due_date=date(2026, 8, 2), notes="Lectura mensual")
        response = self.grid({"node": str(node.pk)})
        self.assertContains(response, "Lectura no registrada · ciclo cerrado por nueva lectura mensual")
        self.assertContains(response, "Lectura: faltan 2 días")
        old.refresh_from_db()
        self.assertEqual(old.status, ReadingSchedule.Status.PENDING)
        self.assertFalse(old.readings.exists())

    def test_registration_on_august_31_belongs_to_september_monthly(self):
        node = self.nodes[0]
        node.telegram_chat_id = 1
        node.save(update_fields=["telegram_chat_id"])
        user = SimpleNamespace(id=1, username="operador", full_name="Operador")
        with patch.object(bot.timezone, "localdate", return_value=self.today):
            draft, error = async_to_sync(bot.create_manual_reading)(node.pk, Decimal("110"), user, 1)
            self.assertIsNone(error)
            confirmed = async_to_sync(bot.confirm_reading)(draft.pk, user.id, self.today)
        self.assertEqual(confirmed.schedule.due_date, date(2026, 9, 2))
        self.assertFalse(confirmed.schedule.is_follow_up)
        self.assertEqual(confirmed.schedule.status, ReadingSchedule.Status.COMPLETED)
        self.assertFalse(any(item.node == node for item in get_reading_notifications(self.today)))
        self.assertEqual(get_node_obligation(node, self.today), (date(2026, 9, 10), "FOLLOW_UP"))
