from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def reading_value(value):
    if value in (None, ""):
        return "—"
    try:
        formatted = format(Decimal(str(value)), "f")
    except InvalidOperation:
        return "—"
    formatted = formatted.rstrip("0").rstrip(".") if "." in formatted else formatted
    return formatted.replace(".", ",")
