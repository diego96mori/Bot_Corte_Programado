from readings.test_access_helpers import create_interface_user
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from readings.models import Node, Reading, ReadingSchedule
from readings.services.annual_grid import annual_row


class AnnualCycleTests(TestCase):
    def setUp(self):
        self.node = Node.objects.create(code="GUARDIA", name="Guardia Peruana", reading_day=2)
        self.client.force_login(create_interface_user(username="consulta"))

    def reading(self, due, taken, notes="Lectura mensual", value=123):
        schedule, _ = ReadingSchedule.objects.get_or_create(
            node=self.node, due_date=due, defaults={"notes": notes, "status": "COMPLETED"},
        )
        return Reading.objects.create(schedule=schedule, reading_date=taken,
                                      confirmed_value=value, status="CONFIRMED")

    def row(self, year=2026, today=date(2026, 9, 1)):
        readings = list(Reading.objects.select_related("schedule__node").order_by("reading_date", "pk"))
        return annual_row(self.node, readings, list(self.node.schedules.all()), year, today)

    def test_august_31_belongs_to_september_with_real_date_and_pending_followup(self):
        monthly = self.reading(date(2026, 9, 2), date(2026, 8, 31))
        row = self.row()
        self.assertEqual(row["months"][7], [])
        entries = row["months"][8]
        self.assertEqual(entries[0]["reading"].pk, monthly.pk)
        self.assertEqual(entries[1]["due"], date(2026, 9, 10))
        self.assertEqual(entries[1]["state"], "Pendiente")
        response = self.client.get(reverse("readings:annual_grid"), {"year": 2026})
        self.assertContains(response, "Tomada el 31/08/2026")
        self.assertContains(response, 'data-cycle="2026-09"')
        monthly.refresh_from_db()
        self.assertEqual(monthly.reading_date, date(2026, 8, 31))
        self.assertEqual(Reading.objects.count(), 1)

    def test_followup_uses_parent_cycle_even_when_actual_month_differs(self):
        monthly = self.reading(date(2026, 8, 2), date(2026, 8, 25))
        follow = self.reading(date(2026, 9, 4), date(2026, 9, 1), "Seguimiento de 10 días", 130)
        row = self.row()
        self.assertEqual([e["reading"].pk for e in row["months"][7]], [monthly.pk, follow.pk])
        self.assertEqual(row["months"][8], [])

    def test_december_photo_can_fulfil_january_and_next_year_followup_can_belong_to_december(self):
        january = self.reading(date(2027, 1, 2), date(2026, 12, 31))
        self.assertEqual(self.row()["months"][11], [])
        self.assertEqual(self.row(2027, date(2027, 1, 1))["months"][0][0]["reading"].pk, january.pk)
        december = self.reading(date(2026, 12, 2), date(2026, 12, 25))
        follow = self.reading(date(2027, 1, 4), date(2027, 1, 1), "Seguimiento de 10 días")
        entries = self.row(today=date(2027, 1, 2))["months"][11]
        self.assertEqual([e["reading"].pk for e in entries], [december.pk, follow.pk])

    def test_imports_and_orphans_are_not_guessed_into_another_cycle(self):
        historical = self.reading(date(2026, 8, 31), date(2026, 8, 31), "Importada desde LECTURAS 2026")
        orphan = self.reading(date(2026, 9, 10), date(2026, 9, 9), "Seguimiento de 10 días")
        row = self.row()
        self.assertEqual(row["months"][7][0]["reading"].pk, historical.pk)
        self.assertEqual(row["months"][8][0]["reading"].pk, orphan.pk)
        self.assertIn("sin identificar", row["months"][8][0]["kind"])

    def test_ambiguous_parent_does_not_duplicate_followup_or_invent_pending(self):
        self.reading(date(2026, 8, 2), date(2026, 8, 31))
        self.reading(date(2026, 9, 2), date(2026, 8, 31))
        follow = self.reading(date(2026, 9, 10), date(2026, 9, 10), "Seguimiento de 10 días")
        entries = [e for month in self.row()["months"] for e in month]
        self.assertEqual(len(entries), 3)
        self.assertEqual(sum(e["reading"].pk == follow.pk for e in entries), 1)
        self.assertIn("sin identificar", next(e for e in entries if e["reading"].pk == follow.pk)["kind"])

    def test_closed_and_cancelled_followups_are_not_shown_as_active_pending(self):
        self.reading(date(2026, 9, 2), date(2026, 8, 31))
        self.assertIn("ciclo cerrado", self.row(today=date(2026, 9, 30))["months"][8][1]["state"])
        ReadingSchedule.objects.create(node=self.node, due_date=date(2026, 9, 10), notes="Seguimiento", status="CANCELLED")
        self.assertEqual(self.row()["months"][8][1]["state"], "Anulado")

    def test_august_baseline_keeps_explicit_august_cycle_and_missing_date_is_visible(self):
        self.reading(date(2026, 8, 2), date(2026, 8, 31), "Lectura mensual | Base operativa agosto 2026")
        self.reading(date(2026, 7, 1), None, "Importada")
        row = self.row()
        self.assertEqual(row["months"][8], [])
        self.assertEqual(row["months"][7][0]["kind"], "Mensual")
        self.assertEqual(len(row["undated"]), 1)
