from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_http_methods
from django.db.models import Prefetch, Case, When, IntegerField, Value
from django.http import JsonResponse, FileResponse, Http404
from django.shortcuts import render, redirect
from .access import interface_required
from django.utils import timezone

from .models import Node, Reading, ReadingSchedule
from .forms import WebReadingForm
from .services.web_registration import pending_option, register_reading
from .services.calendar import get_calendar_events
from .services.annual_grid import annual_row
from .services.notifications import get_follow_up_cutoff, get_reading_notifications, monthly_due_date, shift_month


@login_required
@require_http_methods(["GET", "HEAD"])
def protected_photo(request, path):
    reading = Reading.objects.filter(photo=path).first()
    if not reading:
        raise Http404
    try:
        photo = reading.photo.open("rb")
    except (OSError, ValueError):
        raise Http404
    response = FileResponse(photo)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_http_methods(["GET", "POST"])
def web_reading(request):
    if not request.user.has_perm("readings.add_reading"):
        return JsonResponse({"error": "Tu usuario tiene acceso de consulta; no puede registrar lecturas."}, status=403)
    if request.method == "POST":
        form = WebReadingForm(request.POST, request.FILES)
        if not form.is_valid():
            return JsonResponse({"errors": form.errors}, status=400)
        try:
            reading = register_reading(request.user, form.cleaned_data)
        except ValidationError as error:
            return JsonResponse({"errors": {"pending": error.messages}}, status=409)
        return JsonResponse({"id": reading.pk, "message": "Lectura registrada correctamente."}, status=201)
    today = timezone.localdate()
    nodes = Node.objects.filter(active=True).order_by("name")
    if "node" not in request.GET:
        return JsonResponse({"nodes": list(nodes.values("id", "name")), "today": today.isoformat()})
    node_id = request.GET.get("node", "")
    valid_id = node_id.isascii() and node_id.isdigit() and len(node_id) <= 19 and int(node_id) <= 9223372036854775807
    node = nodes.filter(pk=int(node_id)).first() if valid_id else None
    if not node:
        return JsonResponse({"error": "Elige un nodo disponible."}, status=400)
    try:
        option = pending_option(node, today)
    except ValidationError as error:
        return JsonResponse({"options": [], "message": " ".join(error.messages)})
    return JsonResponse({"options": [option]})


