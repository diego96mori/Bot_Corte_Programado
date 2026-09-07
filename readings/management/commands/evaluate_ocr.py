"""Evaluación local sin red y exportación reutilizable de ejemplos confirmados."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from readings.models import Reading
from readings.services.ocr import read_meter
from readings.services.ocr_learning import append_attempt, build_profile


class Command(BaseCommand):
    help = "Evalúa OCR local con fotos confirmadas; opcionalmente exporta un manifiesto JSONL. No llama a Cloudflare."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--export", help="Archivo JSONL de fotos y etiquetas, sin copiar las imágenes.")
        parser.add_argument("--learn", action="store_true", help="Registra candidatos de fotos históricas como ejemplos del medidor actual. Usar solo si sigue siendo el mismo equipo.")

    def handle(self, *args, **options):
        readings = Reading.objects.filter(status=Reading.Status.CONFIRMED, confirmed_value__isnull=False).exclude(photo="").select_related("schedule__node").order_by("confirmed_at", "pk")
        if options["limit"] > 0:
            readings = readings[:options["limit"]]
        counts = {"total": 0, "exact": 0, "wrong": 0, "rejected": 0, "missing": 0}
        exported = []
        for reading in readings:
            if not Path(reading.photo.path).is_file():
                counts["missing"] += 1
                continue
            profile = build_profile(reading.schedule.node, before=reading.confirmed_at) if reading.confirmed_at else {}
            result = read_meter(reading.photo.path, profile=profile, allow_cloudflare=False)
            counts["total"] += 1
            counts["rejected" if result.value is None else "exact" if result.value == reading.confirmed_value else "wrong"] += 1
            row = {"reading_id": reading.pk, "node_id": reading.schedule.node_id,
                   "image": reading.photo.name, "label": str(reading.confirmed_value),
                   "label_verified": reading.ocr_learning_verified,
                   "learning_excluded": reading.ocr_learning_excluded,
                   "predicted": str(result.value) if result.value is not None else None,
                   "attempt": result.details}
            exported.append(row)
            if options["learn"]:
                result.details["historical_replay"] = True
                append_attempt(reading, result, reading.schedule.node)
                reading.save(update_fields=["ocr_attempts"])
            self.stdout.write(json.dumps({k: v for k, v in row.items() if k != "attempt"}))
            self.stdout.flush()
        if options["export"]:
            with Path(options["export"]).open("x", encoding="utf-8") as output:
                for row in exported:
                    output.write(json.dumps(row) + "\n")
        self.stdout.write(json.dumps(counts))
