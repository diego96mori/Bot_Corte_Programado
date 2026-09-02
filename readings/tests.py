from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.template import Context, Template
from django.urls import reverse
from django.utils import timezone

from .models import Node, Reading, ReadingSchedule, ReminderLog
from .authorized_nodes import AUTHORIZED_NODES
from .management.commands.import_readings_excel import normalize, parse_day, parse_reading
from .management.commands.run_telegram_bot import (
    ACTIVE_CHAT_ID,
    ACTIVE_UNTIL,
    STATE,
    WAIT_PHOTO,
    find_best_node_name,
    is_conversation_active,
    normalize_node_name,
    parse_reading_date,
    parse_reading_value,
)
from .services.ocr import (
    OCRCandidate,
    OCRResult,
    choose_consistent_candidate,
    detect_red_decimal,
    find_display_crop,
    find_display_regions,
    find_kba_display_crop,
    generate_display_variants,
    read_meter,
    read_meter_cloudflare,
    select_direct_recognition,
    select_meter_value,
)
from .services.notifications import ReadingNotification, get_node_obligation, get_reading_notifications
from .services.calendar import get_calendar_events
from .services.reminders import prepare_reminder_jobs, reminder_text


class GridAccessTests(TestCase):
    def setUp(self):
        self.node = Node.objects.create(code="NODO-001", name="Nodo de prueba")
        ReadingSchedule.objects.create(node=self.node, due_date=date(2026, 8, 20))

    def test_anonymous_user_is_sent_to_regular_login(self):
        response = self.client.get(reverse("readings:grid"))
        self.assertRedirects(response, f"{reverse('login')}?next=/")

    def test_consultation_user_can_only_see_grid(self):
        user = get_user_model().objects.create_user(username="consulta", password="prueba-segura")
        self.client.force_login(user)
        response = self.client.get(reverse("readings:grid"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nodo de prueba")
        self.assertNotContains(response, 'href="/admin/"')
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_administrator_sees_admin_link(self):
        user = get_user_model().objects.create_superuser(
            username="administrador", email="admin@example.com", password="prueba-segura"
        )
        self.client.force_login(user)
        response = self.client.get(reverse("readings:grid"))
        self.assertContains(response, 'href="/admin/"')

    def test_grid_filters_node_provider_and_status_separately(self):
        self.node.provider = "PLUZ"
        self.node.save(update_fields=["provider"])
        other = Node.objects.create(code="NODO-002", name="Otro nodo", provider="ENOSA")
        ReadingSchedule.objects.create(
            node=other, due_date=date(2026, 8, 21), status=ReadingSchedule.Status.COMPLETED
        )
        user = get_user_model().objects.create_user(username="filtros", password="prueba-segura")
        self.client.force_login(user)
        response = self.client.get(
            reverse("readings:grid"), {"node": self.node.id, "provider": "PLUZ", "status": "PENDING"}
        )
        self.assertContains(response, "Nodo de prueba", count=2)
        self.assertContains(response, "Otro nodo", count=1)
        self.assertContains(response, "Todas las concesionarias")

    def test_grid_distinguishes_monthly_and_follow_up_pending_statuses(self):
        self.node.schedules.update(notes="Lectura mensual")
        follow_node = Node.objects.create(code="NODO-010", name="Nodo seguimiento")
        ReadingSchedule.objects.create(
            node=follow_node,
            due_date=date(2026, 8, 30),
            status=ReadingSchedule.Status.PENDING,
            notes="Seguimiento de 10 días",
        )
        user = get_user_model().objects.create_user(username="estados", password="prueba-segura")
        self.client.force_login(user)

        monthly = self.client.get(reverse("readings:grid"), {"status": "PENDING_READING"})
        self.assertContains(monthly, "Pendiente de lectura")
        self.assertContains(monthly, "Nodo de prueba", count=2)
        self.assertContains(monthly, "Nodo seguimiento", count=1)

        follow_up = self.client.get(reverse("readings:grid"), {"status": "PENDING_FOLLOW_UP"})
        self.assertContains(follow_up, "Pendiente de seguimiento")
        self.assertContains(follow_up, "Nodo seguimiento", count=2)
        self.assertContains(follow_up, "Nodo de prueba", count=1)

    def test_grid_orders_rows_by_the_scheduled_reading_date(self):
        completed_node = Node.objects.create(code="NODO-015", name="Lectura completada")
        completed_schedule = ReadingSchedule.objects.create(
            node=completed_node,
            due_date=date(2026, 8, 25),
            status=ReadingSchedule.Status.COMPLETED,
        )
        Reading.objects.create(
            schedule=completed_schedule,
            reading_date=date(2026, 8, 15),
            detected_value=100,
            confirmed_value=100,
            status=Reading.Status.CONFIRMED,
        )
        user = get_user_model().objects.create_user(username="orden", password="prueba-segura")
        self.client.force_login(user)

        response = self.client.get(reverse("readings:grid"))
        ordered_names = [schedule.node.name for schedule in response.context["schedules"]]

        self.assertEqual(ordered_names, ["Lectura completada", "Nodo de prueba"])
        self.assertContains(response, "Fecha de lectura")
        self.assertContains(response, "Fecha bot")
        self.assertContains(response, "Fecha de registro")

    def test_grid_switches_from_follow_up_to_monthly_three_days_before_reading_day(self):
        self.node.reading_day = 14
        self.node.save(update_fields=["reading_day"])
        self.node.schedules.all().delete()
        monthly = ReadingSchedule.objects.create(
            node=self.node,
            due_date=date(2026, 8, 14),
            status=ReadingSchedule.Status.COMPLETED,
            notes="Lectura mensual",
        )
        Reading.objects.create(
            schedule=monthly,
            reading_date=date(2026, 9, 5),
            detected_value=100,
            confirmed_value=100,
            status=Reading.Status.CONFIRMED,
        )
        ReadingSchedule.objects.create(
            node=self.node,
            due_date=date(2026, 9, 15),
            status=ReadingSchedule.Status.PENDING,
            notes="Seguimiento de 10 días",
        )
        ReadingSchedule.objects.create(
            node=self.node,
            due_date=date(2026, 9, 14),
            status=ReadingSchedule.Status.PENDING,
            notes="Lectura mensual",
        )
        user = get_user_model().objects.create_user(username="prioridad", password="prueba-segura")
        self.client.force_login(user)

        with patch("readings.views.timezone.localdate", return_value=date(2026, 9, 10)):
            response = self.client.get(reverse("readings:grid"), {"status": "PENDING_FOLLOW_UP"})
        self.assertEqual([schedule.due_date for schedule in response.context["schedules"]], [date(2026, 9, 15)])
        self.assertNotContains(response, "Seguimiento no registrado · ciclo cerrado por nueva lectura mensual")

        with patch("readings.views.timezone.localdate", return_value=date(2026, 9, 11)):
            response = self.client.get(reverse("readings:grid"), {"status": "PENDING_FOLLOW_UP"})
        self.assertNotContains(response, "Seguimiento no registrado · ciclo cerrado por nueva lectura mensual")

        with patch("readings.views.timezone.localdate", return_value=date(2026, 9, 12)):
            follow_up_response = self.client.get(reverse("readings:grid"), {"status": "PENDING_FOLLOW_UP"})
            monthly_response = self.client.get(reverse("readings:grid"), {"status": "PENDING_READING"})
        self.assertEqual(
            [schedule.due_date for schedule in follow_up_response.context["schedules"]],
            [date(2026, 9, 15)],
        )
        self.assertContains(
            follow_up_response,
            "Seguimiento no registrado · ciclo cerrado por nueva lectura mensual",
        )
        self.assertEqual(
            [schedule.due_date for schedule in monthly_response.context["schedules"]],
            [date(2026, 9, 14)],
        )

    def test_follow_up_stops_counting_overdue_on_first_of_month_for_reading_day_three(self):
        self.node.reading_day = 3
        self.node.save(update_fields=["reading_day"])
        self.node.schedules.all().delete()
        monthly = ReadingSchedule.objects.create(
            node=self.node,
            due_date=date(2026, 8, 3),
            status=ReadingSchedule.Status.COMPLETED,
            notes="Lectura mensual",
        )
        Reading.objects.create(
            schedule=monthly,
            reading_date=date(2026, 8, 8),
            detected_value=100,
            confirmed_value=100,
            status=Reading.Status.CONFIRMED,
        )
        ReadingSchedule.objects.create(
            node=self.node,
            due_date=date(2026, 8, 18),
            status=ReadingSchedule.Status.PENDING,
            notes="Seguimiento de 10 días",
        )
        user = get_user_model().objects.create_user(username="corte_dia_tres", password="prueba-segura")
        self.client.force_login(user)

        with patch("readings.views.timezone.localdate", return_value=date(2026, 8, 31)):
            response = self.client.get(reverse("readings:grid"), {"status": "PENDING_FOLLOW_UP"})
        self.assertContains(response, "Seguimiento atrasado 13 días")

        with patch("readings.views.timezone.localdate", return_value=date(2026, 9, 1)):
            response = self.client.get(reverse("readings:grid"), {"status": "PENDING_FOLLOW_UP"})
        self.assertContains(response, "Seguimiento no registrado · ciclo cerrado por nueva lectura mensual")
        self.assertNotContains(response, "Seguimiento atrasado 14 días")


class OCRSelectionTests(TestCase):
    def test_prefers_large_meter_display_and_preserves_decimal(self):
        result = [
            ([[470, 350], [760, 350], [760, 416], [470, 416]], "170269.6", 1.0),
            ([[880, 690], [1240, 690], [1240, 720], [880, 720]], "-12.05665615 -77.12476173", 0.99),
            ([[730, 610], [900, 610], [900, 640], [730, 640]], "8402965", 0.99),
            ([[1100, 670], [1240, 670], [1240, 696], [1100, 696]], "2026", 0.99),
        ]
        selected = select_meter_value(result)
        self.assertEqual(selected.value, Decimal("170269.6"))
        self.assertEqual(selected.confidence, 1.0)

    def test_grid_value_hides_unused_decimal_zeroes(self):
        rendered = Template("{% load reading_formats %}{{ value|reading_value }}").render(
            Context({"value": Decimal("170269.600")})
        )
        self.assertEqual(rendered, "170269,6")

    def test_uses_kwh_label_to_crop_the_display_on_its_left(self):
        import numpy as np

        image = np.zeros((576, 1280, 3), dtype=np.uint8)
        result = [
            ([[805, 203], [839, 203], [839, 223], [805, 223]], "kWh", 0.96),
            ([[617, 246], [690, 249], [690, 268], [616, 265]], "1600IMP/Kw-h", 0.93),
        ]
        crop = find_display_crop(image, result)
        self.assertIsNotNone(crop)
        self.assertGreater(crop.shape[1], 200)
        self.assertLess(crop.shape[1], 300)

    def test_direct_display_recognition_preserves_decimal(self):
        selected = select_direct_recognition([["31484.6", 0.984]], "FORUSA | kWh")
        self.assertEqual(selected.value, Decimal("31484.6"))
        self.assertEqual(selected.confidence, 0.984)
        self.assertIn("VISOR: 31484.6", selected.raw_text)

    def test_uses_kba_brand_to_crop_the_faint_lcd_above_it(self):
        import numpy as np

        image = np.zeros((1599, 899, 3), dtype=np.uint8)
        result = [
            ([[308, 716], [427, 716], [427, 762], [308, 762]], "KBA", 0.98),
            ([[521, 706], [668, 706], [668, 736], [521, 736]], "KBA-113D", 0.99),
        ]
        crop = find_kba_display_crop(image, result)
        self.assertIsNotNone(crop)
        self.assertGreater(crop.shape[1], 300)
        self.assertGreater(crop.shape[0], 70)

    def test_direct_recognition_prefers_complete_decimal_over_high_confidence_without_separator(self):
        selected = select_direct_recognition(
            [["234339", 0.98], ["23433.9", 0.84]],
            "FORUSA | kWh",
        )
        self.assertEqual(selected.value, Decimal("23433.9"))

    def test_mechanical_meter_appends_detected_red_tenths_digit(self):
        import numpy as np

        image = np.zeros((400, 600, 3), dtype=np.uint8)
        image[80:210, 365:460] = (0, 0, 255)
        result = [
            ([[100, 100], [400, 100], [400, 180], [100, 180]], "327748", 0.98),
        ]

        class FakeEngine:
            def __call__(self, _image, **_kwargs):
                return [["9", 0.80]], None

        selected = detect_red_decimal(
            image,
            result,
            OCRResult(Decimal("327748"), "327748", 0.98),
            FakeEngine(),
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected.value, Decimal("327748.9"))
        self.assertIn("DÍGITO ROJO: 9", selected.raw_text)

    def test_regular_meter_does_not_invent_red_decimal(self):
        import numpy as np

        image = np.zeros((400, 600, 3), dtype=np.uint8)
        result = [
            ([[100, 100], [400, 100], [400, 180], [100, 180]], "327748", 0.98),
        ]

        class FakeEngine:
            def __call__(self, _image, **_kwargs):
                return [["9", 0.99]], None

        selected = detect_red_decimal(
            image,
            result,
            OCRResult(Decimal("327748"), "327748", 0.98),
            FakeEngine(),
        )
        self.assertIsNone(selected)

    def test_contour_locator_finds_rectangular_display_without_text_anchor(self):
        import cv2
        import numpy as np

        image = np.full((500, 800, 3), 235, dtype=np.uint8)
        cv2.rectangle(image, (180, 150), (620, 270), (35, 35, 35), 8)
        cv2.rectangle(image, (190, 160), (610, 260), (150, 165, 145), -1)
        cv2.putText(image, "123456.7", (215, 230), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (25, 25, 25), 4)

        regions = find_display_regions(image, full_ocr=[])

        self.assertTrue(regions)
        self.assertTrue(any(region.label.startswith("contorno") for region in regions))

    def test_display_variants_include_contrast_threshold_inverse_and_reflection_reduction(self):
        import numpy as np

        display = np.full((80, 300, 3), 180, dtype=np.uint8)
        names = {name for name, _image in generate_display_variants(display)}

        self.assertTrue({"gris", "clahe", "sin-reflejo", "adaptativo", "otsu"}.issubset(names))
        self.assertIn("adaptativo-invertido", names)
        self.assertIn("otsu-invertido", names)

    def test_consensus_preserves_decimal_seen_by_one_trusted_variant(self):
        candidates = [
            OCRCandidate(Decimal("1575192"), 0.99, "rapidocr", "clahe"),
            OCRCandidate(Decimal("1575192"), 0.98, "rapidocr", "otsu"),
            OCRCandidate(Decimal("157519.2"), 0.94, "rapidocr-deteccion", "gris"),
        ]

        selected = choose_consistent_candidate(candidates, previous_value=Decimal("150000"))

        self.assertEqual(selected.value, Decimal("157519.2"))

    def test_consensus_rejects_value_that_does_not_exceed_previous_reading(self):
        candidates = [
            OCRCandidate(Decimal("999"), 0.99, "rapidocr", "gris"),
            OCRCandidate(Decimal("999"), 0.98, "rapidocr", "clahe"),
        ]

        selected = choose_consistent_candidate(candidates, previous_value=Decimal("1000"))

        self.assertIsNone(selected.value)

    @patch("readings.services.ocr.read_meter_cloudflare")
    @patch("readings.services.ocr.read_meter_local")
    def test_cloudflare_is_only_used_after_local_ocr_fails(self, local_mock, cloudflare_mock):
        import numpy as np

        image = np.zeros((50, 100, 3), dtype=np.uint8)
        local_mock.return_value = (OCRResult(None, "sin consenso", None), [], image)
        cloudflare_mock.return_value = OCRResult(
            Decimal("1234.5"), "CLOUDFLARE: visor reconocido", 0.91, "cloudflare"
        )

        selected = read_meter("foto.jpg", previous_value=Decimal("1200"))

        self.assertEqual(selected.value, Decimal("1234.5"))
        cloudflare_mock.assert_called_once()

    @patch("readings.services.ocr.read_meter_cloudflare")
    @patch("readings.services.ocr.read_meter_local")
    def test_local_result_prevents_external_request(self, local_mock, cloudflare_mock):
        local_mock.return_value = (
            OCRResult(Decimal("1234.5"), "LOCAL", 0.95),
            [],
            None,
        )

        selected = read_meter("foto.jpg", previous_value=Decimal("1200"))

        self.assertEqual(selected.source, "local")
        cloudflare_mock.assert_not_called()

    def test_cloudflare_response_is_parsed_and_validated(self):
        import json
        import os
        import numpy as np

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "success": True,
                    "result": {"result": {"answer": "170269.6"}},
                }).encode("utf-8")

        image = np.zeros((80, 300, 3), dtype=np.uint8)
        environment = {
            "CLOUDFLARE_ACCOUNT_ID": "cuenta-prueba",
            "CLOUDFLARE_API_TOKEN": "token-prueba",
            "CLOUDFLARE_VISION_MODEL": "@cf/moondream/moondream3.1-9B-A2B",
        }
        with patch.dict(os.environ, environment), patch(
            "readings.services.ocr.urllib.request.urlopen", return_value=FakeResponse()
        ) as urlopen_mock:
            selected = read_meter_cloudflare(image, previous_value=Decimal("160000"))

        self.assertEqual(selected.value, Decimal("170269.6"))
        self.assertEqual(selected.source, "cloudflare")
        request = urlopen_mock.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertTrue(payload["image"].startswith("data:image/jpeg;base64,"))

    def test_cloudflare_chat_model_embeds_image_in_user_message(self):
        import json
        import os
        import numpy as np

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "success": True,
                    "result": {"choices": [{"message": {
                        "content": '{"reading":"170269.6","confidence":0.95}'
                    }}]},
                }).encode("utf-8")

        image = np.zeros((80, 300, 3), dtype=np.uint8)
        environment = {
            "CLOUDFLARE_ACCOUNT_ID": "cuenta-prueba",
            "CLOUDFLARE_API_TOKEN": "token-prueba",
            "CLOUDFLARE_VISION_MODEL": "@cf/google/gemma-4-26b-a4b-it",
        }
        with patch.dict(os.environ, environment), patch(
            "readings.services.ocr.urllib.request.urlopen", return_value=FakeResponse()
        ) as urlopen_mock:
            selected = read_meter_cloudflare(image)

        self.assertEqual(selected.value, Decimal("170269.6"))
        request = urlopen_mock.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        user_content = payload["messages"][1]["content"]
        self.assertEqual(user_content[0]["type"], "text")
        self.assertEqual(user_content[1]["type"], "image_url")
        self.assertTrue(user_content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertNotIn("image", payload)
        self.assertEqual(payload["max_completion_tokens"], 400)
        self.assertNotIn("max_tokens", payload)


class AuthorizedNodesTests(TestCase):
    def test_authorized_list_has_33_unique_nodes(self):
        names = [normalize(item["name"]) for item in AUTHORIZED_NODES]
        self.assertEqual(len(names), 33)
        self.assertEqual(len(set(names)), 33)

    def test_excel_helpers_handle_operational_values(self):
        self.assertEqual(parse_day("02 de cada Mes"), 2)
        self.assertEqual(parse_reading("170269,6"), Decimal("170269.6"))
        self.assertIsNone(parse_reading("PENDIENTE"))

    def test_annual_grid_only_shows_authorized_nodes(self):
        authorized = AUTHORIZED_NODES[0]
        Node.objects.create(code="SUM-1081759", name=authorized["name"], location=authorized["location"])
        Node.objects.create(code="NO-AUTORIZADO", name="Higuereta")
        user = get_user_model().objects.create_user(username="visor", password="prueba-segura")
        self.client.force_login(user)
        response = self.client.get(reverse("readings:annual_grid"))
        self.assertContains(response, "200 Millas")
        self.assertNotContains(response, "Higuereta")

    def test_annual_grid_accepts_a_valid_year_and_rejects_an_invalid_one(self):
        user = get_user_model().objects.create_user(username="visor_anual", password="prueba-segura")
        self.client.force_login(user)

        response = self.client.get(reverse("readings:annual_grid"), {"year": "2027"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["year"], 2027)

        response = self.client.get(reverse("readings:annual_grid"), {"year": "texto"})
        self.assertEqual(response.status_code, 400)


class NotificationTests(TestCase):
    today = date(2026, 8, 17)

    def create_node(self, code, reading_day):
        return Node.objects.create(code=code, name=code, reading_day=reading_day, active=True)

    def add_reading(self, node, reading_date):
        schedule = ReadingSchedule.objects.create(
            node=node, due_date=reading_date, status=ReadingSchedule.Status.COMPLETED
        )
        return Reading.objects.create(
            schedule=schedule,
            reading_date=reading_date,
            detected_value=100,
            confirmed_value=100,
            status=Reading.Status.CONFIRMED,
        )

    def test_monthly_notification_starts_three_days_before(self):
        node = self.create_node("MENSUAL", 19)
        item = get_reading_notifications(self.today)[0]
        self.assertEqual(item.node, node)
        self.assertEqual(item.kind, "MONTHLY")
        self.assertEqual(item.days_until, 2)

    def test_monthly_notification_is_hidden_before_three_day_window(self):
        node = self.create_node("AUN-NO", 20)
        # No early August alert when July's monthly reading and follow-up are complete.
        self.add_reading(node, date(2026, 7, 20))
        follow_up = self.add_reading(node, date(2026, 7, 30))
        follow_up.schedule.notes = "Seguimiento de 10 días"
        follow_up.schedule.save(update_fields=["notes"])
        self.assertEqual(get_reading_notifications(self.today), [])

    def test_follow_up_starts_one_day_before_ten_days(self):
        node = self.create_node("SEGUIMIENTO", 2)
        self.add_reading(node, date(2026, 8, 8))
        item = get_reading_notifications(self.today)[0]
        self.assertEqual(item.kind, "FOLLOW_UP")
        self.assertEqual(item.due_date, date(2026, 8, 18))
        self.assertEqual(item.days_until, 1)

    def test_overdue_follow_up_remains_visible(self):
        node = self.create_node("ATRASADA", 2)
        self.add_reading(node, date(2026, 8, 5))
        item = get_reading_notifications(self.today)[0]
        self.assertTrue(item.is_overdue)
        self.assertEqual(item.days_until, -2)


class CalendarTests(TestCase):
    today = date(2026, 8, 17)

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="calendario", password="prueba-segura")
        self.node = Node.objects.create(code="CAL-001", name="Zárate", reading_day=20, active=True)

    def add_reading(self, reading_date, value=1234):
        schedule = ReadingSchedule.objects.create(
            node=self.node, due_date=reading_date, status=ReadingSchedule.Status.COMPLETED
        )
        return Reading.objects.create(
            schedule=schedule,
            reading_date=reading_date,
            detected_value=value,
            confirmed_value=value,
            status=Reading.Status.CONFIRMED,
        )

    def test_calendar_marks_three_day_warning_in_orange(self):
        self.node.reading_day = 19
        self.node.save(update_fields=["reading_day"])
        event = get_calendar_events(2026, 8, self.today)[0]
        self.assertEqual(event["date"], "2026-08-19")
        self.assertEqual(event["node_name"], "Zárate")
        self.assertEqual(event["state"], "warning")
        self.assertEqual(event["status_label"], "Faltan 2 días")

    def test_calendar_shows_record_and_follow_up(self):
        self.node.reading_day = 2
        self.node.save(update_fields=["reading_day"])
        self.add_reading(date(2026, 8, 8), 9876)
        events = get_calendar_events(2026, 8, self.today)
        record = next(event for event in events if event["type"] == "record")
        task = next(event for event in events if event["type"] == "task")
        self.assertEqual(record["state"], "completed")
        self.assertEqual(record["value"], "9876")
        self.assertEqual(task["date"], "2026-08-18")
        self.assertEqual(task["kind_label"], "Seguimiento de 10 días")
        self.assertEqual(task["state"], "warning")

    def test_follow_up_only_turns_orange_one_day_before(self):
        self.node.reading_day = 2
        self.node.save(update_fields=["reading_day"])
        self.add_reading(date(2026, 8, 8), 9876)
        two_days_before = get_calendar_events(2026, 8, date(2026, 8, 16))
        one_day_before = get_calendar_events(2026, 8, date(2026, 8, 17))
        self.assertEqual(next(event for event in two_days_before if event["type"] == "task")["state"], "planned")
        self.assertEqual(next(event for event in one_day_before if event["type"] == "task")["state"], "warning")

    def test_calendar_endpoint_requires_login_and_returns_events(self):
        url = reverse("readings:calendar_events")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.user)
        response = self.client.get(url, {"year": 2026, "month": 8})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["events"][0]["node_name"], "Zárate")

    def test_grid_contains_calendar_button_and_dialog(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("readings:grid"))
        self.assertContains(response, 'id="calendar-trigger"')
        self.assertContains(response, 'id="calendar-modal"')

    def test_late_monthly_reading_can_create_follow_up_in_next_month(self):
        self.node.reading_day = 15
        self.node.save(update_fields=["reading_day"])
        self.add_reading(date(2026, 8, 25), 2500)

        september = get_calendar_events(2026, 9, date(2026, 9, 1))
        follow_up = next(
            event for event in september
            if event["type"] == "task" and event["kind_label"] == "Seguimiento de 10 días"
        )
        monthly = next(
            event for event in september
            if event["type"] == "task" and event["kind_label"] == "Lectura mensual"
        )
        self.assertEqual(follow_up["date"], "2026-09-04")
        self.assertEqual(monthly["date"], "2026-09-15")
        self.assertEqual(get_node_obligation(self.node, date(2026, 9, 3)), (date(2026, 9, 4), "FOLLOW_UP"))

    def test_completed_follow_up_does_not_create_a_second_follow_up(self):
        self.node.reading_day = 15
        self.node.save(update_fields=["reading_day"])
        self.add_reading(date(2026, 8, 25), 2500)
        follow_up_schedule = ReadingSchedule.objects.create(
            node=self.node,
            due_date=date(2026, 9, 4),
            status=ReadingSchedule.Status.COMPLETED,
            notes="Seguimiento de 10 días",
        )
        Reading.objects.create(
            schedule=follow_up_schedule,
            reading_date=date(2026, 9, 6),
            detected_value=2600,
            confirmed_value=2600,
            status=Reading.Status.CONFIRMED,
        )

        september = get_calendar_events(2026, 9, date(2026, 9, 6))
        pending_follow_ups = [
            event for event in september
            if event["type"] == "task" and event["kind_label"] == "Seguimiento de 10 días"
        ]
        self.assertEqual(pending_follow_ups, [])
        self.assertTrue(any(event["kind_label"] == "Seguimiento registrado" for event in september))
        self.assertEqual(get_node_obligation(self.node, date(2026, 9, 6)), (date(2026, 9, 15), "MONTHLY"))

    def test_calendar_stops_follow_up_overdue_count_when_new_monthly_window_starts(self):
        self.node.reading_day = 3
        self.node.save(update_fields=["reading_day"])
        self.add_reading(date(2026, 8, 8), 3000)

        before_cutoff = get_calendar_events(2026, 8, date(2026, 8, 31))
        active = next(event for event in before_cutoff if event["type"] == "task")
        self.assertEqual(active["date"], "2026-08-18")
        self.assertEqual(active["state"], "danger")
        self.assertEqual(active["status_label"], "Seguimiento atrasado 13 días")

        after_cutoff = get_calendar_events(2026, 8, date(2026, 9, 1))
        closed = next(event for event in after_cutoff if event["type"] == "task")
        self.assertEqual(closed["state"], "closed")
        self.assertEqual(
            closed["status_label"],
            "Seguimiento no registrado · ciclo cerrado por nueva lectura mensual",
        )

    def test_calendar_closes_missing_monthly_reading_when_next_cycle_starts(self):
        self.node.reading_day = 20
        self.node.save(update_fields=["reading_day"])

        still_active = get_calendar_events(2026, 7, date(2026, 8, 17))
        overdue = next(event for event in still_active if event["type"] == "task")
        self.assertEqual(overdue["date"], "2026-07-20")
        self.assertEqual(overdue["state"], "danger")

        next_cycle = get_calendar_events(2026, 7, date(2026, 8, 18))
        closed = next(event for event in next_cycle if event["type"] == "task")
        self.assertEqual(closed["state"], "closed")
        self.assertEqual(
            closed["status_label"],
            "Lectura no registrada · ciclo cerrado por nueva lectura mensual",
        )


