import re
from decimal import Decimal

from django import forms


class WebReadingForm(forms.Form):
    node = forms.IntegerField(min_value=1, max_value=9223372036854775807)
    obligation = forms.CharField(max_length=500)
    reading_date = forms.DateField(input_formats=["%Y-%m-%d"])
    value = forms.CharField(max_length=16, strip=False)
    photo = forms.ImageField(required=False)

    def clean_value(self):
        value = self.cleaned_data["value"]
        if not re.fullmatch(r"[0-9]{1,12}(?:[.,][0-9]{1,3})?", value):
            raise forms.ValidationError("Ingresa solo números: hasta 12 dígitos enteros y 3 decimales, sin signos ni letras.")
        return Decimal(value.replace(",", "."))

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and (photo.size > 10 * 1024 * 1024 or photo.image.format not in {"JPEG", "PNG", "WEBP"}):
            raise forms.ValidationError("Adjunta una imagen JPG, PNG o WebP de hasta 10 MB.")
        return photo
