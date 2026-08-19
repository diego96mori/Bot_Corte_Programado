from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import render

from .authorized_nodes import AUTHORIZED_NODES
from .models import Node, Reading, ReadingSchedule


@login_required
def reading_grid(request):
    status = request.GET.get("status", "")
    node_id = request.GET.get("node", "")
    provider = request.GET.get("provider", "")
    schedules = ReadingSchedule.objects.select_related("node").prefetch_related(
        Prefetch("readings", queryset=Reading.objects.order_by("-created_at"), to_attr="latest_readings")
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
def annual_grid(request):
    year = 2026
    names = [item["name"] for item in AUTHORIZED_NODES]
    nodes_by_name = {node.name: node for node in Node.objects.filter(name__in=names)}
    readings = (
        Reading.objects.select_related("schedule__node")
        .filter(
            schedule__node__name__in=names,
            reading_date__year__in=[year - 1, year],
            status=Reading.Status.CONFIRMED,
            confirmed_value__isnull=False,
        )
        .order_by("reading_date", "id")
    )
    by_node = {}
    for reading in readings:
        by_node.setdefault(reading.schedule.node_id, []).append(reading)

    rows = []
    for authorized in AUTHORIZED_NODES:
        node = nodes_by_name.get(authorized["name"])
        if not node:
            continue
        node_readings = by_node.get(node.id, [])
        previous = [reading for reading in node_readings if reading.reading_date.year == year - 1]
        months = []
        for month in range(1, 13):
            months.append([
                reading for reading in node_readings
                if reading.reading_date.year == year and reading.reading_date.month == month
            ])
        rows.append({"node": node, "previous": previous[-1] if previous else None, "months": months})

    return render(
        request,
        "readings/annual_grid.html",
        {
            "rows": rows, "year": year,
            "months": ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"],
            "active_page": "annual",
        },
    )
