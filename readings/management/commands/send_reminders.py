from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from telegram import Bot

from readings.services.reminders import prepare_reminder_jobs, send_reminder_jobs

import asyncio


class Command(BaseCommand):
    help = "Envía recordatorios mensuales, seguimientos a 10 días y avisos atrasados"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Envía nuevamente los pendientes y reinicia su intervalo de cinco horas",
        )

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError("Configura TELEGRAM_BOT_TOKEN en el archivo .env")
        jobs = prepare_reminder_jobs(force=options["force"])
        results = asyncio.run(self.send_all(jobs))
        self.stdout.write(
            self.style.SUCCESS(f"Recordatorios enviados: {len(results)}")
        )

    async def send_all(self, jobs):
        bot = Bot(settings.TELEGRAM_BOT_TOKEN)
        async with bot:
            return await send_reminder_jobs(bot, jobs)
