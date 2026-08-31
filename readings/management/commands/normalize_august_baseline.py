import json
import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from readings.services.august_baseline import apply_baseline, baseline_plan


class Command(BaseCommand):
    help = "Revisa la base de agosto 2026: primera lectura mensual, segunda seguimiento."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Aplica con respaldo; detener primero el bot.")

    def handle(self, *args, **options):
        try:
            plan = baseline_plan()
            if not options["apply"]:
                self.stdout.write(json.dumps(plan, ensure_ascii=False, indent=2))
                self.stdout.write(f"Solo revisión: {len(plan)} lecturas, {len({item['node_id'] for item in plan})} nodos.")
                return
            db = settings.DATABASES["default"]
            if db["ENGINE"] != "django.db.backends.sqlite3" or not Path(db["NAME"]).is_file():
                raise CommandError("Este ajuste requiere la base SQLite local y un respaldo verificable.")
            folder = settings.BASE_DIR / "backups"
            folder.mkdir(exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup = folder / f"db_before_august_baseline_{stamp}.sqlite3"
            with sqlite3.connect(Path(db["NAME"]).resolve().as_uri() + "?mode=ro", uri=True) as source:
                with sqlite3.connect(backup) as destination:
                    source.backup(destination)
                    if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise CommandError("El respaldo no pasó la verificación. No se aplicó el ajuste.")
            report = backup.with_suffix(".json")
            report.write_text(json.dumps({"backup": str(backup), "plan": plan}, ensure_ascii=False, indent=2), encoding="utf-8")
            result = apply_baseline(plan)
            report.write_text(json.dumps({"backup": str(backup), **result}, ensure_ascii=False, indent=2), encoding="utf-8")
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error
        self.stdout.write(self.style.SUCCESS(f"Base de agosto aplicada: {len(plan)} lecturas. Respaldo: {backup}. Detalle: {report}"))
