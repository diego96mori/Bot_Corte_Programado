from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone

from readings.models import Node, Reading


@dataclass(frozen=True)
class ReadingNotification:
    node: Node
    due_date: date
    kind: str
    days_until: int
    cutoff: date | None = None

    @property
    def is_overdue(self):
        return self.days_until < 0

    @property
    def status_label(self):
        if self.kind == "FOLLOW_UP" and self.cutoff and self.due_date >= self.cutoff:
            return f"Disponible hasta el {self.cutoff - timedelta(days=1):%d/%m/%Y}"
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


def shift_month(value, offset):
    month_index = value.year * 12 + value.month - 1 + offset
    year, zero_based_month = divmod(month_index, 12)
    return date(year, zero_based_month + 1, 1)


def active_cycle_due(node, today):
    """Use the latest monthly window already open, even across month/year boundaries."""
    candidates = [monthly_due_date(node, shift_month(today, offset)) for offset in (-1, 0, 1)]
    return max(due for due in candidates if today >= due - timedelta(days=2))


def cycle_due_for_reading(node, reading_date):
    """Assign a monthly reading to the closest fixed reading day."""
    month = reading_date.replace(day=1)
    candidates = [
        monthly_due_date(node, shift_month(month, offset))
        for offset in (-1, 0, 1)
    ]
    return min(candidates, key=lambda due: (abs((reading_date - due).days), due))


def _reading_cycle_due(reading):
    if reading.schedule.notes.casefold().startswith("lectura mensual"):
        return reading.schedule.due_date
    return cycle_due_for_reading(reading.schedule.node, reading.reading_date)


def get_cycle_state(node, cycle_due, as_of=None):
    """Return the monthly reading and its single 10-day follow-up state."""
    next_due = monthly_due_date(node, shift_month(cycle_due, 1))
    cutoff = next_due - timedelta(days=2)
    candidates = (
        Reading.objects.select_related("schedule__node")
        .filter(
            schedule__node=node,
            status=Reading.Status.CONFIRMED,
            confirmed_value__isnull=False,
            reading_date__lt=cutoff,
        )
        .filter(
            # Preserve the cycle explicitly assigned to existing monthly records,
            # even when their actual capture date precedes the normal window.
            Q(schedule__due_date=cycle_due, schedule__notes__istartswith="Lectura mensual")
            | Q(reading_date__gte=cycle_due - timedelta(days=3))
        )
        .exclude(schedule__notes__istartswith="Seguimiento")
        .order_by("reading_date", "id")
    )
    if as_of is not None:
        candidates = candidates.filter(reading_date__lte=as_of)
    monthly_reading = next(
        (reading for reading in candidates if _reading_cycle_due(reading) == cycle_due),
        None,
    )
    follow_up_due = None
    follow_up_completed = False
    if monthly_reading:
        follow_up_due = monthly_reading.reading_date + timedelta(days=10)
        follow_up_readings = Reading.objects.filter(
            schedule__node=node,
            schedule__due_date=follow_up_due,
            schedule__notes__istartswith="Seguimiento",
            status=Reading.Status.CONFIRMED,
            confirmed_value__isnull=False,
        )
        if as_of is not None:
            follow_up_readings = follow_up_readings.filter(reading_date__lte=as_of)
        follow_up_completed = follow_up_readings.exists()
    return {
        "cycle_due": cycle_due,
        "next_due": next_due,
        "cutoff": cutoff,
        "monthly_reading": monthly_reading,
        "follow_up_due": follow_up_due,
        "follow_up_completed": follow_up_completed,
    }


def get_follow_up_cutoff(node, follow_up_due):
    """Return when an unfinished follow-up yields priority to the next monthly reading."""
    source_date = follow_up_due - timedelta(days=10)
    source_reading = (
        Reading.objects.select_related("schedule__node")
        .filter(
            schedule__node=node,
            status=Reading.Status.CONFIRMED,
            confirmed_value__isnull=False,
            reading_date=source_date,
        )
        .exclude(schedule__notes__istartswith="Seguimiento")
        .order_by("id")
        .first()
    )
    if not source_reading:
        return None
    cycle_due = _reading_cycle_due(source_reading)
    next_due = monthly_due_date(node, shift_month(cycle_due, 1))
    return next_due - timedelta(days=2)


def get_node_obligation(node, today=None):
    today = today or timezone.localdate()
    cycle_due = active_cycle_due(node, today)
    state = get_cycle_state(node, cycle_due, as_of=today)
    if not state["monthly_reading"]:
        return cycle_due, "MONTHLY"
    if state["follow_up_due"] and not state["follow_up_completed"]:
        return state["follow_up_due"], "FOLLOW_UP"
    return state["next_due"], "MONTHLY"


def get_reading_notifications(today=None):
    today = today or timezone.localdate()
    nodes = list(Node.objects.filter(active=True, reading_day__isnull=False).order_by("location", "name"))
    notifications = []
    for node in nodes:
        due_date, kind = get_node_obligation(node, today)
        days_until = (due_date - today).days
        lead_days = 2 if kind == "MONTHLY" else 1
        cutoff = None
        shortened_follow_up = False
        if kind == "FOLLOW_UP":
            cycle_due = active_cycle_due(node, today)
            cutoff = get_cycle_state(node, cycle_due, as_of=today)["cutoff"]
            # A late monthly reading can put its normal 10-day follow-up due
            # beyond the next monthly window. In that case there is no useful
            # "one day before due" reminder: notify throughout the remaining
            # registration window and stop when the new cycle opens.
            shortened_follow_up = due_date >= cutoff
        if days_until <= lead_days or shortened_follow_up:
            notifications.append(
                ReadingNotification(
                    node=node, due_date=due_date, kind=kind,
                    days_until=days_until, cutoff=cutoff,
                )
            )
    return sorted(notifications, key=lambda item: (not item.is_overdue, item.due_date, item.node.name))
