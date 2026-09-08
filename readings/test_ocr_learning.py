import json
import os
import tempfile
from types import SimpleNamespace
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from asgiref.sync import async_to_sync

import numpy as np
from django.test import TestCase, SimpleTestCase
from django.utils import timezone

from readings.models import Node, Reading, ReadingSchedule
from readings.services.ocr import (
    OCRCandidate, OCRResult, DisplayRegion, choose_consistent_candidate,
    read_meter, read_meter_cloudflare, recognize_seven_segment,
)
from readings.services.ocr_learning import build_profile, meter_scope


class LearningTests(TestCase):
    def setUp(self):
        self.node = Node.objects.create(code="TEST", name="Test", meter_number="A")
        self.schedule = ReadingSchedule.objects.create(node=self.node, due_date=date(2026, 9, 7))

    def example(self, fingerprint, status=Reading.Status.CONFIRMED, value="123.4"):
        return Reading.objects.create(
            schedule=self.schedule, photo="example.jpg", confirmed_value=Decimal(value),
            confirmed_at=timezone.now(), status=status,
            ocr_learning_verified=True,
            ocr_attempts=[{"scope": meter_scope(self.node), "sha256": fingerprint,
                           "candidates": [{"method": "rapidocr", "variant": "visor-1:gris", "value": "123.4"}]}],
        )

    def test_only_confirmed_examples_count_and_duplicate_photos_vote_once(self):
        self.example("a")
        self.example("a")
        self.example("b", Reading.Status.CANCELLED)
        profile = build_profile(self.node)
        self.assertEqual(profile["examples"], 1)
        self.assertEqual(profile["techniques"]["rapidocr:gris"], [1, 1])

    def test_manual_correction_teaches_failure_without_overwriting_prediction(self):
        row = self.example("a", value="123.5")
        self.assertEqual(build_profile(self.node)["techniques"]["rapidocr:gris"], [0, 1])
        row.refresh_from_db()
        self.assertEqual(row.ocr_attempts[0]["candidates"][0]["value"], "123.4")

    def test_meter_change_or_reset_excludes_old_examples(self):
        self.example("a")
        self.node.meter_number = "B"
        self.assertEqual(build_profile(self.node)["examples"], 0)
        self.node.meter_number = "A"
        self.node.ocr_learning_generation += 1
        self.assertEqual(build_profile(self.node)["examples"], 0)

    def test_unreviewed_historical_label_does_not_train(self):
        row = self.example("a")
        row.ocr_learning_verified = False
        row.save()
        self.assertEqual(build_profile(self.node)["examples"], 0)

    def test_excluded_historical_photo_never_teaches_even_if_marked_verified(self):
        row = self.example("old-photo")
        row.ocr_learning_excluded = True
        row.save()
        self.assertEqual(build_profile(self.node)["examples"], 0)
        self.example("new-photo")
        self.assertEqual(build_profile(self.node)["examples"], 1)

    def test_evaluation_cannot_learn_current_or_future_labels(self):
        row = self.example("a")
        self.assertEqual(build_profile(self.node, before=row.confirmed_at)["examples"], 0)

    def test_display_format_can_be_configured_per_meter_without_affecting_others(self):
        with patch.dict(os.environ, {"OCR_DISPLAY_FORMATS": '{"TEST":"6+1"}'}):
            self.assertEqual(build_profile(self.node)["display_format"], "6+1")
            other = Node.objects.create(code="OTHER", name="Other", meter_number="B")
            self.assertNotIn("display_format", build_profile(other))

    def test_bot_keeps_failed_photo_and_candidates_for_manual_confirmation(self):
        from readings.management.commands import run_telegram_bot as bot
        self.node.reading_day = timezone.localdate().day
        self.node.telegram_chat_id = 99
        self.node.save()
        result = OCRResult(None, "fallo", None, "manual", details={"version": "2.0", "candidates": [
            {"method": "rapidocr", "variant": "visor-0:gris", "value": "123.4", "confidence": .8},
        ]})
        user = SimpleNamespace(id=1, username="test", full_name="Test")
        with tempfile.TemporaryDirectory() as folder, self.settings(MEDIA_ROOT=folder), patch.object(bot, "read_meter", return_value=result):
            row, error = async_to_sync(bot.create_reading)(self.node.pk, b"photo-bytes", "test.jpg", user, 99)
            self.assertIsNone(error)
            row.refresh_from_db()
            self.assertTrue(row.photo.storage.exists(row.photo.name))
            self.assertEqual(len(row.ocr_attempts[0]["sha256"]), 64)
            self.assertEqual(build_profile(self.node)["examples"], 0)
            async_to_sync(bot.confirm_reading)(row.pk, user.id, timezone.localdate(), Decimal("123.5"))
            self.assertEqual(build_profile(self.node)["techniques"]["rapidocr:gris"], [0, 1])


