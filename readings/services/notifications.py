from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone

from readings.models import Node, Reading


@dataclass(frozen=True)
class ReadingNotification:
    node: Node
    due_date: date
    kind: str
    days_until: int

    @property
    def is_overdue(self):
        return self.days_until < 0

    @property
    def status_label(self):
        if self.days_until < 0:
            return f"Atrasada {-self.days_until} día(s)"
        if self.days_until == 0:
            return "Vence hoy"
        return f"Vence en {self.days_until} día(s)"

    @property
    def kind_label(self):
        return "Lectura mensual" if self.kind == "MONTHLY" else "Seguimiento de 10 días"


def monthly_due_date(node, today):
    last_day = monthrange(today.year, today.month)[1]
    return date(today.year, today.month, min(node.reading_day, last_day))


def get_node_obligation(node, today=None):
    today = today or timezone.localdate()
    month_start = today.replace(day=1)
    latest = (
        Reading.objects.filter(
            schedule__node=node,
            status=Reading.Status.CONFIRMED,
            confirmed_value__isnull=False,
            reading_date__gte=month_start,
            reading_date__lte=today,
        )
        .order_by("-reading_date", "-id")
        .first()
    )
    if latest:
        return latest.reading_date + timedelta(days=10), "FOLLOW_UP"
    return monthly_due_date(node, today), "MONTHLY"


def get_reading_notifications(today=None):
    today = today or timezone.localdate()
    month_start = today.replace(day=1)
    nodes = list(Node.objects.filter(active=True, reading_day__isnull=False).order_by("location", "name"))
    readings = (
        Reading.objects.select_related("schedule")
        .filter(
            schedule__node__in=nodes,
            status=Reading.Status.CONFIRMED,
            confirmed_value__isnull=False,
            reading_date__gte=month_start,
            reading_date__lte=today,
        )
        .order_by("reading_date", "id")
    )
    latest_by_node = {}
    for reading in readings:
        latest_by_node[reading.schedule.node_id] = reading

    notifications = []
    for node in nodes:
        latest = latest_by_node.get(node.id)
        if latest:
            due_date = latest.reading_date + timedelta(days=10)
            lead_days = 1
            kind = "FOLLOW_UP"
        else:
            due_date = monthly_due_date(node, today)
            lead_days = 3
            kind = "MONTHLY"
        days_until = (due_date - today).days
        if days_until <= lead_days:
            notifications.append(
                ReadingNotification(node=node, due_date=due_date, kind=kind, days_until=days_until)
            )
    return sorted(notifications, key=lambda item: (not item.is_overdue, item.due_date, item.node.name))
