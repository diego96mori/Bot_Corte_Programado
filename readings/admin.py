from django.contrib import admin

from .models import Node, Reading, ReadingSchedule, ReminderLog


@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "location", "supply_number", "provider", "reading_day", "telegram_chat_id", "active")
    list_filter = ("active", "location", "provider")
    search_fields = ("code", "name", "meter_number", "supply_number")


@admin.register(ReadingSchedule)
class ReadingScheduleAdmin(admin.ModelAdmin):
    list_display = ("node", "due_date", "status")
    list_filter = ("status", "due_date")
    search_fields = ("node__code", "node__name")


@admin.register(Reading)
class ReadingAdmin(admin.ModelAdmin):
    list_display = ("schedule", "reading_date", "detected_value", "confirmed_value", "source", "status", "telegram_username", "created_at")
    list_filter = ("status", "source", "reading_date", "created_at")
    search_fields = ("schedule__node__code", "schedule__node__name", "telegram_username")
    readonly_fields = ("ocr_text", "ocr_confidence", "created_at", "confirmed_at")


@admin.register(ReminderLog)
class ReminderLogAdmin(admin.ModelAdmin):
    list_display = ("schedule", "sent_on", "chat_id", "sent_at")
    readonly_fields = ("sent_at",)