class ManagementStatusLabelTests(TestCase):
    today = date(2026, 8, 18)

    def create_schedule(self, due_date, notes="Lectura mensual"):
        node = Node.objects.create(code=f"EST-{due_date.day}-{len(notes)}", name=f"Nodo {due_date}")
        return ReadingSchedule.objects.create(node=node, due_date=due_date, notes=notes)

    def test_monthly_label_shows_days_remaining_today_and_overdue(self):
        upcoming = self.create_schedule(date(2026, 8, 20))
        today = self.create_schedule(date(2026, 8, 18))
        overdue = self.create_schedule(date(2026, 8, 17))
        self.assertEqual(
            upcoming.management_status_label_for(self.today),
            "Lectura: faltan 2 días",
        )
        self.assertEqual(today.management_status_label_for(self.today), "Lectura para hoy")
        self.assertEqual(overdue.management_status_label_for(self.today), "Lectura atrasada 1 día")

    def test_follow_up_label_uses_follow_up_wording(self):
        schedule = self.create_schedule(date(2026, 8, 19), "Seguimiento de 10 días")
        self.assertEqual(
            schedule.management_status_label_for(self.today),
            "Seguimiento: falta 1 día",
        )


class TelegramConversationTests(TestCase):
    def test_node_search_ignores_accents_and_accepts_typing_errors(self):
        choices = [(1, "Hipolito Unanue", "SUM-626339"), (2, "Pachacamac", "SUM-745883")]
        self.assertEqual(normalize_node_name(" Hipólito  Unánue "), "hipolito unanue")
        self.assertEqual(find_best_node_name("hipolto unanue", choices)[0], 1)

    def test_unknown_node_is_not_guessed(self):
        choices = [(1, "Hipolito Unanue", "SUM-626339")]
        self.assertIsNone(find_best_node_name("xyz", choices))

    def test_reading_date_accepts_today_or_day_month_year(self):
        today = date(2026, 8, 17)
        self.assertEqual(parse_reading_date("hoy", today), today)
        self.assertEqual(parse_reading_date("03/08/2026", today), date(2026, 8, 3))

    def test_reading_date_rejects_other_text_and_invalid_dates(self):
        today = date(2026, 8, 17)
        self.assertIsNone(parse_reading_date("mañana", today))
        self.assertIsNone(parse_reading_date("31/02/2026", today))
        self.assertIsNone(parse_reading_date("2026-08-17", today))

    def test_manual_reading_accepts_decimal_point_or_comma(self):
        self.assertEqual(parse_reading_value("97072.94"), Decimal("97072.94"))
        self.assertEqual(parse_reading_value("170269,6"), Decimal("170269.6"))

    def test_manual_reading_rejects_text_negative_and_excess_decimals(self):
        self.assertIsNone(parse_reading_value("lectura 123"))
        self.assertIsNone(parse_reading_value("-123"))
        self.assertIsNone(parse_reading_value("123.4567"))

    def test_active_reading_flow_pauses_notifications_for_that_chat(self):
        now = timezone.make_aware(datetime(2026, 8, 17, 16, 0))
        data = {
            STATE: WAIT_PHOTO,
            ACTIVE_CHAT_ID: 8463146362,
            ACTIVE_UNTIL: now + timedelta(minutes=30),
        }
        self.assertTrue(is_conversation_active(data, now))

    def test_abandoned_flow_expires_and_does_not_pause_forever(self):
        now = timezone.make_aware(datetime(2026, 8, 17, 16, 0))
        data = {
            STATE: WAIT_PHOTO,
            ACTIVE_CHAT_ID: 8463146362,
            ACTIVE_UNTIL: now - timedelta(seconds=1),
        }
        self.assertFalse(is_conversation_active(data, now))


