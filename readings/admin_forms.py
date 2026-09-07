from django import forms
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from .forms import WebReadingForm
from .models import Node, Reading, ReadingSchedule


INTERFACES = {
    "management": ("Ver Gestión de lecturas", {"readings.access_management"}),
    "annual": ("Ver Lecturas WI-NET", {"readings.access_annual"}),
    "notifications": ("Ver calendario y campana de notificaciones", {"readings.access_notifications"}),
    "register": ("Registrar lecturas por la web", {"readings.add_reading"}),
    "administration": ("Administrar usuarios, grupos, nodos y lecturas", {
        "readings.access_admin",
        *{f"readings.{action}_{model}" for action in ("view", "add", "change", "delete") for model in ("node", "reading", "readingschedule", "reminderlog") if (action, model) != ("add", "reading")},
        *{f"auth.{action}_{model}" for action in ("view", "add", "change", "delete") for model in ("user", "group")},
    }),
}


class SimpleGroupForm(forms.ModelForm):
    management = forms.BooleanField(required=False)
    annual = forms.BooleanField(required=False)
    notifications = forms.BooleanField(required=False)
    register = forms.BooleanField(required=False)
    administration = forms.BooleanField(required=False)
    class Meta:
        model = Group
        fields = ("name",)
        labels = {"name": "Nombre del grupo"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        held = set()
        if self.instance.pk:
            held = {f"{p.content_type.app_label}.{p.codename}" for p in self.instance.permissions.select_related("content_type")}
        for key, (label, codes) in INTERFACES.items():
            self.fields[key] = forms.BooleanField(label=label, required=False, initial=codes <= held)

    def _save_m2m(self):
        desired = set().union(*(codes for key, (_, codes) in INTERFACES.items() if self.cleaned_data.get(key)))
        all_codes = set().union(*(codes for _, codes in INTERFACES.values()))
        available = list(Permission.objects.select_related("content_type"))
        managed = [p.pk for p in available if f"{p.content_type.app_label}.{p.codename}" in all_codes]
        self.instance.permissions.remove(*managed)
        self.instance.permissions.add(*(p for p in available if f"{p.content_type.app_label}.{p.codename}" in desired))


class NodeAdminForm(forms.ModelForm):
    reading_day = forms.IntegerField(label="Día mensual de lectura (1 a 31)", min_value=1, max_value=31)
    class Meta:
        model = Node
        fields = ("name", "location", "supply_number", "provider", "reading_day", "active")
        labels = {"reading_day": "Día mensual de lectura (1 a 31)"}

    def clean_supply_number(self):
        supply = self.cleaned_data["supply_number"].strip()
        if not supply or not supply.isascii() or not supply.isdigit() or len(supply) > 36:
            raise ValidationError("Ingresa un suministro de 1 a 36 dígitos, sin espacios ni letras.")
        if Node.objects.exclude(pk=self.instance.pk).filter(code=f"SUM-{supply}").exists():
            raise ValidationError("Ya existe un nodo con ese suministro.")
        return supply


class ReadingAdminForm(forms.ModelForm):
    confirmed_value = forms.CharField(label="Valor confirmado", max_length=16)
    photo = forms.ImageField(label="Fotografía", required=False)

    class Meta:
        model = Reading
        fields = ("confirmed_value", "photo")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.confirmed_value is not None:
            self.initial["confirmed_value"] = format(self.instance.confirmed_value, "f")

    def clean_confirmed_value(self):
        validator = WebReadingForm({"node": 1, "obligation": "placeholder", "reading_date": "2026-01-01", "value": self.cleaned_data["confirmed_value"]})
        validator.is_valid()
        if "value" in validator.errors:
            raise ValidationError(validator.errors["value"])
        return validator.cleaned_data["value"]

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and hasattr(photo, "image") and (photo.size > 10*1024*1024 or photo.image.format not in {"PNG", "JPEG", "WEBP"}):
            raise ValidationError("Usa JPG, PNG o WebP de hasta 10 MB.")
        return photo


class ScheduleAdminForm(forms.ModelForm):
    class Meta:
        model = ReadingSchedule
        fields = ("status",)

    def clean_status(self):
        status = self.cleaned_data["status"]
        confirmed = self.instance.readings.filter(status=Reading.Status.CONFIRMED, confirmed_value__isnull=False).exists()
        if confirmed and status != ReadingSchedule.Status.COMPLETED:
            raise ValidationError("Tiene una lectura confirmada. Elimínala desde Lecturas antes de cambiar este estado.")
        if not confirmed and status == ReadingSchedule.Status.COMPLETED:
            raise ValidationError("Para completarla registra la lectura por Telegram o la web.")
        return status
