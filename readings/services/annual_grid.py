"""Presentación por ciclo sin modificar fechas ni reclasificar históricos ambiguos."""
from collections import defaultdict
from datetime import timedelta

from readings.models import ReadingSchedule
from readings.services.notifications import monthly_due_date, shift_month


def annual_row(node, readings, schedules, year, today):
    monthly = [r for r in readings if r.schedule.notes.casefold().startswith("lectura mensual")]
    parents = defaultdict(list)
    for reading in monthly:
        if reading.reading_date:
            parents[reading.reading_date + timedelta(days=10)].append(reading)
    months = [[] for _ in range(12)]
    previous = []
    undated = []
    linked = set()

    def place(entry, cycle):
        if cycle is None:
            undated.append(entry)
        elif cycle.year == year:
            months[cycle.month - 1].append(entry)
        elif cycle.year < year and entry.get("reading"):
            previous.append(entry["reading"])

    for reading in readings:
        notes = reading.schedule.notes.casefold()
        if notes.startswith("lectura mensual"):
            cycle, label = reading.schedule.due_date, "Mensual"
        elif notes.startswith("seguimiento") and len(parents[reading.schedule.due_date]) == 1:
            parent = parents[reading.schedule.due_date][0]
            cycle, label = parent.schedule.due_date, "Seguimiento"
            linked.add(parent.pk)
        else:
            # Importaciones y seguimientos sin padre inequívoco conservan su mes real.
            cycle, label = reading.reading_date, "Histórica · ciclo sin identificar"
        place({"reading": reading, "kind": label, "cycle": cycle}, cycle)

    schedule_by_date = {s.due_date: s for s in schedules}
    for reading in monthly:
        if reading.pk in linked or not reading.reading_date:
            continue
        cycle = reading.schedule.due_date
        if cycle.year != year or reading.reading_date > today:
            continue
        due = reading.reading_date + timedelta(days=10)
        # Un origen ambiguo no permite proyectar otro seguimiento.
        if len(parents[due]) != 1:
            continue
        schedule = schedule_by_date.get(due)
        if schedule and not schedule.is_follow_up:
            continue
        cutoff = monthly_due_date(node, shift_month(cycle, 1)) - timedelta(days=2) if node.reading_day else None
        if schedule and schedule.status == ReadingSchedule.Status.CANCELLED:
            state = "Anulado"
        elif cutoff and today >= cutoff:
            state = "No registrado · ciclo cerrado"
        elif cutoff and due - timedelta(days=1) >= cutoff:
            state = "Sin ventana disponible antes del cierre"
        elif due < today:
            state = "Pendiente · atrasado"
        else:
            state = "Pendiente"
        place({"kind": "Seguimiento", "state": state, "due": due,
               "cutoff": cutoff - timedelta(days=1) if cutoff and due - timedelta(days=1) < cutoff and due >= cutoff else None,
               "reading": None}, cycle)
    for entries in months:
        entries.sort(key=lambda e: (
            e.get("cycle") or e.get("due"),
            {"Mensual": 0, "Seguimiento": 1}.get(e["kind"], 2),
            e["reading"].reading_date if e.get("reading") and e["reading"].reading_date else today,
        ))
    previous = [r for r in previous if r.reading_date]
    return {"node": node, "months": months, "undated": undated,
            "previous": max(previous, key=lambda r: (r.reading_date, r.pk), default=None)}
