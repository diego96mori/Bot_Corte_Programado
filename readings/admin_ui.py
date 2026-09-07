from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django import forms
from datetime import timedelta
from .admin_forms import SimpleGroupForm, NodeAdminForm, ReadingAdminForm, ScheduleAdminForm
from .models import Node, Reading, ReadingSchedule, ReminderLog
from .services.ocr_learning import verify_for_learning, review_token

admin.site.site_header = "Administración WI-NET"
admin.site.site_title = "WI-NET"
admin.site.index_title = "Configura los accesos y administra las lecturas"

def sync_staff(user):
    fresh = User.objects.get(pk=user.pk)
    User.objects.filter(pk=user.pk).update(is_staff=fresh.is_superuser or fresh.has_perm("readings.access_admin"))

class FriendlyAdmin(admin.ModelAdmin):
    actions = None
    list_per_page = 30
    save_on_top = True
    @admin.display(description="Editar")
    def edit_button(self, obj):
        return format_html('<a class="button" href="{}">Editar</a>', reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change", args=[obj.pk]))

@admin.register(Node)
class NodeAdmin(FriendlyAdmin):
    form = NodeAdminForm
    list_display = ("code", "name", "location", "supply_number", "provider", "reading_day", "active", "edit_button")
    list_display_links = None
    list_filter = ("active", "location", "provider")
    search_fields = ("code", "name", "supply_number")
    fields = ("code_explanation", "name", "location", "supply_number", "provider", "reading_day", "active")
    readonly_fields = ("code_explanation",)
    @admin.display(description="Código automático")
    def code_explanation(self, obj):
        return f"{obj.code if obj and obj.pk else 'Se genera al guardar'}. Formato: SUM- seguido del suministro."
    def has_delete_permission(self, request, obj=None):
        return False
    def save_model(self, request, obj, form, change):
        obj.code = f"SUM-{obj.supply_number}"
        if not change:
            obj.telegram_chat_id = 8463146362
        super().save_model(request, obj, form, change)

@admin.register(ReadingSchedule)
class ReadingScheduleAdmin(FriendlyAdmin):
    form = ScheduleAdminForm
    list_display = ("node", "due_date", "status", "edit_button")
    list_display_links = None
    list_filter = ("status", "due_date")
    search_fields = ("node__code", "node__name")
    fields = ("node", "due_date", "status")
    readonly_fields = ("node", "due_date")
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Reading)
class ReadingAdmin(FriendlyAdmin):
    form = ReadingAdminForm
    list_display = ("node_name", "scheduled_date", "reading_date", "confirmed_value", "source", "status", "edit_button", "delete_button", "learning_button")
    list_display_links = None
    list_select_related = ("schedule__node",)
    list_filter = ("status", "source", "ocr_learning_verified", "reading_date")
    search_fields = ("schedule__node__name", "schedule__node__supply_number")
    fields = ("node_name", "scheduled_date", "reading_date", "confirmed_value", "photo")
    readonly_fields = ("node_name", "scheduled_date", "reading_date")
    @admin.display(description="Nodo", ordering="schedule__node__name")
    def node_name(self, obj):
        return obj.schedule.node.name
    @admin.display(description="Fecha programada", ordering="schedule__due_date")
    def scheduled_date(self, obj):
        return obj.schedule.due_date
    @admin.display(description="Eliminar")
    def delete_button(self, obj):
        return format_html('<a class="button" href="{}">Eliminar</a>', reverse("admin:readings_reading_delete", args=[obj.pk]))
    @admin.display(description="Aprendizaje")
    def learning_button(self, obj):
        if obj.ocr_learning_excluded:
            return "Histórica excluida"
        if not obj.photo or obj.status != Reading.Status.CONFIRMED:
            return "—"
        return format_html('<a class="button" href="{}">Revisar foto</a>', reverse("admin:reading_verify", args=[obj.pk]))
    def has_add_permission(self, request):
        return False
    def save_model(self, request, obj, form, change):
        if {"confirmed_value", "photo"} & set(form.changed_data):
            obj.ocr_learning_verified = False
            if "photo" in form.changed_data:
                obj.ocr_attempts = []
        super().save_model(request, obj, form, change)
    @transaction.atomic
    def delete_model(self, request, obj):
        schedule = ReadingSchedule.objects.select_for_update().get(pk=obj.schedule_id)
        follow_due = obj.reading_date + timedelta(days=10) if obj.reading_date and not schedule.is_follow_up else None
        super().delete_model(request, obj)
        if schedule.status != ReadingSchedule.Status.CANCELLED:
            complete = schedule.readings.filter(status=Reading.Status.CONFIRMED, confirmed_value__isnull=False).exists()
            schedule.status = ReadingSchedule.Status.COMPLETED if complete else ReadingSchedule.Status.PENDING
            schedule.save(update_fields=["status"])
        if follow_due and not Reading.objects.filter(schedule__node=schedule.node, reading_date=follow_due-timedelta(days=10), status=Reading.Status.CONFIRMED).exclude(schedule__notes__istartswith="Seguimiento").exists():
            for follow in ReadingSchedule.objects.filter(node=schedule.node, due_date=follow_due, notes__istartswith="Seguimiento", status=ReadingSchedule.Status.PENDING):
                if not follow.readings.filter(status=Reading.Status.CONFIRMED).exists():
                    follow.status = ReadingSchedule.Status.CANCELLED
                    follow.notes += " | Mensual eliminada; seguimiento no exigible"
                    follow.save(update_fields=["status", "notes"])
    def get_urls(self):
        return [path("<int:pk>/verificar/", self.admin_site.admin_view(self.verify_view), name="reading_verify")] + super().get_urls()
    def verify_view(self, request, pk):
        reading = get_object_or_404(Reading, pk=pk)
        if not self.has_change_permission(request, reading):
            raise PermissionDenied
        if request.method == "POST":
            try:
                verify_for_learning(pk, expected_token=request.POST.get("review_token", ""))
                self.message_user(request, "Foto preparada para aprendizaje local.")
            except (ValidationError, OSError) as error:
                self.message_user(request, " ".join(error.messages) if isinstance(error, ValidationError) else "No se pudo abrir la foto.", messages.WARNING)
            return redirect("admin:readings_reading_changelist")
        try:
            token = review_token(reading)
        except OSError:
            self.message_user(request, "No se pudo abrir la fotografía.", messages.WARNING)
            return redirect("admin:readings_reading_changelist")
        return TemplateResponse(request, "admin/readings/verify_photo.html", {**self.admin_site.each_context(request), "reading": reading, "review_token": token, "title": "Revisar fotografía y decimales", "opts": self.model._meta})

