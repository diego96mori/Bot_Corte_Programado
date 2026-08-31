"""Eligibility for new bot registrations, without changing historical records."""

from dataclasses import dataclass
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from readings.services.notifications import active_cycle_due, get_cycle_state


@dataclass(frozen=True)
class RegistrationPlan:
    cycle_due: date
    due_date: date
    kind: str
    cutoff: date
    monthly_date: date | None = None

    @property
    def explanation(self):
        if self.kind == "MONTHLY":
            return (
                f"📋 Corresponde una lectura mensual del ciclo {self.cycle_due:%m/%Y}.\n"
                f"Fecha programada: {self.due_date:%d/%m/%Y}.\n"
                f"La ventana de este ciclo comienza el {self.cycle_due - timedelta(days=2):%d/%m/%Y}. "
                "Los seguimientos pendientes del ciclo anterior ya están cerrados."
            )
        return (
            f"📋 Corresponde un seguimiento del ciclo {self.cycle_due:%m/%Y}.\n"
            f"La lectura mensual ya fue registrada el {self.monthly_date:%d/%m/%Y}.\n"
            f"Seguimiento programado: {self.due_date:%d/%m/%Y} (10 días después).\n"
            f"Puede registrarse como seguimiento hasta el {self.cutoff - timedelta(days=1):%d/%m/%Y}; "
            f"desde el {self.cutoff:%d/%m/%Y} corresponde al siguiente ciclo mensual."
        )


def get_registration_plan(node, reading_date=None):
    if node.reading_day is None or not 1 <= node.reading_day <= 31:
        raise ValidationError(
            "Este nodo no tiene configurado un día de lectura válido. "
            "Pide al administrador que configure un día entre 1 y 31."
        )
    reading_date = reading_date or timezone.localdate()
    cycle_due = active_cycle_due(node, reading_date)
    # Count all confirmations in the cycle. Backdating must not hide an existing
    # confirmation and reopen a completed monthly reading or follow-up.
    state = get_cycle_state(node, cycle_due)
    monthly = state["monthly_reading"]
    if monthly and state["follow_up_completed"]:
        raise ValidationError(
            f"🏢 Nodo: {node.name}\n\n"
            f"El ciclo {cycle_due:%m/%Y} ya tiene su lectura mensual y su seguimiento registrados. "
            "Todavía no puedes registrar otra lectura para ese ciclo.\n\n"
            f"Puedes registrar la próxima lectura desde el {state['cutoff']:%d/%m/%Y}, "
            f"para la fecha mensual del {state['next_due']:%d/%m/%Y}.",
            code="cycle_complete",
        )
    if monthly and reading_date < monthly.reading_date:
        raise ValidationError(
            f"Este ciclo ya tiene una lectura mensual del {monthly.reading_date:%d/%m/%Y}. "
            "El seguimiento no puede tener una fecha anterior a esa lectura. "
            "Corrige la fecha o cancela el registro.", code="before_monthly",
        )
    return RegistrationPlan(
        cycle_due=cycle_due, due_date=state["follow_up_due"] if monthly else cycle_due,
        kind="FOLLOW_UP" if monthly else "MONTHLY", cutoff=state["cutoff"],
        monthly_date=monthly.reading_date if monthly else None,
    )
