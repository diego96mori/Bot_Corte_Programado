from readings.test_access_helpers import create_interface_user
from datetime import date
from decimal import Decimal
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from readings.models import Node, Reading, ReadingSchedule
from readings.management.commands import run_telegram_bot as bot
from readings.services.ocr import OCRResult
from readings.services.ocr_learning import verify_for_learning, build_profile, review_token
from readings.services.notifications import get_reading_notifications
from readings.services.calendar import get_calendar_events
from readings.services.annual_grid import annual_row


class AuditFixTests(TestCase):
    def setUp(self):
        self.user = create_interface_user(username='reviewer')
        self.client.force_login(self.user)
        self.node = Node.objects.create(code='NEW', name='Nodo nuevo fuera de lista', reading_day=11, telegram_chat_id=1)
        self.schedule = ReadingSchedule.objects.create(node=self.node, due_date=date(2026, 9, 11), notes='Lectura mensual')
        self.operator = SimpleNamespace(id=1, username='test', full_name='Test')
        clock = patch('django.utils.timezone.localdate', return_value=date(2026, 9, 11))
        clock.start()
        self.addCleanup(clock.stop)
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)

    def record(self):
        return Reading.objects.create(schedule=self.schedule, reading_date=date(2026,9,11), confirmed_value=100, status='CONFIRMED')

    def test_cancelled_schedule_cannot_start_or_finish_telegram(self):
        draft, error = async_to_sync(bot.create_manual_reading)(self.node.pk, Decimal('100'), self.operator, 1)
        self.assertIsNone(error)
        self.schedule.status = 'CANCELLED'
        self.schedule.save()
        with self.assertRaises(ValidationError):
            async_to_sync(bot.confirm_reading)(draft.pk, 1, date(2026,9,11))
        new, error = async_to_sync(bot.create_manual_reading)(self.node.pk, Decimal('100'), self.operator, 1)
        self.assertIsNone(new)
        self.assertIn('anulada', error)
        with patch.object(bot, 'read_meter') as ocr:
            photo, error = async_to_sync(bot.create_reading)(self.node.pk, b'photo', 'test.jpg', self.operator, 1)
            self.assertIsNone(photo)
            ocr.assert_not_called()
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status, 'CANCELLED')
        self.assertFalse(Reading.objects.filter(status='CONFIRMED').exists())
        self.assertEqual(get_reading_notifications(date(2026,9,11)), [])

    def test_grid_prefers_confirmed_over_later_cancelled_attempt(self):
        confirmed = self.record()
        Reading.objects.create(schedule=self.schedule, status='CANCELLED', detected_value=999)
        response = self.client.get(reverse('readings:grid'))
        row = next(s for s in response.context['schedules'] if s.pk == self.schedule.pk)
        self.assertEqual(row.latest_readings[0].pk, confirmed.pk)

    def test_new_active_node_appears_in_annual_grid(self):
        self.assertContains(self.client.get(reverse('readings:annual_grid')), self.node.name)
        self.node.active = False
        self.node.save()
        self.assertNotContains(self.client.get(reverse('readings:annual_grid')), self.node.name)

    def test_photo_requires_login_and_existing_reference_even_with_debug(self):
        reading = self.record()
        reading.photo.save('test.jpg', ContentFile(b'test image bytes'))
        url = reading.photo.url
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'test image bytes')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(self.client.get('/media/not-referenced.jpg').status_code, 404)

    def test_web_photo_verified_action_builds_local_profile_and_never_uses_cloud(self):
        reading = self.record()
        reading.photo.save('test.jpg', ContentFile(b'photo'))
        result = OCRResult(Decimal('100'), 'local', .9, 'local', details={
            'candidates': [{'value':'100','method':'rapidocr','variant':'visor-0:gris','confidence':.9}],
        })
        with patch('readings.services.ocr.read_meter', return_value=result) as ocr:
            verify_for_learning(reading.pk)
            self.assertFalse(ocr.call_args.kwargs['allow_cloudflare'])
        self.assertEqual(build_profile(self.node)['examples'], 1)
        reading.refresh_from_db()
        reading.ocr_learning_excluded = True
        reading.save()
        with patch('readings.services.ocr.read_meter') as ocr:
            with self.assertRaises(ValidationError):
                verify_for_learning(reading.pk)
            ocr.assert_not_called()
        self.assertEqual(build_profile(self.node)['examples'], 0)

    def test_unavailable_followup_has_no_alert_and_consistent_projection(self):
        self.schedule.due_date = date(2026,8,11)
        self.schedule.save()
        reading = self.record()
        reading.reading_date = date(2026,8,31)
        reading.save()
        today = date(2026,9,7)
        self.assertEqual(get_reading_notifications(today), [])
        event = next(e for e in get_calendar_events(2026,9,today) if e['kind_label']=='Seguimiento de 10 días')
        self.assertEqual(event['state'], 'closed')
        self.assertIn('sin ventana', event['status_label'])
        row = annual_row(self.node,[reading],[self.schedule],2026,today)
        self.assertIn('Sin ventana', row['months'][7][1]['state'])

    def test_learning_without_candidates_leaves_photo_unverified(self):
        reading = self.record()
        reading.photo.save('test.jpg', ContentFile(b'photo'))
        with patch('readings.services.ocr.read_meter', return_value=OCRResult(None, 'no candidates', None)):
            with self.assertRaises(ValidationError):
                verify_for_learning(reading.pk)
        reading.refresh_from_db()
        self.assertFalse(reading.ocr_learning_verified)
        self.assertEqual(reading.ocr_attempts, [])

    def test_review_rejects_changed_value_photo_and_missing_token(self):
        reading=self.record()
        reading.photo.save('review.jpg',ContentFile(b'original photo'))
        token=review_token(reading)
        Reading.objects.filter(pk=reading.pk).update(confirmed_value=200)
        with patch('readings.services.ocr.read_meter') as ocr:
            with self.assertRaisesMessage(ValidationError,'cambiaron'):
                verify_for_learning(reading.pk,expected_token=token)
            ocr.assert_not_called()
        Reading.objects.filter(pk=reading.pk).update(confirmed_value=100)
        with reading.photo.storage.open(reading.photo.name,'wb') as photo:
            photo.write(b'changed photo')
        with self.assertRaisesMessage(ValidationError,'cambiaron'):
            verify_for_learning(reading.pk,expected_token=token)
        with self.assertRaises(ValidationError):
            verify_for_learning(reading.pk,expected_token='')
        reading.refresh_from_db()
        self.assertFalse(reading.ocr_learning_verified)
