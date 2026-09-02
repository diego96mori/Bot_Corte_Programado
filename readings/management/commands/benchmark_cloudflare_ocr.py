import cv2

from django.core.management.base import BaseCommand

from readings.models import Reading
from readings.services.ocr import read_meter_cloudflare


class Command(BaseCommand):
    help = "Compara un modelo Cloudflare Vision con las lecturas confirmadas que tienen foto."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        readings = (
            Reading.objects.filter(status=Reading.Status.CONFIRMED)
            .exclude(photo="")
            .select_related("schedule__node")
            .order_by("id")
        )
        if options["limit"] > 0:
            readings = readings[: options["limit"]]

        exact = 0
        returned = 0
        total = 0
        for reading in readings:
            total += 1
            image = cv2.imread(reading.photo.path)
            result = read_meter_cloudflare(image)
            if result.value is not None:
                returned += 1
            if result.value == reading.confirmed_value:
                exact += 1
            self.stdout.write(
                "RESULT|{}|{}|{}|{}|{}|{}".format(
                    reading.pk,
                    reading.schedule.node.code,
                    reading.confirmed_value,
                    result.value or "",
                    result.confidence if result.confidence is not None else "",
                    result.raw_text,
                )
            )
        self.stdout.write(f"SUMMARY|total={total}|returned={returned}|exact={exact}")
