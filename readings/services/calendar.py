from calendar import monthrange
from datetime import date, timedelta

from django.utils import timezone

from readings.models import Node, Reading, ReadingSchedule
from readings.services.notifications import get_cycle_state, monthly_due_date, shift_month


def _task_state(due_date, today, kind):
    days_until = (due_date - today).days
    if days_until <= 0:
        return "danger"
    lead_days = 2 if kind == "MONTHLY" else 1
    if days_until <= lead_days:
        return "warning"
    return "planned"


def _task_status(kind, due_date, today):
    days_until = (due_date - today).days
    label = "Lectura" if kind == "MONTHLY" else "Seguimiento"
    if days_until < 0:
        days = -days_until
        overdue = "atrasada" if kind == "MONTHLY" else "atrasado"
        return f"{label} {overdue} {days} {'día' if days == 1 else 'días'}"
    if days_until == 0:
        return f"{label} para hoy"
    if days_until <= 2:
        return f"Faltan {days_until} {'día' if days_until == 1 else 'días'}"
    return f"{label} programada"


def get_calendar_events(year, month, today=None):
    """Return readings and the current obligation for every active node in a month."""
    today = today or timezone.localdate()
    month_start = date(year, month, 1)
    month_end = date(year, month, monthrange(year, month)[1])
    nodes = list(Node.objects.filter(active=True, reading_day__isnull=False).order_by("name"))
    readings = list(
        Reading.objects.select_related("schedule__node")
        .filter(
            schedule__node__in=nodes,
            status=Reading.Status.CONFIRMED,
            confirmed_value__isnull=False,
            reading_date__gte=month_start,
            reading_date__lte=month_end,
        )
        .order_by("reading_date", "schedule__node__name", "id")
    )

    events = []
    cancelled = list(ReadingSchedule.objects.filter(node__in=nodes, status=ReadingSchedule.Status.CANCELLED, due_date__range=(month_start, month_end)).select_related("node"))
    cancelled_keys = {(s.node_id, s.due_date) for s in cancelled}
    for reading in readings:
        value = reading.confirmed_value if reading.confirmed_value is not None else reading.detected_value
        is_follow_up = reading.schedule.is_follow_up
        events.append(
            {
                "date": reading.reading_date.isoformat(),
                "node_id": reading.schedule.node_id,
                "node_name": reading.schedule.node.name,
                "type": "record",
                "kind_label": "Seguimiento registrado" if is_follow_up else "Lectura registrada",
                "status_label": "Completada",
                "state": "completed",
                "value": format(value.normalize(), "f") if value is not None else None,
            }
        )

    for node in nodes:
        cycle_due = monthly_due_date(node, month_start)
        current_cycle = get_cycle_state(node, cycle_due)
        if not current_cycle["monthly_reading"] and (node.pk, cycle_due) not in cancelled_keys:
            is_closed = today >= current_cycle["cutoff"]
            events.append(
                {
                    "date": cycle_due.isoformat(),
                    "node_id": node.id,
                    "node_name": node.name,
                    "type": "task",
                    "kind_label": "Lectura mensual",
                    "status_label": (
                        "Lectura no registrada · ciclo cerrado por nueva lectura mensual"
                        if is_closed else _task_status("MONTHLY", cycle_due, today)
                    ),
                    "state": "closed" if is_closed else _task_state(cycle_due, today, "MONTHLY"),
                    "value": None,
                }
            )

        previous_cycle_due = monthly_due_date(node, shift_month(month_start, -1))
        for state in (get_cycle_state(node, previous_cycle_due), current_cycle):
            due_date = state["follow_up_due"]
            if (
                not due_date
                or state["follow_up_completed"]
                or not month_start <= due_date <= month_end
                or (node.pk, due_date) in cancelled_keys
            ):
                continue
            no_window = due_date - timedelta(days=1) >= state["cutoff"]
            is_closed = today >= state["cutoff"] or no_window
            events.append(
                {
                    "date": due_date.isoformat(),
                    "node_id": node.id,
                    "node_name": node.name,
                    "type": "task",
                    "kind_label": "Seguimiento de 10 días",
                    "status_label": (
                        ("Seguimiento sin ventana disponible antes del cierre" if no_window and today < state["cutoff"] else "Seguimiento no registrado · ciclo cerrado por nueva lectura mensual")
                        if is_closed else _task_status("FOLLOW_UP", due_date, today)
                    ),
                    "state": "closed" if is_closed else _task_state(due_date, today, "FOLLOW_UP"),
                    "value": None,
                }
            )

    for schedule in cancelled:
        events.append({"date": schedule.due_date.isoformat(), "node_id": schedule.node_id,
            "node_name": schedule.node.name, "type": "task",
            "kind_label": "Seguimiento de 10 días" if schedule.is_follow_up else "Lectura mensual",
            "status_label": "Seguimiento no exigible · mensual eliminada" if "Mensual eliminada" in schedule.notes else "Programación anulada · no exigible",
            "state": "closed", "value": None})
    state_order = {"danger": 0, "warning": 1, "planned": 2, "closed": 3, "completed": 4}
    return sorted(events, key=lambda event: (event["date"], state_order[event["state"]], event["node_name"]))
