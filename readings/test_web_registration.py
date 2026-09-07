from readings.test_access_helpers import create_interface_user
from datetime import date
from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from readings.models import Node, Reading, ReadingSchedule


class WebRegistrationTests(TestCase):
    def setUp(self):
        self.today = date(2026, 8, 31)
        clock = patch('django.utils.timezone.localdate', side_effect=lambda: self.today)
        clock.start()
        self.addCleanup(clock.stop)
        self.user = create_interface_user(username='operador', password='test-password')
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label='readings', codename='add_reading'))
        self.client.force_login(self.user)
        self.node = Node.objects.create(code='GUA', name='Guardia Peruana', reading_day=2)
        self.url = reverse('readings:web_reading')
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)

    def option(self):
        return self.client.get(self.url, {'node': self.node.pk}).json()['options'][0]['token']

    def post(self, token=None, **extra):
        return self.client.post(self.url, {
            'node': self.node.pk, 'obligation': token or self.option(), 'value': '174306,9', 'reading_date': self.today.isoformat(), **extra,
        })

    def test_authentication_and_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.get(self.url).status_code, 302)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, {}).status_code, 403)
        self.assertEqual(Reading.objects.count(), 0)

    def test_month_boundary_audit_grid_and_green_calendar(self):
        token = self.option()
        self.assertEqual(ReadingSchedule.objects.count(), 0)
        response = self.post(token)
        self.assertEqual(response.status_code, 201, response.content)
        reading = Reading.objects.get()
        self.assertEqual(reading.confirmed_value, Decimal('174306.9'))
        self.assertEqual(reading.reading_date, self.today)
        self.assertEqual(reading.schedule.due_date, date(2026, 9, 2))
        self.assertEqual(reading.schedule.status, 'COMPLETED')
        self.assertEqual(reading.confirmed_by, self.user)
        self.assertEqual(reading.source, 'MANUAL')
        self.assertFalse(reading.ocr_learning_verified)
        self.assertContains(self.client.get(reverse('readings:grid')), 'operador')
        calendar = self.client.get(reverse('readings:calendar_events'), {'year': 2026, 'month': 8}).json()
        self.assertTrue(any(item['state'] == 'completed' and item['node_id'] == self.node.pk for item in calendar['events']))

    def test_consultation_user_cannot_register_or_see_buttons(self):
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='readings', codename='add_reading'))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {}).status_code, 403)
        self.assertNotContains(self.client.get(reverse('readings:grid')), 'data-add-reading>Agregar lectura</button>')

    def test_stale_submission_does_not_turn_monthly_into_follow_up(self):
        token = self.option()
        self.assertEqual(self.post(token).status_code, 201)
        self.assertEqual(self.post(token).status_code, 409)
        self.assertEqual(Reading.objects.count(), 1)
        self.today = date(2026, 9, 10)
        follow = self.option()
        self.assertEqual(self.post(follow, value='174400.125').status_code, 201)
        self.assertEqual(self.post(follow).status_code, 409)
        self.assertEqual(Reading.objects.count(), 2)
        reading = Reading.objects.order_by('id').last()
        self.assertTrue(reading.schedule.is_follow_up)
        self.assertEqual(reading.schedule.due_date, date(2026, 9, 10))
        self.assertEqual(self.client.get(self.url, {'node': self.node.pk}).json()['options'], [])

    def test_no_letters_signs_exponents_or_excess_precision(self):
        token = self.option()
        for value in ['12abc', '-1', '+1', '1e3', 'NaN', 'Infinity', '1.1234', '1234567890123', '1,234.5', '', ' 12', '١٢']:
            with self.subTest(value=value):
                self.assertEqual(self.post(token, value=value).status_code, 400)
        self.assertFalse(Reading.objects.exists())
        self.assertEqual(self.post(token, value='0').status_code, 201)

    def test_disabled_cancelled_and_wrong_node_are_rejected(self):
        token = self.option()
        other = Node.objects.create(code='OTHER', name='Otro', reading_day=2)
        self.assertEqual(self.post(token, node=other.pk).status_code, 409)
        self.node.active = False
        self.node.save()
        self.assertEqual(self.post(token).status_code, 409)
        self.node.active = True
        self.node.save()
        ReadingSchedule.objects.create(node=self.node, due_date=date(2026, 9, 2), status='CANCELLED', notes='Lectura mensual')
        self.assertEqual(self.client.get(self.url, {'node': self.node.pk}).json()['options'], [])
        self.assertEqual(self.post(token).status_code, 409)
        self.assertFalse(Reading.objects.exists())

    def test_closed_cycle_and_forged_token_are_rejected(self):
        token = self.option()
        self.assertEqual(self.post(token + 'tampered').status_code, 409)
        self.today = date(2026, 9, 30)
        self.assertEqual(self.post(token).status_code, 409)
        self.assertFalse(Reading.objects.exists())
        self.assertFalse(ReadingSchedule.objects.exists())

    def test_optional_photo_is_validated_and_saved_as_evidence(self):
        token = self.option()
        fake = SimpleUploadedFile('fake.jpg', b'not an image', content_type='image/jpeg')
        self.assertEqual(self.post(token, photo=fake).status_code, 400)
        buffer = BytesIO()
        Image.new('RGB', (10, 10), 'white').save(buffer, format='PNG')
        photo = SimpleUploadedFile('meter.png', buffer.getvalue(), content_type='image/png')
        self.assertEqual(self.post(token, photo=photo).status_code, 201)
        reading = Reading.objects.get()
        self.assertTrue(reading.photo.storage.exists(reading.photo.name))
        self.assertFalse(reading.ocr_learning_verified)

    def test_two_entry_points_render_the_shared_dialog(self):
        response = self.client.get(reverse('readings:grid'))
        self.assertContains(response, 'data-add-reading>Agregar lectura</button>', count=2)
        self.assertContains(response, '<dialog id="reading-dialog"', count=1)

    def test_chancay_backdated_capture_keeps_actual_registration_timestamp(self):
        self.node.reading_day = 18
        self.node.save()
        self.today = date(2026, 9, 7)
        response = self.post(reading_date='2026-08-19')
        self.assertEqual(response.status_code, 201, response.content)
        reading = Reading.objects.get()
        self.assertEqual(reading.reading_date, date(2026, 8, 19))
        self.assertEqual(reading.schedule.due_date, date(2026, 8, 18))
        self.assertGreater(reading.created_at.date(), reading.reading_date)
        self.assertContains(self.client.get(reverse('readings:grid')), 'Fecha bot/web')
        option = self.client.get(self.url, {'node': self.node.pk}).json()['options'][0]
        self.assertIn('29/08/2026', option['label'])

    def test_capture_date_rejects_future_closed_cycle_and_invalid_dates(self):
        token = self.option()
        for value, status in [('2026-09-01', 409), ('2026-08-30', 409), ('invalid', 400), ('', 400)]:
            with self.subTest(value=value):
                self.assertEqual(self.post(token, reading_date=value).status_code, status)
        self.assertFalse(Reading.objects.exists())

    def test_follow_up_blocks_early_entry_and_backdated_capture(self):
        self.today = date(2026, 9, 7)
        self.assertEqual(self.post(reading_date='2026-09-02').status_code, 201)
        payload = self.client.get(self.url, {'node': self.node.pk}).json()
        self.assertEqual(payload['options'], [])
        self.assertIn('11/09/2026', payload['message'])
        self.today = date(2026, 9, 11)
        token = self.option()
        self.assertEqual(self.post(token, reading_date='2026-09-01').status_code, 409)
        self.assertEqual(self.post(token, reading_date='2026-09-07').status_code, 409)
        self.assertEqual(self.post(token, reading_date='2026-09-11').status_code, 201)
        follow = Reading.objects.order_by('id').last()
        self.assertEqual(follow.schedule.due_date, date(2026, 9, 12))
        self.assertEqual(follow.reading_date, date(2026, 9, 11))