@admin.register(ReminderLog)
class ReminderLogAdmin(FriendlyAdmin):
    list_display = ("schedule", "sent_on", "chat_id", "sent_at")
    list_display_links = None
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

admin.site.unregister(Group)
@admin.register(Group)
class SimpleGroupAdmin(FriendlyAdmin):
    form = SimpleGroupForm
    list_display = ("name", "members", "edit_button")
    list_display_links = None
    fields = ("name", "management", "annual", "notifications", "register", "administration")
    @admin.display(description="Usuarios del grupo")
    def members(self, obj):
        return ", ".join(obj.user_set.values_list("username", flat=True)) or "Sin usuarios"
    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        for user in form.instance.user_set.all():
            sync_staff(user)

admin.site.unregister(User)
@admin.register(User)
class SimpleUserAdmin(UserAdmin):
    actions = None
    list_display = ("username", "first_name", "is_active", "group_names")
    fieldsets = (("Cuenta", {"fields": ("username", "password")}), ("Datos del usuario", {"fields": ("first_name", "last_name", "email")}), ("Acceso", {"fields": ("is_active", "groups")}))
    add_fieldsets = (("Nuevo usuario", {"fields": ("username", "password1", "password2", "is_active", "groups")}),)
    filter_horizontal = ()
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "groups":
            kwargs["widget"] = forms.CheckboxSelectMultiple
            kwargs["help_text"] = "Marca los grupos de este usuario. Los permisos de los grupos se suman."
        return super().formfield_for_manytomany(db_field, request, **kwargs)
    @admin.display(description="Grupos")
    def group_names(self, obj):
        return ", ".join(obj.groups.values_list("name", flat=True))
    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        sync_staff(form.instance)