@login_required
def reading_grid(request):
    if not request.user.has_perm("readings.access_management"):
        if request.user.has_perm("readings.access_annual"):
            return redirect("readings:annual_grid")
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Tu grupo no tiene acceso a esta pantalla.")
    status = request.GET.get("status", "")
    node_id = request.GET.get("node", "")
    provider = request.GET.get("provider", "")
    schedules = ReadingSchedule.objects.select_related("node").prefetch_related(
        Prefetch("readings", queryset=Reading.objects.select_related("confirmed_by").annotate(
            display_priority=Case(When(status=Reading.Status.CONFIRMED, then=Value(0)), default=Value(1), output_field=IntegerField())
        ).order_by("display_priority", "-created_at", "-pk"), to_attr="latest_readings")
    ).filter(node__active=True).order_by("-due_date", "node__name")
    if status == "PENDING_READING":
        schedules = schedules.filter(status=ReadingSchedule.Status.PENDING).exclude(
            notes__istartswith="Seguimiento"
        )
    elif status == "PENDING_FOLLOW_UP":
        schedules = schedules.filter(
            status=ReadingSchedule.Status.PENDING, notes__istartswith="Seguimiento"
        )
    elif status:
        schedules = schedules.filter(status=status)
    if node_id.isdigit():
        schedules = schedules.filter(node_id=int(node_id))
    if provider:
        schedules = schedules.filter(node__provider=provider)
    today = timezone.localdate()
    schedules = list(schedules)
    # Upcoming obligations must be visible even if the Telegram worker is stopped
    # or the node has no chat. These are projected schedules, never fake readings.
    existing = set(ReadingSchedule.objects.filter(node__active=True).values_list("node_id", "due_date"))
    for item in get_reading_notifications(today):
        if (item.node.pk, item.due_date) in existing:
            continue
        upcoming = ReadingSchedule(node=item.node, due_date=item.due_date, notes=item.kind_label)
        if status and status not in {ReadingSchedule.Status.PENDING, upcoming.management_status_class}:
            continue
        if node_id.isdigit() and item.node.pk != int(node_id):
            continue
        if provider and item.node.provider != provider:
            continue
        upcoming.latest_readings = []
        schedules.append(upcoming)
    schedules.sort(key=lambda schedule: (-schedule.due_date.toordinal(), schedule.node.name))
    for schedule in schedules:
        schedule.grid_status_label = schedule.management_status_label_for(today)
        schedule.grid_status_class = schedule.management_status_class
        if schedule.status == ReadingSchedule.Status.PENDING and schedule.is_follow_up:
            cutoff = get_follow_up_cutoff(schedule.node, schedule.due_date)
            if cutoff and today >= cutoff:
                schedule.grid_status_label = "Seguimiento no registrado · ciclo cerrado por nueva lectura mensual"
                schedule.grid_status_class = "CLOSED"
            elif cutoff and schedule.due_date - timedelta(days=1) >= cutoff:
                schedule.grid_status_label = "Seguimiento sin ventana disponible antes del cierre"
                schedule.grid_status_class = "CLOSED"
        elif schedule.status == ReadingSchedule.Status.PENDING and schedule.node.reading_day:
            next_due = monthly_due_date(schedule.node, shift_month(schedule.due_date, 1))
            if today >= next_due - timedelta(days=2):
                schedule.grid_status_label = "Lectura no registrada · ciclo cerrado por nueva lectura mensual"
                schedule.grid_status_class = "CLOSED"
    nodes = Node.objects.filter(active=True).order_by("name")
    providers = (
        Node.objects.filter(active=True).exclude(provider="")
        .values_list("provider", flat=True).distinct().order_by("provider")
    )
    return render(
        request,
        "readings/grid.html",
        {
            "schedules": schedules, "selected_status": status, "selected_node": node_id,
            "selected_provider": provider, "nodes": nodes, "providers": providers,
            "statuses": [
                ("PENDING_READING", "Pendiente de lectura"),
                ("PENDING_FOLLOW_UP", "Pendiente de seguimiento"),
                (ReadingSchedule.Status.COMPLETED, "Completada"),
                (ReadingSchedule.Status.CANCELLED, "Anulada"),
            ],
            "active_page": "records",
        },
    )


@login_required
@interface_required("access_annual")
def annual_grid(request):
    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
        if not 2020 <= year <= 2100:
            raise ValueError
    except (TypeError, ValueError):
        return JsonResponse({"error": "Año no válido."}, status=400)
    nodes = list(Node.objects.filter(active=True).order_by("location", "name", "pk"))
    readings = (
        Reading.objects.select_related("schedule__node")
        .filter(
            schedule__node__in=nodes,
            status=Reading.Status.CONFIRMED,
            confirmed_value__isnull=False,
        )
        .order_by("reading_date", "id")
    )
    by_node = {}
    for reading in readings:
        by_node.setdefault(reading.schedule.node_id, []).append(reading)

    schedules_by_node = {}
    for schedule in ReadingSchedule.objects.filter(node__in=nodes):
        schedules_by_node.setdefault(schedule.node_id, []).append(schedule)
    rows = []
    for node in nodes:
        node_readings = by_node.get(node.id, [])
        rows.append(annual_row(node, node_readings, schedules_by_node.get(node.pk, []), year, today))

    return render(
        request,
        "readings/annual_grid.html",
        {
            "rows": rows, "year": year,
            "months": ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"],
            "active_page": "annual",
        },
    )


@login_required
@interface_required("access_notifications")
def calendar_events(request):
    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        if not 2020 <= year <= 2100 or not 1 <= month <= 12:
            raise ValueError
    except (TypeError, ValueError):
        return JsonResponse({"error": "Mes o año no válido."}, status=400)
    return JsonResponse(
        {
            "year": year,
            "month": month,
            "today": today.isoformat(),
            "events": get_calendar_events(year, month, today),
        }
    )
