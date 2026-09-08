"""Aprendizaje local por medidor; nunca utiliza valores anteriores como predicción."""
from collections import defaultdict
from decimal import Decimal
import json
import os

from readings.models import Reading


def meter_scope(node):
    return f"{node.pk}:{node.meter_number.strip()}:{node.ocr_learning_generation}"


def technique(candidate):
    # El índice del recorte cambia entre fotografías y no identifica una técnica.
    return candidate["method"] + ":" + candidate["variant"].split(":")[-1]


def build_profile(node, before=None):
    readings = Reading.objects.filter(
        schedule__node=node, status=Reading.Status.CONFIRMED,
        confirmed_value__isnull=False, ocr_learning_verified=True, ocr_learning_excluded=False,
    ).exclude(photo="").order_by("-confirmed_at", "-pk")
    if before is not None:
        readings = readings.filter(confirmed_at__lt=before)
    scores = defaultdict(lambda: [0, 0])
    examples = 0
    seen = set()
    for reading in readings[:100]:
        attempts = [a for a in reading.ocr_attempts if a.get("scope") == meter_scope(node)]
        if not attempts:
            continue
        fingerprint = attempts[-1].get("sha256") or reading.photo.name
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        # Una fotografía aporta un voto por técnica, aunque se haya reintentado.
        observed = defaultdict(set)
        for candidate in attempts[-1].get("candidates", []):
            observed[technique(candidate)].add(Decimal(candidate["value"]))
        if not observed:
            continue
        examples += 1
        for key, values in observed.items():
            scores[key][1] += 1
            # Una técnica que también produjo otro número es ambigua.
            scores[key][0] += int(values == {reading.confirmed_value})
    profile = {"scope": meter_scope(node), "examples": examples, "techniques": dict(scores)}
    try:
        configured_formats = json.loads(os.getenv("OCR_DISPLAY_FORMATS", "{}"))
    except (TypeError, json.JSONDecodeError):
        configured_formats = {}
    if isinstance(configured_formats, dict):
        for key in (meter_scope(node), node.code, node.meter_number.strip()):
            if key and key in configured_formats:
                profile["display_format"] = configured_formats[key]
                break
    return profile


def append_attempt(reading, result, node):
    import hashlib
    from django.utils import timezone
    attempt = dict(result.details)
    if reading.photo:
        with reading.photo.open("rb") as photo:
            attempt["sha256"] = hashlib.file_digest(photo, "sha256").hexdigest()
    attempt.update({
        "scope": meter_scope(node), "at": timezone.now().isoformat(),
        "proposed": str(result.value) if result.value is not None else None,
        "source": result.source, "confidence": result.confidence,
        "reason": result.raw_text,
    })
    reading.ocr_attempts = [*reading.ocr_attempts, attempt]


def review_identity(reading):
    import hashlib
    digest = None
    if reading.photo:
        with reading.photo.open("rb") as photo:
            digest = hashlib.file_digest(photo, "sha256").hexdigest()
    return [reading.pk, str(reading.confirmed_value), reading.photo.name, digest,
            meter_scope(reading.schedule.node), reading.status, reading.ocr_learning_excluded]


def review_token(reading):
    from django.core import signing
    return signing.dumps(review_identity(reading), salt="ocr-review")


def verify_for_learning(reading_id, expected_token=None):
    """Called only after an operator verifies the photo against its decimal label."""
    from django.core.exceptions import ValidationError
    from django.db import transaction
    from readings.services.ocr import read_meter

    with transaction.atomic():
        reading = Reading.objects.select_for_update().select_related("schedule__node").get(pk=reading_id)
        if expected_token is not None:
            from django.core import signing
            try:
                identity = signing.loads(expected_token, salt="ocr-review", max_age=3600)
            except signing.BadSignature:
                raise ValidationError("La revisión caducó o no es válida. Abre de nuevo la foto.")
            if identity != review_identity(reading):
                raise ValidationError("La foto o el valor cambiaron. Abre de nuevo la revisión antes de confirmar.")
        if reading.ocr_learning_excluded:
            raise ValidationError("La fotografía histórica está excluida del aprendizaje.")
        if reading.status != Reading.Status.CONFIRMED or reading.confirmed_value is None or not reading.photo:
            raise ValidationError("Se requiere una lectura confirmada con valor y fotografía.")
        # No external calls and no profile: collect independent candidates for this photo.
        result = read_meter(reading.photo.path, allow_cloudflare=False)
        if not result.details.get("candidates"):
            raise ValidationError("El OCR local no obtuvo candidatos; la foto no se habilitó para aprendizaje.")
        append_attempt(reading, result, reading.schedule.node)
        reading.ocr_learning_verified = True
        reading.save(update_fields=["ocr_attempts", "ocr_learning_verified"])
        return reading