class OCRSafetyTests(SimpleTestCase):
    def test_configured_seven_segment_displays_preserve_decimal_and_leading_zeroes(self):
        for text in ("123195.5", "070130.4", "055892.9"):
            digits = text.replace(".", "")
            binary = np.zeros((80, 350), np.uint8)
            binary[0, :] = 255
            binary[-1, :] = 255
            binary[:, 0] = 255
            binary[:, -1] = 255
            decoded = [(digit, .95) for digit in digits]
            with patch("readings.services.ocr._segment_state", side_effect=decoded), patch(
                "readings.services.ocr._decimal_geometry", return_value=(6, (0, 0, 2, 2))
            ):
                candidate = recognize_seven_segment(binary, display_format="6+1")
            self.assertIsNotNone(candidate)
            self.assertEqual(candidate.raw_text, text)
            self.assertEqual(candidate.value, Decimal(text))
            self.assertTrue(candidate.decimal_geometry)

    def test_raw_display_text_drives_digit_count_and_keeps_leading_zeroes(self):
        candidates = [
            OCRCandidate(Decimal("70130.4"), .82, "rapidocr", "visor-0:gris", "070130.4"),
            OCRCandidate(Decimal("70130.4"), .81, "rapidocr", "visor-0:otsu", "070130.4"),
            OCRCandidate(Decimal("999999"), .99, "rapidocr", "visor-1:gris", "999999"),
            OCRCandidate(Decimal("999999"), .98, "rapidocr", "visor-1:otsu", "999999"),
        ]
        selected = choose_consistent_candidate(candidates)
        self.assertEqual(selected.value, Decimal("70130.4"))

    def test_geometric_decimal_reconciles_seven_segment_and_rapidocr(self):
        candidates = [
            OCRCandidate(
                Decimal("701304"), .92, "siete-segmentos", "visor-0:otsu",
                "701304", decimal_places=1, decimal_geometry=True,
            ),
            OCRCandidate(Decimal("70130.4"), .90, "rapidocr", "visor-0:gris", "70130.4"),
        ]
        selected = choose_consistent_candidate(candidates)
        self.assertEqual(selected.value, Decimal("70130.4"))
        self.assertTrue(all(item["accepted"] for item in selected.details["candidate_evaluation"]))

    def test_rejection_diagnostics_include_exact_reason_and_original_text(self):
        selected = choose_consistent_candidate([
            OCRCandidate(Decimal("999"), .99, "rapidocr", "gris", "000999"),
            OCRCandidate(Decimal("999"), .98, "rapidocr", "otsu", "000999"),
        ], previous_value=Decimal("1000"))
        self.assertIsNone(selected.value)
        self.assertEqual(selected.details["candidate_evaluation"][0]["raw_text"], "000999")
        self.assertIn("menor", selected.details["candidate_evaluation"][0]["reason"])

    def test_failed_techniques_are_filtered_but_new_ones_remain_available(self):
        candidates = [OCRCandidate(Decimal("123"), .98, "rapidocr", "visor-0:gris"),
                      OCRCandidate(Decimal("123"), .98, "rapidocr", "visor-0:otsu")]
        self.assertEqual(choose_consistent_candidate(candidates).value, Decimal("123"))
        self.assertIsNone(choose_consistent_candidate(candidates, profile={"techniques": {"rapidocr:gris": [0, 3]}}).value)

    def test_equal_previous_reading_is_allowed(self):
        candidates = [OCRCandidate(Decimal("123"), .98, "rapidocr", name) for name in ("gris", "otsu")]
        self.assertEqual(choose_consistent_candidate(candidates, Decimal("123")).value, Decimal("123"))

    @patch("readings.services.ocr.urllib.request.urlopen")
    def test_free_plan_must_be_explicitly_confirmed(self, request):
        with patch.dict(os.environ, {"CLOUDFLARE_FREE_PLAN_CONFIRMED": "False"}):
            self.assertIsNone(read_meter_cloudflare(np.zeros((40, 100, 3), np.uint8)).value)
        request.assert_not_called()

    @patch("readings.services.ocr.read_meter_cloudflare")
    @patch("readings.services.ocr.read_meter_local")
    def test_disagreement_never_selects_a_guessed_reading(self, local, cloud):
        local.return_value = (OCRResult(Decimal("123"), "LOCAL", .75, details={"candidates": [
            {"method": "rapidocr", "variant": "gris", "value": "123"},
        ]}), [], None)
        cloud.return_value = OCRResult(Decimal("123.4"), "CLOUD", .9, "cloudflare")
        self.assertIsNone(read_meter("x.jpg", profile={"techniques": {"rapidocr:gris": [3, 3]}}).value)

    @patch("readings.services.ocr.read_meter_cloudflare")
    @patch("readings.services.ocr.read_meter_local")
    def test_crop_failure_retries_full_photo_but_quota_failure_does_not(self, local, cloud):
        image = np.zeros((100, 200, 3), np.uint8)
        crop = image[:50]
        local.return_value = (OCRResult(Decimal("123"), "LOCAL", .75, details={"candidates": [
            {"method": "rapidocr", "variant": "gris", "value": "123"},
        ]}), [DisplayRegion(crop, 4, "caja-numerica-del-visor")], image)
        profile = {"techniques": {"rapidocr:gris": [3, 3]}}
        cloud.side_effect = [OCRResult(None, "CLOUDFLARE: lectura insegura", None), OCRResult(Decimal("123"), "ok", .9, "cloudflare")]
        self.assertEqual(read_meter("x.jpg", profile=profile).value, Decimal("123"))
        self.assertEqual(cloud.call_count, 2)
        cloud.reset_mock(side_effect=True)
        cloud.return_value = OCRResult(None, "CLOUDFLARE: servicio no disponible", None)
        read_meter("x.jpg", profile=profile)
        cloud.assert_called_once()

    @patch("readings.services.ocr.read_meter_cloudflare")
    @patch("readings.services.ocr.read_meter_local")
    def test_previous_value_and_display_format_reach_local_and_cloud_crop(self, local, cloud):
        image = np.zeros((100, 200, 3), np.uint8)
        crop = image[:50]
        local.return_value = (OCRResult(None, "LOCAL", None), [DisplayRegion(crop, 3.2, "contorno-perspectiva")], image)
        cloud.return_value = OCRResult(Decimal("123195.5"), "CLOUD", .9, "cloudflare")
        previous = Decimal("123000")

        result = read_meter("x.jpg", previous_value=previous, display_format="6+1")

        self.assertEqual(result.value, Decimal("123195.5"))
        local.assert_called_once_with(
            "x.jpg", previous_value=previous, profile=None, display_format=(6, 1),
        )
        cloud.assert_called_once_with(
            crop, previous_value=previous, display_format=(6, 1),
        )

    @patch("readings.services.ocr.read_meter_cloudflare")
    @patch("readings.services.ocr.read_meter_local")
    def test_evaluation_is_offline(self, local, cloud):
        local.return_value = (OCRResult(None, "LOCAL", None), [], None)
        read_meter("x.jpg", allow_cloudflare=False)
        cloud.assert_not_called()

    @patch("readings.services.ocr.read_meter_cloudflare")
    @patch("readings.services.ocr.read_meter_local")
    def test_unlearned_high_confidence_cannot_bypass_cloudflare(self, local, cloud):
        local.return_value = (OCRResult(Decimal("840205"), "LOCAL", .99), [], None)
        cloud.return_value = OCRResult(Decimal("170269.6"), "CLOUD", .9, "cloudflare")
        result = read_meter("x.jpg", profile={"examples": 0})
        self.assertEqual(result.value, Decimal("170269.6"))
        cloud.assert_called_once()

    def test_cloud_response_rejects_nonfinite_confidence_and_prompt_has_no_history(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self):
                return json.dumps({"success": True, "result": {"reading": "123.4", "confidence": "NaN"}}).encode()
        env = {"CLOUDFLARE_FREE_PLAN_CONFIRMED": "True", "CLOUDFLARE_VISION_MODEL": "@cf/google/gemma-4-26b-a4b-it",
               "CLOUDFLARE_ACCOUNT_ID": "test", "CLOUDFLARE_API_TOKEN": "test"}
        with patch.dict(os.environ, env), patch("readings.services.ocr.urllib.request.urlopen", return_value=Response()) as request:
            result = read_meter_cloudflare(np.zeros((50, 100, 3), np.uint8), Decimal("111.2"))
        self.assertIsNone(result.value)
        self.assertNotIn("111.2", request.call_args.args[0].data.decode())

    def test_truncated_response_cannot_be_used_even_if_it_contains_a_number(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self):
                return json.dumps({"success": True, "result": {"choices": [{
                    "finish_reason": "length", "message": {"content": '{"reading":"123","confidence":1}'},
                }]}}).encode()
        env = {"CLOUDFLARE_FREE_PLAN_CONFIRMED": "True", "CLOUDFLARE_VISION_MODEL": "@cf/google/gemma-4-26b-a4b-it",
               "CLOUDFLARE_ACCOUNT_ID": "test", "CLOUDFLARE_API_TOKEN": "test"}
        with patch.dict(os.environ, env), patch("readings.services.ocr.urllib.request.urlopen", return_value=Response()):
            result = read_meter_cloudflare(np.zeros((50, 100, 3), np.uint8))
        self.assertIsNone(result.value)
        self.assertIn("incompleta", result.raw_text)
