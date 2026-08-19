from django.conf import settings
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Node(models.Model):
    code = models.CharField("código", max_length=40, unique=True)
    name = models.CharField("nombre", max_length=160)
    location = models.CharField("ubicación", max_length=240, blank=True)
    meter_number = models.CharField("número de medidor", max_length=80, blank=True)
    supply_number = models.CharField("número de suministro", max_length=40, blank=True, db_index=True)
    provider = models.CharField("concesionaria", max_length=80, blank=True)
    reading_day = models.PositiveSmallIntegerField(
        "día de lectura", null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(31)]
    )
    billing_day = models.PositiveSmallIntegerField(
        "día de emisión", null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(31)]
    )
    due_day = models.PositiveSmallIntegerField(
        "día de vencimiento", null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(31)]
    )
    telegram_chat_id = models.BigIntegerField("chat de Telegram", null=True, blank=True)
    active = models.BooleanField("activo", default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "nodo"
        verbose_name_plural = "nodos"

    def __str__(self):
        return f"{self.code} - {self.name}"


class ReadingSchedule(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        COMPLETED = "COMPLETED", "Completada"
        CANCELLED = "CANCELLED", "Anulada"

    node = models.ForeignKey(Node, on_delete=models.PROTECT, related_name="schedules", verbose_name="nodo")
    due_date = models.DateField("fecha programada")
    status = models.CharField("estado", max_length=12, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField("observaciones", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "node__code"]
        constraints = [models.UniqueConstraint(fields=["node", "due_date"], name="unique_node_due_date")]
        verbose_name = "programación"
        verbose_name_plural = "programaciones"

    def __str__(self):
        return f"{self.node.code} / {self.due_date}"

    @property
    def is_follow_up(self):
        return self.notes.casefold().startswith("seguimiento")

    @property
    def management_status_label(self):
        return self.management_status_label_for(timezone.localdate())

    def management_status_label_for(self, today):
        if self.status == self.Status.PENDING:
            days = (self.due_date - today).days
            event = "seguimiento" if self.is_follow_up else "lectura"
            article = "el" if self.is_follow_up else "la"
            if days > 1:
                return f"Pendiente: faltan {days} días para {article} {event}"
            if days == 1:
                return f"Pendiente: falta 1 día para {article} {event}"
            if days == 0:
                return f"{event.capitalize()} para hoy"
            overdue = -days
            suffix = "día" if overdue == 1 else "días"
            overdue_word = "atrasado" if self.is_follow_up else "atrasada"
            return f"{event.capitalize()} {overdue_word} {overdue} {suffix}"
        return self.get_status_display()

    @property
    def management_status_class(self):
        if self.status == self.Status.PENDING:
            return "PENDING_FOLLOW_UP" if self.is_follow_up else "PENDING_READING"
        return self.status


class Reading(models.Model):
    class Status(models.TextChoices):
        REVIEW = "REVIEW", "Por confirmar"
        CONFIRMED = "CONFIRMED", "Confirmada"
        CANCELLED = "CANCELLED", "Anulada"

    class Source(models.TextChoices):
        TELEGRAM = "TELEGRAM", "Telegram"
        EXCEL = "EXCEL", "Excel"
        MANUAL = "MANUAL", "Manual"

    schedule = models.ForeignKey(ReadingSchedule, on_delete=models.PROTECT, related_name="readings")
    detected_value = models.DecimalField(
        "valor detectado", max_digits=15, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))]
    )
    confirmed_value = models.DecimalField(
        "valor confirmado", max_digits=15, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))]
    )
    ocr_text = models.TextField("texto OCR", blank=True)
    ocr_confidence = models.FloatField("confianza OCR", null=True, blank=True)
    photo = models.ImageField("fotografía", upload_to="meter_photos/%Y/%m/", blank=True)
    reading_date = models.DateField("fecha de lectura", null=True, blank=True, db_index=True)
    source = models.CharField("origen", max_length=12, choices=Source.choices, default=Source.TELEGRAM)
    status = models.CharField("estado", max_length=12, choices=Status.choices, default=Status.REVIEW)
    telegram_chat_id = models.BigIntegerField(null=True, blank=True)
    telegram_user_id = models.BigIntegerField(null=True, blank=True)
    telegram_username = models.CharField(max_length=160, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="confirmed_readings"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "lectura"
        verbose_name_plural = "lecturas"

    def __str__(self):
        return f"{self.schedule.node.code} - {self.confirmed_value or self.detected_value or 'sin detectar'}"


class ReminderLog(models.Model):
    schedule = models.ForeignKey(ReadingSchedule, on_delete=models.CASCADE, related_name="reminder_logs")
    sent_on = models.DateField("fecha de envío")
    chat_id = models.BigIntegerField()
    telegram_message_id = models.BigIntegerField(null=True, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["schedule", "chat_id", "sent_at"], name="reminder_cooldown_idx")]
        verbose_name = "recordatorio enviado"
        verbose_name_plural = "recordatorios enviados"