class ReminderDeliveryTests(TestCase):
    def setUp(self):
        self.node = Node.objects.create(
            code="AVISO", name="Nodo Aviso", reading_day=19, active=True,
            telegram_chat_id=8463146362, supply_number="12345", provider="PLUZ",
        )
        self.now = timezone.make_aware(datetime(2026, 8, 17, 10, 0))

    def test_reminder_contains_operational_data(self):
        job = prepare_reminder_jobs(self.now)[0]
        text = reminder_text(job["item"])
        self.assertIn("WI-NET | RECORDATORIO", text)
        self.assertIn("Nodo Aviso", text)
        self.assertIn("12345", text)
        self.assertIn("LECTURA MENSUAL PRÓXIMA", text)
        self.assertIn("Tipo: Día de lectura mensual", text)

    def test_overdue_follow_up_is_clearly_distinguished(self):
        item = ReadingNotification(
            node=self.node,
            due_date=date(2026, 8, 15),
            kind="FOLLOW_UP",
            days_until=-2,
        )
        text = reminder_text(item)
        self.assertIn("SEGUIMIENTO DE 10 DÍAS ATRASADO", text)
        self.assertIn("Tipo: Seguimiento de lectura (10 días)", text)

    def test_does_not_repeat_before_five_hours(self):
        job = prepare_reminder_jobs(self.now)[0]
        log = ReminderLog.objects.create(
            schedule=job["schedule"], sent_on=self.now.date(), chat_id=self.node.telegram_chat_id
        )
        ReminderLog.objects.filter(pk=log.pk).update(sent_at=self.now - timedelta(hours=4, minutes=59))
        self.assertEqual(prepare_reminder_jobs(self.now), [])

    def test_repeats_after_five_hours(self):
        job = prepare_reminder_jobs(self.now)[0]
        log = ReminderLog.objects.create(
            schedule=job["schedule"], sent_on=self.now.date(), chat_id=self.node.telegram_chat_id
        )
        ReminderLog.objects.filter(pk=log.pk).update(sent_at=self.now - timedelta(hours=5))
        self.assertEqual(len(prepare_reminder_jobs(self.now)), 1)

    def test_force_resends_before_five_hours(self):
        job = prepare_reminder_jobs(self.now)[0]
        log = ReminderLog.objects.create(
            schedule=job["schedule"], sent_on=self.now.date(), chat_id=self.node.telegram_chat_id
        )
        ReminderLog.objects.filter(pk=log.pk).update(sent_at=self.now - timedelta(minutes=10))
        self.assertEqual(len(prepare_reminder_jobs(self.now, force=True)), 1)
